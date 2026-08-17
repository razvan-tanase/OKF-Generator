import tempfile,unittest
from pathlib import Path
from okf_generator.compile import CompilationEngine
from okf_generator.structuralize import StructuralizationEngine
from okf_generator.structural_errors import StructuralizationError
from compilation_test_support import *
from structural_test_support import read_run

class StructuralStateTests(unittest.TestCase):
 def compiled(self,tmp):
  pc="urn:okf-generator:concept:sha256-"+"1"*64
  b=bundle([op(1,"create","concept",prov=pc,path="concepts/alpha.md",payload={"name":"Alpha","description":"A"})])
  return CompilationEngine(tmp/"s",tmp/"r",tmp/"p",tmp/"state",plan_verifier=Verifier(b)).compile(SOURCE_ID,SNAPSHOT_ID,SYNTH_RUN,RES_RUN,PLAN_RUN,synthesis_provider=PROVIDER)
 def test_default_loads_exact_active_stage09_generation(self):
  td=tempfile.TemporaryDirectory(); self.addCleanup(td.cleanup); t=Path(td.name); c=self.compiled(t); m=StructuralizationEngine(t/"state",t/"structural").structuralize(); self.assertEqual(m.state_generation_id,c.generation_id); self.assertEqual(read_run(t/"structural",m)[1][0]["path"],"concepts/alpha.md")
 def test_explicit_generation_loads_without_pointer_selection(self):
  td=tempfile.TemporaryDirectory(); self.addCleanup(td.cleanup); t=Path(td.name); c=self.compiled(t); m=StructuralizationEngine(t/"state",t/"structural").structuralize(c.generation_id); self.assertEqual(m.state_generation_id,c.generation_id)
 def test_missing_current_generation_rejected(self):
  td=tempfile.TemporaryDirectory(); self.addCleanup(td.cleanup); t=Path(td.name); self.assertRaises(StructuralizationError,StructuralizationEngine(t/"state",t/"structural").structuralize)
 def test_tampered_generation_rejected(self):
  td=tempfile.TemporaryDirectory(); self.addCleanup(td.cleanup); t=Path(td.name); c=self.compiled(t); p=t/"state"/"generations"/c.generation_id/"concepts.jsonl"; p.write_text("bad\n"); self.assertRaises(StructuralizationError,StructuralizationEngine(t/"state",t/"structural").structuralize)

if __name__=='__main__': unittest.main()
