from __future__ import annotations
import hashlib, json, re
from pathlib import Path
from typing import Any, Mapping
from .planning_errors import PlanningError
from .planning_io import canonical_json_bytes, load_json, load_jsonl, sha256_file
from .resolution_catalog import validate_catalog
from .resolution_upstream import load_verified_synthesis, synthesis_run_dir

RESOLUTION_RUN_RE=re.compile(r'^sha256-[0-9a-f]{64}$')
RESOLUTION_FIELDS={'candidate_id','candidate_name','status','method','resolved_internal_id','considered_internal_ids','evidence_anchors','signals'}

def resolution_run_dir(root:Path, source_id:str, snapshot_id:str, ruleset:str, extraction_profile:str,
                       normalization_profile:str, synthesis_profile:str, synthesis_provider:str,
                       synthesis_run_id:str, resolution_profile:str, resolution_run_id:str)->Path:
    return root/source_id/snapshot_id/ruleset/extraction_profile/normalization_profile/synthesis_profile/synthesis_provider/synthesis_run_id/resolution_profile/resolution_run_id

def _validate_resolutions(rows:list[dict[str,Any]], concept_candidates:list[dict[str,Any]], expected_counts:Mapping[str,Any])->list[dict[str,Any]]:
    candidates={item['candidate_id']:item for item in concept_candidates}; seen=set(); counts={'matched':0,'new':0,'ambiguous':0}
    if set(expected_counts)!={'matched','new','ambiguous'}: raise PlanningError('Stage 07 resolution_counts is malformed')
    for index,row in enumerate(rows):
        if set(row)!=RESOLUTION_FIELDS: raise PlanningError(f'Stage 07 resolution {index} schema mismatch')
        cid=row['candidate_id']; status=row['status']; resolved=row['resolved_internal_id']; considered=row['considered_internal_ids']
        if cid not in candidates or cid in seen: raise PlanningError(f'Stage 07 resolution {index} has unknown or duplicate candidate_id')
        if row['candidate_name']!=candidates[cid]['name']: raise PlanningError(f'Stage 07 resolution {cid} candidate_name mismatch')
        if status not in counts: raise PlanningError(f'Stage 07 resolution {cid} has unsupported status')
        if not isinstance(row['method'],str) or not row['method']: raise PlanningError(f'Stage 07 resolution {cid} method is malformed')
        if not isinstance(considered,list) or not all(isinstance(x,str) and x for x in considered) or len(set(considered))!=len(considered): raise PlanningError(f'Stage 07 resolution {cid} considered_internal_ids is malformed')
        if not isinstance(row['evidence_anchors'],list) or row['evidence_anchors']!=candidates[cid]['evidence_anchors']: raise PlanningError(f'Stage 07 resolution {cid} evidence mismatch')
        if not isinstance(row['signals'],list): raise PlanningError(f'Stage 07 resolution {cid} signals is malformed')
        if status=='matched':
            if not isinstance(resolved,str) or not resolved or resolved not in considered: raise PlanningError(f'Stage 07 matched resolution {cid} lacks a considered target')
        elif resolved is not None:
            raise PlanningError(f'Stage 07 non-matched resolution {cid} must not have a resolved target')
        seen.add(cid); counts[status]+=1
    if seen!=set(candidates): raise PlanningError('Stage 07 resolutions do not cover every concept candidate')
    if dict(expected_counts)!=counts: raise PlanningError(f'Stage 07 resolution_counts mismatch: expected {dict(expected_counts)}, actual {counts}')
    return rows

def rederive_resolution_run_id(manifest:Mapping[str,Any])->str:
    fields=['profile','synthesis_manifest_sha256','synthesis_candidates_sha256','catalog_source_sha256','catalog_canonical_sha256','similarity_threshold','shortlist_limit','adjudication_provider','adjudication_model','resolutions_sha256','adjudication_requests_sha256','adjudication_responses_sha256','adjudication_receipts_sha256']
    missing=[field for field in fields if field not in manifest]
    if missing: raise PlanningError(f'Stage 07 resolution manifest is missing run identity fields: {missing}')
    descriptor={field:manifest[field] for field in fields}
    return 'sha256-'+hashlib.sha256(canonical_json_bytes(descriptor)).hexdigest()

def load_verified_resolution(resolution_dir:Path, synthesis_root:Path, expected:Mapping[str,str]):
    manifest_path=resolution_dir/'resolution.json'; manifest=load_json(manifest_path,'Stage 07 resolution manifest')
    identities={'stage':'07-resolve','source_id':expected['source_id'],'snapshot_id':expected['snapshot_id'],'classification_ruleset':expected['ruleset'],'extraction_profile':expected['extraction_profile'],'normalization_profile':expected['normalization_profile'],'synthesis_profile':expected['synthesis_profile'],'synthesis_provider':expected['synthesis_provider'],'synthesis_run_id':expected['synthesis_run_id'],'profile':expected['resolution_profile'],'run_id':expected['resolution_run_id']}
    for field,value in identities.items():
        if manifest.get(field)!=value: raise PlanningError(f'Stage 07 resolution identity mismatch for {field}')
    if manifest.get('schema_version')!='0.1' or not RESOLUTION_RUN_RE.fullmatch(expected['resolution_run_id']): raise PlanningError('unsupported or invalid Stage 07 resolution identity')
    expected_paths={'catalog':'catalog.json','resolutions':'resolutions.jsonl','adjudication_requests':'adjudication-requests.jsonl','adjudication_responses':'adjudication-responses.jsonl','adjudication_receipts':'adjudication-receipts.jsonl'}
    for name,path_name in expected_paths.items():
        field=name+'_path'; hash_field=name+'_sha256' if name!='catalog' else None
        if manifest.get(field)!=path_name: raise PlanningError(f'Stage 07 {field} is unexpected')
        if hash_field and manifest.get(hash_field)!=sha256_file(resolution_dir/path_name): raise PlanningError(f'Stage 07 {name} hash mismatch')
    catalog_raw=load_json(resolution_dir/'catalog.json','Stage 07 catalog snapshot')
    try:
        catalog=validate_catalog(catalog_raw)
    except Exception as exc:
        raise PlanningError(f'Stage 07 catalog snapshot is invalid: {exc}') from exc
    catalog_canonical_sha=hashlib.sha256(canonical_json_bytes(catalog)).hexdigest()
    if manifest.get('catalog_canonical_sha256')!=catalog_canonical_sha: raise PlanningError('Stage 07 catalog canonical hash mismatch')
    if rederive_resolution_run_id(manifest)!=expected['resolution_run_id']: raise PlanningError('Stage 07 resolution run_id does not match its content-addressed descriptor')
    synth_dir=synthesis_run_dir(synthesis_root, expected['source_id'],expected['snapshot_id'],expected['ruleset'],expected['extraction_profile'],expected['normalization_profile'],expected['synthesis_profile'],expected['synthesis_provider'],expected['synthesis_run_id'])
    synthesis_expected={'source_id':expected['source_id'],'snapshot_id':expected['snapshot_id'],'ruleset':expected['ruleset'],'extraction_profile':expected['extraction_profile'],'normalization_profile':expected['normalization_profile'],'synthesis_profile':expected['synthesis_profile'],'synthesis_provider':expected['synthesis_provider'],'run_id':expected['synthesis_run_id']}
    try:
        synthesis,candidates,synthesis_manifest_sha,synthesis_candidates_sha=load_verified_synthesis(synth_dir,synthesis_expected)
    except Exception as exc:
        raise PlanningError(f'Stage 06 synthesis verification failed: {exc}') from exc
    if manifest.get('synthesis_manifest_sha256')!=synthesis_manifest_sha or manifest.get('synthesis_candidates_sha256')!=synthesis_candidates_sha: raise PlanningError('Stage 07 does not bind the verified Stage 06 synthesis')
    rows=load_jsonl(resolution_dir/'resolutions.jsonl','Stage 07 resolutions')
    concepts=[item for item in candidates if item['candidate_type']=='concept']
    _validate_resolutions(rows,concepts,manifest.get('resolution_counts',{}))
    return manifest,rows,catalog,synthesis,candidates,sha256_file(manifest_path),sha256_file(resolution_dir/'resolutions.jsonl'),synthesis_candidates_sha
