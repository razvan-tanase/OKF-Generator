from __future__ import annotations
from typing import Any, Mapping
from .canonical_state import union_strings
from .compilation_errors import CompilationError
from .compilation_apply_common import index_rows, payload_keys, require_target, translate

def apply_relation(op:Mapping[str,Any], relations:list[dict[str,Any]], concepts:list[dict[str,Any]], targets:list[str], survivor:str|None, provisional:Mapping[str,str])->list[str]:
    oid=op["operation_id"]; action=op["operation"]
    by=index_rows(relations); payload_keys(op,{"subject_internal_id","predicate","object_internal_id"})
    payload=dict(op["payload"])
    payload["subject_internal_id"]=translate(payload["subject_internal_id"],provisional)
    payload["object_internal_id"]=translate(payload["object_internal_id"],provisional)
    active_concepts={x["internal_id"] for x in concepts if x["status"]!="merged"}
    if payload["subject_internal_id"] not in active_concepts or payload["object_internal_id"] not in active_concepts:
        raise CompilationError(f"{oid} relation endpoints do not resolve to active concepts")
    if action=="create":
        iid=provisional[op["provisional_internal_id"]]
        relations.append({"internal_id":iid,**payload,"evidence_anchors":list(op["evidence_anchors"]),"status":"active","merged_into":None})
        return [iid]
    if action=="update":
        if len(targets)!=1 or survivor not in {None,targets[0]}: raise CompilationError(f"{oid} relation update requires one target")
        r=require_target(by,targets[0],oid); r.update(payload); r["evidence_anchors"]=union_strings(r["evidence_anchors"],op["evidence_anchors"])
        return [r["internal_id"]]
    if action=="merge":
        if not targets or survivor is None or survivor not in targets: raise CompilationError(f"{oid} relation merge requires targets and survivor")
        s=require_target(by,survivor,oid)
        for lid in [x for x in targets if x!=survivor]:
            loser=require_target(by,lid,oid); s["evidence_anchors"]=union_strings(s["evidence_anchors"],loser["evidence_anchors"]); loser["status"]="merged"; loser["merged_into"]=survivor
        s.update(payload); s["evidence_anchors"]=union_strings(s["evidence_anchors"],op["evidence_anchors"])
        return [survivor]
    raise CompilationError(f"{oid} unsupported relation action {action}")
