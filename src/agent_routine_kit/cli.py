"""Read-only command line for local snapshot audits."""

from __future__ import annotations

import argparse
import json
import os
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
        raw, opened_identity = _read_opened_snapshot(path)
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
        destination = Path(args.output)
        error = _write_distinct_output(path, destination, payload, opened_identity)
        if error:
            print(error, file=sys.stderr)
            return 2
    if args.format == "json":
        sys.stdout.write(payload)
    elif args.format == "text":
        sys.stdout.write(text)
    else:
        sys.stdout.write(payload)
        sys.stderr.write(text)
    return 0 if report["all_clear"] else 1


def _read_opened_snapshot(path):
    """Return the snapshot text and the identity of the file the descriptor opened."""
    with path.open("r", encoding="utf-8") as handle:
        return handle.read(), _descriptor_identity(handle.fileno())


def _write_distinct_output(snapshot, destination, payload, opened_identity):
    """Write payload only when the opened output is a different file from the snapshot.

    Returns an error string, or None after a complete write. The opened descriptor
    is compared with the identity retained from the read, before any truncate.
    A later lookup of the input path is not that identity. An identity check that
    raises OSError fails closed and leaves existing bytes unchanged.
    """
    try:
        if _output_identifies_snapshot(snapshot, destination):
            return "error: --output identifies the snapshot file"
    except OSError as exc:
        return f"error: {exc}"
    try:
        descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT, 0o644)
    except OSError as exc:
        return f"error: {exc}"
    try:
        try:
            if _opened_output_identifies_snapshot(opened_identity, descriptor):
                return "error: --output identifies the snapshot file"
        except OSError as exc:
            return f"error: {exc}"
        try:
            os.ftruncate(descriptor, 0)
            encoded = payload.encode("utf-8")
            offset = 0
            while offset < len(encoded):
                written = os.write(descriptor, encoded[offset:])
                if written <= 0:
                    return "error: output write returned no progress"
                offset += written
        except OSError as exc:
            return f"error: {exc}"
    finally:
        os.close(descriptor)
    return None


def _output_identifies_snapshot(snapshot, output):
    """True when the output path is the snapshot, including a resolved or link alias.

    Raises OSError when that identity cannot be established. A missing output
    path is not an alias.
    """
    if snapshot.resolve() == output.resolve():
        return True
    if not output.exists():
        return False
    return snapshot.samefile(output)


def _descriptor_identity(descriptor):
    """Device and inode of an already opened descriptor."""
    info = os.fstat(descriptor)
    return (info.st_dev, info.st_ino)


def _opened_output_identifies_snapshot(opened_identity, descriptor):
    """True when the opened output descriptor is the file that was read."""
    return _descriptor_identity(descriptor) == opened_identity
