from __future__ import annotations
import hashlib,json,re
from pathlib import Path
from .structural_errors import StructuralizationError
from .structural_io import canonical_json_bytes,jsonl,publish_run,sha_text
from .structural_ir import build_documents,build_identity_map
from .structural_model import StructuralizationManifest
from .structural_state import load_verified_state

PROFILE_ID="builtin-v1"
SOURCE_OKF_VERSION="0.1"
SOURCE_OKF_SPEC_COMMIT="ee67a5ca27044ebe7c38385f5b6cffc2305a9c1a"
RUN_RE=re.compile(r"^sha256-[0-9a-f]{64}$")

def deferred_contract()->dict:
    return {"schema_version":"0.1","reserved_documents":[
        {"path":"index.md","owner_stage":"13-derive","reason":"directory indexes are derived from the structuralized knowledge tree"},
        {"path":"log.md","owner_stage":"13-derive","reason":"chronological log is derived from the canonical event ledger"},
    ],"final_markdown_yaml_serialization_stage":"14-serialize"}

class StructuralizationEngine:
    def __init__(self,state_root:Path|str=Path(".okf-generator/state"),output_root:Path|str=Path(".okf-generator/structural"),*,profile:str=PROFILE_ID,state_loader=load_verified_state)->None:
        if profile!=PROFILE_ID: raise StructuralizationError(f"unsupported structuralization profile: {profile}")
        self.state_root=Path(state_root); self.output_root=Path(output_root); self.profile=profile; self.state_loader=state_loader
    def structuralize(self,generation_id:str|None=None)->StructuralizationManifest:
        manifest,state,state_manifest_sha=self.state_loader(self.state_root,generation_id)
        identity_map,refs,paths=build_identity_map(state)
        documents=build_documents(state,refs,paths)
        deferred=deferred_contract()
        documents_text=jsonl(documents)
        identity_text=json.dumps(identity_map,indent=2,sort_keys=True,ensure_ascii=True,allow_nan=False)+"\n"
        deferred_text=json.dumps(deferred,indent=2,sort_keys=True,ensure_ascii=True,allow_nan=False)+"\n"
        docs_sha=sha_text(documents_text); identity_sha=sha_text(identity_text); deferred_sha=sha_text(deferred_text)
        counts={k:0 for k in ("concept","summary","claim","relation")}
        for doc in documents: counts[doc["object_type"]]+=1
        descriptor={"profile":self.profile,"state_generation_id":manifest.generation_id,"state_manifest_sha256":state_manifest_sha,"source_okf_version":SOURCE_OKF_VERSION,"source_okf_spec_commit":SOURCE_OKF_SPEC_COMMIT,"documents_sha256":docs_sha,"identity_map_sha256":identity_sha,"deferred_sha256":deferred_sha}
        run_id="sha256-"+hashlib.sha256(canonical_json_bytes(descriptor)).hexdigest()
        if not RUN_RE.fullmatch(run_id): raise StructuralizationError("internal structural run identity failure")
        result=StructuralizationManifest(schema_version="0.1",stage="10-structuralize",profile=self.profile,run_id=run_id,state_generation_id=manifest.generation_id,state_manifest_sha256=state_manifest_sha,source_okf_version=SOURCE_OKF_VERSION,source_okf_spec_commit=SOURCE_OKF_SPEC_COMMIT,documents_path="documents.jsonl",documents_sha256=docs_sha,document_count=len(documents),document_counts=counts,identity_map_path="identity-map.json",identity_map_sha256=identity_sha,deferred_path="deferred.json",deferred_sha256=deferred_sha)
        manifest_after,state_after,state_manifest_sha_after=self.state_loader(self.state_root,manifest.generation_id)
        if manifest_after!=manifest or state_after!=state or state_manifest_sha_after!=state_manifest_sha:
            raise StructuralizationError("Stage 09 canonical state changed while structuralization was running")
        final_dir=self.output_root/manifest.generation_id/self.profile/run_id
        publish_run(final_dir,{"documents.jsonl":documents_text,"identity-map.json":identity_text,"deferred.json":deferred_text,"structuralization.json":result.to_json()})
        return result

__all__=["PROFILE_ID","SOURCE_OKF_VERSION","SOURCE_OKF_SPEC_COMMIT","StructuralizationEngine","StructuralizationError","StructuralizationManifest"]
