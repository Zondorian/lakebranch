"""Tests for the lakebranch CLI parser."""

from __future__ import annotations

from src.lakebranch.cli import build_parser


def test_parser_has_subcommands():
    parser = build_parser()
    choices = parser._subparsers._group_actions[0].choices
    assert {"up", "down", "pipeline", "runs", "ui", "init-demo", "sql"} <= set(choices)


def test_ui_defaults():
    args = build_parser().parse_args(["ui"])
    assert args.host == "127.0.0.1"
    assert args.port == 8787

    args = build_parser().parse_args(["ui", "--port", "9000"])
    assert args.port == 9000


def test_sql_subcommand():
    """`lakebranch sql` accepts a query and a --limit flag."""
    args = build_parser().parse_args(["sql", "SELECT * FROM db_events"])
    assert args.query == "SELECT * FROM db_events"
    assert args.limit == 1000

    args = build_parser().parse_args(["sql", "--limit", "50", "SELECT 1"])
    assert args.query == "SELECT 1"
    assert args.limit == 50
