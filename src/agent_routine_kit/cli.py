"""Read-only command line for local snapshot audits."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agent_routine_kit.audit import audit_snapshot
from agent_routine_kit.errors import ContractError
from agent_routine_kit.report import render_json, render_text


def main(argv=None):
    parser = argparse.ArgumentParser(prog="agent-routine-kit")
    commands = parser.add_subparsers(dest="command")
    audit = commands.add_parser("audit", help="Audit a local normalized snapshot")
    audit.add_argument("snapshot", help="Path to a local snapshot JSON file")
    audit.add_argument(
        "--format",
        choices=("json", "text", "both"),
        default="json",
        help="json on stdout (default), text on stdout, or json on stdout and text on stderr",
    )
    audit.add_argument(
        "--output",
        help="Write the JSON report to this local file. This is the only file the command writes.",
    )
    args = parser.parse_args(argv)
    if args.command != "audit":
        parser.print_help(sys.stderr)
        return 2
    path = Path(args.snapshot)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"error: invalid JSON: {exc}", file=sys.stderr)
        return 2
    try:
        report = audit_snapshot(data)
    except ContractError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    payload = render_json(report)
    text = render_text(report)
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
    if args.format == "json":
        sys.stdout.write(payload)
    elif args.format == "text":
        sys.stdout.write(text)
    else:
        sys.stdout.write(payload)
        sys.stderr.write(text)
    return 0 if report["all_clear"] else 1
