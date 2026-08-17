from __future__ import annotations
import json
from dataclasses import asdict, dataclass
from typing import Mapping

@dataclass(frozen=True)
class CompilationManifest:
    schema_version: str
    stage: str
    profile: str
    generation_id: str
    parent_generation_id: str | None
    plan_run_id: str
    plan_manifest_sha256: str
    operations_sha256: str
    concepts_path: str
    concepts_sha256: str
    concept_count: int
    summaries_path: str
    summaries_sha256: str
    summary_count: int
    claims_path: str
    claims_sha256: str
    claim_count: int
    relations_path: str
    relations_sha256: str
    relation_count: int
    identity_registry_path: str
    identity_registry_sha256: str
    events_path: str
    events_sha256: str
    event_count: int
    resolution_catalog_path: str
    resolution_catalog_sha256: str
    planning_state_path: str
    planning_state_sha256: str
    applied_plan_run_ids: tuple[str, ...]
    operation_counts: Mapping[str, int]

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n"
