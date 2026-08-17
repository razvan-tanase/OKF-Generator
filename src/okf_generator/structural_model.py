from __future__ import annotations
import json
from dataclasses import asdict, dataclass
from typing import Mapping

@dataclass(frozen=True)
class StructuralizationManifest:
    schema_version: str
    stage: str
    profile: str
    run_id: str
    state_generation_id: str
    state_manifest_sha256: str
    source_okf_version: str
    source_okf_spec_commit: str
    documents_path: str
    documents_sha256: str
    document_count: int
    document_counts: Mapping[str,int]
    identity_map_path: str
    identity_map_sha256: str
    deferred_path: str
    deferred_sha256: str
    def to_json(self)->str:
        return json.dumps(asdict(self),indent=2,sort_keys=True,ensure_ascii=True,allow_nan=False)+"\n"
