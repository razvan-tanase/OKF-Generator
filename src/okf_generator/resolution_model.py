from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Mapping


@dataclass(frozen=True)
class ResolutionManifest:
    schema_version: str
    stage: str
    profile: str
    run_id: str
    source_id: str
    snapshot_id: str
    classification_ruleset: str
    extraction_profile: str
    normalization_profile: str
    synthesis_profile: str
    synthesis_provider: str
    synthesis_run_id: str
    synthesis_manifest_sha256: str
    synthesis_candidates_sha256: str
    catalog_mode: str
    catalog_source_sha256: str | None
    catalog_canonical_sha256: str
    catalog_path: str
    similarity_threshold: float
    shortlist_limit: int
    adjudication_provider: str | None
    adjudication_model: str | None
    resolutions_path: str
    resolutions_sha256: str
    resolution_counts: Mapping[str, int]
    adjudication_requests_path: str
    adjudication_requests_sha256: str
    adjudication_responses_path: str
    adjudication_responses_sha256: str
    adjudication_receipts_path: str
    adjudication_receipts_sha256: str

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n"
