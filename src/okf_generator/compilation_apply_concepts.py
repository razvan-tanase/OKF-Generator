from __future__ import annotations
from typing import Any, Mapping
from .canonical_state import union_strings
from .compilation_errors import CompilationError
from .compilation_apply_common import index_rows, payload_keys, require_target
from .resolution_catalog import normalize_path_key

def apply_concept(op:Mapping[str,Any], concepts:list[dict[str,Any]], relations:list[dict[str,Any]], targets:list[str], survivor:str|None, provisional:Mapping[str,str])->list[str]:
    oid=op["operation_id"]; action=op["operation"]
    by=index_rows(concepts); payload_keys(op,{"name","description"})
    if action=="create":
        iid=provisional[op["provisional_internal_id"]]; path=op["proposed_canonical_path"]
        if not isinstance(path,str) or not path: raise CompilationError(f"{oid} concept create requires proposed_canonical_path")
        used={normalize_path_key(p) for c in concepts for p in [c["canonical_path"],*c["path_history"]]}
        if normalize_path_key(path) in used: raise CompilationError(f"{oid} proposed concept path collides with canonical/history path")
        concepts.append({"internal_id":iid,"title":op["payload"]["name"],"description":op["payload"]["description"],"canonical_path":path,
                         "aliases":[],"title_history":[],"path_history":[],"resource_uris":[],"source_anchors":list(op["evidence_anchors"]),
                         "status":"active","merged_into":None})
        return [iid]
    if action=="update":
        if len(targets)!=1 or survivor not in {None,targets[0]}: raise CompilationError(f"{oid} concept update requires one target")
        item=require_target(by,targets[0],oid); old=item["title"]; new=op["payload"]["name"]
        if old!=new: item["title_history"]=union_strings(item["title_history"],[old]); item["title"]=new
        item["description"]=op["payload"]["description"]; item["source_anchors"]=union_strings(item["source_anchors"],op["evidence_anchors"])
        return [item["internal_id"]]
    if action=="merge":
        if not targets or survivor is None or survivor not in targets: raise CompilationError(f"{oid} concept merge requires targets and survivor")
        s=require_target(by,survivor,oid); losers=[t for t in targets if t!=survivor]
        for lid in losers:
            loser=require_target(by,lid,oid)
            s["aliases"]=union_strings(s["aliases"],loser["aliases"],[loser["title"]])
            s["title_history"]=union_strings(s["title_history"],loser["title_history"])
            s["path_history"]=union_strings(s["path_history"],[loser["canonical_path"]],loser["path_history"])
            s["resource_uris"]=union_strings(s["resource_uris"],loser["resource_uris"])
            s["source_anchors"]=union_strings(s["source_anchors"],loser["source_anchors"])
            loser["status"]="merged"; loser["merged_into"]=survivor
        old=s["title"]; new=op["payload"]["name"]
        if old!=new: s["title_history"]=union_strings(s["title_history"],[old]); s["title"]=new
        s["description"]=op["payload"]["description"]; s["source_anchors"]=union_strings(s["source_anchors"],op["evidence_anchors"])
        replacements={x:survivor for x in losers}
        for rel in relations:
            if rel["status"]!="merged":
                rel["subject_internal_id"]=replacements.get(rel["subject_internal_id"],rel["subject_internal_id"])
                rel["object_internal_id"]=replacements.get(rel["object_internal_id"],rel["object_internal_id"])
        return [survivor]
    raise CompilationError(f"{oid} unsupported concept action {action}")

def apply_summary(op:Mapping[str,Any], summaries:list[dict[str,Any]], targets:list[str], survivor:str|None, provisional:Mapping[str,str])->list[str]:
    oid=op["operation_id"]; action=op["operation"]
    by=index_rows(summaries); payload_keys(op,{"text"})
    if action=="create":
        iid=provisional[op["provisional_internal_id"]]
        summaries.append({"internal_id":iid,"text":op["payload"]["text"],"evidence_anchors":list(op["evidence_anchors"]),"status":"active","merged_into":None})
        return [iid]
    if action=="merge":
        if not targets or survivor is None or survivor not in targets: raise CompilationError(f"{oid} summary merge requires targets and survivor")
        s=require_target(by,survivor,oid)
        for lid in [x for x in targets if x!=survivor]:
            loser=require_target(by,lid,oid); s["evidence_anchors"]=union_strings(s["evidence_anchors"],loser["evidence_anchors"]); loser["status"]="merged"; loser["merged_into"]=survivor
        s["text"]=op["payload"]["text"]; s["evidence_anchors"]=union_strings(s["evidence_anchors"],op["evidence_anchors"])
        return [survivor]
    raise CompilationError(f"{oid} unsupported summary action {action}")
