from __future__ import annotations
import hashlib, json, re
from pathlib import Path
from typing import Any, Mapping
from .canonical_state import (
    STATE_SCHEMA_VERSION, CURRENT_SCHEMA_VERSION, REGISTRY_SCHEMA_VERSION,
    validate_concepts, validate_summaries, validate_claims, validate_relations, validate_events,
    identity_registry, resolution_catalog_projection, planning_state_projection
)
from .compilation_errors import CompilationError
from .compilation_io import canonical_json_bytes, jsonl, load_json, load_jsonl, sha_file, sha_text
from .compilation_model import CompilationManifest

GENERATION_RE=re.compile(r"^sha256-[0-9a-f]{64}$")

def generation_descriptor(manifest: Mapping[str,Any])->dict[str,Any]:
    fields=[
        "profile","parent_generation_id","plan_run_id","plan_manifest_sha256","operations_sha256",
        "concepts_sha256","summaries_sha256","claims_sha256","relations_sha256",
        "identity_registry_sha256","events_sha256","resolution_catalog_sha256","planning_state_sha256",
        "applied_plan_run_ids"
    ]
    missing=[f for f in fields if f not in manifest]
    if missing: raise CompilationError(f"state manifest missing generation fields: {missing}")
    return {f:manifest[f] for f in fields}

def rederive_generation_id(manifest: Mapping[str,Any])->str:
    return "sha256-"+hashlib.sha256(canonical_json_bytes(generation_descriptor(manifest))).hexdigest()

def _validate_registry(value:Any, concepts:list[dict[str,Any]], summaries:list[dict[str,Any]], claims:list[dict[str,Any]], relations:list[dict[str,Any]])->dict[str,Any]:
    expected=identity_registry(concepts,summaries,claims,relations)
    if value!=expected: raise CompilationError("identity registry does not match canonical objects")
    return value

def _validate_projections(catalog:Any, planning:Any, concepts:list[dict[str,Any]], claims:list[dict[str,Any]], relations:list[dict[str,Any]])->None:
    if catalog!=resolution_catalog_projection(concepts): raise CompilationError("resolution catalog projection does not match canonical concepts")
    if planning!=planning_state_projection(claims,relations): raise CompilationError("planning-state projection does not match canonical state")

def load_generation(state_root:Path,generation_id:str,expected_manifest_sha:str|None=None)->tuple[CompilationManifest,dict[str,Any]]:
    if not GENERATION_RE.fullmatch(generation_id): raise CompilationError("current pointer has invalid generation_id")
    gen_dir=state_root/"generations"/generation_id
    manifest_path=gen_dir/"state.json"; raw_manifest=load_json(manifest_path,"canonical state manifest")
    if expected_manifest_sha is not None and sha_file(manifest_path)!=expected_manifest_sha:
        raise CompilationError("current pointer state manifest hash mismatch")
    if raw_manifest.get("schema_version")!=STATE_SCHEMA_VERSION or raw_manifest.get("stage")!="09-compile" or raw_manifest.get("generation_id")!=generation_id:
        raise CompilationError("canonical state manifest identity mismatch")
    if rederive_generation_id(raw_manifest)!=generation_id: raise CompilationError("canonical state generation_id does not match content descriptor")
    path_fields={
        "concepts":"concepts.jsonl","summaries":"summaries.jsonl","claims":"claims.jsonl","relations":"relations.jsonl",
        "identity_registry":"identity-registry.json","events":"events.jsonl","resolution_catalog":"resolution-catalog.json","planning_state":"planning-state.json"
    }
    for stem,name in path_fields.items():
        if raw_manifest.get(f"{stem}_path")!=name: raise CompilationError(f"canonical state {stem}_path is unexpected")
        if raw_manifest.get(f"{stem}_sha256")!=sha_file(gen_dir/name): raise CompilationError(f"canonical state {stem} hash mismatch")
    concepts=validate_concepts(load_jsonl(gen_dir/"concepts.jsonl","canonical concepts"))
    summaries=validate_summaries(load_jsonl(gen_dir/"summaries.jsonl","canonical summaries"))
    claims=validate_claims(load_jsonl(gen_dir/"claims.jsonl","canonical claims"))
    active_concepts={x["internal_id"] for x in concepts if x["status"]!="merged"}
    relations=validate_relations(load_jsonl(gen_dir/"relations.jsonl","canonical relations"),active_concepts)
    events=validate_events(load_jsonl(gen_dir/"events.jsonl","canonical events"))
    registry=load_json(gen_dir/"identity-registry.json","canonical identity registry")
    catalog=load_json(gen_dir/"resolution-catalog.json","canonical resolution catalog")
    planning=load_json(gen_dir/"planning-state.json","canonical planning-state projection")
    _validate_registry(registry,concepts,summaries,claims,relations)
    _validate_projections(catalog,planning,concepts,claims,relations)
    counts={
        "concept_count":len(concepts),"summary_count":len(summaries),"claim_count":len(claims),
        "relation_count":len(relations),"event_count":len(events)
    }
    for field,count in counts.items():
        if raw_manifest.get(field)!=count: raise CompilationError(f"canonical state {field} mismatch")
    applied=raw_manifest.get("applied_plan_run_ids")
    if not isinstance(applied,list) or not all(isinstance(x,str) and x for x in applied) or len(set(applied))!=len(applied):
        raise CompilationError("canonical state applied_plan_run_ids is malformed")
    # Dataclass constructor also ensures known manifest shape is used by callers; tolerate no unknown fields? Fail closed.
    expected_manifest_fields=set(CompilationManifest.__dataclass_fields__)
    if set(raw_manifest)!=expected_manifest_fields:
        raise CompilationError(f"canonical state manifest schema mismatch; missing={sorted(expected_manifest_fields-set(raw_manifest))}, extra={sorted(set(raw_manifest)-expected_manifest_fields)}")
    manifest=CompilationManifest(**raw_manifest)
    return manifest,{"concepts":concepts,"summaries":summaries,"claims":claims,"relations":relations,"events":events,"applied_plan_run_ids":list(applied),"catalog":catalog,"planning_state":planning}

def load_current(state_root:Path)->tuple[CompilationManifest|None,dict[str,Any]|None]:
    pointer=state_root/"current.json"
    if not pointer.exists(): return None,None
    current=load_json(pointer,"canonical current pointer")
    if set(current)!={"schema_version","generation_id","state_manifest_sha256"} or current.get("schema_version")!=CURRENT_SCHEMA_VERSION:
        raise CompilationError("canonical current pointer schema mismatch")
    gid=current.get("generation_id"); mh=current.get("state_manifest_sha256")
    if not isinstance(gid,str) or not isinstance(mh,str) or len(mh)!=64:
        raise CompilationError("canonical current pointer is malformed")
    return load_generation(state_root,gid,mh)

def build_generation_files(*,concepts:list[dict[str,Any]],summaries:list[dict[str,Any]],claims:list[dict[str,Any]],
                           relations:list[dict[str,Any]],events:list[dict[str,Any]])->tuple[dict[str,str],dict[str,str]]:
    concepts=validate_concepts(concepts); summaries=validate_summaries(summaries); claims=validate_claims(claims)
    active={x["internal_id"] for x in concepts if x["status"]!="merged"}
    relations=validate_relations(relations,active); events=validate_events(events)
    registry=identity_registry(concepts,summaries,claims,relations)
    catalog=resolution_catalog_projection(concepts)
    planning=planning_state_projection(claims,relations)
    files={
        "concepts.jsonl":jsonl(concepts),"summaries.jsonl":jsonl(summaries),"claims.jsonl":jsonl(claims),
        "relations.jsonl":jsonl(relations),"events.jsonl":jsonl(events),
        "identity-registry.json":json.dumps(registry,indent=2,sort_keys=True,ensure_ascii=True,allow_nan=False)+"\n",
        "resolution-catalog.json":json.dumps(catalog,indent=2,sort_keys=True,ensure_ascii=True,allow_nan=False)+"\n",
        "planning-state.json":json.dumps(planning,indent=2,sort_keys=True,ensure_ascii=True,allow_nan=False)+"\n",
    }
    hashes={name:sha_text(text) for name,text in files.items()}
    return files,hashes
