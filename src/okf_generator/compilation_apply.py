from __future__ import annotations
import copy
from typing import Any
from .canonical_state import event_row, union_strings
from .compilation_errors import CompilationError
from .compilation_apply_common import ALLOWED_BY_OBJECT, allocate, translate
from .compilation_apply_concepts import apply_concept, apply_summary
from .compilation_apply_claims import apply_claim
from .compilation_apply_relations import apply_relation

def apply_operations(base:dict[str,Any],operations:list[dict[str,Any]],plan_run_id:str)->dict[str,Any]:
    state=copy.deepcopy(base)
    concepts=state["concepts"]; summaries=state["summaries"]; claims=state["claims"]; relations=state["relations"]; events=state["events"]
    all_existing={x["internal_id"] for rows in (concepts,summaries,claims,relations) for x in rows}
    provisional=allocate(operations,all_existing)
    completed:set[str]=set()
    for op in operations:
        oid=op["operation_id"]; action=op["operation"]; typ=op["object_type"]
        if action not in ALLOWED_BY_OBJECT[typ]: raise CompilationError(f"{oid} action {action} is invalid for {typ}")
        if any(dep not in completed for dep in op["dependencies"]): raise CompilationError(f"{oid} dependency is not satisfied")
        targets=[translate(x,provisional) for x in op["target_internal_ids"]]
        survivor=translate(op["survivor_internal_id"],provisional)
        result_ids:list[str]=[]
        if action=="ignore":
            if op["provisional_internal_id"] is not None: raise CompilationError(f"{oid} ignore must not allocate identity")
        elif typ=="concept": result_ids=apply_concept(op,concepts,relations,targets,survivor,provisional)
        elif typ=="summary": result_ids=apply_summary(op,summaries,targets,survivor,provisional)
        elif typ=="claim": result_ids=apply_claim(op,claims,targets,survivor,provisional)
        elif typ=="relation": result_ids=apply_relation(op,relations,concepts,targets,survivor,provisional)
        events.append(event_row(plan_run_id,op,result_ids)); completed.add(oid)
    state["applied_plan_run_ids"]=union_strings(state["applied_plan_run_ids"],[plan_run_id])
    return state

__all__=["apply_operations"]
