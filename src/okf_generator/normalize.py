from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Mapping

from .acquire import SOURCE_ID_RE
from .classify import RULESET_ID, SNAPSHOT_ID_RE
from .extract import ExtractionEngine, ExtractionError, PROFILE_ID as EXTRACTION_PROFILE_ID
from .normalization_errors import NormalizationError
from .normalization_io import load_json, load_units, publish_immutable, sha256_file
from .normalization_model import NormalizationManifest, NormalizedUnit
from .normalization_values import (
    ANCHOR_BASIS,
    TEXT_NORMALIZATION,
    anchor_id,
    canonical_json_bytes,
    canonicalize_json,
    normalize_source_path,
    normalize_text,
    normalize_unicode,
    source_uri,
    source_version_uri,
)

PROFILE_ID = "builtin-v1"


class NormalizationEngine:
    def __init__(
        self,
        snapshot_root: Path | str = Path(".okf-generator/snapshots"),
        classification_root: Path | str = Path(".okf-generator/classifications"),
        extraction_root: Path | str = Path(".okf-generator/extractions"),
        output_root: Path | str = Path(".okf-generator/normalized"),
        *,
        ruleset: str = RULESET_ID,
        extraction_profile: str = EXTRACTION_PROFILE_ID,
        profile: str = PROFILE_ID,
        extraction_verifier: Callable[[str, str], Mapping[str, Any]] | None = None,
        extraction_engine: ExtractionEngine | None = None,
    ) -> None:
        if ruleset != RULESET_ID:
            raise NormalizationError(
                f"unsupported classification ruleset for Stage 05: {ruleset}"
            )
        if extraction_profile != EXTRACTION_PROFILE_ID:
            raise NormalizationError(
                f"unsupported extraction profile for Stage 05: {extraction_profile}"
            )
        if profile != PROFILE_ID:
            raise NormalizationError(f"unsupported normalization profile: {profile}")
        self.snapshot_root = Path(snapshot_root)
        self.classification_root = Path(classification_root)
        self.extraction_root = Path(extraction_root)
        self.output_root = Path(output_root)
        self.ruleset = ruleset
        self.extraction_profile = extraction_profile
        self.profile = profile
        self.extraction_engine = extraction_engine or ExtractionEngine(
            snapshot_root=self.snapshot_root,
            classification_root=self.classification_root,
            output_root=self.extraction_root,
            ruleset=self.ruleset,
            profile=self.extraction_profile,
        )
        self.extraction_verifier = extraction_verifier or self._verify_extraction

    def _extraction_dir(self, source_id: str, snapshot_id: str) -> Path:
        return (
            self.extraction_root
            / source_id
            / snapshot_id
            / self.ruleset
            / self.extraction_profile
        )

    def _verify_extraction(self, source_id: str, snapshot_id: str) -> Mapping[str, Any]:
        extraction_dir = self._extraction_dir(source_id, snapshot_id)
        manifest_path = extraction_dir / "extraction.json"
        existing = load_json(manifest_path, "Stage 04 extraction manifest")
        try:
            derived = self.extraction_engine.extract(source_id, snapshot_id)
        except ExtractionError as exc:
            raise NormalizationError(
                f"Stage 04 extraction verification failed: {exc}"
            ) from exc
        if json.loads(derived.to_json()) != existing:
            raise NormalizationError(
                "Stage 04 extraction does not match the current verified upstream inputs"
            )
        return existing

    def normalize(self, source_id: str, snapshot_id: str) -> NormalizationManifest:
        if not SOURCE_ID_RE.fullmatch(source_id):
            raise NormalizationError(
                "source_id must match Stage 01 source identifier rules"
            )
        if not SNAPSHOT_ID_RE.fullmatch(snapshot_id):
            raise NormalizationError(
                "snapshot_id must match Stage 02 content-addressed identifier rules"
            )

        extraction_dir = self._extraction_dir(source_id, snapshot_id)
        extraction_manifest_path = extraction_dir / "extraction.json"
        units_path = extraction_dir / "units.jsonl"

        extraction = dict(self.extraction_verifier(source_id, snapshot_id))
        if (
            extraction.get("stage") != "04-extract"
            or extraction.get("source_id") != source_id
            or extraction.get("snapshot_id") != snapshot_id
            or extraction.get("classification_ruleset") != self.ruleset
            or extraction.get("profile") != self.extraction_profile
        ):
            raise NormalizationError(
                "extraction verifier returned inconsistent identity metadata"
            )

        manifest_sha256 = sha256_file(extraction_manifest_path)
        if extraction.get("units_path") != "units.jsonl":
            raise NormalizationError(
                "Stage 04 units_path is unexpected for this normalization profile"
            )
        actual_units_sha256 = sha256_file(units_path)
        if extraction.get("units_sha256") != actual_units_sha256:
            raise NormalizationError(
                "Stage 04 units hash does not match extraction.json"
            )

        raw_units = load_units(units_path)
        if extraction.get("unit_count") != len(raw_units):
            raise NormalizationError(
                "Stage 04 unit_count does not match units.jsonl"
            )

        raw_top_diagnostics = extraction.get("diagnostics", [])
        if not isinstance(raw_top_diagnostics, list) or not all(
            isinstance(item, str) for item in raw_top_diagnostics
        ):
            raise NormalizationError(
                "Stage 04 extraction diagnostics are malformed"
            )
        top_diagnostics = tuple(normalize_unicode(item) for item in raw_top_diagnostics)

        logical_source_uri = source_uri(source_id)
        version_uri = source_version_uri(logical_source_uri, snapshot_id)
        normalized_units: list[NormalizedUnit] = []
        seen_unit_ids: set[str] = set()
        seen_anchors: dict[str, str] = {}
        normalized_path_origins: dict[str, str] = {}
        raw_unit_diagnostic_count = 0
        expected_unit_fields = {
            "unit_id",
            "source_path",
            "kind",
            "text",
            "data",
            "native_locator",
            "metadata",
            "diagnostics",
        }

        for index, raw in enumerate(raw_units, start=1):
            if set(raw) != expected_unit_fields:
                missing = sorted(expected_unit_fields - set(raw))
                extra = sorted(set(raw) - expected_unit_fields)
                raise NormalizationError(
                    f"unit {index} Stage 04 schema mismatch; "
                    f"missing={missing}, extra={extra}"
                )

            unit_id = raw.get("unit_id")
            source_path_raw = raw.get("source_path")
            kind_raw = raw.get("kind")
            text_raw = raw.get("text")
            data_raw = raw.get("data")
            locator_raw = raw.get("native_locator")
            metadata_raw = raw.get("metadata")
            diagnostics_raw = raw.get("diagnostics")

            if not isinstance(unit_id, str) or not unit_id:
                raise NormalizationError(
                    f"unit {index} has an invalid unit_id"
                )
            if unit_id in seen_unit_ids:
                raise NormalizationError(
                    f"duplicate Stage 04 unit_id: {unit_id}"
                )
            seen_unit_ids.add(unit_id)
            if not isinstance(source_path_raw, str):
                raise NormalizationError(
                    f"unit {unit_id} has an invalid source_path"
                )
            if not isinstance(kind_raw, str) or not kind_raw:
                raise NormalizationError(f"unit {unit_id} has an invalid kind")
            if text_raw is not None and not isinstance(text_raw, str):
                raise NormalizationError(
                    f"unit {unit_id} has non-string text"
                )
            if (
                not isinstance(data_raw, dict)
                or not isinstance(locator_raw, dict)
                or not isinstance(metadata_raw, dict)
            ):
                raise NormalizationError(
                    f"unit {unit_id} data/native_locator/metadata must be objects"
                )
            if not isinstance(diagnostics_raw, list) or not all(
                isinstance(item, str) for item in diagnostics_raw
            ):
                raise NormalizationError(
                    f"unit {unit_id} diagnostics must be strings"
                )

            source_path = normalize_source_path(source_path_raw)
            previous_origin = normalized_path_origins.get(source_path)
            if (
                previous_origin is not None
                and previous_origin != source_path_raw
            ):
                raise NormalizationError(
                    "distinct Stage 04 source paths collide after Unicode NFC normalization"
                )
            normalized_path_origins[source_path] = source_path_raw

            kind = normalize_unicode(kind_raw)
            text = normalize_text(text_raw) if text_raw is not None else None
            data = canonicalize_json(
                data_raw, label=f"unit {unit_id} data"
            )
            locator = canonicalize_json(
                locator_raw, label=f"unit {unit_id} native_locator"
            )
            metadata = canonicalize_json(
                metadata_raw, label=f"unit {unit_id} metadata"
            )
            diagnostics = tuple(
                normalize_unicode(item) for item in diagnostics_raw
            )
            raw_unit_diagnostic_count += len(diagnostics_raw)

            unit_anchor_id = anchor_id(source_path, kind, locator)
            prior_unit = seen_anchors.get(unit_anchor_id)
            if prior_unit is not None:
                raise NormalizationError(
                    "native locator collision: units "
                    f"{prior_unit} and {unit_id} map to {unit_anchor_id}"
                )
            seen_anchors[unit_anchor_id] = unit_id
            anchor_uri = f"{version_uri}#{unit_anchor_id}"

            body = {
                "source_path": source_path,
                "kind": kind,
                "text": text,
                "data": data,
                "native_locator": locator,
                "metadata": metadata,
                "diagnostics": list(diagnostics),
            }
            content_sha256 = hashlib.sha256(
                canonical_json_bytes(body)
            ).hexdigest()
            normalized_units.append(
                NormalizedUnit(
                    unit_id=unit_id,
                    anchor_id=unit_anchor_id,
                    source_uri=logical_source_uri,
                    source_version_uri=version_uri,
                    anchor_uri=anchor_uri,
                    source_path=source_path,
                    kind=kind,
                    text=text,
                    data=data,
                    native_locator=locator,
                    metadata=metadata,
                    diagnostics=diagnostics,
                    content_sha256=content_sha256,
                )
            )

        extraction_after = dict(
            self.extraction_verifier(source_id, snapshot_id)
        )
        if (
            extraction_after != extraction
            or sha256_file(extraction_manifest_path) != manifest_sha256
            or sha256_file(units_path) != actual_units_sha256
        ):
            raise NormalizationError(
                "Stage 04 extraction changed while normalization was running"
            )

        units_text = "".join(
            unit.to_json() + "\n" for unit in normalized_units
        )
        units_sha256 = hashlib.sha256(
            units_text.encode("utf-8")
        ).hexdigest()
        diagnostic_count = len(top_diagnostics) + sum(
            len(unit.diagnostics) for unit in normalized_units
        )
        if extraction.get("diagnostic_count") != (
            len(raw_top_diagnostics) + raw_unit_diagnostic_count
        ):
            raise NormalizationError(
                "Stage 04 diagnostic_count is inconsistent with extraction evidence"
            )

        manifest = NormalizationManifest(
            schema_version="0.1",
            stage="05-normalize",
            profile=self.profile,
            source_id=source_id,
            snapshot_id=snapshot_id,
            classification_ruleset=self.ruleset,
            extraction_profile=self.extraction_profile,
            extraction_manifest_sha256=manifest_sha256,
            extraction_units_sha256=actual_units_sha256,
            source_uri=logical_source_uri,
            source_version_uri=version_uri,
            anchor_basis=ANCHOR_BASIS,
            text_normalization=TEXT_NORMALIZATION,
            units_path="units.jsonl",
            units_sha256=units_sha256,
            unit_count=len(normalized_units),
            diagnostic_count=diagnostic_count,
            diagnostics=top_diagnostics,
        )
        final_dir = (
            self.output_root
            / source_id
            / snapshot_id
            / self.ruleset
            / self.extraction_profile
            / self.profile
        )
        publish_immutable(
            final_dir,
            manifest.to_json(),
            units_text,
            profile=self.profile,
        )
        return manifest


__all__ = [
    "ANCHOR_BASIS",
    "PROFILE_ID",
    "TEXT_NORMALIZATION",
    "NormalizationEngine",
    "NormalizationError",
    "NormalizationManifest",
    "NormalizedUnit",
    "normalize_text",
]
