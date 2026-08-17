import tempfile,unittest,json
from pathlib import Path
from unittest.mock import patch
from okf_generator.plan import PlanningEngine
from okf_generator.planning_errors import PlanningError
from okf_generator.planning_state import validate_planning_state
from okf_generator.planning_decisions import validate_decisions
from planning_test_support import *

class IntegrityTests(unittest.TestCase):
 def test_tampered_resolution_artifact_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   fx=build_fixture(Path(d),[concept()]); (fx['rdir']/'resolutions.jsonl').write_text('{}\n')
   with self.assertRaises(PlanningError): PlanningEngine(fx['synth_root'],fx['res_root'],fx['plan_root']).plan(SOURCE_ID,SNAPSHOT_ID,fx['synth_id'],fx['res_id'],synthesis_provider=PROVIDER)
 def test_tampered_resolution_run_id_descriptor_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   fx=build_fixture(Path(d),[concept()]); p=fx['rdir']/'resolution.json'; m=json.loads(p.read_text()); m['shortlist_limit']=9; p.write_text(json.dumps(m,indent=2,sort_keys=True)+'\n')
   with self.assertRaises(PlanningError): PlanningEngine(fx['synth_root'],fx['res_root'],fx['plan_root']).plan(SOURCE_ID,SNAPSHOT_ID,fx['synth_id'],fx['res_id'],synthesis_provider=PROVIDER)
 def test_tampered_synthesis_candidates_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   fx=build_fixture(Path(d),[concept()]); (fx['sdir']/'candidates.jsonl').write_text('')
   with self.assertRaises(PlanningError): PlanningEngine(fx['synth_root'],fx['res_root'],fx['plan_root']).plan(SOURCE_ID,SNAPSHOT_ID,fx['synth_id'],fx['res_id'],synthesis_provider=PROVIDER)
 def test_repeat_is_idempotent_and_tamper_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   fx=build_fixture(Path(d),[concept()]); e=PlanningEngine(fx['synth_root'],fx['res_root'],fx['plan_root']); m1=e.plan(SOURCE_ID,SNAPSHOT_ID,fx['synth_id'],fx['res_id'],synthesis_provider=PROVIDER); m2=e.plan(SOURCE_ID,SNAPSHOT_ID,fx['synth_id'],fx['res_id'],synthesis_provider=PROVIDER); self.assertEqual(m1,m2)
   out=fx['plan_root']/SOURCE_ID/SNAPSHOT_ID/RULESET/PROFILE/PROFILE/PROFILE/PROVIDER/fx['synth_id']/PROFILE/fx['res_id']/PROFILE/m1.run_id; (out/'operations.jsonl').write_text('{}\n')
   with self.assertRaises(PlanningError): e.plan(SOURCE_ID,SNAPSHOT_ID,fx['synth_id'],fx['res_id'],synthesis_provider=PROVIDER)
 def test_planning_state_duplicate_id_rejected(self):
  state={'schema_version':'0.1','claims':[{'internal_id':'x','statement':'A','evidence_anchors':[],'status':'active'}],'relations':[{'internal_id':'x','subject_internal_id':'c','predicate':'p','object_internal_id':'c','evidence_anchors':[],'status':'active'}]}
  with self.assertRaises(PlanningError): validate_planning_state(state,{'c'})
 def test_planning_relation_unknown_concept_rejected(self):
  state={'schema_version':'0.1','claims':[],'relations':[{'internal_id':'r','subject_internal_id':'x','predicate':'p','object_internal_id':'y','evidence_anchors':[],'status':'active'}]}
  with self.assertRaises(PlanningError): validate_planning_state(state,set())
 def test_duplicate_decision_candidate_rejected(self):
  row={'candidate_id':'c','action':'ignore','target_internal_ids':[],'survivor_internal_id':None,'reason':'x'}
  with self.assertRaises(PlanningError): validate_decisions({'schema_version':'0.1','decisions':[row,row]})
 def test_invalid_source_id_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   fx=build_fixture(Path(d),[concept()]); e=PlanningEngine(fx['synth_root'],fx['res_root'],fx['plan_root'])
   with self.assertRaises(PlanningError): e.plan('../bad',SNAPSHOT_ID,fx['synth_id'],fx['res_id'],synthesis_provider=PROVIDER)

if __name__=='__main__': unittest.main()
