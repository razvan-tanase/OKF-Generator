from __future__ import annotations
from typing import Any, Mapping
from .canonical_state import union_strings
from .compilation_errors import CompilationError
from .compilation_apply_common import index_rows, payload_keys, replace_list_ids, require_target

def apply_claim(op:Mapping[str,Any], claims:list[dict[str,Any]], targets:list[str], survivor:str|None, provisional:Mapping[str,str])->list[str]:
    oid=op["operation_id"]; action=op["operation"]
    by=index_rows(claims); payload_keys(op,{"statement"})
    if action=="create":
        iid=provisional[op["provisional_internal_id"]]
        claims.append({"internal_id":iid,"statement":op["payload"]["statement"],"evidence_anchors":list(op["evidence_anchors"]),"status":"active","merged_into":None,
                       "contradicts":[],"contradicted_by":[],"supersedes":[],"superseded_by":[]})
        return [iid]
    if action=="update":
        if len(targets)!=1 or survivor not in {None,targets[0]}: raise CompilationError(f"{oid} claim update requires one target")
        q=require_target(by,targets[0],oid); q["statement"]=op["payload"]["statement"]; q["evidence_anchors"]=union_strings(q["evidence_anchors"],op["evidence_anchors"])
        return [q["internal_id"]]
    if action=="merge":
        if not targets or survivor is None or survivor not in targets: raise CompilationError(f"{oid} claim merge requires targets and survivor")
        s=require_target(by,survivor,oid); losers=[x for x in targets if x!=survivor]
        for lid in losers:
            loser=require_target(by,lid,oid)
            for field in ("evidence_anchors","contradicts","contradicted_by","supersedes","superseded_by"):
                s[field]=union_strings(s[field],loser[field])
            loser["status"]="merged"; loser["merged_into"]=survivor
        replacements={x:survivor for x in losers}
        for q in claims:
            for field in ("contradicts","contradicted_by","supersedes","superseded_by"):
                q[field]=[x for x in replace_list_ids(q[field],replacements) if x!=q["internal_id"]]
        s["statement"]=op["payload"]["statement"]; s["evidence_anchors"]=union_strings(s["evidence_anchors"],op["evidence_anchors"])
        return [survivor]
    if action in {"contradict","supersede"}:
        if len(targets)!=1 or survivor is not None: raise CompilationError(f"{oid} {action} requires one target and no survivor")
        target=require_target(by,targets[0],oid); iid=provisional[op["provisional_internal_id"]]
        q={"internal_id":iid,"statement":op["payload"]["statement"],"evidence_anchors":list(op["evidence_anchors"]),"status":"active","merged_into":None,
           "contradicts":[],"contradicted_by":[],"supersedes":[],"superseded_by":[]}
        if action=="contradict":
            q["contradicts"]=[target["internal_id"]]; target["contradicted_by"]=union_strings(target["contradicted_by"],[iid])
        else:
            q["supersedes"]=[target["internal_id"]]; target["superseded_by"]=union_strings(target["superseded_by"],[iid]); target["status"]="superseded"
        claims.append(q)
        return [iid]
    raise CompilationError(f"{oid} unsupported claim action {action}")
