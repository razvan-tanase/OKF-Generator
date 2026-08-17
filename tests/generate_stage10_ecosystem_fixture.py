from pathlib import Path
import sys,tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from okf_generator.structuralize import StructuralizationEngine
from structural_test_support import *
out=Path(sys.argv[1]).resolve(); work=out.parent/".stage10-fixture-work"
st=state([concept(),concept("c2","Beta","concepts/beta.md")],[summary()],[claim("q1",contradicts=["q2"]),claim("q2","Beta claim")],[relation()])
m=StructuralizationEngine(work/"state",work/"structural",state_loader=Loader(st)).structuralize(); docs=read_run(work/"structural",m)[1]; materialize_fixture(docs,out); print(out)
