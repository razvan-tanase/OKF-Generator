import hashlib,json
from pathlib import Path
SOURCE_ID="paper"; SNAPSHOT_ID="sha256-"+"a"*64; PROVIDER="openai"; SYNTH_RUN="sha256-"+"b"*64; RES_RUN="sha256-"+"c"*64; PLAN_RUN="sha256-"+"d"*64
def catalog_concept(i="c1",title="Alpha",path="concepts/alpha.md",anchors=None):
    return {"internal_id":i,"title":title,"description":title+" desc","canonical_path":path,"aliases":[],"title_history":[],"path_history":[],"resource_uris":[],"source_anchors":anchors or [],"status":"active"}
def empty_catalog(): return {"schema_version":"0.1","concepts":[]}
def empty_state(): return {"schema_version":"0.1","claims":[],"relations":[]}
def empty_decisions(): return {"schema_version":"0.1","decisions":[]}
def op(n,action,typ,cids=None,targets=None,survivor=None,prov=None,path=None,payload=None,anchors=None,deps=None,reason="test"):
    return {"operation_id":f"op{n:06d}","operation":action,"object_type":typ,"candidate_ids":cids or [f"cand-{n}"],
            "target_internal_ids":targets or [],"survivor_internal_id":survivor,"provisional_internal_id":prov,
            "proposed_canonical_path":path,"payload":payload or {},"evidence_anchors":anchors or [f"a{n}"],"dependencies":deps or [],"reason":reason}
def bundle(ops,catalog=None,state=None,run_id=PLAN_RUN):
    cat=catalog or empty_catalog(); st=state or empty_state(); dec=empty_decisions()
    manifest={"stage":"08-plan","run_id":run_id}
    return [manifest,ops,cat,st,dec,"1"*64,"2"*64]
class Verifier:
    def __init__(self,bundle,mutate_second=False):
        self.bundle=bundle; self.calls=0; self.mutate_second=mutate_second
    def __call__(self,*args,**kwargs):
        self.calls+=1
        out=json.loads(json.dumps(self.bundle))
        if self.mutate_second and self.calls>=2:
            out[0]["changed"]=True
        return tuple(out)
def read_current(root):
    return json.loads((root/"current.json").read_text())
def gen_dir(root,gid): return root/"generations"/gid
def read_jsonl(path):
    return [json.loads(x) for x in path.read_text().splitlines()]
