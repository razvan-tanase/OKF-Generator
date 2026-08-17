from __future__ import annotations
from typing import Any, Mapping
from .canonical_state import final_internal_id
from .compilation_errors import CompilationError

ALLOWED_BY_OBJECT={
    "concept":{"create","update","merge","ignore"},
    "summary":{"create","merge","ignore"},
    "claim":{"create","update","merge","contradict","supersede","ignore"},
    "relation":{"create","update","merge","ignore"},
}

def index_rows(rows:list[dict[str,Any]])->dict[str,dict[str,Any]]:
    return {x["internal_id"]:x for x in rows}

def payload_keys(operation:Mapping[str,Any], expected:set[str])->None:
    if set(operation["payload"])!=expected:
        raise CompilationError(f"{operation['operation_id']} {operation['object_type']} payload schema mismatch")

def require_target(by_id:Mapping[str,dict[str,Any]], internal_id:str, op_id:str)->dict[str,Any]:
    if internal_id not in by_id: raise CompilationError(f"{op_id} references unknown target identity {internal_id}")
    if by_id[internal_id]["status"]=="merged": raise CompilationError(f"{op_id} targets already-merged identity {internal_id}")
    return by_id[internal_id]

def replace_list_ids(values:list[str], replacements:Mapping[str,str])->list[str]:
    out=[]
    for value in values:
        mapped=replacements.get(value,value)
        if mapped not in out: out.append(mapped)
    return out

def allocate(operations:list[dict[str,Any]],existing_ids:set[str])->dict[str,str]:
    mapping:dict[str,str]={}
    for op in operations:
        if op["operation"] in {"create","contradict","supersede"}:
            provisional=op["provisional_internal_id"]
            if not isinstance(provisional,str) or not provisional:
                raise CompilationError(f"{op['operation_id']} requires a provisional_internal_id")
            if provisional in mapping: raise CompilationError(f"duplicate provisional identity: {provisional}")
            final=final_internal_id(op["object_type"],provisional)
            if final in existing_ids or final in mapping.values(): raise CompilationError(f"final identity collision for {op['operation_id']}")
            mapping[provisional]=final
    return mapping

def translate(value:str|None,mapping:Mapping[str,str])->str|None:
    return mapping.get(value,value) if value is not None else None
