from __future__ import annotations
import json
from dataclasses import asdict, dataclass
from typing import Mapping

@dataclass(frozen=True)
class PlanningManifest:
    schema_version:str
    stage:str
    profile:str
    run_id:str
    source_id:str
    snapshot_id:str
    classification_ruleset:str
    extraction_profile:str
    normalization_profile:str
    synthesis_profile:str
    synthesis_provider:str
    synthesis_run_id:str
    resolution_profile:str
    resolution_run_id:str
    resolution_manifest_sha256:str
    resolution_rows_sha256:str
    synthesis_candidates_sha256:str
    catalog_canonical_sha256:str
    planning_state_mode:str
    planning_state_source_sha256:str|None
    planning_state_canonical_sha256:str
    planning_state_path:str
    decision_mode:str
    decision_source_sha256:str|None
    decision_canonical_sha256:str
    decision_path:str
    slug_basis:str
    unicode_version:str
    operations_path:str
    operations_sha256:str
    operation_count:int
    operation_counts:Mapping[str,int]
    object_counts:Mapping[str,int]
    blocked_count:int
    def to_json(self)->str:
        return json.dumps(asdict(self),indent=2,sort_keys=True,ensure_ascii=True,allow_nan=False)+'\n'
