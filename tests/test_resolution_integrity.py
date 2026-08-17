import json, tempfile, unittest
from pathlib import Path
from okf_generator.resolve import ResolutionEngine
from okf_generator.resolution_errors import ResolutionError
from resolution_test_support import *

class IntegrityTests(unittest.TestCase):
    def test_candidate_hash_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); run,run_id=make_synthesis(root/'s',[candidate_concept('b-c0001','A')]); (run/'candidates.jsonl').write_text((run/'candidates.jsonl').read_text()+'{}\n')
            with self.assertRaisesRegex(ResolutionError,'hash mismatch'): ResolutionEngine(synthesis_root=root/'s',output_root=root/'o').resolve(SOURCE,SNAP,run_id,synthesis_provider='openai')
    def test_relation_unknown_endpoint_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); _,run_id=make_synthesis(root/'s',[candidate_concept('b-c0001','A')],[candidate_relation('b-r0001','b-c0001','missing')])
            with self.assertRaisesRegex(ResolutionError,'unknown concept'): ResolutionEngine(synthesis_root=root/'s',output_root=root/'o').resolve(SOURCE,SNAP,run_id,synthesis_provider='openai')
    def test_coordinated_manifest_tamper_rejected_by_run_id(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); run,run_id=make_synthesis(root/'s',[candidate_concept('b-c0001','A')]); p=run/'synthesis.json'; m=json.loads(p.read_text()); m['requested_model']='other-model'; p.write_text(json.dumps(m,indent=2,sort_keys=True)+'\n')
            with self.assertRaisesRegex(ResolutionError,'run_id does not match'): ResolutionEngine(synthesis_root=root/'s',output_root=root/'o').resolve(SOURCE,SNAP,run_id,synthesis_provider='openai')
    def test_invalid_source_id_rejected(self):
        eng=ResolutionEngine(synthesis_root='x',output_root='y')
        with self.assertRaises(ResolutionError): eng.resolve('../x',SNAP,'sha256-'+'2'*64,synthesis_provider='openai')
    def test_invalid_provider_rejected(self):
        eng=ResolutionEngine(synthesis_root='x',output_root='y')
        with self.assertRaises(ResolutionError): eng.resolve(SOURCE,SNAP,'sha256-'+'2'*64,synthesis_provider='../openai')
    def test_invalid_run_id_rejected(self):
        eng=ResolutionEngine(synthesis_root='x',output_root='y')
        with self.assertRaises(ResolutionError): eng.resolve(SOURCE,SNAP,'bad',synthesis_provider='openai')
    def test_repeat_is_idempotent_and_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); _,run_id=make_synthesis(root/'s',[candidate_concept('b-c0001','A')]); eng=ResolutionEngine(synthesis_root=root/'s',output_root=root/'o')
            a=eng.resolve(SOURCE,SNAP,run_id,synthesis_provider='openai'); b=eng.resolve(SOURCE,SNAP,run_id,synthesis_provider='openai'); self.assertEqual(a.run_id,b.run_id)
            run=root/'o'/SOURCE/SNAP/'builtin-v1'/'builtin-v1'/'builtin-v1'/'builtin-v1'/'openai'/run_id/'builtin-v1'/a.run_id
            (run/'resolutions.jsonl').write_text('{}\n')
            with self.assertRaisesRegex(ResolutionError,'existing resolution run differs'): eng.resolve(SOURCE,SNAP,run_id,synthesis_provider='openai')

if __name__=='__main__': unittest.main()
