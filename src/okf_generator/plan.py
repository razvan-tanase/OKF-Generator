from __future__ import annotations
import hashlib, json, re, unicodedata
from pathlib import Path
from typing import Any, Mapping
from .acquire import SOURCE_ID_RE
from .classify import RULESET_ID, SNAPSHOT_ID_RE
from .extract import PROFILE_ID as EXTRACTION_PROFILE_ID
from .normalize import PROFILE_ID as NORMALIZATION_PROFILE_ID
from .synthesize import PROFILE_ID as SYNTHESIS_PROFILE_ID, PROVIDER_RE
from .resolve import PROFILE_ID as RESOLUTION_PROFILE_ID
from .planning_decisions import decision_index, load_decisions
from .planning_errors import PlanningError
from .planning_identity import SLUG_BASIS, propose_concept_path, provisional_id
from .planning_io import canonical_json_bytes, jsonl, publish_run, sha256_file
from .planning_model import PlanningManifest
from .planning_state import claim_key, load_planning_state, relation_key
from .planning_upstream import RESOLUTION_RUN_RE, load_verified_resolution, resolution_run_dir
from .resolution_catalog import normalize_label, normalize_path_key

PROFILE_ID='builtin-v1'
PLANNING_RUN_RE=re.compile(r'^sha256-[0-9a-f]{64}$')
OPERATIONS=('create','update','merge','contradict','supersede','ignore')
OBJECTS=('concept','summary','claim','relation')

def _union_anchors(items:list[Mapping[str,Any]])->list[str]:
    seen=set(); out=[]
    for item in items:
        for anchor in item.get('evidence_anchors',[]):
            if anchor not in seen: seen.add(anchor); out.append(anchor)
    return out

def _fingerprint(object_type:str,payload:Mapping[str,Any])->str:
    return hashlib.sha256(canonical_json_bytes({'object_type':object_type,'payload':payload})).hexdigest()

class PlanningEngine:
    def __init__(self,
        synthesis_root:Path|str=Path('.okf-generator/syntheses'),
        resolution_root:Path|str=Path('.okf-generator/resolutions'),
        output_root:Path|str=Path('.okf-generator/plans'),*,
        ruleset:str=RULESET_ID, extraction_profile:str=EXTRACTION_PROFILE_ID,
        normalization_profile:str=NORMALIZATION_PROFILE_ID, synthesis_profile:str=SYNTHESIS_PROFILE_ID,
        resolution_profile:str=RESOLUTION_PROFILE_ID, profile:str=PROFILE_ID) -> None:
        if (ruleset,extraction_profile,normalization_profile,synthesis_profile,resolution_profile)!=(RULESET_ID,EXTRACTION_PROFILE_ID,NORMALIZATION_PROFILE_ID,SYNTHESIS_PROFILE_ID,RESOLUTION_PROFILE_ID):
            raise PlanningError('Stage 08 supports only the currently pinned upstream builtin-v1 profiles')
        if profile!=PROFILE_ID: raise PlanningError(f'unsupported planning profile: {profile}')
        self.synthesis_root=Path(synthesis_root); self.resolution_root=Path(resolution_root); self.output_root=Path(output_root)
        self.ruleset=ruleset; self.extraction_profile=extraction_profile; self.normalization_profile=normalization_profile
        self.synthesis_profile=synthesis_profile; self.resolution_profile=resolution_profile; self.profile=profile

    def _validate_identity(self,source_id:str,snapshot_id:str,synthesis_provider:str,synthesis_run_id:str,resolution_run_id:str)->None:
        if not SOURCE_ID_RE.fullmatch(source_id): raise PlanningError('source_id must match Stage 01 source identifier rules')
        if not SNAPSHOT_ID_RE.fullmatch(snapshot_id): raise PlanningError('snapshot_id must match Stage 02 content-addressed identifier rules')
        if not PROVIDER_RE.fullmatch(synthesis_provider): raise PlanningError('synthesis_provider is unsafe for planning paths')
        if not re.fullmatch(r'^sha256-[0-9a-f]{64}$',synthesis_run_id): raise PlanningError('synthesis_run_id must be content-addressed')
        if not RESOLUTION_RUN_RE.fullmatch(resolution_run_id): raise PlanningError('resolution_run_id must be content-addressed')

    def plan(self,source_id:str,snapshot_id:str,synthesis_run_id:str,resolution_run_id:str,*,synthesis_provider:str,
             planning_state_path:Path|str|None=None,decision_path:Path|str|None=None)->PlanningManifest:
        self._validate_identity(source_id,snapshot_id,synthesis_provider,synthesis_run_id,resolution_run_id)
        res_dir=resolution_run_dir(self.resolution_root,source_id,snapshot_id,self.ruleset,self.extraction_profile,self.normalization_profile,self.synthesis_profile,synthesis_provider,synthesis_run_id,self.resolution_profile,resolution_run_id)
        expected={'source_id':source_id,'snapshot_id':snapshot_id,'ruleset':self.ruleset,'extraction_profile':self.extraction_profile,'normalization_profile':self.normalization_profile,'synthesis_profile':self.synthesis_profile,'synthesis_provider':synthesis_provider,'synthesis_run_id':synthesis_run_id,'resolution_profile':self.resolution_profile,'resolution_run_id':resolution_run_id}
        resolution,resolutions,catalog,synthesis,candidates,res_manifest_sha,res_rows_sha,synth_candidates_sha=load_verified_resolution(res_dir,self.synthesis_root,expected)
        concept_ids={item['internal_id'] for item in catalog['concepts']}
        state_path=Path(planning_state_path) if planning_state_path is not None else None
        decisions_path=Path(decision_path) if decision_path is not None else None
        state,state_mode,state_source_sha,state_canonical_sha=load_planning_state(state_path,concept_ids)
        ledger,decision_mode,decision_source_sha,decision_canonical_sha=load_decisions(decisions_path)
        decisions=decision_index(ledger); candidate_by_id={item['candidate_id']:item for item in candidates}
        unknown=sorted(set(decisions)-set(candidate_by_id))
        if unknown: raise PlanningError(f'decision ledger references unknown candidates: {unknown}')
        resolution_by_id={item['candidate_id']:item for item in resolutions}
        catalog_by_id={item['internal_id']:item for item in catalog['concepts']}
        used_paths=set()
        for concept in catalog['concepts']:
            for path in [concept['canonical_path'],*concept.get('path_history',[])]: used_paths.add(normalize_path_key(path))
        claims_by_key:dict[str,list[dict[str,Any]]]={}
        claim_by_id={item['internal_id']:item for item in state['claims']}
        for item in state['claims']: claims_by_key.setdefault(claim_key(item['statement']),[]).append(item)
        relations_by_key:dict[tuple[str,str,str],list[dict[str,Any]]]={}
        relation_by_id={item['internal_id']:item for item in state['relations']}
        for item in state['relations']: relations_by_key.setdefault(relation_key(item['subject_internal_id'],item['predicate'],item['object_internal_id']),[]).append(item)

        operations:list[dict[str,Any]]=[]
        def add(operation:str,object_type:str,candidate_ids:list[str],target_ids:list[str],survivor:str|None,provisional:str|None,path:str|None,payload:dict[str,Any],anchors:list[str],deps:list[str],reason:str)->str:
            op_id=f'op{len(operations)+1:06d}'
            operations.append({'operation_id':op_id,'operation':operation,'object_type':object_type,'candidate_ids':candidate_ids,'target_internal_ids':target_ids,'survivor_internal_id':survivor,'provisional_internal_id':provisional,'proposed_canonical_path':path,'payload':payload,'evidence_anchors':anchors,'dependencies':deps,'reason':reason})
            return op_id

        concept_endpoint:dict[str,str|None]={}; concept_dependency:dict[str,str|None]={}; new_concept_fingerprints:dict[str,tuple[str,str]]={}
        for candidate in [x for x in candidates if x['candidate_type']=='concept']:
            cid=candidate['candidate_id']; row=resolution_by_id[cid]; decision=decisions.get(cid); payload={'name':candidate['name'],'description':candidate['description']}
            if decision is not None:
                action=decision['action']; targets=decision['target_internal_ids']; survivor=decision['survivor_internal_id']
                if action=='ignore':
                    if targets or survivor is not None: raise PlanningError(f'ignore decision {cid} must not name targets')
                    op=add('ignore','concept',[cid],[],None,None,None,payload,candidate['evidence_anchors'],[],decision['reason']); concept_endpoint[cid]=None; concept_dependency[cid]=op; continue
                if action!='merge': raise PlanningError(f'concept decision {cid} may only be merge or ignore')
                if row['status']!='ambiguous' or len(targets)<2 or survivor is None: raise PlanningError(f'concept merge decision {cid} requires an ambiguous resolution, at least two targets, and a survivor')
                if not set(targets).issubset(set(row['considered_internal_ids'])) or any(t not in catalog_by_id for t in targets): raise PlanningError(f'concept merge decision {cid} targets must be considered catalog identities')
                op=add('merge','concept',[cid],targets,survivor,None,None,payload,candidate['evidence_anchors'],[],decision['reason']); concept_endpoint[cid]=survivor; concept_dependency[cid]=op; continue
            if row['status']=='matched':
                target=row['resolved_internal_id']; op=add('update','concept',[cid],[target],target,None,None,payload,candidate['evidence_anchors'],[],'resolved-existing-concept'); concept_endpoint[cid]=target; concept_dependency[cid]=op
            elif row['status']=='ambiguous':
                op=add('ignore','concept',[cid],row['considered_internal_ids'],None,None,None,payload,candidate['evidence_anchors'],[],'identity-ambiguous'); concept_endpoint[cid]=None; concept_dependency[cid]=op
            else:
                semantic={'name':normalize_label(candidate['name']),'description':normalize_label(candidate['description'])}; fp=_fingerprint('concept',semantic)
                if fp in new_concept_fingerprints:
                    target,dep=new_concept_fingerprints[fp]; op=add('merge','concept',[cid],[target],target,None,None,payload,candidate['evidence_anchors'],[dep],'exact-new-concept-duplicate'); concept_endpoint[cid]=target; concept_dependency[cid]=op
                else:
                    descriptor={'synthesis_run_id':synthesis_run_id,'candidate_id':cid,'name':candidate['name'],'description':candidate['description'],'evidence_anchors':candidate['evidence_anchors']}
                    provisional=provisional_id('concept',descriptor); path=propose_concept_path(candidate['name'],descriptor,used_paths)
                    op=add('create','concept',[cid],[],provisional,provisional,path,payload,candidate['evidence_anchors'],[],'resolved-new-concept'); concept_endpoint[cid]=provisional; concept_dependency[cid]=op; new_concept_fingerprints[fp]=(provisional,op)

        new_summary:dict[str,tuple[str,str]]={}
        for candidate in [x for x in candidates if x['candidate_type']=='summary']:
            cid=candidate['candidate_id']; decision=decisions.get(cid); payload={'text':candidate['text']}
            if decision is not None:
                if decision['action']!='ignore' or decision['target_internal_ids'] or decision['survivor_internal_id'] is not None: raise PlanningError(f'summary decision {cid} may only ignore without targets')
                add('ignore','summary',[cid],[],None,None,None,payload,candidate['evidence_anchors'],[],decision['reason']); continue
            fp=_fingerprint('summary',{'text':normalize_label(candidate['text'])})
            if fp in new_summary:
                target,dep=new_summary[fp]; add('merge','summary',[cid],[target],target,None,None,payload,candidate['evidence_anchors'],[dep],'exact-new-summary-duplicate')
            else:
                descriptor={'synthesis_run_id':synthesis_run_id,'candidate_id':cid,'text':candidate['text'],'evidence_anchors':candidate['evidence_anchors']}; provisional=provisional_id('summary',descriptor)
                op=add('create','summary',[cid],[],provisional,provisional,None,payload,candidate['evidence_anchors'],[],'new-source-summary'); new_summary[fp]=(provisional,op)

        new_claims:dict[str,tuple[str,str]]={}
        for candidate in [x for x in candidates if x['candidate_type']=='claim']:
            cid=candidate['candidate_id']; decision=decisions.get(cid); payload={'statement':candidate['statement']}; key=claim_key(candidate['statement'])
            if decision is not None:
                action=decision['action']; targets=decision['target_internal_ids']; survivor=decision['survivor_internal_id']
                if action=='ignore':
                    if targets or survivor is not None: raise PlanningError(f'ignore decision {cid} must not name targets')
                    add('ignore','claim',[cid],[],None,None,None,payload,candidate['evidence_anchors'],[],decision['reason']); continue
                if action=='update':
                    if len(targets)!=1 or survivor not in {None,targets[0]} or targets[0] not in claim_by_id: raise PlanningError(f'claim update decision {cid} requires one existing claim target')
                    add('update','claim',[cid],targets,targets[0],None,None,payload,candidate['evidence_anchors'],[],decision['reason']); continue
                if action in {'contradict','supersede'}:
                    if len(targets)!=1 or survivor is not None or targets[0] not in claim_by_id: raise PlanningError(f'claim {action} decision {cid} requires one existing claim target and no survivor')
                    descriptor={'synthesis_run_id':synthesis_run_id,'candidate_id':cid,'statement':candidate['statement'],'evidence_anchors':candidate['evidence_anchors']}; provisional=provisional_id('claim',descriptor)
                    add(action,'claim',[cid],targets,None,provisional,None,payload,candidate['evidence_anchors'],[],decision['reason']); continue
                if action=='merge':
                    if len(targets)<2 or survivor is None or survivor not in targets or any(t not in claim_by_id for t in targets): raise PlanningError(f'claim merge decision {cid} requires existing claim targets and a survivor')
                    add('merge','claim',[cid],targets,survivor,None,None,payload,candidate['evidence_anchors'],[],decision['reason']); continue
            matches=claims_by_key.get(key,[])
            if len(matches)==1:
                target=matches[0]['internal_id']; add('update','claim',[cid],[target],target,None,None,payload,candidate['evidence_anchors'],[],'exact-existing-claim')
            elif len(matches)>1:
                add('ignore','claim',[cid],[x['internal_id'] for x in matches],None,None,None,payload,candidate['evidence_anchors'],[],'existing-claim-duplicate-ambiguous')
            elif key in new_claims:
                target,dep=new_claims[key]; add('merge','claim',[cid],[target],target,None,None,payload,candidate['evidence_anchors'],[dep],'exact-new-claim-duplicate')
            else:
                descriptor={'synthesis_run_id':synthesis_run_id,'candidate_id':cid,'statement':candidate['statement'],'evidence_anchors':candidate['evidence_anchors']}; provisional=provisional_id('claim',descriptor)
                op=add('create','claim',[cid],[],provisional,provisional,None,payload,candidate['evidence_anchors'],[],'new-claim'); new_claims[key]=(provisional,op)

        new_relations:dict[tuple[str,str,str],tuple[str,str]]={}
        for candidate in [x for x in candidates if x['candidate_type']=='relation']:
            cid=candidate['candidate_id']; decision=decisions.get(cid); subject=concept_endpoint.get(candidate['subject_candidate_id']); obj=concept_endpoint.get(candidate['object_candidate_id']); payload={'subject_internal_id':subject,'predicate':candidate['predicate'],'object_internal_id':obj}
            deps=[d for d in [concept_dependency.get(candidate['subject_candidate_id']),concept_dependency.get(candidate['object_candidate_id'])] if d]
            deps=list(dict.fromkeys(deps))
            if decision is not None and decision['action']=='ignore':
                if decision['target_internal_ids'] or decision['survivor_internal_id'] is not None: raise PlanningError(f'ignore decision {cid} must not name targets')
                add('ignore','relation',[cid],[],None,None,None,payload,candidate['evidence_anchors'],deps,decision['reason']); continue
            if subject is None or obj is None:
                if decision is not None: raise PlanningError(f'relation decision {cid} cannot override an unresolved endpoint')
                add('ignore','relation',[cid],[],None,None,None,payload,candidate['evidence_anchors'],deps,'relation-endpoint-unresolved'); continue
            key=relation_key(subject,candidate['predicate'],obj)
            if decision is not None:
                action=decision['action']; targets=decision['target_internal_ids']; survivor=decision['survivor_internal_id']
                if action=='update':
                    if len(targets)!=1 or survivor not in {None,targets[0]} or targets[0] not in relation_by_id: raise PlanningError(f'relation update decision {cid} requires one existing relation target')
                    add('update','relation',[cid],targets,targets[0],None,None,payload,candidate['evidence_anchors'],deps,decision['reason']); continue
                if action=='merge':
                    if len(targets)<2 or survivor is None or survivor not in targets or any(t not in relation_by_id for t in targets): raise PlanningError(f'relation merge decision {cid} requires existing relation targets and a survivor')
                    add('merge','relation',[cid],targets,survivor,None,None,payload,candidate['evidence_anchors'],deps,decision['reason']); continue
                raise PlanningError(f'relation decision {cid} may only update, merge, or ignore')
            matches=relations_by_key.get(key,[])
            if len(matches)==1:
                target=matches[0]['internal_id']; add('update','relation',[cid],[target],target,None,None,payload,candidate['evidence_anchors'],deps,'exact-existing-relation')
            elif len(matches)>1:
                add('ignore','relation',[cid],[x['internal_id'] for x in matches],None,None,None,payload,candidate['evidence_anchors'],deps,'existing-relation-duplicate-ambiguous')
            elif key in new_relations:
                target,dep=new_relations[key]; add('merge','relation',[cid],[target],target,None,None,payload,candidate['evidence_anchors'],list(dict.fromkeys([*deps,dep])),'exact-new-relation-duplicate')
            else:
                descriptor={'synthesis_run_id':synthesis_run_id,'candidate_id':cid,'subject_internal_id':subject,'predicate':candidate['predicate'],'object_internal_id':obj,'evidence_anchors':candidate['evidence_anchors']}; provisional=provisional_id('relation',descriptor)
                op=add('create','relation',[cid],[],provisional,provisional,None,payload,candidate['evidence_anchors'],deps,'new-relation'); new_relations[key]=(provisional,op)

        # Every explicit decision must have been type-valid and consumed above.
        consumed={cid for op in operations for cid in op['candidate_ids'] if cid in decisions}
        if consumed!=set(decisions): raise PlanningError(f'unconsumed decisions: {sorted(set(decisions)-consumed)}')

        # Reverify all mutable inputs after planning.
        resolution_after,_,_,_,_,res_manifest_sha_after,res_rows_sha_after,synth_candidates_sha_after=load_verified_resolution(res_dir,self.synthesis_root,expected)
        if resolution_after!=resolution or res_manifest_sha_after!=res_manifest_sha or res_rows_sha_after!=res_rows_sha or synth_candidates_sha_after!=synth_candidates_sha: raise PlanningError('Stage 07/06 evidence changed while planning was running')
        if state_path is not None:
            _,_,source_after,canonical_after=load_planning_state(state_path,concept_ids)
            if source_after!=state_source_sha or canonical_after!=state_canonical_sha: raise PlanningError('planning state changed while planning was running')
        if decisions_path is not None:
            _,_,source_after,canonical_after=load_decisions(decisions_path)
            if source_after!=decision_source_sha or canonical_after!=decision_canonical_sha: raise PlanningError('decision ledger changed while planning was running')

        operations_text=jsonl(operations); operations_sha=hashlib.sha256(operations_text.encode()).hexdigest()
        state_text=json.dumps(state,indent=2,sort_keys=True,ensure_ascii=True,allow_nan=False)+'\n'; decisions_text=json.dumps(ledger,indent=2,sort_keys=True,ensure_ascii=True,allow_nan=False)+'\n'
        operation_counts={name:0 for name in OPERATIONS}; object_counts={name:0 for name in OBJECTS}
        for op in operations: operation_counts[op['operation']]+=1; object_counts[op['object_type']]+=1
        descriptor={'profile':self.profile,'resolution_manifest_sha256':res_manifest_sha,'resolution_rows_sha256':res_rows_sha,'synthesis_candidates_sha256':synth_candidates_sha,'catalog_canonical_sha256':resolution['catalog_canonical_sha256'],'planning_state_canonical_sha256':state_canonical_sha,'decision_canonical_sha256':decision_canonical_sha,'slug_basis':SLUG_BASIS,'unicode_version':unicodedata.unidata_version,'operations_sha256':operations_sha}
        run_id='sha256-'+hashlib.sha256(canonical_json_bytes(descriptor)).hexdigest()
        if not PLANNING_RUN_RE.fullmatch(run_id): raise PlanningError('internal planning run identity failure')
        manifest=PlanningManifest(schema_version='0.1',stage='08-plan',profile=self.profile,run_id=run_id,source_id=source_id,snapshot_id=snapshot_id,classification_ruleset=self.ruleset,extraction_profile=self.extraction_profile,normalization_profile=self.normalization_profile,synthesis_profile=self.synthesis_profile,synthesis_provider=synthesis_provider,synthesis_run_id=synthesis_run_id,resolution_profile=self.resolution_profile,resolution_run_id=resolution_run_id,resolution_manifest_sha256=res_manifest_sha,resolution_rows_sha256=res_rows_sha,synthesis_candidates_sha256=synth_candidates_sha,catalog_canonical_sha256=resolution['catalog_canonical_sha256'],planning_state_mode=state_mode,planning_state_source_sha256=state_source_sha,planning_state_canonical_sha256=state_canonical_sha,planning_state_path='planning-state.json',decision_mode=decision_mode,decision_source_sha256=decision_source_sha,decision_canonical_sha256=decision_canonical_sha,decision_path='decisions.json',slug_basis=SLUG_BASIS,unicode_version=unicodedata.unidata_version,operations_path='operations.jsonl',operations_sha256=operations_sha,operation_count=len(operations),operation_counts=operation_counts,object_counts=object_counts,blocked_count=operation_counts['ignore'])
        final_dir=self.output_root/source_id/snapshot_id/self.ruleset/self.extraction_profile/self.normalization_profile/self.synthesis_profile/synthesis_provider/synthesis_run_id/self.resolution_profile/resolution_run_id/self.profile/run_id
        publish_run(final_dir,{'planning-state.json':state_text,'decisions.json':decisions_text,'operations.jsonl':operations_text,'plan.json':manifest.to_json()})
        return manifest

__all__=['PROFILE_ID','PlanningEngine','PlanningError','PlanningManifest','SLUG_BASIS']
