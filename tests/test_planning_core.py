import tempfile,unittest,json
from pathlib import Path
from okf_generator.plan import PlanningEngine
from planning_test_support import *

class PlanningCoreTests(unittest.TestCase):
 def run_plan(self,candidates,resolutions=None,catalog=None,state=None,decisions=None):
  td=tempfile.TemporaryDirectory(); tmp=Path(td.name); fx=build_fixture(tmp,candidates,resolutions,catalog)
  sp=dp=None
  if state is not None: sp=tmp/'state.json'; sp.write_text(json.dumps(state))
  if decisions is not None: dp=tmp/'decisions.json'; dp.write_text(json.dumps(decisions))
  m=PlanningEngine(fx['synth_root'],fx['res_root'],fx['plan_root']).plan(SOURCE_ID,SNAPSHOT_ID,fx['synth_id'],fx['res_id'],synthesis_provider=PROVIDER,planning_state_path=sp,decision_path=dp)
  return td,fx,m,read_ops(fx['plan_root'],fx['synth_id'],fx['res_id'],m.run_id)
 def test_first_run_all_candidate_types(self):
  cs=[summary(),concept(),concept('b0001-c0002','Beta','Beta concept'),claim(),relation()]
  td,fx,m,ops=self.run_plan(cs); self.addCleanup(td.cleanup)
  self.assertEqual([o['operation'] for o in ops],['create','create','create','create','create'])
  self.assertEqual([o['object_type'] for o in ops],['concept','concept','summary','claim','relation'])
  self.assertTrue(ops[0]['proposed_canonical_path'].startswith('concepts/alpha'))
  self.assertEqual(ops[-1]['payload']['subject_internal_id'],ops[0]['provisional_internal_id'])
  self.assertEqual(m.blocked_count,0)
 def test_matched_concept_updates(self):
  c=concept(); cat={'schema_version':'0.1','concepts':[catalog_concept()]}; r=[{'candidate_id':c['candidate_id'],'candidate_name':'Alpha','status':'matched','method':'title-path-exact','resolved_internal_id':'concept-1','considered_internal_ids':['concept-1'],'evidence_anchors':c['evidence_anchors'],'signals':[]}]
  td,fx,m,ops=self.run_plan([c],r,cat); self.addCleanup(td.cleanup); self.assertEqual((ops[0]['operation'],ops[0]['target_internal_ids']),('update',['concept-1']))
 def test_ambiguous_concept_blocks(self):
  c=concept(); cat={'schema_version':'0.1','concepts':[catalog_concept('c1','Alpha One','concepts/a1.md'),catalog_concept('c2','Alpha Two','concepts/a2.md')]}; r=[{'candidate_id':c['candidate_id'],'candidate_name':'Alpha','status':'ambiguous','method':'similarity-shortlist','resolved_internal_id':None,'considered_internal_ids':['c1','c2'],'evidence_anchors':c['evidence_anchors'],'signals':[]}]
  td,fx,m,ops=self.run_plan([c],r,cat); self.addCleanup(td.cleanup); self.assertEqual(ops[0]['operation'],'ignore'); self.assertEqual(m.blocked_count,1)
 def test_relation_with_ambiguous_endpoint_ignored(self):
  c1=concept(); c2=concept('b0001-c0002','Beta','Beta'); rel=relation(); cat={'schema_version':'0.1','concepts':[catalog_concept('x','Alpha X','concepts/x.md')]}; rs=[{'candidate_id':c1['candidate_id'],'candidate_name':'Alpha','status':'ambiguous','method':'similarity-shortlist','resolved_internal_id':None,'considered_internal_ids':['x'],'evidence_anchors':c1['evidence_anchors'],'signals':[]},{'candidate_id':c2['candidate_id'],'candidate_name':'Beta','status':'new','method':'none','resolved_internal_id':None,'considered_internal_ids':[],'evidence_anchors':c2['evidence_anchors'],'signals':[]}]
  td,fx,m,ops=self.run_plan([c1,c2,rel],rs,cat); self.addCleanup(td.cleanup); self.assertEqual(ops[-1]['operation'],'ignore'); self.assertEqual(ops[-1]['reason'],'relation-endpoint-unresolved')
 def test_exact_new_concept_duplicate_merges(self):
  td,fx,m,ops=self.run_plan([concept(),concept('b0002-c0001')]); self.addCleanup(td.cleanup); self.assertEqual([o['operation'] for o in ops],['create','merge']); self.assertEqual(ops[1]['target_internal_ids'],[ops[0]['provisional_internal_id']])
 def test_path_collision_gets_hash_suffix(self):
  c=concept(name='Alpha',description='different'); cat={'schema_version':'0.1','concepts':[catalog_concept('c1','Other','concepts/alpha.md')]}
  td,fx,m,ops=self.run_plan([c],catalog=cat); self.addCleanup(td.cleanup); self.assertIn('--',ops[0]['proposed_canonical_path'])
 def test_exact_existing_claim_updates(self):
  state={'schema_version':'0.1','claims':[{'internal_id':'q1','statement':'Alpha is useful.','evidence_anchors':['old'],'status':'active'}],'relations':[]}
  td,fx,m,ops=self.run_plan([claim()],state=state); self.addCleanup(td.cleanup); self.assertEqual((ops[0]['operation'],ops[0]['target_internal_ids']),('update',['q1']))
 def test_exact_new_claim_duplicate_merges(self):
  td,fx,m,ops=self.run_plan([claim(),claim('b0002-q0001')]); self.addCleanup(td.cleanup); self.assertEqual([o['operation'] for o in ops],['create','merge'])
 def test_existing_relation_updates(self):
  c1=concept(); c2=concept('b0001-c0002','Beta','Beta'); cat={'schema_version':'0.1','concepts':[catalog_concept('a','Alpha','concepts/a.md'),catalog_concept('b','Beta','concepts/b.md')]}; rs=[]
  for c,t in [(c1,'a'),(c2,'b')]: rs.append({'candidate_id':c['candidate_id'],'candidate_name':c['name'],'status':'matched','method':'title-path-exact','resolved_internal_id':t,'considered_internal_ids':[t],'evidence_anchors':c['evidence_anchors'],'signals':[]})
  state={'schema_version':'0.1','claims':[],'relations':[{'internal_id':'r1','subject_internal_id':'a','predicate':'relates to','object_internal_id':'b','evidence_anchors':['old'],'status':'active'}]}
  td,fx,m,ops=self.run_plan([c1,c2,relation()],rs,cat,state); self.addCleanup(td.cleanup); self.assertEqual(ops[-1]['operation'],'update'); self.assertEqual(ops[-1]['target_internal_ids'],['r1'])
 def test_duplicate_summary_merges(self):
  td,fx,m,ops=self.run_plan([summary(),summary('b0002-s0001')]); self.addCleanup(td.cleanup); self.assertEqual([o['operation'] for o in ops],['create','merge'])
 def test_operation_counts(self):
  td,fx,m,ops=self.run_plan([concept(),claim()]); self.addCleanup(td.cleanup); self.assertEqual(m.operation_count,2); self.assertEqual(m.operation_counts['create'],2); self.assertEqual(m.object_counts['concept'],1)

if __name__=='__main__': unittest.main()
