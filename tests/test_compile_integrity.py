import json,tempfile,unittest
from pathlib import Path
from okf_generator.compile import CompilationEngine,CompilationError
from okf_generator.canonical_state import final_internal_id
from okf_generator.compilation_state import load_current
from compilation_test_support import *

class CompileIntegrityTests(unittest.TestCase):
    def test_plan_mutation_during_compile_rejected(self):
        td=tempfile.TemporaryDirectory(); self.addCleanup(td.cleanup); t=Path(td.name)
        v=Verifier(bundle([op(1,"ignore","claim",payload={"statement":"x"})]),mutate_second=True)
        e=CompilationEngine(t/"s",t/"r",t/"p",t/"state",plan_verifier=v)
        with self.assertRaises(CompilationError): e.compile(SOURCE_ID,SNAPSHOT_ID,SYNTH_RUN,RES_RUN,PLAN_RUN,synthesis_provider=PROVIDER)
        self.assertFalse((t/"state"/"current.json").exists())
    def test_pointer_failure_preserves_no_current(self):
        td=tempfile.TemporaryDirectory(); self.addCleanup(td.cleanup); t=Path(td.name)
        def fail(path,text): raise OSError("boom")
        e=CompilationEngine(t/"s",t/"r",t/"p",t/"state",plan_verifier=Verifier(bundle([op(1,"ignore","claim",payload={"statement":"x"})])),pointer_writer=fail)
        with self.assertRaises(CompilationError): e.compile(SOURCE_ID,SNAPSHOT_ID,SYNTH_RUN,RES_RUN,PLAN_RUN,synthesis_provider=PROVIDER)
        self.assertFalse((t/"state"/"current.json").exists())
    def test_generation_tamper_detected(self):
        td=tempfile.TemporaryDirectory(); self.addCleanup(td.cleanup); t=Path(td.name)
        b=bundle([op(1,"create","claim",prov="urn:q",payload={"statement":"x"})]); e=CompilationEngine(t/"s",t/"r",t/"p",t/"state",plan_verifier=Verifier(b))
        m=e.compile(SOURCE_ID,SNAPSHOT_ID,SYNTH_RUN,RES_RUN,PLAN_RUN,synthesis_provider=PROVIDER)
        (gen_dir(t/"state",m.generation_id)/"claims.jsonl").write_text("")
        with self.assertRaises(CompilationError): load_current(t/"state")
    def test_current_pointer_hash_tamper_detected(self):
        td=tempfile.TemporaryDirectory(); self.addCleanup(td.cleanup); t=Path(td.name)
        e=CompilationEngine(t/"s",t/"r",t/"p",t/"state",plan_verifier=Verifier(bundle([op(1,"ignore","claim",payload={"statement":"x"})])))
        e.compile(SOURCE_ID,SNAPSHOT_ID,SYNTH_RUN,RES_RUN,PLAN_RUN,synthesis_provider=PROVIDER)
        p=read_current(t/"state"); p["state_manifest_sha256"]="0"*64; (t/"state"/"current.json").write_text(json.dumps(p))
        with self.assertRaises(CompilationError): load_current(t/"state")
    def test_dependency_must_be_completed(self):
        td=tempfile.TemporaryDirectory(); self.addCleanup(td.cleanup); t=Path(td.name)
        bad=op(1,"ignore","claim",payload={"statement":"x"},deps=["op000002"])
        e=CompilationEngine(t/"s",t/"r",t/"p",t/"state",plan_verifier=Verifier(bundle([bad])))
        with self.assertRaises(CompilationError): e.compile(SOURCE_ID,SNAPSHOT_ID,SYNTH_RUN,RES_RUN,PLAN_RUN,synthesis_provider=PROVIDER)
    def test_final_id_is_deterministic_and_type_scoped(self):
        self.assertEqual(final_internal_id("claim","x"),final_internal_id("claim","x"))
        self.assertNotEqual(final_internal_id("claim","x"),final_internal_id("concept","x"))
    def test_plan_already_applied_to_ancestor_rejected(self):
        td=tempfile.TemporaryDirectory(); self.addCleanup(td.cleanup); t=Path(td.name)
        run1="sha256-"+"e"*64; run2="sha256-"+"f"*64
        e1=CompilationEngine(t/"s",t/"r",t/"p",t/"state",plan_verifier=Verifier(bundle([op(1,"ignore","claim",payload={"statement":"x"})],run_id=run1)))
        m1=e1.compile(SOURCE_ID,SNAPSHOT_ID,SYNTH_RUN,RES_RUN,run1,synthesis_provider=PROVIDER)
        d1=gen_dir(t/"state",m1.generation_id); cat=json.loads((d1/"resolution-catalog.json").read_text()); st=json.loads((d1/"planning-state.json").read_text())
        e2=CompilationEngine(t/"s",t/"r",t/"p",t/"state",plan_verifier=Verifier(bundle([op(1,"ignore","claim",payload={"statement":"y"})],cat,st,run2)))
        e2.compile(SOURCE_ID,SNAPSHOT_ID,SYNTH_RUN,RES_RUN,run2,synthesis_provider=PROVIDER)
        # Replaying run1 is stale/already-applied, not a duplicate mutation.
        with self.assertRaises(CompilationError): e1.compile(SOURCE_ID,SNAPSHOT_ID,SYNTH_RUN,RES_RUN,run1,synthesis_provider=PROVIDER)
if __name__=="__main__": unittest.main()
