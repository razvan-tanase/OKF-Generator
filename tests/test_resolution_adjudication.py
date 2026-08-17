import json, tempfile, unittest
from pathlib import Path
from dataclasses import dataclass
from okf_generator.resolve import ResolutionEngine
from okf_generator.resolution_adjudication import AdjudicationResult
from okf_generator.resolution_errors import ResolutionError
from resolution_test_support import *

class FakeAdjudicator:
    name='fake'
    def __init__(self, output, hook=None): self.output=output; self.hook=hook
    def adjudicate(self, request):
        if self.hook: self.hook()
        return AdjudicationResult(self.output,response_id='r1',resolved_model='fixed',usage={'x':1})

class AdjudicationTests(unittest.TestCase):
    def setup_case(self, adj, catalog_concepts, candidate=None):
        td=tempfile.TemporaryDirectory(); root=Path(td.name); synth=root/'s'; out=root/'o'; _,run_id=make_synthesis(synth,[candidate or candidate_concept('b-c0001','Shared')])
        catalog=root/'catalog.json'; write_catalog(catalog,catalog_concepts)
        eng=ResolutionEngine(synthesis_root=synth,output_root=out,adjudicator=adj,similarity_threshold=.1)
        return td,root,synth,out,catalog,eng,run_id
    def read_rows(self,out,m,run_id):
        run=out/SOURCE/SNAP/'builtin-v1'/'builtin-v1'/'builtin-v1'/'builtin-v1'/'openai'/run_id/'builtin-v1'/m.run_id
        return [json.loads(x) for x in (run/'resolutions.jsonl').read_text().splitlines()],run
    def test_adjudicated_match(self):
        cats=[concept('k1','A',aliases=['Shared']),concept('k2','B',aliases=['Shared'])]
        td,_,_,out,cat,eng,run_id=self.setup_case(FakeAdjudicator({'decision':'match','internal_id':'k2','reason':'same concept'}),cats); self.addCleanup(td.cleanup)
        m=eng.resolve(SOURCE,SNAP,run_id,synthesis_provider='openai',catalog_path=cat,adjudication_model='model-x'); rows,run=self.read_rows(out,m,run_id)
        self.assertEqual((rows[0]['status'],rows[0]['resolved_internal_id'],rows[0]['method']),('matched','k2','adjudicated-match'))
        self.assertEqual(len((run/'adjudication-requests.jsonl').read_text().splitlines()),1)
    def test_adjudicated_new(self):
        cats=[concept('k1','Similar',description='Shared description')]
        td,_,_,out,cat,eng,run_id=self.setup_case(FakeAdjudicator({'decision':'new','internal_id':'','reason':'different'}),cats,candidate_concept('b-c0001','Shared',desc='Shared description')); self.addCleanup(td.cleanup)
        m=eng.resolve(SOURCE,SNAP,run_id,synthesis_provider='openai',catalog_path=cat,adjudication_model='model-x'); rows,_=self.read_rows(out,m,run_id)
        self.assertEqual(rows[0]['status'],'new')
    def test_invalid_match_outside_shortlist_rejected(self):
        cats=[concept('k1','A',aliases=['Shared']),concept('k2','B',aliases=['Shared'])]
        td,_,_,_,cat,eng,run_id=self.setup_case(FakeAdjudicator({'decision':'match','internal_id':'nope','reason':'bad'}),cats); self.addCleanup(td.cleanup)
        with self.assertRaises(ResolutionError): eng.resolve(SOURCE,SNAP,run_id,synthesis_provider='openai',catalog_path=cat,adjudication_model='model-x')
    def test_adjudicator_requires_model(self):
        cats=[concept('k1','A',aliases=['Shared']),concept('k2','B',aliases=['Shared'])]
        td,_,_,_,cat,eng,run_id=self.setup_case(FakeAdjudicator({'decision':'ambiguous','internal_id':'','reason':'tie'}),cats); self.addCleanup(td.cleanup)
        with self.assertRaises(ResolutionError): eng.resolve(SOURCE,SNAP,run_id,synthesis_provider='openai',catalog_path=cat)
    def test_catalog_mutation_during_call_rejected(self):
        cats=[concept('k1','A',aliases=['Shared']),concept('k2','B',aliases=['Shared'])]
        td,_,_,_,cat,_,run_id=self.setup_case(None,cats); self.addCleanup(td.cleanup)
        adj=FakeAdjudicator({'decision':'ambiguous','internal_id':'','reason':'tie'},hook=lambda: cat.write_text(cat.read_text()+' '))
        eng=ResolutionEngine(synthesis_root=Path(td.name)/'s',output_root=Path(td.name)/'o',adjudicator=adj)
        with self.assertRaisesRegex(ResolutionError,'catalog changed'): eng.resolve(SOURCE,SNAP,run_id,synthesis_provider='openai',catalog_path=cat,adjudication_model='m')

if __name__=='__main__': unittest.main()
