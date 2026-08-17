import tempfile,unittest,json
from pathlib import Path
from okf_generator.plan import PlanningEngine
from okf_generator.planning_errors import PlanningError
from planning_test_support import *

class DecisionTests(unittest.TestCase):
 def plan(self,candidates,resolutions=None,catalog=None,state=None,decisions=None):
  td=tempfile.TemporaryDirectory(); tmp=Path(td.name); fx=build_fixture(tmp,candidates,resolutions,catalog); sp=dp=None
  if state is not None: sp=tmp/'state.json'; sp.write_text(json.dumps(state))
  if decisions is not None: dp=tmp/'decisions.json'; dp.write_text(json.dumps(decisions))
  eng=PlanningEngine(fx['synth_root'],fx['res_root'],fx['plan_root'])
  return td,fx,eng,sp,dp
 def ledger(self,*rows): return {'schema_version':'0.1','decisions':list(rows)}
 def row(self,cid,action,targets=None,survivor=None,reason='reviewed'): return {'candidate_id':cid,'action':action,'target_internal_ids':targets or [],'survivor_internal_id':survivor,'reason':reason}
 def test_contradict_claim(self):
  state={'schema_version':'0.1','claims':[{'internal_id':'q1','statement':'Opposite.','evidence_anchors':[],'status':'active'}],'relations':[]}; d=self.ledger(self.row('b0001-q0001','contradict',['q1']))
  td,fx,e,sp,dp=self.plan([claim()],state=state,decisions=d); self.addCleanup(td.cleanup); m=e.plan(SOURCE_ID,SNAPSHOT_ID,fx['synth_id'],fx['res_id'],synthesis_provider=PROVIDER,planning_state_path=sp,decision_path=dp); op=read_ops(fx['plan_root'],fx['synth_id'],fx['res_id'],m.run_id)[0]; self.assertEqual(op['operation'],'contradict'); self.assertIsNotNone(op['provisional_internal_id'])
 def test_supersede_claim(self):
  state={'schema_version':'0.1','claims':[{'internal_id':'q1','statement':'Old.','evidence_anchors':[],'status':'active'}],'relations':[]}; d=self.ledger(self.row('b0001-q0001','supersede',['q1']))
  td,fx,e,sp,dp=self.plan([claim()],state=state,decisions=d); self.addCleanup(td.cleanup); m=e.plan(SOURCE_ID,SNAPSHOT_ID,fx['synth_id'],fx['res_id'],synthesis_provider=PROVIDER,planning_state_path=sp,decision_path=dp); self.assertEqual(read_ops(fx['plan_root'],fx['synth_id'],fx['res_id'],m.run_id)[0]['operation'],'supersede')
 def test_ambiguous_concept_merge_decision(self):
  c=concept(); cat={'schema_version':'0.1','concepts':[catalog_concept('c1','Alpha 1','concepts/a1.md'),catalog_concept('c2','Alpha 2','concepts/a2.md')]}; r=[{'candidate_id':c['candidate_id'],'candidate_name':'Alpha','status':'ambiguous','method':'similarity','resolved_internal_id':None,'considered_internal_ids':['c1','c2'],'evidence_anchors':c['evidence_anchors'],'signals':[]}]; d=self.ledger(self.row(c['candidate_id'],'merge',['c1','c2'],'c1'))
  td,fx,e,sp,dp=self.plan([c],r,cat,decisions=d); self.addCleanup(td.cleanup); m=e.plan(SOURCE_ID,SNAPSHOT_ID,fx['synth_id'],fx['res_id'],synthesis_provider=PROVIDER,decision_path=dp); op=read_ops(fx['plan_root'],fx['synth_id'],fx['res_id'],m.run_id)[0]; self.assertEqual((op['operation'],op['survivor_internal_id']),('merge','c1'))
 def test_invalid_concept_update_decision_rejected(self):
  d=self.ledger(self.row('b0001-c0001','update',['x'],'x')); td,fx,e,sp,dp=self.plan([concept()],decisions=d); self.addCleanup(td.cleanup)
  with self.assertRaises(PlanningError): e.plan(SOURCE_ID,SNAPSHOT_ID,fx['synth_id'],fx['res_id'],synthesis_provider=PROVIDER,decision_path=dp)
 def test_unknown_decision_candidate_rejected(self):
  d=self.ledger(self.row('nope','ignore')); td,fx,e,sp,dp=self.plan([concept()],decisions=d); self.addCleanup(td.cleanup)
  with self.assertRaises(PlanningError): e.plan(SOURCE_ID,SNAPSHOT_ID,fx['synth_id'],fx['res_id'],synthesis_provider=PROVIDER,decision_path=dp)
 def test_ignore_with_targets_rejected(self):
  d=self.ledger(self.row('b0001-q0001','ignore',['x'])); td,fx,e,sp,dp=self.plan([claim()],decisions=d); self.addCleanup(td.cleanup)
  with self.assertRaises(PlanningError): e.plan(SOURCE_ID,SNAPSHOT_ID,fx['synth_id'],fx['res_id'],synthesis_provider=PROVIDER,decision_path=dp)
 def test_claim_update_target_must_exist(self):
  d=self.ledger(self.row('b0001-q0001','update',['x'],'x')); td,fx,e,sp,dp=self.plan([claim()],decisions=d); self.addCleanup(td.cleanup)
  with self.assertRaises(PlanningError): e.plan(SOURCE_ID,SNAPSHOT_ID,fx['synth_id'],fx['res_id'],synthesis_provider=PROVIDER,decision_path=dp)
 def test_relation_cannot_contradict(self):
  c1=concept(); c2=concept('b0001-c0002','Beta','Beta'); d=self.ledger(self.row('b0001-r0001','contradict',['r1'])); td,fx,e,sp,dp=self.plan([c1,c2,relation()],decisions=d); self.addCleanup(td.cleanup)
  with self.assertRaises(PlanningError): e.plan(SOURCE_ID,SNAPSHOT_ID,fx['synth_id'],fx['res_id'],synthesis_provider=PROVIDER,decision_path=dp)
 def test_summary_only_ignore_decision(self):
  d=self.ledger(self.row('b0001-s0001','ignore')); td,fx,e,sp,dp=self.plan([summary()],decisions=d); self.addCleanup(td.cleanup); m=e.plan(SOURCE_ID,SNAPSHOT_ID,fx['synth_id'],fx['res_id'],synthesis_provider=PROVIDER,decision_path=dp); self.assertEqual(read_ops(fx['plan_root'],fx['synth_id'],fx['res_id'],m.run_id)[0]['operation'],'ignore')

if __name__=='__main__': unittest.main()
