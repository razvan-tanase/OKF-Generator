from __future__ import annotations
import copy, json
from typing import Any
from .canonical_state import CURRENT_SCHEMA_VERSION, STATE_SCHEMA_VERSION, bootstrap_from_projections
from .compilation_errors import CompilationError
from .compilation_io import publish_directory, sha_text, state_lock
from .compilation_model import CompilationManifest
from .compilation_state import build_generation_files, load_current, rederive_generation_id
from .compilation_apply import apply_operations

def compile_state(engine:Any,source_id:str,snapshot_id:str,synthesis_run_id:str,resolution_run_id:str,plan_run_id:str,*,synthesis_provider:str)->CompilationManifest:
    engine._validate_identity(source_id,snapshot_id,synthesis_provider,synthesis_run_id,resolution_run_id,plan_run_id)
    pdir, first=engine._load_plan(source_id,snapshot_id,synthesis_provider,synthesis_run_id,resolution_run_id,plan_run_id)
    plan,operations,catalog,planning_state,decisions,plan_manifest_sha,operations_sha=first
    with state_lock(engine.state_root):
        current_manifest,current_state=load_current(engine.state_root)
        if current_manifest is not None and plan_run_id in current_manifest.applied_plan_run_ids:
            if current_manifest.plan_run_id==plan_run_id:
                if current_manifest.plan_manifest_sha256!=plan_manifest_sha or current_manifest.operations_sha256!=operations_sha:
                    raise CompilationError("already-applied Stage 08 plan no longer matches the active canonical generation provenance")
                return current_manifest
            raise CompilationError("Stage 08 plan was already applied to an ancestor canonical generation")
        if current_state is None:
            base=bootstrap_from_projections(catalog,planning_state)
            parent=None
        else:
            if current_state["catalog"]!=catalog:
                raise CompilationError("Stage 08 plan is stale: its Stage 07 catalog is not the current canonical projection")
            if current_state["planning_state"]!=planning_state:
                raise CompilationError("Stage 08 plan is stale: its planning-state snapshot is not the current canonical projection")
            base={k:copy.deepcopy(current_state[k]) for k in ("concepts","summaries","claims","relations","events","applied_plan_run_ids")}
            parent=current_manifest.generation_id
        new_state=apply_operations(base,operations,plan_run_id)
        files,hashes=build_generation_files(concepts=new_state["concepts"],summaries=new_state["summaries"],claims=new_state["claims"],relations=new_state["relations"],events=new_state["events"])
        # Reverify the complete upstream plan after semantic application and before state publication.
        _, second=engine._load_plan(source_id,snapshot_id,synthesis_provider,synthesis_run_id,resolution_run_id,plan_run_id)
        plan2,ops2,catalog2,state2,decisions2,plan_manifest_sha2,operations_sha2=second
        if plan2!=plan or ops2!=operations or catalog2!=catalog or state2!=planning_state or decisions2!=decisions or plan_manifest_sha2!=plan_manifest_sha or operations_sha2!=operations_sha:
            raise CompilationError("Stage 08/07/06 inputs changed while compilation was running")
        applied=tuple(new_state["applied_plan_run_ids"])
        op_counts={name:0 for name in ("create","update","merge","contradict","supersede","ignore")}
        for op in operations: op_counts[op["operation"]]+=1
        provisional_manifest={
            "schema_version":STATE_SCHEMA_VERSION,"stage":"09-compile","profile":engine.profile,"generation_id":"",
            "parent_generation_id":parent,"plan_run_id":plan_run_id,"plan_manifest_sha256":plan_manifest_sha,"operations_sha256":operations_sha,
            "concepts_path":"concepts.jsonl","concepts_sha256":hashes["concepts.jsonl"],"concept_count":len(new_state["concepts"]),
            "summaries_path":"summaries.jsonl","summaries_sha256":hashes["summaries.jsonl"],"summary_count":len(new_state["summaries"]),
            "claims_path":"claims.jsonl","claims_sha256":hashes["claims.jsonl"],"claim_count":len(new_state["claims"]),
            "relations_path":"relations.jsonl","relations_sha256":hashes["relations.jsonl"],"relation_count":len(new_state["relations"]),
            "identity_registry_path":"identity-registry.json","identity_registry_sha256":hashes["identity-registry.json"],
            "events_path":"events.jsonl","events_sha256":hashes["events.jsonl"],"event_count":len(new_state["events"]),
            "resolution_catalog_path":"resolution-catalog.json","resolution_catalog_sha256":hashes["resolution-catalog.json"],
            "planning_state_path":"planning-state.json","planning_state_sha256":hashes["planning-state.json"],
            "applied_plan_run_ids":list(applied),"operation_counts":op_counts,
        }
        generation_id=rederive_generation_id(provisional_manifest)
        provisional_manifest["generation_id"]=generation_id
        manifest=CompilationManifest(**provisional_manifest)
        generation_files=dict(files); generation_files["state.json"]=manifest.to_json()
        final_dir=engine.state_root/"generations"/generation_id
        publish_directory(final_dir,generation_files)
        # Detect non-cooperating pointer mutations even while our advisory lock is held.
        check_manifest,_=load_current(engine.state_root)
        current_id=check_manifest.generation_id if check_manifest is not None else None
        if current_id!=parent:
            raise CompilationError("canonical current pointer changed during compilation; new generation was not activated")
        pointer={"schema_version":CURRENT_SCHEMA_VERSION,"generation_id":generation_id,"state_manifest_sha256":sha_text(manifest.to_json())}
        pointer_text=json.dumps(pointer,indent=2,sort_keys=True,ensure_ascii=True,allow_nan=False)+"\n"
        try:
            engine.pointer_writer(engine.state_root/"current.json",pointer_text)
        except Exception as exc:
            raise CompilationError("failed to atomically activate compiled canonical generation; prior current state remains authoritative") from exc
        return manifest

__all__=["compile_state"]
