import re,tempfile,unittest
from pathlib import Path
import yaml
from okf_generator.structuralize import StructuralizationEngine
from structural_test_support import *

OPENWIKI_COMMIT="79dd5fc2b3561c723c9abcfadb5359a0234f1221"
OKFY_COMMIT="c73caa4fb7fdb0e2a6f69f2c677a4b632df4b226"

def parse_frontmatter(text):
 if not text.startswith("---\n"): return None
 end=text.find("\n---\n",4)
 if end<0: return None
 return yaml.safe_load(text[4:end])
def replay_openwiki_contract(root:Path):
 issues=[]
 for p in root.rglob("*.md"):
  if p.name in {"index.md","log.md"}: continue
  fm=parse_frontmatter(p.read_text())
  if not isinstance(fm,dict): issues.append((p,"missing/invalid frontmatter")); continue
  if not isinstance(fm.get("type"),str) or not fm["type"].strip(): issues.append((p,"missing type"))
  for key in ("title","description","resource","timestamp"):
   if key in fm and (not isinstance(fm[key],str) or not fm[key].strip()): issues.append((p,"invalid "+key))
  if "tags" in fm and (not isinstance(fm["tags"],list) or any(not isinstance(x,str) or not x.strip() for x in fm["tags"])): issues.append((p,"invalid tags"))
 return issues
def replay_okfy_contract(root:Path):
 issues=[]
 idx=root/"index.md"; fm=parse_frontmatter(idx.read_text());
 if fm!={"okf_version":"0.1"}: issues.append((idx,"root index frontmatter"))
 log=(root/"log.md").read_text()
 if log.startswith("---"): issues.append((root/"log.md","log frontmatter"))
 if not re.search(r"^#\s+",log,re.M): issues.append((root/"log.md","log H1"))
 for p in root.rglob("*.md"):
  if p.name in {"index.md","log.md"}: continue
  fm=parse_frontmatter(p.read_text())
  if not isinstance(fm,dict) or not isinstance(fm.get("type"),str) or not fm["type"].strip(): issues.append((p,"concept type"))
 return issues

class EcosystemContractTests(unittest.TestCase):
 def fixture(self):
  td=tempfile.TemporaryDirectory(); root=Path(td.name); st=state([concept(),concept("c2","Beta","concepts/beta.md")],[summary()],[claim("q1",contradicts=["q2"]),claim("q2","Beta claim")],[relation()]); m=StructuralizationEngine(root/"s",root/"o",state_loader=Loader(st)).structuralize(); docs=read_run(root/"o",m)[1]; bundle=materialize_fixture(docs,root/"bundle"); return td,bundle
 def test_openwiki_pinned_contract_replay(self):
  td,bundle=self.fixture(); self.addCleanup(td.cleanup); self.assertEqual(replay_openwiki_contract(bundle),[],OPENWIKI_COMMIT)
 def test_okfy_pinned_contract_replay(self):
  td,bundle=self.fixture(); self.addCleanup(td.cleanup); self.assertEqual(replay_okfy_contract(bundle),[],OKFY_COMMIT)
 def test_materialized_internal_links_resolve(self):
  td,bundle=self.fixture(); self.addCleanup(td.cleanup)
  for p in bundle.rglob("*.md"):
   for target in re.findall(r"\[[^\]]+\]\(([^)]+\.md)\)",p.read_text()):
    resolved=(p.parent/target).resolve(); self.assertTrue(resolved.is_file(),f"{p}: {target}")

if __name__=='__main__': unittest.main()
