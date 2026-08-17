from __future__ import annotations
import hashlib, json, unicodedata
from pathlib import Path
from typing import Any
from .planning_errors import PlanningError
from .planning_io import canonical_json_bytes

DECISION_SCHEMA_VERSION='0.1'
DECISION_ACTIONS={'update','merge','contradict','supersede','ignore'}

def empty_decisions()->dict[str,Any]:
    return {'schema_version':DECISION_SCHEMA_VERSION,'decisions':[]}

def validate_decisions(value:Any)->dict[str,Any]:
    if not isinstance(value,dict) or set(value)!={'schema_version','decisions'}:
        raise PlanningError('decision ledger must contain exactly schema_version and decisions')
    if value.get('schema_version')!=DECISION_SCHEMA_VERSION:
        raise PlanningError(f"unsupported decision ledger schema: {value.get('schema_version')!r}")
    rows=value.get('decisions')
    if not isinstance(rows,list): raise PlanningError('decision ledger decisions must be an array')
    fields={'candidate_id','action','target_internal_ids','survivor_internal_id','reason'}
    clean=[]; seen=set()
    for index,item in enumerate(rows):
        if not isinstance(item,dict) or set(item)!=fields: raise PlanningError(f'decision {index} schema mismatch')
        cid=item['candidate_id']; action=item['action']; targets=item['target_internal_ids']; survivor=item['survivor_internal_id']; reason=item['reason']
        if not isinstance(cid,str) or not cid or cid in seen: raise PlanningError(f'decision {index} has invalid or duplicate candidate_id')
        if action not in DECISION_ACTIONS: raise PlanningError(f'decision {cid} has unsupported action')
        if not isinstance(targets,list) or not all(isinstance(x,str) and x for x in targets) or len(set(targets))!=len(targets): raise PlanningError(f'decision {cid} target_internal_ids is malformed')
        if survivor is not None and (not isinstance(survivor,str) or not survivor): raise PlanningError(f'decision {cid} survivor_internal_id is malformed')
        if not isinstance(reason,str) or not reason.strip(): raise PlanningError(f'decision {cid} reason must be non-empty')
        if survivor is not None and survivor not in targets: raise PlanningError(f'decision {cid} survivor must be one of target_internal_ids')
        seen.add(cid); clean.append({'candidate_id':cid,'action':action,'target_internal_ids':list(targets),'survivor_internal_id':survivor,'reason':unicodedata.normalize('NFC',reason)})
    clean.sort(key=lambda item:item['candidate_id'])
    return {'schema_version':DECISION_SCHEMA_VERSION,'decisions':clean}

def load_decisions(path:Path|None)->tuple[dict[str,Any],str,str|None,str]:
    if path is None:
        ledger=empty_decisions(); canonical=canonical_json_bytes(ledger)
        return ledger,'empty',None,hashlib.sha256(canonical).hexdigest()
    if not path.is_file(): raise PlanningError(f'decision ledger is missing: {path}')
    raw=path.read_bytes(); source_sha=hashlib.sha256(raw).hexdigest()
    try: value=json.loads(raw.decode('utf-8'))
    except (UnicodeDecodeError,json.JSONDecodeError) as exc: raise PlanningError('decision ledger is unreadable JSON') from exc
    ledger=validate_decisions(value); canonical_sha=hashlib.sha256(canonical_json_bytes(ledger)).hexdigest()
    return ledger,'file',source_sha,canonical_sha

def decision_index(ledger:dict[str,Any])->dict[str,dict[str,Any]]:
    return {item['candidate_id']:item for item in ledger['decisions']}
