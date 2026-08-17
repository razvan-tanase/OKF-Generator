from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .acquire import AcquisitionEngine, AcquisitionError, AcquisitionSpec, DEFAULT_MAX_HTTP_BYTES
from .classify import ClassificationEngine, ClassificationError, RULESET_ID
from .extract import ExtractionEngine, ExtractionError, PROFILE_ID as EXTRACTION_PROFILE_ID
from .normalize import NormalizationEngine, NormalizationError, PROFILE_ID as NORMALIZATION_PROFILE_ID
from .snapshot import SnapshotEngine, SnapshotError
from .synthesize import (
    DEFAULT_MAX_BATCH_UNITS,
    DEFAULT_MAX_INPUT_CHARS,
    DEFAULT_MAX_OUTPUT_TOKENS,
    PROFILE_ID as SYNTHESIS_PROFILE_ID,
    SynthesisEngine,
    SynthesisError,
)


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

    classify = subparsers.add_parser(
        "classify",
        help="Stage 03: deterministically classify a verified immutable snapshot",
    )
    classify.add_argument("source_id")
    classify.add_argument("snapshot_id")
    classify.add_argument(
        "--snapshots-root",
        type=Path,
        default=Path(".okf-generator/snapshots"),
    )
    classify.add_argument(
        "--out",
        type=Path,
        default=Path(".okf-generator/classifications"),
    )
    classify.add_argument("--ruleset", default=RULESET_ID)

    extract = subparsers.add_parser(
        "extract",
        help="Stage 04: extract structured source units from a verified classified snapshot",
    )
    extract.add_argument("source_id")
    extract.add_argument("snapshot_id")
    extract.add_argument(
        "--snapshots-root",
        type=Path,
        default=Path(".okf-generator/snapshots"),
    )
    extract.add_argument(
        "--classifications-root",
        type=Path,
        default=Path(".okf-generator/classifications"),
    )
    extract.add_argument(
        "--out",
        type=Path,
        default=Path(".okf-generator/extractions"),
    )
    extract.add_argument("--ruleset", default=RULESET_ID)
    extract.add_argument("--profile", default=EXTRACTION_PROFILE_ID)

    normalize = subparsers.add_parser(
        "normalize",
        help="Stage 05: canonicalize verified Stage 04 source units without semantic synthesis",
    )
    normalize.add_argument("source_id")
    normalize.add_argument("snapshot_id")
    normalize.add_argument(
        "--snapshots-root",
        type=Path,
        default=Path(".okf-generator/snapshots"),
    )
    normalize.add_argument(
        "--classifications-root",
        type=Path,
        default=Path(".okf-generator/classifications"),
    )
    normalize.add_argument(
        "--extractions-root",
        type=Path,
        default=Path(".okf-generator/extractions"),
    )
    normalize.add_argument(
        "--out",
        type=Path,
        default=Path(".okf-generator/normalized"),
    )
    normalize.add_argument("--ruleset", default=RULESET_ID)
    normalize.add_argument("--extraction-profile", default=EXTRACTION_PROFILE_ID)
    normalize.add_argument("--profile", default=NORMALIZATION_PROFILE_ID)

    synthesize = subparsers.add_parser(
        "synthesize",
        help="Stage 06: produce evidence-grounded candidate knowledge from verified normalized units",
    )
    synthesize.add_argument("source_id")
    synthesize.add_argument("snapshot_id")
    synthesize.add_argument(
        "--model",
        required=True,
        help="Explicit provider model identifier; use a pinned snapshot when available",
    )
    synthesize.add_argument(
        "--snapshots-root",
        type=Path,
        default=Path(".okf-generator/snapshots"),
    )
    synthesize.add_argument(
        "--classifications-root",
        type=Path,
        default=Path(".okf-generator/classifications"),
    )
    synthesize.add_argument(
        "--extractions-root",
        type=Path,
        default=Path(".okf-generator/extractions"),
    )
    synthesize.add_argument(
        "--normalized-root",
        type=Path,
        default=Path(".okf-generator/normalized"),
    )
    synthesize.add_argument(
        "--out",
        type=Path,
        default=Path(".okf-generator/syntheses"),
    )
    synthesize.add_argument("--ruleset", default=RULESET_ID)
    synthesize.add_argument("--extraction-profile", default=EXTRACTION_PROFILE_ID)
    synthesize.add_argument("--normalization-profile", default=NORMALIZATION_PROFILE_ID)
    synthesize.add_argument("--profile", default=SYNTHESIS_PROFILE_ID)
    synthesize.add_argument("--max-input-chars", type=int, default=DEFAULT_MAX_INPUT_CHARS)
    synthesize.add_argument("--max-batch-units", type=int, default=DEFAULT_MAX_BATCH_UNITS)
    synthesize.add_argument("--max-output-tokens", type=int, default=DEFAULT_MAX_OUTPUT_TOKENS)
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
        if args.command == "classify":
            manifest = ClassificationEngine(
                snapshot_root=args.snapshots_root,
                output_root=args.out,
                ruleset=args.ruleset,
            ).classify(args.source_id, args.snapshot_id)
            sys.stdout.write(manifest.to_json())
            return 0
        if args.command == "extract":
            manifest = ExtractionEngine(
                snapshot_root=args.snapshots_root,
                classification_root=args.classifications_root,
                output_root=args.out,
                ruleset=args.ruleset,
                profile=args.profile,
            ).extract(args.source_id, args.snapshot_id)
            sys.stdout.write(manifest.to_json())
            return 0
        if args.command == "normalize":
            manifest = NormalizationEngine(
                snapshot_root=args.snapshots_root,
                classification_root=args.classifications_root,
                extraction_root=args.extractions_root,
                output_root=args.out,
                ruleset=args.ruleset,
                extraction_profile=args.extraction_profile,
                profile=args.profile,
            ).normalize(args.source_id, args.snapshot_id)
            sys.stdout.write(manifest.to_json())
            return 0
        if args.command == "synthesize":
            manifest = SynthesisEngine(
                snapshot_root=args.snapshots_root,
                classification_root=args.classifications_root,
                extraction_root=args.extractions_root,
                normalization_root=args.normalized_root,
                output_root=args.out,
                ruleset=args.ruleset,
                extraction_profile=args.extraction_profile,
                normalization_profile=args.normalization_profile,
                profile=args.profile,
                max_input_chars=args.max_input_chars,
                max_batch_units=args.max_batch_units,
                max_output_tokens=args.max_output_tokens,
            ).synthesize(args.source_id, args.snapshot_id, model=args.model)
            sys.stdout.write(manifest.to_json())
            return 0
    except (
        AcquisitionError,
        SnapshotError,
        ClassificationError,
        ExtractionError,
        NormalizationError,
        SynthesisError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
