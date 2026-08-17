from __future__ import annotations
import hashlib,json
from pathlib import Path
from typing import Any
from okf_generator.planning_io import canonical_json_bytes
from okf_generator.resolution_upstream import rederive_synthesis_run_id
from okf_generator.planning_upstream import rederive_resolution_run_id

SOURCE_ID='paper'; SNAPSHOT_ID='sha256-'+'1'*64; RULESET='builtin-v1'; PROFILE='builtin-v1'; PROVIDER='openai'

def jline(rows): return ''.join(json.dumps(x,sort_keys=True,ensure_ascii=True,separators=(',',':'),allow_nan=False)+'\n' for x in rows)
def sha(s:str): return hashlib.sha256(s.encode()).hexdigest()

def concept(cid='b0001-c0001',name='Alpha',description='Alpha concept',anchors=None):
 return {'candidate_id':cid,'candidate_type':'concept','batch_id':'b0001','name':name,'description':description,'evidence_anchors':anchors or ['okf-source:paper?v=1#a']}
def summary(cid='b0001-s0001',text='Summary',anchors=None):
 return {'candidate_id':cid,'candidate_type':'summary','batch_id':'b0001','text':text,'evidence_anchors':anchors or ['okf-source:paper?v=1#a']}
def claim(cid='b0001-q0001',statement='Alpha is useful.',anchors=None):
 return {'candidate_id':cid,'candidate_type':'claim','batch_id':'b0001','statement':statement,'evidence_anchors':anchors or ['okf-source:paper?v=1#a']}
def relation(cid='b0001-r0001',sub='b0001-c0001',pred='relates to',obj='b0001-c0002',anchors=None):
 return {'candidate_id':cid,'candidate_type':'relation','batch_id':'b0001','subject_candidate_id':sub,'predicate':pred,'object_candidate_id':obj,'evidence_anchors':anchors or ['okf-source:paper?v=1#a']}

def catalog_concept(i='concept-1',title='Alpha',path='concepts/alpha.md'):
 return {'internal_id':i,'title':title,'description':title+' description','canonical_path':path,'aliases':[],'title_history':[],'path_history':[],'resource_uris':[],'source_anchors':[],'status':'active'}

def build_fixture(tmp:Path,candidates:list[dict[str,Any]],resolutions:list[dict[str,Any]]|None=None,catalog:dict[str,Any]|None=None):
 synth_root=tmp/'syntheses'; res_root=tmp/'resolutions'; plan_root=tmp/'plans'
 requests=responses=receipts=''; ctext=jline(candidates)
 counts={'summary':0,'concept':0,'claim':0,'relation':0}
 for c in candidates: counts[c['candidate_type']]+=1
 sm={
  'schema_version':'0.1','stage':'06-synthesize','profile':PROFILE,'run_id':'pending','source_id':SOURCE_ID,'snapshot_id':SNAPSHOT_ID,
  'classification_ruleset':RULESET,'extraction_profile':PROFILE,'normalization_profile':PROFILE,'provider':PROVIDER,'requested_model':'model-x',
  'normalization_manifest_sha256':'2'*64,'normalization_units_sha256':'3'*64,'prompt_version':'prompt-v1','prompt_sha256':'4'*64,
  'candidate_schema_version':'candidate-v1','candidate_schema_sha256':'5'*64,'max_input_chars':120000,'max_batch_units':50,'max_output_tokens':8000,
  'batch_count':1,'requests_path':'requests.jsonl','requests_sha256':sha(requests),'responses_path':'responses.jsonl','responses_sha256':sha(responses),
  'receipts_path':'receipts.jsonl','receipts_sha256':sha(receipts),'candidates_path':'candidates.jsonl','candidates_sha256':sha(ctext),'candidate_counts':counts}
 synth_id=rederive_synthesis_run_id(sm); sm['run_id']=synth_id
 sdir=synth_root/SOURCE_ID/SNAPSHOT_ID/RULESET/PROFILE/PROFILE/PROFILE/PROVIDER/synth_id; sdir.mkdir(parents=True)
 (sdir/'requests.jsonl').write_text(requests); (sdir/'responses.jsonl').write_text(responses); (sdir/'receipts.jsonl').write_text(receipts); (sdir/'candidates.jsonl').write_text(ctext); (sdir/'synthesis.json').write_text(json.dumps(sm,indent=2,sort_keys=True)+'\n')
 sm_sha=hashlib.sha256((sdir/'synthesis.json').read_bytes()).hexdigest()
 if catalog is None: catalog={'schema_version':'0.1','concepts':[]}
 cat_text=json.dumps(catalog,indent=2,sort_keys=True)+'\n'; cat_can=hashlib.sha256(canonical_json_bytes(catalog)).hexdigest()
 concepts=[c for c in candidates if c['candidate_type']=='concept']
 if resolutions is None:
  resolutions=[{'candidate_id':c['candidate_id'],'candidate_name':c['name'],'status':'new','method':'no-catalog-candidate','resolved_internal_id':None,'considered_internal_ids':[],'evidence_anchors':c['evidence_anchors'],'signals':[]} for c in concepts]
 rtext=jline(resolutions); counts_r={'matched':0,'new':0,'ambiguous':0}
 for r in resolutions: counts_r[r['status']]+=1
 empty=''
 rm={
  'schema_version':'0.1','stage':'07-resolve','profile':PROFILE,'run_id':'pending','source_id':SOURCE_ID,'snapshot_id':SNAPSHOT_ID,
  'classification_ruleset':RULESET,'extraction_profile':PROFILE,'normalization_profile':PROFILE,'synthesis_profile':PROFILE,'synthesis_provider':PROVIDER,
  'synthesis_run_id':synth_id,'synthesis_manifest_sha256':sm_sha,'synthesis_candidates_sha256':sha(ctext),'catalog_mode':'empty' if not catalog['concepts'] else 'file',
  'catalog_source_sha256':None,'catalog_canonical_sha256':cat_can,'catalog_path':'catalog.json','similarity_threshold':0.4,'shortlist_limit':5,
  'adjudication_provider':None,'adjudication_model':None,'resolutions_path':'resolutions.jsonl','resolutions_sha256':sha(rtext),'resolution_counts':counts_r,
  'adjudication_requests_path':'adjudication-requests.jsonl','adjudication_requests_sha256':sha(empty),'adjudication_responses_path':'adjudication-responses.jsonl','adjudication_responses_sha256':sha(empty),
  'adjudication_receipts_path':'adjudication-receipts.jsonl','adjudication_receipts_sha256':sha(empty)}
 res_id=rederive_resolution_run_id(rm); rm['run_id']=res_id
 rdir=res_root/SOURCE_ID/SNAPSHOT_ID/RULESET/PROFILE/PROFILE/PROFILE/PROVIDER/synth_id/PROFILE/res_id; rdir.mkdir(parents=True)
 (rdir/'catalog.json').write_text(cat_text); (rdir/'resolutions.jsonl').write_text(rtext); (rdir/'adjudication-requests.jsonl').write_text(empty); (rdir/'adjudication-responses.jsonl').write_text(empty); (rdir/'adjudication-receipts.jsonl').write_text(empty); (rdir/'resolution.json').write_text(json.dumps(rm,indent=2,sort_keys=True)+'\n')
 return {'synth_root':synth_root,'res_root':res_root,'plan_root':plan_root,'synth_id':synth_id,'res_id':res_id,'sdir':sdir,'rdir':rdir,'catalog':catalog}

def read_ops(plan_root:Path, synth_id:str,res_id:str,run_id:str):
 path=plan_root/SOURCE_ID/SNAPSHOT_ID/RULESET/PROFILE/PROFILE/PROFILE/PROVIDER/synth_id/PROFILE/res_id/PROFILE/run_id/'operations.jsonl'
 return [json.loads(line) for line in path.read_text().splitlines()]
