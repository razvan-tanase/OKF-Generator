from __future__ import annotations
import hashlib, json
from pathlib import Path

SOURCE='paper'
SNAP='sha256-'+'1'*64


def jsonl(rows):
    return ''.join(json.dumps(x, sort_keys=True, ensure_ascii=True, separators=(',',':'))+'\n' for x in rows)
def sha(data: bytes): return hashlib.sha256(data).hexdigest()
def canonical(value): return json.dumps(value,sort_keys=True,ensure_ascii=True,separators=(',',':')).encode()

def candidate_concept(cid, name, desc='description', anchors=None, batch='b0001'):
    return {'candidate_id':cid,'candidate_type':'concept','batch_id':batch,'name':name,'description':desc,'evidence_anchors':anchors or ['okf-source:paper@sha256-'+('1'*64)+'#a1']}
def candidate_relation(cid, subj, obj):
    return {'candidate_id':cid,'candidate_type':'relation','batch_id':'b0001','subject_candidate_id':subj,'predicate':'relates to','object_candidate_id':obj,'evidence_anchors':['okf-source:paper@sha256-'+('1'*64)+'#a1']}

def make_synthesis(root: Path, concepts, extra=None, provider='openai'):
    extra=extra or []
    rows=[*concepts,*extra]
    counts={'summary':0,'concept':len(concepts),'claim':0,'relation':sum(1 for r in extra if r['candidate_type']=='relation')}
    artifacts={'requests.jsonl':'','responses.jsonl':'','receipts.jsonl':'','candidates.jsonl':jsonl(rows)}
    manifest={
      'schema_version':'0.1','stage':'06-synthesize','profile':'builtin-v1',
      'source_id':SOURCE,'snapshot_id':SNAP,'classification_ruleset':'builtin-v1','extraction_profile':'builtin-v1','normalization_profile':'builtin-v1',
      'normalization_manifest_sha256':'3'*64,'normalization_units_sha256':'4'*64,
      'provider':provider,'requested_model':'model-x','prompt_version':'prompt-v1','prompt_sha256':'5'*64,
      'candidate_schema_version':'candidate-v1','candidate_schema_sha256':'6'*64,
      'max_input_chars':120000,'max_batch_units':50,'max_output_tokens':8000,
      'candidate_counts':counts,
    }
    for stem in ('requests','responses','receipts','candidates'):
        manifest[f'{stem}_path']=f'{stem}.jsonl'; manifest[f'{stem}_sha256']=sha(artifacts[f'{stem}.jsonl'].encode())
    fields=['profile','source_id','snapshot_id','normalization_manifest_sha256','normalization_units_sha256','provider','requested_model','prompt_version','prompt_sha256','candidate_schema_version','candidate_schema_sha256','max_input_chars','max_batch_units','max_output_tokens','requests_sha256','responses_sha256','receipts_sha256','candidates_sha256']
    descriptor={k:manifest[k] for k in fields}
    run_id='sha256-'+sha(canonical(descriptor))
    manifest['run_id']=run_id
    run=root/SOURCE/SNAP/'builtin-v1'/'builtin-v1'/'builtin-v1'/'builtin-v1'/provider/run_id
    run.mkdir(parents=True)
    for name,text in artifacts.items(): (run/name).write_text(text)
    (run/'synthesis.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
    return run,run_id

def concept(iid,title,description='description',path=None,aliases=None,title_history=None,path_history=None,resources=None,anchors=None,status='active'):
    return {'internal_id':iid,'title':title,'description':description,'canonical_path':path or title.lower().replace(' ','-'),
      'aliases':aliases or [],'title_history':title_history or [],'path_history':path_history or [],'resource_uris':resources or [],'source_anchors':anchors or [],'status':status}
def write_catalog(path:Path, concepts):
    path.write_text(json.dumps({'schema_version':'0.1','concepts':concepts},indent=2,sort_keys=True)+'\n')
