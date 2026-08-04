"""
Lakebranch - CLI
==============

A single ``lakebranch`` command for the most common workflows, so the core is
usable without remembering the exact ``docker compose`` / ``python -m``
invocations.

Subcommands:
    lakebranch up           Start the Docker stack (SeaweedFS + Nessie)
    lakebranch pipeline     Run the end-to-end Iceberg writer/query pipeline
    lakebranch runs         Show the 10 most recent pipeline runs
    lakebranch ui           Start the web UI (FastAPI dev server)
    lakebranch init-demo    Load the demo dataset
    lakebranch down         Stop the Docker stack

Install the console script with::

    pip install -e .

(core is Apache 2.0)
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

# Project root = the directory containing this src/ package.
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _docker_compose(args: list[str]) -> int:
    """Run docker compose against the default profile file."""
    compose_file = PROJECT_ROOT / "docker" / "docker-compose.yml"
    cmd = ["docker", "compose", "-f", str(compose_file)]
    if (PROJECT_ROOT / ".env").exists():
        cmd += ["--env-file", str(PROJECT_ROOT / ".env")]
    return subprocess.call(cmd + args)


def cmd_up(_: argparse.Namespace) -> int:
    """Start SeaweedFS + Nessie in the background."""
    print("[cli] Starting Lakebranch stack (SeaweedFS + Nessie)...")
    return _docker_compose(["up", "-d"])


def cmd_down(_: argparse.Namespace) -> int:
    """Stop the Docker stack (keeps the SeaweedFS data volume)."""
    print("[cli] Stopping Lakebranch stack...")
    return _docker_compose(["down"])


def cmd_pipeline(_: argparse.Namespace) -> int:
    """Run the end-to-end Iceberg write/query pipeline."""
    from src.lakebranch.write_iceberg import main as pipeline_main

    pipeline_main()
    return 0


def cmd_runs(_: argparse.Namespace) -> int:
    """Print the 10 most recent pipeline runs."""
    from src.lakebranch.runs import print_recent_runs

    print_recent_runs()
    return 0


def cmd_ui(args: argparse.Namespace) -> int:
    """Start the Lakebranch web UI (FastAPI dev server)."""
    try:
        import uvicorn  # noqa: F401  (imported for the error message)
    except ImportError:
        print(
            "[cli] The web UI requires the GUI dependencies.\n"
            "      Install with:  pip install -r requirements-gui.txt"
            "   (or: pip install -e '.[gui]')",
            file=sys.stderr,
        )
        return 1

    import uvicorn as _uvicorn

    from src.lakebranch.api.app import app

    _uvicorn.run(app, host=args.host, port=args.port)
    return 0


def cmd_init_demo(_: argparse.Namespace) -> int:
    """Load the demo dataset."""
    from src.lakebranch.init_demo import main as demo_main

    try:
        demo_main()
    except KeyboardInterrupt:
        print("[cli] Interrupted.", file=sys.stderr)
        return 130
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lakebranch",
        description="Local-first Apache Iceberg data lakehouse (Nessie + SeaweedFS).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_up = sub.add_parser("up", help="Start SeaweedFS + Nessie")
    p_up.set_defaults(func=cmd_up)

    sub.add_parser("down", help="Stop SeaweedFS + Nessie").set_defaults(func=cmd_down)

    sub.add_parser(
        "pipeline",
        help="Run the Iceberg write/query pipeline",
    ).set_defaults(func=cmd_pipeline)

    sub.add_parser(
        "runs",
        help="Show the 10 most recent pipeline runs",
    ).set_defaults(func=cmd_runs)

    p_ui = sub.add_parser("ui", help="Start the web UI")
    p_ui.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    p_ui.add_argument("--port", type=int, default=8787, help="Bind port (default: 8787)")
    p_ui.set_defaults(func=cmd_ui)

    sub.add_parser(
        "init-demo",
        help="Load the demo dataset",
    ).set_defaults(func=cmd_init_demo)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())