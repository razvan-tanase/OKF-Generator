from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class NormalizedUnit:
    unit_id: str
    anchor_id: str
    source_uri: str
    source_version_uri: str
    anchor_uri: str
    source_path: str
    kind: str
    text: str | None
    data: Mapping[str, Any]
    native_locator: Mapping[str, Any]
    metadata: Mapping[str, Any]
    diagnostics: tuple[str, ...]
    content_sha256: str

    def to_json(self) -> str:
        return json.dumps(
            asdict(self),
            sort_keys=True,
            ensure_ascii=True,
            separators=(",", ":"),
            allow_nan=False,
        )


@dataclass(frozen=True)
class NormalizationManifest:
    schema_version: str
    stage: str
    profile: str
    source_id: str
    snapshot_id: str
    classification_ruleset: str
    extraction_profile: str
    extraction_manifest_sha256: str
    extraction_units_sha256: str
    source_uri: str
    source_version_uri: str
    anchor_basis: str
    text_normalization: str
    units_path: str
    units_sha256: str
    unit_count: int
    diagnostic_count: int
    diagnostics: tuple[str, ...]

    def to_json(self) -> str:
        return json.dumps(
            asdict(self),
            indent=2,
            sort_keys=True,
            ensure_ascii=True,
            allow_nan=False,
        ) + "\n"
