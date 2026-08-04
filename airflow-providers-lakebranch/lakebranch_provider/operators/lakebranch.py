"""
Lakebranch — Airflow Operator
===========================

``LakebranchWriteOperator`` turns "write to Iceberg via Lakebranch" into a single
task. It resolves the storage profile from the environment, ensures the
warehouse, guarantees the namespace/table exist (creating them if needed), and
appends (or overwrites) the supplied rows via PyIceberg + PyArrow.

Usage in a DAG is intentionally minimal:

.. code-block:: python

    write_events = LakebranchWriteOperator(
        task_id="write_events",
        table_name="db.events",
        mode="append",
        data=[
            {"event_id": 4, "event_type": "signup", "timestamp": "2026-08-01T12:00:00Z"},
        ],
    )
"""

from __future__ import annotations

import json
from typing import Any, Sequence

import pyarrow as pa
from airflow.models.baseoperator import BaseOperator
from pyiceberg.io.pyarrow import schema_to_pyarrow

from lakebranch_provider.hooks.lakebranch import DEFAULT_EVENTS_SCHEMA, LakebranchHook

VALID_MODES = ("append", "overwrite")


class LakebranchWriteOperator(BaseOperator):
    """Write rows to an Iceberg table via the Lakebranch stack.

    The operator is a thin wrapper over :class:`LakebranchHook`:

    1. Ensure the configured warehouse (bucket/directory) exists.
    2. Load (or create) the Iceberg table named by ``table_name``.
    3. Convert ``data`` to a PyArrow table.
    4. Append or overwrite the rows on the table.

    The storage backend is selected at runtime from the environment via
    ``STORAGE_PROFILE`` (``seaweedfs``, ``minio``, ``aws-s3``, ...), exactly
    like the Lakebranch CLI pipeline — switching backends requires zero changes
    to this operator or the calling DAG.

    Args:
        table_name: Fully qualified Iceberg table name (e.g. ``db.events``).
        mode: ``"append"`` to add rows, ``"overwrite"`` to replace the
            table's existing data files (metadata-only rewrite).
        data: List of dicts (rows) to write, or a JSON-payload string
            encoding the same structure.
        lakebranch_conn_id: Logical Airflow connection id (placeholder — Lakebranch
            reads real config from the environment).
    """

    template_fields: Sequence[str] = ("table_name", "mode", "data")

    def __init__(
        self,
        *,
        table_name: str,
        mode: str = "append",
        data: list[dict[str, Any]] | str | None = None,
        lakebranch_conn_id: str = LakebranchHook.default_conn_name,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.table_name = table_name
        self.mode = mode
        self.data = data
        self.lakebranch_conn_id = lakebranch_conn_id

        if self.mode not in VALID_MODES:
            raise ValueError(
                f"Invalid mode '{self.mode}'. Valid modes: {', '.join(VALID_MODES)}"
            )

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------
    def execute(self, context: dict) -> None:
        """Run the Lakebranch write pipeline."""
        hook = LakebranchHook(conn_id=self.lakebranch_conn_id)

        # 1. Ensure the warehouse exists.
        hook.ensure_warehouse()

        # 2. Load (or create) the target table with the demo schema.
        table = hook.get_table(self.table_name, schema=DEFAULT_EVENTS_SCHEMA)

        # 3. Normalize data to a list of dicts.
        rows = self._coerce_data(self.data)
        if not rows:
            self.log.info("No rows provided for table '%s'; nothing to write.", self.table_name)
            return

        # Build the PyArrow table with the Iceberg table's own schema so field
        # names, types, AND nullability match — PyIceberg rejects appends when
        # the inferred Arrow schema differs (e.g. required vs optional).
        arrow_table = pa.Table.from_pylist(rows, schema=schema_to_pyarrow(table.schema()))

        # 4. Append or overwrite.
        if self.mode == "append":
            table.append(arrow_table)
            self.log.info("Appended %d rows to '%s'", arrow_table.num_rows, self.table_name)
        elif self.mode == "overwrite":
            table.overwrite(arrow_table)
            self.log.info("Overwrote '%s' with %d rows", self.table_name, arrow_table.num_rows)

        # Push the row count to XCom for downstream tasks / UI visibility.
        self.xcom_push(context, key="row_count", value=arrow_table.num_rows)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _coerce_data(data: list[dict[str, Any]] | str | None) -> list[dict[str, Any]]:
        """Coerce the ``data`` param (list of dicts or JSON string) to a list."""
        if data is None:
            return []
        if isinstance(data, str):
            parsed = json.loads(data)
            if not isinstance(parsed, list):
                raise ValueError(
                    "When 'data' is a JSON string it must encode a list of objects "
                    f"(got {type(parsed).__name__})."
                )
            return parsed
        if isinstance(data, list):
            return data
        raise ValueError(
            f"'data' must be a list of dicts or a JSON string, got {type(data).__name__}."
        )