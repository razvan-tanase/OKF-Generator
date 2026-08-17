import hashlib,json,tempfile,unittest
from pathlib import Path
from okf_generator.compilation_upstream import load_verified_plan,rederive_plan_run_id
from okf_generator.compilation_errors import CompilationError
from okf_generator.compilation_io import canonical_json_bytes
from compilation_test_support import *

class UpstreamTests(unittest.TestCase):
    def fixture(self,tmp):
        plan_dir=tmp/"plan"; plan_dir.mkdir()
        ops=[op(1,"ignore","claim",payload={"statement":"x"})]
        optext="".join(json.dumps(x,sort_keys=True,separators=(",",":"))+"\n" for x in ops)
        (plan_dir/"operations.jsonl").write_text(optext)
        state=empty_state(); decisions=empty_decisions()
        (plan_dir/"planning-state.json").write_text(json.dumps(state,indent=2,sort_keys=True)+"\n")
        (plan_dir/"decisions.json").write_text(json.dumps(decisions,indent=2,sort_keys=True)+"\n")
        res_manifest_sha="3"*64; res_rows_sha="4"*64; synth_sha="5"*64; catalog_sha="6"*64
        manifest={
            "schema_version":"0.1","stage":"08-plan","profile":"builtin-v1","run_id":"",
            "source_id":SOURCE_ID,"snapshot_id":SNAPSHOT_ID,"classification_ruleset":"builtin-v1","extraction_profile":"builtin-v1",
            "normalization_profile":"builtin-v1","synthesis_profile":"builtin-v1","synthesis_provider":PROVIDER,"synthesis_run_id":SYNTH_RUN,
            "resolution_profile":"builtin-v1","resolution_run_id":RES_RUN,
            "resolution_manifest_sha256":res_manifest_sha,"resolution_rows_sha256":res_rows_sha,"synthesis_candidates_sha256":synth_sha,
            "catalog_canonical_sha256":catalog_sha,"planning_state_mode":"empty","planning_state_source_sha256":None,
            "planning_state_canonical_sha256":hashlib.sha256(canonical_json_bytes(state)).hexdigest(),"planning_state_path":"planning-state.json",
            "decision_mode":"empty","decision_source_sha256":None,"decision_canonical_sha256":hashlib.sha256(canonical_json_bytes(decisions)).hexdigest(),
            "decision_path":"decisions.json","slug_basis":"unicode-nfc-casefold-alnum-v1","unicode_version":"16.0.0",
            "operations_path":"operations.jsonl","operations_sha256":hashlib.sha256(optext.encode()).hexdigest(),"operation_count":1,
            "operation_counts":{"create":0,"update":0,"merge":0,"contradict":0,"supersede":0,"ignore":1},
            "object_counts":{"concept":0,"summary":0,"claim":1,"relation":0},"blocked_count":1,
        }
        manifest["run_id"]=rederive_plan_run_id(manifest); (plan_dir/"plan.json").write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n")
        catalog=empty_catalog()
        resolution={"catalog_canonical_sha256":catalog_sha}
        def verify(*args):
            return resolution,[],catalog,{},[],res_manifest_sha,res_rows_sha,synth_sha
        expected={"source_id":SOURCE_ID,"snapshot_id":SNAPSHOT_ID,"ruleset":"builtin-v1","extraction_profile":"builtin-v1","normalization_profile":"builtin-v1",
                  "synthesis_profile":"builtin-v1","synthesis_provider":PROVIDER,"synthesis_run_id":SYNTH_RUN,"resolution_profile":"builtin-v1",
                  "resolution_run_id":RES_RUN,"planning_profile":"builtin-v1","plan_run_id":manifest["run_id"]}
        return plan_dir,manifest,expected,verify
    def test_valid_plan(self):
        with tempfile.TemporaryDirectory() as d:
            p,m,e,v=self.fixture(Path(d)); out=load_verified_plan(p,Path(d)/"r",Path(d)/"s",e,resolution_verifier=v); self.assertEqual(out[0]["run_id"],m["run_id"])
    def test_operations_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as d:
            p,m,e,v=self.fixture(Path(d)); (p/"operations.jsonl").write_text("")
            with self.assertRaises(CompilationError): load_verified_plan(p,Path(d)/"r",Path(d)/"s",e,resolution_verifier=v)
    def test_run_id_mismatch(self):
        with tempfile.TemporaryDirectory() as d:
            p,m,e,v=self.fixture(Path(d)); x=json.loads((p/"plan.json").read_text()); x["unicode_version"]="X"; (p/"plan.json").write_text(json.dumps(x))
            with self.assertRaises(CompilationError): load_verified_plan(p,Path(d)/"r",Path(d)/"s",e,resolution_verifier=v)
    def test_counts_mismatch(self):
        with tempfile.TemporaryDirectory() as d:
            p,m,e,v=self.fixture(Path(d)); x=json.loads((p/"plan.json").read_text()); x["operation_count"]=2; (p/"plan.json").write_text(json.dumps(x))
            with self.assertRaises(CompilationError): load_verified_plan(p,Path(d)/"r",Path(d)/"s",e,resolution_verifier=v)
    def test_planning_state_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as d:
            p,m,e,v=self.fixture(Path(d)); (p/"planning-state.json").write_text(json.dumps({"schema_version":"0.1","claims":[{"internal_id":"q","statement":"x","evidence_anchors":[],"status":"active"}],"relations":[]}))
            with self.assertRaises(CompilationError): load_verified_plan(p,Path(d)/"r",Path(d)/"s",e,resolution_verifier=v)
    def test_resolution_binding_mismatch(self):
        with tempfile.TemporaryDirectory() as d:
            p,m,e,v=self.fixture(Path(d))
            def bad(*args): return {"catalog_canonical_sha256":"6"*64},[],empty_catalog(),{},[],"9"*64,"4"*64,"5"*64
            with self.assertRaises(CompilationError): load_verified_plan(p,Path(d)/"r",Path(d)/"s",e,resolution_verifier=bad)
    def test_forward_dependency_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p,m,e,v=self.fixture(Path(d))
            rows=[op(1,"ignore","claim",payload={"statement":"x"},deps=["op000002"])]
            text="".join(json.dumps(x,sort_keys=True,separators=(",",":"))+"\n" for x in rows); (p/"operations.jsonl").write_text(text)
            x=json.loads((p/"plan.json").read_text()); x["operations_sha256"]=hashlib.sha256(text.encode()).hexdigest()
            # rederive id and expected selection, so failure is dependency validation rather than identity.
            x["run_id"]=rederive_plan_run_id(x); (p/"plan.json").write_text(json.dumps(x)); e["plan_run_id"]=x["run_id"]
            with self.assertRaises(CompilationError): load_verified_plan(p,Path(d)/"r",Path(d)/"s",e,resolution_verifier=v)
if __name__=="__main__": unittest.main()
