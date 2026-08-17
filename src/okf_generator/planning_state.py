from __future__ import annotations
import hashlib, json, unicodedata
from pathlib import Path
from typing import Any
from .planning_errors import PlanningError
from .planning_io import canonical_json_bytes
from .resolution_catalog import normalize_label

PLANNING_STATE_SCHEMA_VERSION = '0.1'

def _strings(value: Any, label: str, *, allow_empty: bool = True) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise PlanningError(f'{label} must be an array of non-empty strings')
    if len(set(value)) != len(value):
        raise PlanningError(f'{label} contains duplicate values')
    if not allow_empty and not value:
        raise PlanningError(f'{label} must not be empty')
    return [unicodedata.normalize('NFC', item) for item in value]

def empty_planning_state() -> dict[str, Any]:
    return {'schema_version': PLANNING_STATE_SCHEMA_VERSION, 'claims': [], 'relations': []}

def validate_planning_state(value: Any, concept_ids: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {'schema_version', 'claims', 'relations'}:
        raise PlanningError('planning state must contain exactly schema_version, claims, and relations')
    if value.get('schema_version') != PLANNING_STATE_SCHEMA_VERSION:
        raise PlanningError(f"unsupported planning state schema: {value.get('schema_version')!r}")
    claims = value.get('claims'); relations = value.get('relations')
    if not isinstance(claims, list) or not isinstance(relations, list):
        raise PlanningError('planning state claims and relations must be arrays')
    clean_claims=[]; seen_ids=set(); seen_claim_statements=set()
    claim_fields={'internal_id','statement','evidence_anchors','status'}
    for index,item in enumerate(claims):
        if not isinstance(item,dict) or set(item)!=claim_fields:
            raise PlanningError(f'planning claim {index} schema mismatch')
        internal_id=item['internal_id']; statement=item['statement']; status=item['status']
        if not isinstance(internal_id,str) or not internal_id or internal_id in seen_ids:
            raise PlanningError(f'planning claim {index} has invalid or duplicate internal_id')
        if not isinstance(statement,str) or not statement.strip() or not isinstance(status,str) or not status:
            raise PlanningError(f'planning claim {internal_id} is malformed')
        seen_ids.add(internal_id)
        clean_claims.append({'internal_id':internal_id,'statement':unicodedata.normalize('NFC',statement),'evidence_anchors':_strings(item['evidence_anchors'],f'planning claim {internal_id} evidence_anchors'),'status':unicodedata.normalize('NFC',status)})
    relation_fields={'internal_id','subject_internal_id','predicate','object_internal_id','evidence_anchors','status'}
    clean_relations=[]
    for index,item in enumerate(relations):
        if not isinstance(item,dict) or set(item)!=relation_fields:
            raise PlanningError(f'planning relation {index} schema mismatch')
        internal_id=item['internal_id']; subject=item['subject_internal_id']; obj=item['object_internal_id']; predicate=item['predicate']; status=item['status']
        if not isinstance(internal_id,str) or not internal_id or internal_id in seen_ids:
            raise PlanningError(f'planning relation {index} has invalid or duplicate internal_id')
        if subject not in concept_ids or obj not in concept_ids:
            raise PlanningError(f'planning relation {internal_id} references an unknown concept identity')
        if not isinstance(predicate,str) or not predicate.strip() or not isinstance(status,str) or not status:
            raise PlanningError(f'planning relation {internal_id} is malformed')
        seen_ids.add(internal_id)
        clean_relations.append({'internal_id':internal_id,'subject_internal_id':subject,'predicate':unicodedata.normalize('NFC',predicate),'object_internal_id':obj,'evidence_anchors':_strings(item['evidence_anchors'],f'planning relation {internal_id} evidence_anchors'),'status':unicodedata.normalize('NFC',status)})
    clean_claims.sort(key=lambda item:item['internal_id']); clean_relations.sort(key=lambda item:item['internal_id'])
    return {'schema_version':PLANNING_STATE_SCHEMA_VERSION,'claims':clean_claims,'relations':clean_relations}

def load_planning_state(path: Path | None, concept_ids: set[str]) -> tuple[dict[str, Any], str, str | None, str]:
    if path is None:
        state=empty_planning_state(); canonical=canonical_json_bytes(state)
        return state,'empty',None,hashlib.sha256(canonical).hexdigest()
    if not path.is_file(): raise PlanningError(f'planning state is missing: {path}')
    raw=path.read_bytes(); source_sha=hashlib.sha256(raw).hexdigest()
    try: value=json.loads(raw.decode('utf-8'))
    except (UnicodeDecodeError,json.JSONDecodeError) as exc: raise PlanningError('planning state is unreadable JSON') from exc
    state=validate_planning_state(value,concept_ids)
    canonical_sha=hashlib.sha256(canonical_json_bytes(state)).hexdigest()
    return state,'file',source_sha,canonical_sha

def claim_key(statement: str) -> str:
    return normalize_label(statement)

def relation_key(subject: str, predicate: str, obj: str) -> tuple[str,str,str]:
    return subject, normalize_label(predicate), obj
