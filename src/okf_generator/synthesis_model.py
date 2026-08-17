from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class SynthesisManifest:
    schema_version: str
    stage: str
    profile: str
    run_id: str
    source_id: str
    snapshot_id: str
    classification_ruleset: str
    extraction_profile: str
    normalization_profile: str
    normalization_manifest_sha256: str
    normalization_units_sha256: str
    provider: str
    requested_model: str
    prompt_version: str
    prompt_sha256: str
    candidate_schema_version: str
    candidate_schema_sha256: str
    max_input_chars: int
    max_batch_units: int
    max_output_tokens: int
    batch_count: int
    requests_path: str
    requests_sha256: str
    responses_path: str
    responses_sha256: str
    receipts_path: str
    receipts_sha256: str
    candidates_path: str
    candidates_sha256: str
    candidate_counts: Mapping[str, int]

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n"
