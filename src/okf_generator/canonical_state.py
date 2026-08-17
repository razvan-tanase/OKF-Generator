from __future__ import annotations
import hashlib, json
from pathlib import Path
from typing import Any, Iterable, Mapping
from .compilation_errors import CompilationError
from .compilation_io import canonical_json_bytes, jsonl, load_json, load_jsonl, sha_file, sha_text
from .resolution_catalog import normalize_path_key

STATE_SCHEMA_VERSION = "0.1"
REGISTRY_SCHEMA_VERSION = "0.1"
CURRENT_SCHEMA_VERSION = "0.1"
FINAL_ID_BASIS = "stage09-final-id-v1"

CONCEPT_FIELDS = {
    "internal_id","title","description","canonical_path","aliases","title_history","path_history",
    "resource_uris","source_anchors","status","merged_into"
}
SUMMARY_FIELDS = {"internal_id","text","evidence_anchors","status","merged_into"}
CLAIM_FIELDS = {
    "internal_id","statement","evidence_anchors","status","merged_into",
    "contradicts","contradicted_by","supersedes","superseded_by"
}
RELATION_FIELDS = {
    "internal_id","subject_internal_id","predicate","object_internal_id",
    "evidence_anchors","status","merged_into"
}
EVENT_FIELDS = {
    "event_id","plan_run_id","operation_id","operation","object_type",
    "candidate_ids","target_internal_ids","result_internal_ids","evidence_anchors","reason","operation_snapshot"
}

def _strings(value: Any, label: str, *, allow_empty: bool = True) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(x, str) and x for x in value):
        raise CompilationError(f"{label} must be an array of non-empty strings")
    if len(set(value)) != len(value):
        raise CompilationError(f"{label} contains duplicates")
    if not allow_empty and not value:
        raise CompilationError(f"{label} must not be empty")
    return list(value)

def _nullable_id(value: Any, label: str) -> str | None:
    if value is not None and (not isinstance(value, str) or not value):
        raise CompilationError(f"{label} must be a non-empty string or null")
    return value

def final_internal_id(object_type: str, provisional_internal_id: str) -> str:
    descriptor = {"basis": FINAL_ID_BASIS, "object_type": object_type, "provisional_internal_id": provisional_internal_id}
    digest = hashlib.sha256(canonical_json_bytes(descriptor)).hexdigest()
    return f"urn:okf-generator:identity:{object_type}:sha256-{digest}"

def union_strings(*values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for seq in values:
        for item in seq:
            if item not in seen:
                seen.add(item)
                out.append(item)
    return out

def validate_concepts(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen_ids: set[str] = set(); active_paths: set[str] = set()
    clean: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if set(row) != CONCEPT_FIELDS:
            raise CompilationError(f"concept {index} schema mismatch")
        iid = row["internal_id"]
        if not isinstance(iid, str) or not iid or iid in seen_ids:
            raise CompilationError(f"concept {index} has invalid or duplicate internal_id")
        seen_ids.add(iid)
        for field in ("title","description","canonical_path","status"):
            if not isinstance(row[field], str) or not row[field]:
                raise CompilationError(f"concept {iid} field {field} must be non-empty")
        merged_into = _nullable_id(row["merged_into"], f"concept {iid} merged_into")
        if row["status"] == "merged":
            if merged_into is None:
                raise CompilationError(f"merged concept {iid} must name merged_into")
        elif merged_into is not None:
            raise CompilationError(f"non-merged concept {iid} must not name merged_into")
        key = normalize_path_key(row["canonical_path"])
        if row["status"] != "merged":
            if key in active_paths:
                raise CompilationError(f"duplicate active concept path: {row['canonical_path']}")
            active_paths.add(key)
        clean.append({
            "internal_id": iid, "title": row["title"], "description": row["description"],
            "canonical_path": row["canonical_path"], "aliases": _strings(row["aliases"], f"concept {iid} aliases"),
            "title_history": _strings(row["title_history"], f"concept {iid} title_history"),
            "path_history": _strings(row["path_history"], f"concept {iid} path_history"),
            "resource_uris": _strings(row["resource_uris"], f"concept {iid} resource_uris"),
            "source_anchors": _strings(row["source_anchors"], f"concept {iid} source_anchors"),
            "status": row["status"], "merged_into": merged_into,
        })
    by_id = {x["internal_id"]: x for x in clean}
    for item in clean:
        if item["merged_into"] is not None and item["merged_into"] not in by_id:
            raise CompilationError(f"concept {item['internal_id']} merges into an unknown concept")
    return sorted(clean, key=lambda x: x["internal_id"])

def validate_summaries(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set(); clean=[]
    for index,row in enumerate(rows):
        if set(row) != SUMMARY_FIELDS: raise CompilationError(f"summary {index} schema mismatch")
        iid=row["internal_id"]
        if not isinstance(iid,str) or not iid or iid in seen: raise CompilationError(f"summary {index} has invalid or duplicate internal_id")
        seen.add(iid)
        if not isinstance(row["text"],str) or not row["text"].strip() or not isinstance(row["status"],str) or not row["status"]:
            raise CompilationError(f"summary {iid} is malformed")
        merged=_nullable_id(row["merged_into"],f"summary {iid} merged_into")
        if (row["status"]=="merged") != (merged is not None): raise CompilationError(f"summary {iid} merged status is inconsistent")
        clean.append({"internal_id":iid,"text":row["text"],"evidence_anchors":_strings(row["evidence_anchors"],f"summary {iid} evidence"),"status":row["status"],"merged_into":merged})
    by_id={x["internal_id"] for x in clean}
    for x in clean:
        if x["merged_into"] is not None and x["merged_into"] not in by_id: raise CompilationError(f"summary {x['internal_id']} merges into unknown summary")
    return sorted(clean,key=lambda x:x["internal_id"])

def validate_claims(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen:set[str]=set(); clean=[]
    for index,row in enumerate(rows):
        if set(row)!=CLAIM_FIELDS: raise CompilationError(f"claim {index} schema mismatch")
        iid=row["internal_id"]
        if not isinstance(iid,str) or not iid or iid in seen: raise CompilationError(f"claim {index} has invalid or duplicate internal_id")
        seen.add(iid)
        if not isinstance(row["statement"],str) or not row["statement"].strip() or not isinstance(row["status"],str) or not row["status"]:
            raise CompilationError(f"claim {iid} is malformed")
        merged=_nullable_id(row["merged_into"],f"claim {iid} merged_into")
        if (row["status"]=="merged") != (merged is not None): raise CompilationError(f"claim {iid} merged status is inconsistent")
        clean.append({
            "internal_id":iid,"statement":row["statement"],"evidence_anchors":_strings(row["evidence_anchors"],f"claim {iid} evidence"),
            "status":row["status"],"merged_into":merged,
            "contradicts":_strings(row["contradicts"],f"claim {iid} contradicts"),
            "contradicted_by":_strings(row["contradicted_by"],f"claim {iid} contradicted_by"),
            "supersedes":_strings(row["supersedes"],f"claim {iid} supersedes"),
            "superseded_by":_strings(row["superseded_by"],f"claim {iid} superseded_by"),
        })
    ids={x["internal_id"] for x in clean}
    for x in clean:
        for field in ("merged_into",):
            if x[field] is not None and x[field] not in ids: raise CompilationError(f"claim {x['internal_id']} references unknown claim")
        for field in ("contradicts","contradicted_by","supersedes","superseded_by"):
            unknown=[y for y in x[field] if y not in ids]
            if unknown: raise CompilationError(f"claim {x['internal_id']} {field} references unknown claims: {unknown}")
    return sorted(clean,key=lambda x:x["internal_id"])

def validate_relations(rows: list[dict[str, Any]], active_concept_ids: set[str]) -> list[dict[str, Any]]:
    seen:set[str]=set(); clean=[]
    for index,row in enumerate(rows):
        if set(row)!=RELATION_FIELDS: raise CompilationError(f"relation {index} schema mismatch")
        iid=row["internal_id"]
        if not isinstance(iid,str) or not iid or iid in seen: raise CompilationError(f"relation {index} has invalid or duplicate internal_id")
        seen.add(iid)
        if not isinstance(row["predicate"],str) or not row["predicate"].strip() or not isinstance(row["status"],str) or not row["status"]:
            raise CompilationError(f"relation {iid} is malformed")
        merged=_nullable_id(row["merged_into"],f"relation {iid} merged_into")
        if (row["status"]=="merged") != (merged is not None): raise CompilationError(f"relation {iid} merged status is inconsistent")
        if row["status"]!="merged" and (row["subject_internal_id"] not in active_concept_ids or row["object_internal_id"] not in active_concept_ids):
            raise CompilationError(f"active relation {iid} references an inactive/unknown concept")
        clean.append({
            "internal_id":iid,"subject_internal_id":row["subject_internal_id"],"predicate":row["predicate"],"object_internal_id":row["object_internal_id"],
            "evidence_anchors":_strings(row["evidence_anchors"],f"relation {iid} evidence"),"status":row["status"],"merged_into":merged
        })
    ids={x["internal_id"] for x in clean}
    for x in clean:
        if x["merged_into"] is not None and x["merged_into"] not in ids: raise CompilationError(f"relation {x['internal_id']} merges into unknown relation")
    return sorted(clean,key=lambda x:x["internal_id"])

def resolution_catalog_projection(concepts: list[dict[str, Any]]) -> dict[str, Any]:
    rows=[]
    for c in concepts:
        if c["status"]=="merged": continue
        rows.append({k:c[k] for k in ("internal_id","title","description","canonical_path","aliases","title_history","path_history","resource_uris","source_anchors","status")})
    rows.sort(key=lambda x:x["internal_id"])
    return {"schema_version":"0.1","concepts":rows}

def planning_state_projection(claims: list[dict[str, Any]], relations: list[dict[str, Any]]) -> dict[str, Any]:
    c=[{"internal_id":x["internal_id"],"statement":x["statement"],"evidence_anchors":x["evidence_anchors"],"status":x["status"]} for x in claims if x["status"]!="merged"]
    r=[{"internal_id":x["internal_id"],"subject_internal_id":x["subject_internal_id"],"predicate":x["predicate"],"object_internal_id":x["object_internal_id"],"evidence_anchors":x["evidence_anchors"],"status":x["status"]} for x in relations if x["status"]!="merged"]
    c.sort(key=lambda x:x["internal_id"]); r.sort(key=lambda x:x["internal_id"])
    return {"schema_version":"0.1","claims":c,"relations":r}

def identity_registry(concepts: list[dict[str,Any]], summaries: list[dict[str,Any]], claims: list[dict[str,Any]], relations: list[dict[str,Any]]) -> dict[str,Any]:
    entries=[]
    for typ,rows in (("concept",concepts),("summary",summaries),("claim",claims),("relation",relations)):
        for row in rows:
            item={"internal_id":row["internal_id"],"object_type":typ,"status":row["status"],"merged_into":row["merged_into"]}
            if typ=="concept": item["canonical_path"]=row["canonical_path"]
            else: item["canonical_path"]=None
            entries.append(item)
    entries.sort(key=lambda x:(x["object_type"],x["internal_id"]))
    return {"schema_version":REGISTRY_SCHEMA_VERSION,"entries":entries}

def bootstrap_from_projections(catalog: Mapping[str,Any], planning_state: Mapping[str,Any]) -> dict[str,Any]:
    concepts=[{
        "internal_id":c["internal_id"],"title":c["title"],"description":c["description"],"canonical_path":c["canonical_path"],
        "aliases":list(c["aliases"]),"title_history":list(c["title_history"]),"path_history":list(c["path_history"]),
        "resource_uris":list(c["resource_uris"]),"source_anchors":list(c["source_anchors"]),"status":c["status"],"merged_into":None
    } for c in catalog["concepts"]]
    claims=[{
        "internal_id":q["internal_id"],"statement":q["statement"],"evidence_anchors":list(q["evidence_anchors"]),"status":q["status"],"merged_into":None,
        "contradicts":[],"contradicted_by":[],"supersedes":[],"superseded_by":[]
    } for q in planning_state["claims"]]
    relations=[{
        "internal_id":r["internal_id"],"subject_internal_id":r["subject_internal_id"],"predicate":r["predicate"],"object_internal_id":r["object_internal_id"],
        "evidence_anchors":list(r["evidence_anchors"]),"status":r["status"],"merged_into":None
    } for r in planning_state["relations"]]
    return {"concepts":concepts,"summaries":[],"claims":claims,"relations":relations,"events":[],"applied_plan_run_ids":[]}

def event_row(plan_run_id:str, operation:Mapping[str,Any], result_ids:list[str]) -> dict[str,Any]:
    snapshot=dict(operation)
    descriptor={"plan_run_id":plan_run_id,"operation":snapshot,"result_internal_ids":result_ids}
    event_id="event-sha256-"+hashlib.sha256(canonical_json_bytes(descriptor)).hexdigest()
    return {
        "event_id":event_id,"plan_run_id":plan_run_id,"operation_id":operation["operation_id"],"operation":operation["operation"],
        "object_type":operation["object_type"],"candidate_ids":list(operation["candidate_ids"]),"target_internal_ids":list(operation["target_internal_ids"]),
        "result_internal_ids":list(result_ids),"evidence_anchors":list(operation["evidence_anchors"]),"reason":operation["reason"],"operation_snapshot":snapshot
    }

def validate_events(rows:list[dict[str,Any]])->list[dict[str,Any]]:
    seen=set(); out=[]
    for i,row in enumerate(rows):
        if set(row)!=EVENT_FIELDS: raise CompilationError(f"event {i} schema mismatch")
        if not isinstance(row["event_id"],str) or not row["event_id"] or row["event_id"] in seen: raise CompilationError(f"event {i} invalid/duplicate id")
        seen.add(row["event_id"])
        for field in ("plan_run_id","operation_id","operation","object_type","reason"):
            if not isinstance(row[field],str) or not row[field]: raise CompilationError(f"event {row['event_id']} field {field} malformed")
        for field in ("candidate_ids","target_internal_ids","result_internal_ids","evidence_anchors"):
            _strings(row[field],f"event {row['event_id']} {field}")
        if not isinstance(row["operation_snapshot"],dict): raise CompilationError(f"event {row['event_id']} snapshot malformed")
        out.append(dict(row))
    return out
