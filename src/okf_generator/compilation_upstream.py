from __future__ import annotations
import hashlib, json, re
from pathlib import Path
from typing import Any, Callable, Mapping
from .compilation_errors import CompilationError
from .compilation_io import canonical_json_bytes, load_json, load_jsonl, sha_file
from .planning_decisions import validate_decisions
from .planning_state import validate_planning_state
from .planning_upstream import load_verified_resolution, resolution_run_dir

PLAN_RUN_RE = re.compile(r"^sha256-[0-9a-f]{64}$")
OP_FIELDS = {
    "operation_id","operation","object_type","candidate_ids","target_internal_ids","survivor_internal_id",
    "provisional_internal_id","proposed_canonical_path","payload","evidence_anchors","dependencies","reason"
}
OPERATIONS = {"create","update","merge","contradict","supersede","ignore"}
OBJECTS = {"concept","summary","claim","relation"}

def plan_run_dir(root:Path,source_id:str,snapshot_id:str,ruleset:str,extraction_profile:str,normalization_profile:str,
                 synthesis_profile:str,synthesis_provider:str,synthesis_run_id:str,resolution_profile:str,
                 resolution_run_id:str,planning_profile:str,plan_run_id:str)->Path:
    return root/source_id/snapshot_id/ruleset/extraction_profile/normalization_profile/synthesis_profile/synthesis_provider/synthesis_run_id/resolution_profile/resolution_run_id/planning_profile/plan_run_id

def rederive_plan_run_id(manifest:Mapping[str,Any])->str:
    fields=[
        "profile","resolution_manifest_sha256","resolution_rows_sha256","synthesis_candidates_sha256",
        "catalog_canonical_sha256","planning_state_canonical_sha256","decision_canonical_sha256",
        "slug_basis","unicode_version","operations_sha256"
    ]
    missing=[f for f in fields if f not in manifest]
    if missing: raise CompilationError(f"Stage 08 plan manifest is missing run identity fields: {missing}")
    descriptor={f:manifest[f] for f in fields}
    return "sha256-"+hashlib.sha256(canonical_json_bytes(descriptor)).hexdigest()

def validate_operations(rows:list[dict[str,Any]], manifest:Mapping[str,Any])->list[dict[str,Any]]:
    seen_ops:set[str]=set(); seen_candidates:set[str]=set()
    op_counts={x:0 for x in OPERATIONS}; obj_counts={x:0 for x in OBJECTS}; blocked=0
    clean=[]
    for index,row in enumerate(rows,start=1):
        if set(row)!=OP_FIELDS: raise CompilationError(f"Stage 08 operation {index} schema mismatch")
        expected_id=f"op{index:06d}"
        if row["operation_id"]!=expected_id or row["operation_id"] in seen_ops:
            raise CompilationError(f"Stage 08 operation {index} has invalid operation_id")
        seen_ops.add(expected_id)
        if row["operation"] not in OPERATIONS or row["object_type"] not in OBJECTS:
            raise CompilationError(f"Stage 08 operation {expected_id} has unsupported operation/object type")
        for field in ("candidate_ids","target_internal_ids","evidence_anchors","dependencies"):
            value=row[field]
            if not isinstance(value,list) or not all(isinstance(x,str) and x for x in value) or len(set(value))!=len(value):
                raise CompilationError(f"Stage 08 operation {expected_id} field {field} is malformed")
        if not row["candidate_ids"]:
            raise CompilationError(f"Stage 08 operation {expected_id} must reference at least one candidate")
        if any(dep not in seen_ops or dep==expected_id for dep in row["dependencies"]):
            raise CompilationError(f"Stage 08 operation {expected_id} has a forward/unknown dependency")
        if row["survivor_internal_id"] is not None and (not isinstance(row["survivor_internal_id"],str) or not row["survivor_internal_id"]):
            raise CompilationError(f"Stage 08 operation {expected_id} survivor is malformed")
        if row["provisional_internal_id"] is not None and (not isinstance(row["provisional_internal_id"],str) or not row["provisional_internal_id"]):
            raise CompilationError(f"Stage 08 operation {expected_id} provisional ID is malformed")
        if row["proposed_canonical_path"] is not None and (not isinstance(row["proposed_canonical_path"],str) or not row["proposed_canonical_path"]):
            raise CompilationError(f"Stage 08 operation {expected_id} path is malformed")
        if not isinstance(row["payload"],dict):
            raise CompilationError(f"Stage 08 operation {expected_id} payload must be an object")
        if not isinstance(row["reason"],str) or not row["reason"].strip():
            raise CompilationError(f"Stage 08 operation {expected_id} reason must be non-empty")
        # Each Stage 06 candidate is planned exactly once.
        dup=seen_candidates.intersection(row["candidate_ids"])
        if dup: raise CompilationError(f"Stage 08 candidate(s) planned more than once: {sorted(dup)}")
        seen_candidates.update(row["candidate_ids"])
        op_counts[row["operation"]]+=1; obj_counts[row["object_type"]]+=1
        if row["operation"]=="ignore": blocked+=1
        clean.append(dict(row))
    if manifest.get("operation_count")!=len(clean): raise CompilationError("Stage 08 operation_count mismatch")
    if manifest.get("operation_counts")!=op_counts: raise CompilationError("Stage 08 operation_counts mismatch")
    if manifest.get("object_counts")!=obj_counts: raise CompilationError("Stage 08 object_counts mismatch")
    if manifest.get("blocked_count")!=blocked: raise CompilationError("Stage 08 blocked_count mismatch")
    return clean

def load_verified_plan(plan_dir:Path,resolution_root:Path,synthesis_root:Path,expected:Mapping[str,str], *,
                       resolution_verifier:Callable[...,Any]=load_verified_resolution):
    manifest_path=plan_dir/"plan.json"
    manifest=load_json(manifest_path,"Stage 08 plan manifest")
    identities={
        "stage":"08-plan","source_id":expected["source_id"],"snapshot_id":expected["snapshot_id"],
        "classification_ruleset":expected["ruleset"],"extraction_profile":expected["extraction_profile"],
        "normalization_profile":expected["normalization_profile"],"synthesis_profile":expected["synthesis_profile"],
        "synthesis_provider":expected["synthesis_provider"],"synthesis_run_id":expected["synthesis_run_id"],
        "resolution_profile":expected["resolution_profile"],"resolution_run_id":expected["resolution_run_id"],
        "profile":expected["planning_profile"],"run_id":expected["plan_run_id"],
    }
    for field,value in identities.items():
        if manifest.get(field)!=value: raise CompilationError(f"Stage 08 plan identity mismatch for {field}")
    if manifest.get("schema_version")!="0.1" or not PLAN_RUN_RE.fullmatch(expected["plan_run_id"]):
        raise CompilationError("unsupported or invalid Stage 08 plan identity")
    paths={"planning_state_path":"planning-state.json","decision_path":"decisions.json","operations_path":"operations.jsonl"}
    for field,name in paths.items():
        if manifest.get(field)!=name: raise CompilationError(f"Stage 08 {field} is unexpected")
    if manifest.get("operations_sha256")!=sha_file(plan_dir/"operations.jsonl"):
        raise CompilationError("Stage 08 operations hash mismatch")
    if rederive_plan_run_id(manifest)!=expected["plan_run_id"]:
        raise CompilationError("Stage 08 plan_run_id does not match its content-addressed descriptor")

    res_dir=resolution_run_dir(
        resolution_root,expected["source_id"],expected["snapshot_id"],expected["ruleset"],expected["extraction_profile"],
        expected["normalization_profile"],expected["synthesis_profile"],expected["synthesis_provider"],expected["synthesis_run_id"],
        expected["resolution_profile"],expected["resolution_run_id"]
    )
    resolution_expected={
        "source_id":expected["source_id"],"snapshot_id":expected["snapshot_id"],"ruleset":expected["ruleset"],
        "extraction_profile":expected["extraction_profile"],"normalization_profile":expected["normalization_profile"],
        "synthesis_profile":expected["synthesis_profile"],"synthesis_provider":expected["synthesis_provider"],
        "synthesis_run_id":expected["synthesis_run_id"],"resolution_profile":expected["resolution_profile"],
        "resolution_run_id":expected["resolution_run_id"],
    }
    try:
        resolution,resolution_rows,catalog,synthesis,candidates,res_manifest_sha,res_rows_sha,synth_candidates_sha=resolution_verifier(
            res_dir,synthesis_root,resolution_expected
        )
    except Exception as exc:
        if isinstance(exc,CompilationError): raise
        raise CompilationError(f"Stage 07/06 verification failed: {exc}") from exc
    if manifest.get("resolution_manifest_sha256")!=res_manifest_sha or manifest.get("resolution_rows_sha256")!=res_rows_sha:
        raise CompilationError("Stage 08 plan does not bind the verified Stage 07 resolution")
    if manifest.get("synthesis_candidates_sha256")!=synth_candidates_sha:
        raise CompilationError("Stage 08 plan does not bind the verified Stage 06 candidates")
    if manifest.get("catalog_canonical_sha256")!=resolution.get("catalog_canonical_sha256"):
        raise CompilationError("Stage 08 plan catalog hash does not match Stage 07")

    concept_ids={x["internal_id"] for x in catalog["concepts"]}
    state_raw=load_json(plan_dir/"planning-state.json","Stage 08 planning-state snapshot")
    decisions_raw=load_json(plan_dir/"decisions.json","Stage 08 decision snapshot")
    try:
        state=validate_planning_state(state_raw,concept_ids)
        decisions=validate_decisions(decisions_raw)
    except Exception as exc:
        raise CompilationError(f"Stage 08 embedded input snapshot is invalid: {exc}") from exc
    state_sha=hashlib.sha256(canonical_json_bytes(state)).hexdigest()
    decision_sha=hashlib.sha256(canonical_json_bytes(decisions)).hexdigest()
    if manifest.get("planning_state_canonical_sha256")!=state_sha:
        raise CompilationError("Stage 08 planning-state canonical hash mismatch")
    if manifest.get("decision_canonical_sha256")!=decision_sha:
        raise CompilationError("Stage 08 decision canonical hash mismatch")
    operations=validate_operations(load_jsonl(plan_dir/"operations.jsonl","Stage 08 operations"),manifest)
    return manifest,operations,catalog,state,decisions,sha_file(manifest_path),sha_file(plan_dir/"operations.jsonl")
