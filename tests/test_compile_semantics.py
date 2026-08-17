import json,tempfile,unittest
from pathlib import Path
from okf_generator.compile import CompilationEngine,CompilationError
from compilation_test_support import *

class CompileSemanticTests(unittest.TestCase):
    def run_compile(self,t,ops,cat=None,state=None,run=PLAN_RUN):
        e=CompilationEngine(t/"s",t/"r",t/"p",t/"state",plan_verifier=Verifier(bundle(ops,cat,state,run)))
        return e.compile(SOURCE_ID,SNAPSHOT_ID,SYNTH_RUN,RES_RUN,run,synthesis_provider=PROVIDER)
    def test_concept_merge_rewrites_relations_and_hides_loser_projection(self):
        td=tempfile.TemporaryDirectory(); self.addCleanup(td.cleanup); t=Path(td.name)
        cat={"schema_version":"0.1","concepts":[catalog_concept("c1","One","concepts/one.md"),catalog_concept("c2","Two","concepts/two.md")]}
        state={"schema_version":"0.1","claims":[],"relations":[{"internal_id":"r1","subject_internal_id":"c2","predicate":"p","object_internal_id":"c1","evidence_anchors":[],"status":"active"}]}
        m=self.run_compile(t,[op(1,"merge","concept",targets=["c1","c2"],survivor="c1",payload={"name":"One","description":"merged"})],cat,state)
        d=gen_dir(t/"state",m.generation_id); rel=read_jsonl(d/"relations.jsonl")[0]; self.assertEqual(rel["subject_internal_id"],"c1")
        cats=json.loads((d/"resolution-catalog.json").read_text()); self.assertEqual([x["internal_id"] for x in cats["concepts"]],["c1"])
        concepts={x["internal_id"]:x for x in read_jsonl(d/"concepts.jsonl")}; self.assertEqual(concepts["c2"]["merged_into"],"c1"); self.assertIn("concepts/two.md",concepts["c1"]["path_history"])
    def test_new_duplicate_merge_uses_finalized_target(self):
        td=tempfile.TemporaryDirectory(); self.addCleanup(td.cleanup); t=Path(td.name)
        p="urn:new"
        ops=[op(1,"create","summary",prov=p,payload={"text":"S"}),op(2,"merge","summary",targets=[p],survivor=p,payload={"text":"S"},deps=["op000001"])]
        m=self.run_compile(t,ops); rows=read_jsonl(gen_dir(t/"state",m.generation_id)/"summaries.jsonl"); self.assertEqual(len(rows),1); self.assertEqual(rows[0]["evidence_anchors"],["a1","a2"])
    def test_claim_merge_rewrites_claim_links(self):
        td=tempfile.TemporaryDirectory(); self.addCleanup(td.cleanup); t=Path(td.name)
        st={"schema_version":"0.1","claims":[
            {"internal_id":"q1","statement":"A","evidence_anchors":[],"status":"active"},
            {"internal_id":"q2","statement":"B","evidence_anchors":[],"status":"active"},
        ],"relations":[]}
        # bootstrap lacks cross-links; create them by first generation through contradiction then second generation merge
        m1=self.run_compile(t,[op(1,"contradict","claim",targets=["q2"],prov="urn:q3",payload={"statement":"C"})],state=st,run="sha256-"+"e"*64)
        d1=gen_dir(t/"state",m1.generation_id); current_cat=json.loads((d1/"resolution-catalog.json").read_text()); current_state=json.loads((d1/"planning-state.json").read_text())
        # merge q1 q2 with q1; compiler current state has q3 contradicts q2 and must rewrite to q1
        m2=self.run_compile(t,[op(1,"merge","claim",targets=["q1","q2"],survivor="q1",payload={"statement":"A merged"})],current_cat,current_state,run="sha256-"+"f"*64)
        claims={x["internal_id"]:x for x in read_jsonl(gen_dir(t/"state",m2.generation_id)/"claims.jsonl")}
        q3=[x for x in claims.values() if x["internal_id"] not in {"q1","q2"}][0]
        self.assertEqual(q3["contradicts"],["q1"]); self.assertEqual(claims["q2"]["status"],"merged")
    def test_second_generation_parent_and_projection_match(self):
        td=tempfile.TemporaryDirectory(); self.addCleanup(td.cleanup); t=Path(td.name)
        m1=self.run_compile(t,[op(1,"create","concept",prov="urn:c",path="concepts/c.md",payload={"name":"C","description":"C"})],run="sha256-"+"e"*64)
        d1=gen_dir(t/"state",m1.generation_id); cat=json.loads((d1/"resolution-catalog.json").read_text()); st=json.loads((d1/"planning-state.json").read_text())
        cid=cat["concepts"][0]["internal_id"]
        m2=self.run_compile(t,[op(1,"update","concept",targets=[cid],survivor=cid,payload={"name":"C2","description":"C2"})],cat,st,run="sha256-"+"f"*64)
        self.assertEqual(m2.parent_generation_id,m1.generation_id)
    def test_stale_catalog_rejected(self):
        td=tempfile.TemporaryDirectory(); self.addCleanup(td.cleanup); t=Path(td.name)
        m1=self.run_compile(t,[op(1,"create","concept",prov="urn:c",path="concepts/c.md",payload={"name":"C","description":"C"})],run="sha256-"+"e"*64)
        with self.assertRaises(CompilationError):
            self.run_compile(t,[op(1,"ignore","claim",payload={"statement":"x"})],empty_catalog(),empty_state(),run="sha256-"+"f"*64)
    def test_stale_planning_state_rejected(self):
        td=tempfile.TemporaryDirectory(); self.addCleanup(td.cleanup); t=Path(td.name)
        st={"schema_version":"0.1","claims":[{"internal_id":"q1","statement":"A","evidence_anchors":[],"status":"active"}],"relations":[]}
        m1=self.run_compile(t,[op(1,"update","claim",targets=["q1"],survivor="q1",payload={"statement":"A2"})],state=st,run="sha256-"+"e"*64)
        d=gen_dir(t/"state",m1.generation_id); cat=json.loads((d/"resolution-catalog.json").read_text())
        with self.assertRaises(CompilationError):
            self.run_compile(t,[op(1,"ignore","claim",payload={"statement":"x"})],cat,empty_state(),run="sha256-"+"f"*64)
if __name__=="__main__": unittest.main()
