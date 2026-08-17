import json,tempfile,unittest
from pathlib import Path
from okf_generator.structuralize import StructuralizationEngine
from okf_generator.structural_errors import StructuralizationError
from structural_test_support import *

class StructuralIntegrityTests(unittest.TestCase):
 def test_repeat_is_byte_idempotent(self):
  td=tempfile.TemporaryDirectory(); self.addCleanup(td.cleanup); root=Path(td.name); loader=Loader(state([concept()])); e=StructuralizationEngine(root/"s",root/"o",state_loader=loader); a=e.structuralize(); before=(root/"o"/a.state_generation_id/a.profile/a.run_id/"documents.jsonl").read_bytes(); b=e.structuralize(); after=(root/"o"/b.state_generation_id/b.profile/b.run_id/"documents.jsonl").read_bytes(); self.assertEqual((a.run_id,b.run_id),(a.run_id,a.run_id)); self.assertEqual(before,after)
 def test_existing_run_tamper_rejected(self):
  td=tempfile.TemporaryDirectory(); self.addCleanup(td.cleanup); root=Path(td.name); loader=Loader(state([concept()])); e=StructuralizationEngine(root/"s",root/"o",state_loader=loader); m=e.structuralize(); p=root/"o"/m.state_generation_id/m.profile/m.run_id/"documents.jsonl"; p.write_text("bad\n"); self.assertRaises(StructuralizationError,e.structuralize)
 def test_state_mutation_detected_before_publication(self):
  td=tempfile.TemporaryDirectory(); self.addCleanup(td.cleanup); root=Path(td.name); loader=Loader(state([concept()]),mutate_second=True); e=StructuralizationEngine(root/"s",root/"o",state_loader=loader)
  with self.assertRaisesRegex(StructuralizationError,"changed while"):
   e.structuralize()
  self.assertFalse((root/"o").exists())
 def test_run_id_changes_with_generation(self):
  td=tempfile.TemporaryDirectory(); self.addCleanup(td.cleanup); root=Path(td.name); a=StructuralizationEngine(root/"s",root/"o",state_loader=Loader(state([concept()]),generation="sha256-"+"1"*64)).structuralize(); b=StructuralizationEngine(root/"s",root/"o",state_loader=Loader(state([concept()]),generation="sha256-"+"2"*64)).structuralize(); self.assertNotEqual(a.run_id,b.run_id)
 def test_identity_refs_are_stable_under_unrelated_addition(self):
  td=tempfile.TemporaryDirectory(); self.addCleanup(td.cleanup); root=Path(td.name); a=StructuralizationEngine(root/"s",root/"a",state_loader=Loader(state([concept("c1")]))).structuralize(); b=StructuralizationEngine(root/"s",root/"b",state_loader=Loader(state([concept("c1"),concept("c2","B","concepts/b.md")]))).structuralize(); ia=read_run(root/"a",a)[2]["entries"][0]["identity_ref"]; ib=next(x for x in read_run(root/"b",b)[2]["entries"] if x["internal_id"]=="c1")["identity_ref"]; self.assertEqual(ia,ib)

if __name__=='__main__': unittest.main()
