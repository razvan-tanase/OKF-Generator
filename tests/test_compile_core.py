import json,tempfile,unittest
from pathlib import Path
from okf_generator.compile import CompilationEngine,CompilationError
from okf_generator.canonical_state import final_internal_id
from compilation_test_support import *

class CompileCoreTests(unittest.TestCase):
    def engine(self,tmp,b):
        return CompilationEngine(tmp/"s",tmp/"r",tmp/"p",tmp/"state",plan_verifier=Verifier(b))
    def compile(self,e,run=PLAN_RUN):
        return e.compile(SOURCE_ID,SNAPSHOT_ID,SYNTH_RUN,RES_RUN,run,synthesis_provider=PROVIDER)
    def test_first_run_all_object_types(self):
        td=tempfile.TemporaryDirectory(); self.addCleanup(td.cleanup); t=Path(td.name)
        pc="urn:okf-generator:concept:sha256-"+"1"*64; ps="urn:okf-generator:summary:sha256-"+"2"*64; pq="urn:okf-generator:claim:sha256-"+"3"*64; pr="urn:okf-generator:relation:sha256-"+"4"*64
        ops=[op(1,"create","concept",prov=pc,path="concepts/alpha.md",payload={"name":"Alpha","description":"A"}),
             op(2,"create","summary",prov=ps,payload={"text":"Summary"}),
             op(3,"create","claim",prov=pq,payload={"statement":"Claim"}),
             op(4,"create","relation",prov=pr,payload={"subject_internal_id":pc,"predicate":"relates","object_internal_id":pc},deps=["op000001"])]
        m=self.compile(self.engine(t,bundle(ops)))
        d=gen_dir(t/"state",m.generation_id)
        self.assertEqual(len(read_jsonl(d/"concepts.jsonl")),1); self.assertEqual(len(read_jsonl(d/"summaries.jsonl")),1)
        rel=read_jsonl(d/"relations.jsonl")[0]; self.assertEqual(rel["subject_internal_id"],final_internal_id("concept",pc))
        self.assertEqual(read_current(t/"state")["generation_id"],m.generation_id)
    def test_replay_is_idempotent(self):
        td=tempfile.TemporaryDirectory(); self.addCleanup(td.cleanup); t=Path(td.name); p="urn:x"
        e=self.engine(t,bundle([op(1,"create","claim",prov=p,payload={"statement":"A"})]))
        a=self.compile(e); b=self.compile(e); self.assertEqual(a.generation_id,b.generation_id)
    def test_ignore_records_event_without_object(self):
        td=tempfile.TemporaryDirectory(); self.addCleanup(td.cleanup); t=Path(td.name)
        m=self.compile(self.engine(t,bundle([op(1,"ignore","claim",payload={"statement":"A"})])))
        d=gen_dir(t/"state",m.generation_id); self.assertEqual(read_jsonl(d/"claims.jsonl"),[]); self.assertEqual(len(read_jsonl(d/"events.jsonl")),1)
    def test_concept_update_preserves_title_history(self):
        td=tempfile.TemporaryDirectory(); self.addCleanup(td.cleanup); t=Path(td.name)
        cat={"schema_version":"0.1","concepts":[catalog_concept()]}
        m=self.compile(self.engine(t,bundle([op(1,"update","concept",targets=["c1"],survivor="c1",payload={"name":"Alpha New","description":"new"})],cat)))
        c=read_jsonl(gen_dir(t/"state",m.generation_id)/"concepts.jsonl")[0]; self.assertEqual(c["title"],"Alpha New"); self.assertIn("Alpha",c["title_history"])
    def test_contradict_and_supersede(self):
        td=tempfile.TemporaryDirectory(); self.addCleanup(td.cleanup); t=Path(td.name)
        st={"schema_version":"0.1","claims":[{"internal_id":"q1","statement":"Old","evidence_anchors":[],"status":"active"}],"relations":[]}
        p1="urn:p1"; p2="urn:p2"
        ops=[op(1,"contradict","claim",targets=["q1"],prov=p1,payload={"statement":"Not old"}),
             op(2,"supersede","claim",targets=["q1"],prov=p2,payload={"statement":"New"})]
        m=self.compile(self.engine(t,bundle(ops,state=st))); claims={x["internal_id"]:x for x in read_jsonl(gen_dir(t/"state",m.generation_id)/"claims.jsonl")}
        q1=claims["q1"]; self.assertEqual(q1["status"],"superseded"); self.assertEqual(len(q1["contradicted_by"]),1); self.assertEqual(len(q1["superseded_by"]),1)
    def test_relation_unknown_endpoint_rejected(self):
        td=tempfile.TemporaryDirectory(); self.addCleanup(td.cleanup); t=Path(td.name)
        with self.assertRaises(CompilationError):
            self.compile(self.engine(t,bundle([op(1,"create","relation",prov="urn:r",payload={"subject_internal_id":"x","predicate":"p","object_internal_id":"y"})])))
    def test_invalid_action_matrix_rejected(self):
        td=tempfile.TemporaryDirectory(); self.addCleanup(td.cleanup); t=Path(td.name)
        with self.assertRaises(CompilationError): self.compile(self.engine(t,bundle([op(1,"update","summary",targets=["x"],payload={"text":"x"})])))
    def test_create_requires_provisional(self):
        td=tempfile.TemporaryDirectory(); self.addCleanup(td.cleanup); t=Path(td.name)
        with self.assertRaises(CompilationError): self.compile(self.engine(t,bundle([op(1,"create","claim",payload={"statement":"x"})])))
if __name__=="__main__": unittest.main()
