from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .acquire import AcquisitionEngine, AcquisitionError, AcquisitionSpec, DEFAULT_MAX_HTTP_BYTES
from .snapshot import SnapshotEngine, SnapshotError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="okf-generator")
    subparsers = parser.add_subparsers(dest="command", required=True)

    acquire = subparsers.add_parser(
        "acquire",
        help="Stage 01: acquire a source without semantic transformation",
    )
    acquire.add_argument("source_id")
    acquire.add_argument("locator")
    acquire.add_argument("--provider", choices=["auto", "local", "http", "git"], default="auto")
    acquire.add_argument("--ref", help="Git ref to require in an acquired git repository")
    acquire.add_argument("--out", type=Path, default=Path(".okf-generator/acquired"))
    acquire.add_argument("--replace", action="store_true")
    acquire.add_argument("--max-http-bytes", type=int, default=DEFAULT_MAX_HTTP_BYTES)

    snapshot = subparsers.add_parser(
        "snapshot",
        help="Stage 02: fingerprint and preserve an immutable acquired source version",
    )
    snapshot.add_argument("source_id")
    snapshot.add_argument(
        "--acquired-root",
        type=Path,
        default=Path(".okf-generator/acquired"),
    )
    snapshot.add_argument(
        "--out",
        type=Path,
        default=Path(".okf-generator/snapshots"),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "acquire":
            receipt = AcquisitionEngine(
                args.out,
                max_http_bytes=args.max_http_bytes,
            ).acquire(
                AcquisitionSpec(
                    source_id=args.source_id,
                    locator=args.locator,
                    provider=args.provider,
                    ref=args.ref,
                ),
                replace=args.replace,
            )
            sys.stdout.write(receipt.to_json())
            return 0
        if args.command == "snapshot":
            manifest = SnapshotEngine(
                acquisition_root=args.acquired_root,
                snapshot_root=args.out,
            ).snapshot(args.source_id)
            sys.stdout.write(manifest.to_json())
            return 0
    except (AcquisitionError, SnapshotError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
