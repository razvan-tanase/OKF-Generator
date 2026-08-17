from __future__ import annotations
from pathlib import PurePosixPath
from typing import Any
from .structural_errors import StructuralizationError
from .structural_paths import auxiliary_path, identity_ref, validate_public_path

OKF_TYPES={"concept":"Concept","summary":"Summary","claim":"Claim","relation":"Relation"}

def _title_from_text(text:str, fallback:str)->str:
    clean=" ".join(text.split())
    if not clean: return fallback
    return clean if len(clean)<=120 else clean[:117].rstrip()+"..."

def _paragraph(text:str)->dict[str,Any]: return {"kind":"paragraph","text":text}
def _heading(text:str,level:int=1)->dict[str,Any]: return {"kind":"heading","level":level,"text":text}
def _list(heading:str,items:list[str])->dict[str,Any]: return {"kind":"list","heading":heading,"items":items}
def _links(heading:str,items:list[dict[str,str]])->dict[str,Any]: return {"kind":"links","heading":heading,"items":items}

def build_identity_map(state:dict[str,Any])->dict[str,Any]:
    entries=[]; refs={}; paths={}; seen_paths=set(); seen_refs=set()
    collections={"concept":"concepts","summary":"summaries","claim":"claims","relation":"relations"}
    for typ in ("concept","summary","claim","relation"):
        for row in state[collections[typ]]:
            ref=identity_ref(row["internal_id"])
            if ref in seen_refs: raise StructuralizationError("identity reference collision")
            seen_refs.add(ref); refs[row["internal_id"]]=ref
            public_path=None
            if row["status"]!="merged":
                public_path=validate_public_path(row["canonical_path"] if typ=="concept" else auxiliary_path(typ,row["internal_id"]))
                key=public_path.casefold()
                if key in seen_paths: raise StructuralizationError(f"structural public path collision: {public_path}")
                seen_paths.add(key); paths[row["internal_id"]]=public_path
            entries.append({"identity_ref":ref,"internal_id":row["internal_id"],"object_type":typ,"status":row["status"],"public_path":public_path,"merged_into_identity_ref":None})
    by_id={row["internal_id"]:row for typ in ("concept","summary","claim","relation") for row in state[collections[typ]]}
    for item in entries:
        raw=by_id[item["internal_id"]].get("merged_into")
        if raw is not None:
            if raw not in refs: raise StructuralizationError(f"merged identity points outside canonical state: {raw}")
            item["merged_into_identity_ref"]=refs[raw]
    entries.sort(key=lambda x:(x["object_type"],x["internal_id"]))
    return {"schema_version":"0.1","entries":entries},refs,paths

def _frontmatter(okf_type:str,title:str,description:str)->dict[str,Any]:
    return {"type":okf_type,"title":title,"description":description}

def build_documents(state:dict[str,Any], refs:dict[str,str], paths:dict[str,str])->list[dict[str,Any]]:
    docs=[]
    concepts={x["internal_id"]:x for x in state["concepts"]}
    for c in state["concepts"]:
        if c["status"]=="merged": continue
        body=[_heading(c["title"]),_paragraph(c["description"])]
        if c["aliases"]: body.append(_list("Aliases",list(c["aliases"])))
        if c["resource_uris"]: body.append(_list("Resources",list(c["resource_uris"])))
        if c["source_anchors"]: body.append(_list("Evidence",list(c["source_anchors"])))
        docs.append({"document_id":paths[c["internal_id"]][:-3],"path":paths[c["internal_id"]],"identity_ref":refs[c["internal_id"]],"object_type":"concept","okf_type":"Concept","frontmatter":_frontmatter("Concept",c["title"],c["description"]),"body":body})
    for s in state["summaries"]:
        if s["status"]=="merged": continue
        title=_title_from_text(s["text"],"Summary")
        body=[_heading(title),_paragraph(s["text"])]
        if s["evidence_anchors"]: body.append(_list("Evidence",list(s["evidence_anchors"])))
        docs.append({"document_id":paths[s["internal_id"]][:-3],"path":paths[s["internal_id"]],"identity_ref":refs[s["internal_id"]],"object_type":"summary","okf_type":"Summary","frontmatter":_frontmatter("Summary",title,s["text"]),"body":body})
    for q in state["claims"]:
        if q["status"]=="merged": continue
        title=_title_from_text(q["statement"],"Claim")
        body=[_heading(title),_paragraph(q["statement"])]
        for field,heading in (("contradicts","Contradicts"),("contradicted_by","Contradicted by"),("supersedes","Supersedes"),("superseded_by","Superseded by")):
            items=[]
            for target in q[field]:
                if target in paths: items.append({"label":_title_from_text(next(x["statement"] for x in state["claims"] if x["internal_id"]==target),"Claim"),"target":paths[target]})
            if items: body.append(_links(heading,items))
        if q["evidence_anchors"]: body.append(_list("Evidence",list(q["evidence_anchors"])))
        docs.append({"document_id":paths[q["internal_id"]][:-3],"path":paths[q["internal_id"]],"identity_ref":refs[q["internal_id"]],"object_type":"claim","okf_type":"Claim","frontmatter":_frontmatter("Claim",title,q["statement"]),"body":body})
    for r in state["relations"]:
        if r["status"]=="merged": continue
        if r["subject_internal_id"] not in paths or r["object_internal_id"] not in paths:
            raise StructuralizationError(f"active relation {r['internal_id']} has no active public endpoints")
        subject=concepts[r["subject_internal_id"]]; obj=concepts[r["object_internal_id"]]
        title=_title_from_text(f"{subject['title']} {r['predicate']} {obj['title']}","Relation")
        body=[_heading(title),{"kind":"relation","subject":{"label":subject["title"],"target":paths[subject["internal_id"]]},"predicate":r["predicate"],"object":{"label":obj["title"],"target":paths[obj["internal_id"]]}}]
        if r["evidence_anchors"]: body.append(_list("Evidence",list(r["evidence_anchors"])))
        docs.append({"document_id":paths[r["internal_id"]][:-3],"path":paths[r["internal_id"]],"identity_ref":refs[r["internal_id"]],"object_type":"relation","okf_type":"Relation","frontmatter":_frontmatter("Relation",title,f"Relation: {title}"),"body":body})
    docs.sort(key=lambda x:x["path"])
    return docs
