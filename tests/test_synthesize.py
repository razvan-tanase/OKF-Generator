from __future__ import annotations
import json, tempfile, unittest
from pathlib import Path
from okf_generator.synthesize import SynthesisEngine, SynthesisError
from synthesis_test_support import *

class SynthesisTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
        self.norm=self.root/'normalized'; self.out=self.root/'syntheses'
    def tearDown(self): self.tmp.cleanup()
    def engine(self, manifest, provider, **kwargs):
        return SynthesisEngine(normalization_root=self.norm,output_root=self.out,provider=provider,
            normalization_verifier=lambda s,i: manifest, **kwargs)
    def test_basic_candidates_and_relations(self):
        u=make_unit(1); m=write_normalized(self.norm,[u]); a=u['anchor_uri']
        out={'summaries':[{'text':'S','evidence_anchors':[a]}], 'concepts':[
            {'name':'A','description':'A','evidence_anchors':[a]}, {'name':'B','description':'B','evidence_anchors':[a]}],
            'claims':[{'statement':'C','evidence_anchors':[a]}],
            'relations':[{'subject_index':0,'predicate':'relates to','object_index':1,'evidence_anchors':[a]}]}
        p=FakeProvider([out]); r=self.engine(m,p).synthesize(SOURCE_ID,SNAPSHOT_ID,model='model-snapshot')
        self.assertEqual(r.candidate_counts,{'summary':1,'concept':2,'claim':1,'relation':1})
        d=self.out/SOURCE_ID/SNAPSHOT_ID/RULESET/EXTRACT/NORMALIZE/'builtin-v1'/'fixture'/r.run_id
        cs=[json.loads(x) for x in (d/'candidates.jsonl').read_text().splitlines()]
        rel=cs[-1]; self.assertEqual(rel['subject_candidate_id'],'b0001-c0001'); self.assertEqual(rel['object_candidate_id'],'b0001-c0002')
    def test_unknown_evidence_rejected(self):
        u=make_unit(1); m=write_normalized(self.norm,[u]); o=output_for('bad')
        with self.assertRaisesRegex(SynthesisError,'not present'):
            self.engine(m,FakeProvider([o])).synthesize(SOURCE_ID,SNAPSHOT_ID,model='m')
    def test_duplicate_evidence_rejected(self):
        u=make_unit(1); m=write_normalized(self.norm,[u]); o=output_for(u['anchor_uri']); o['claims'][0]['evidence_anchors']*=2
        with self.assertRaisesRegex(SynthesisError,'duplicate'):
            self.engine(m,FakeProvider([o])).synthesize(SOURCE_ID,SNAPSHOT_ID,model='m')
    def test_relation_index_rejected(self):
        u=make_unit(1); m=write_normalized(self.norm,[u]); o=output_for(u['anchor_uri']); o['relations']=[{'subject_index':0,'predicate':'x','object_index':2,'evidence_anchors':[u['anchor_uri']]}]
        with self.assertRaisesRegex(SynthesisError,'out-of-range'):
            self.engine(m,FakeProvider([o])).synthesize(SOURCE_ID,SNAPSHOT_ID,model='m')
    def test_extra_provider_field_rejected(self):
        u=make_unit(1); m=write_normalized(self.norm,[u]); o=output_for(u['anchor_uri']); o['extra']=1
        with self.assertRaisesRegex(SynthesisError,'schema mismatch'):
            self.engine(m,FakeProvider([o])).synthesize(SOURCE_ID,SNAPSHOT_ID,model='m')
    def test_batching_by_unit_count(self):
        units=[make_unit(i) for i in range(1,4)]; m=write_normalized(self.norm,units)
        p=FakeProvider([output_for(units[0]['anchor_uri']),output_for(units[2]['anchor_uri'])])
        r=self.engine(m,p,max_batch_units=2).synthesize(SOURCE_ID,SNAPSHOT_ID,model='m')
        self.assertEqual(r.batch_count,2); self.assertEqual(len(p.calls),2)
        self.assertEqual([len(json.loads(c.input_text)['units']) for c in p.calls],[2,1])
    def test_oversized_single_unit_rejected_before_provider(self):
        u=make_unit(1,'x'*2000); m=write_normalized(self.norm,[u]); p=FakeProvider([])
        with self.assertRaisesRegex(SynthesisError,'exceeds max_input_chars'):
            self.engine(m,p,max_input_chars=1024).synthesize(SOURCE_ID,SNAPSHOT_ID,model='m')
        self.assertEqual(p.calls,[])
    def test_empty_source_is_valid_zero_batch_run(self):
        m=write_normalized(self.norm,[]); p=FakeProvider([])
        r=self.engine(m,p).synthesize(SOURCE_ID,SNAPSHOT_ID,model='m')
        self.assertEqual(r.batch_count,0); self.assertEqual(sum(r.candidate_counts.values()),0)
    def test_same_receipts_and_output_are_idempotent(self):
        u=make_unit(1); m=write_normalized(self.norm,[u]); p=FakeProvider([output_for(u['anchor_uri'])])
        r1=self.engine(m,p).synthesize(SOURCE_ID,SNAPSHOT_ID,model='m')
        p2=FakeProvider([output_for(u['anchor_uri'])]); r2=self.engine(m,p2).synthesize(SOURCE_ID,SNAPSHOT_ID,model='m')
        self.assertEqual(r1.run_id,r2.run_id)
    def test_distinct_provider_receipt_makes_distinct_run(self):
        class P(FakeProvider):
            def generate(self,request):
                x=super().generate(request); return type(x)(x.output,'different',x.resolved_model,x.usage)
        u=make_unit(1); m=write_normalized(self.norm,[u])
        r1=self.engine(m,FakeProvider([output_for(u['anchor_uri'])])).synthesize(SOURCE_ID,SNAPSHOT_ID,model='m')
        r2=self.engine(m,P([output_for(u['anchor_uri'])])).synthesize(SOURCE_ID,SNAPSHOT_ID,model='m')
        self.assertNotEqual(r1.run_id,r2.run_id)
    def test_existing_run_tamper_detected(self):
        u=make_unit(1); m=write_normalized(self.norm,[u]); r=self.engine(m,FakeProvider([output_for(u['anchor_uri'])])).synthesize(SOURCE_ID,SNAPSHOT_ID,model='m')
        d=self.out/SOURCE_ID/SNAPSHOT_ID/RULESET/EXTRACT/NORMALIZE/'builtin-v1'/'fixture'/r.run_id
        (d/'candidates.jsonl').write_text('tamper\n')
        with self.assertRaisesRegex(SynthesisError,'modified'):
            self.engine(m,FakeProvider([output_for(u['anchor_uri'])])).synthesize(SOURCE_ID,SNAPSHOT_ID,model='m')
    def test_normalization_mutation_during_provider_call_rejected(self):
        u=make_unit(1); m=write_normalized(self.norm,[u]); path=norm_dir(self.norm)/'units.jsonl'
        def mutate(n):
            if n==1: path.write_text(path.read_text()+'{}\n')
        with self.assertRaisesRegex(SynthesisError,'changed while synthesis'):
            self.engine(m,FakeProvider([output_for(u['anchor_uri'])],mutate=mutate)).synthesize(SOURCE_ID,SNAPSHOT_ID,model='m')
    def test_normalization_units_hash_mismatch_rejected(self):
        u=make_unit(1); m=write_normalized(self.norm,[u]); m=dict(m); m['units_sha256']='0'*64
        with self.assertRaisesRegex(SynthesisError,'hash/path'):
            self.engine(m,FakeProvider([])).synthesize(SOURCE_ID,SNAPSHOT_ID,model='m')
    def test_normalization_unit_count_mismatch_rejected(self):
        u=make_unit(1); m=write_normalized(self.norm,[u]); m=dict(m); m['unit_count']=2
        with self.assertRaisesRegex(SynthesisError,'unit_count'):
            self.engine(m,FakeProvider([])).synthesize(SOURCE_ID,SNAPSHOT_ID,model='m')
    def test_duplicate_anchor_rejected(self):
        a=make_unit(1); b=make_unit(2,anchor=a['anchor_uri']); m=write_normalized(self.norm,[a,b])
        with self.assertRaisesRegex(SynthesisError,'duplicate normalized anchor'):
            self.engine(m,FakeProvider([])).synthesize(SOURCE_ID,SNAPSHOT_ID,model='m')
    def test_invalid_source_and_model_rejected(self):
        m=write_normalized(self.norm,[]); e=self.engine(m,FakeProvider([]))
        with self.assertRaises(SynthesisError): e.synthesize('../x',SNAPSHOT_ID,model='m')
        with self.assertRaises(SynthesisError): e.synthesize(SOURCE_ID,SNAPSHOT_ID,model='')
    def test_noncanonical_provider_usage_fails_closed(self):
        from okf_generator.synthesis_provider import ProviderResult
        class P(FakeProvider):
            def generate(self, request):
                return ProviderResult(output=output_for(request_input_anchor(request)), response_id="r", resolved_model=request.model, usage={"bad": float("nan")})
        def request_input_anchor(request):
            return json.loads(request.input_text)["units"][0]["anchor_uri"]
        u=make_unit(1); m=write_normalized(self.norm,[u])
        with self.assertRaisesRegex(SynthesisError,'non-canonical JSON'):
            self.engine(m,P([])).synthesize(SOURCE_ID,SNAPSHOT_ID,model='m')

    def test_request_capture_has_strict_schema(self):
        u=make_unit(1); m=write_normalized(self.norm,[u]); p=FakeProvider([output_for(u['anchor_uri'])])
        r=self.engine(m,p).synthesize(SOURCE_ID,SNAPSHOT_ID,model='m')
        d=self.out/SOURCE_ID/SNAPSHOT_ID/RULESET/EXTRACT/NORMALIZE/'builtin-v1'/'fixture'/r.run_id
        row=json.loads((d/'requests.jsonl').read_text().splitlines()[0])
        self.assertTrue(row['text']['format']['strict']); self.assertEqual(row['text']['format']['type'],'json_schema')

if __name__=='__main__': unittest.main()
