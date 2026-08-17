from __future__ import annotations
import json, posixpath
from pathlib import Path
from types import SimpleNamespace

GEN="sha256-"+"9"*64

def concept(i="c1",title="Alpha",path="concepts/alpha.md",status="active",merged_into=None):
    return {"internal_id":i,"title":title,"description":title+" description","canonical_path":path,"aliases":[],"title_history":[],"path_history":[],"resource_uris":[],"source_anchors":["okf-source:paper#u1"],"status":status,"merged_into":merged_into}
def summary(i="s1",text="Alpha summary",status="active",merged_into=None):
    return {"internal_id":i,"text":text,"evidence_anchors":["okf-source:paper#u1"],"status":status,"merged_into":merged_into}
def claim(i="q1",statement="Alpha is useful.",status="active",merged_into=None,**links):
    return {"internal_id":i,"statement":statement,"evidence_anchors":["okf-source:paper#u1"],"status":status,"merged_into":merged_into,"contradicts":links.get("contradicts",[]),"contradicted_by":links.get("contradicted_by",[]),"supersedes":links.get("supersedes",[]),"superseded_by":links.get("superseded_by",[])}
def relation(i="r1",subject="c1",predicate="relates to",obj="c2",status="active",merged_into=None):
    return {"internal_id":i,"subject_internal_id":subject,"predicate":predicate,"object_internal_id":obj,"evidence_anchors":["okf-source:paper#u1"],"status":status,"merged_into":merged_into}
def state(concepts=None,summaries=None,claims=None,relations=None):
    return {"concepts":concepts or [],"summaries":summaries or [],"claims":claims or [],"relations":relations or [],"events":[],"applied_plan_run_ids":[],"catalog":{"schema_version":"0.1","concepts":[]},"planning_state":{"schema_version":"0.1","claims":[],"relations":[]}}
class Loader:
    def __init__(self,state,mutate_second=False,generation=GEN): self.value=state; self.calls=0; self.mutate_second=mutate_second; self.generation=generation
    def __call__(self,root,generation_id=None):
        self.calls+=1
        value=json.loads(json.dumps(self.value))
        if self.mutate_second and self.calls>=2: value["events"].append({"changed":True})
        return SimpleNamespace(generation_id=self.generation),value,"a"*64

def read_run(root,manifest):
    d=root/manifest.state_generation_id/manifest.profile/manifest.run_id
    docs=[json.loads(x) for x in (d/"documents.jsonl").read_text().splitlines()]
    identity=json.loads((d/"identity-map.json").read_text())
    deferred=json.loads((d/"deferred.json").read_text())
    return d,docs,identity,deferred

def _yaml_scalar(value:str)->str:
    return json.dumps(value,ensure_ascii=False)
def _rel(source:str,target:str)->str:
    base=posixpath.dirname(source) or "."
    return posixpath.relpath(target,base)
def render_document(doc:dict)->str:
    fm=doc["frontmatter"]
    lines=["---",f"type: {_yaml_scalar(fm['type'])}",f"title: {_yaml_scalar(fm['title'])}",f"description: {_yaml_scalar(fm['description'])}","---",""]
    for block in doc["body"]:
        kind=block["kind"]
        if kind=="heading": lines.extend(["#"*block["level"]+" "+block["text"],""])
        elif kind=="paragraph": lines.extend([block["text"],""])
        elif kind=="list":
            lines.extend(["## "+block["heading"],""]+["- "+x for x in block["items"]]+[""])
        elif kind=="links":
            lines.extend(["## "+block["heading"],""]+[f"- [{x['label']}]({_rel(doc['path'],x['target'])})" for x in block["items"]]+[""])
        elif kind=="relation":
            lines.extend([f"[{block['subject']['label']}]({_rel(doc['path'],block['subject']['target'])}) {block['predicate']} [{block['object']['label']}]({_rel(doc['path'],block['object']['target'])})",""])
        else: raise AssertionError(kind)
    return "\n".join(lines).rstrip()+"\n"
def materialize_fixture(documents:list[dict],root:Path)->Path:
    root.mkdir(parents=True,exist_ok=True)
    for doc in documents:
        p=root/doc["path"]; p.parent.mkdir(parents=True,exist_ok=True); p.write_text(render_document(doc),encoding="utf-8")
    links="\n".join(f"- [{d['frontmatter']['title']}]({d['path']})" for d in documents)
    (root/"index.md").write_text('---\nokf_version: "0.1"\n---\n\n# Index\n\n'+links+'\n',encoding="utf-8")
    (root/"log.md").write_text("# Update Log\n",encoding="utf-8")
    return root
