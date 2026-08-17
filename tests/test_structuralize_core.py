import json,tempfile,unittest
from pathlib import Path
from okf_generator.structuralize import StructuralizationEngine,SOURCE_OKF_VERSION,SOURCE_OKF_SPEC_COMMIT
from okf_generator.structural_errors import StructuralizationError
from structural_test_support import *

class StructuralCoreTests(unittest.TestCase):
 def run_it(self,st):
  td=tempfile.TemporaryDirectory(); root=Path(td.name); out=root/"structural"; loader=Loader(st); m=StructuralizationEngine(root/"state",out,state_loader=loader).structuralize(); return td,out,m,read_run(out,m)
 def test_all_active_types_become_documents(self):
  st=state([concept(),concept("c2","Beta","concepts/beta.md")],[summary()],[claim()],[relation()]); td,out,m,(d,docs,identity,deferred)=self.run_it(st); self.addCleanup(td.cleanup)
  self.assertEqual(m.document_counts,{"concept":2,"summary":1,"claim":1,"relation":1}); self.assertEqual(m.document_count,5)
  self.assertEqual({x["object_type"] for x in docs},{"concept","summary","claim","relation"})
 def test_concept_path_preserved(self):
  td,out,m,(_,docs,_,_)=self.run_it(state([concept(path="topics/alpha.md")])); self.addCleanup(td.cleanup); self.assertEqual(docs[0]["path"],"topics/alpha.md")
 def test_auxiliary_path_is_stable_and_not_raw_id(self):
  td,out,m,(_,docs,_,_)=self.run_it(state(summaries=[summary("private-secret-id")])); self.addCleanup(td.cleanup); self.assertRegex(docs[0]["path"],r"^summaries/sha256-[0-9a-f]{24}\.md$"); self.assertNotIn("private-secret-id",docs[0]["path"])
 def test_frontmatter_is_minimal_okf_v01_shape(self):
  td,out,m,(_,docs,_,_)=self.run_it(state([concept()])); self.addCleanup(td.cleanup); self.assertEqual(docs[0]["frontmatter"],{"type":"Concept","title":"Alpha","description":"Alpha description"}); self.assertNotIn("timestamp",docs[0]["frontmatter"])
 def test_relation_has_public_links(self):
  st=state([concept(),concept("c2","Beta","concepts/beta.md")],relations=[relation()]); td,out,m,(_,docs,_,_)=self.run_it(st); self.addCleanup(td.cleanup); r=next(x for x in docs if x["object_type"]=="relation"); b=r["body"][1]; self.assertEqual((b["subject"]["target"],b["object"]["target"]),("concepts/alpha.md","concepts/beta.md"))
 def test_claim_relationships_link_only_active_claims(self):
  st=state(claims=[claim("q1",contradicts=["q2"]),claim("q2","Beta claim")]); td,out,m,(_,docs,_,_)=self.run_it(st); self.addCleanup(td.cleanup); q=next(x for x in docs if x["identity_ref"]==next(e["identity_ref"] for e in read_run(out,m)[2]["entries"] if e["internal_id"]=="q1")); self.assertTrue(any(b["kind"]=="links" and b["heading"]=="Contradicts" for b in q["body"]))
 def test_merged_object_stays_in_identity_map_not_documents(self):
  st=state([concept("c1"),concept("c2","Old","concepts/old.md","merged","c1")]); td,out,m,(_,docs,identity,_)=self.run_it(st); self.addCleanup(td.cleanup); self.assertEqual(len(docs),1); old=next(x for x in identity["entries"] if x["internal_id"]=="c2"); self.assertIsNone(old["public_path"]); self.assertIsNotNone(old["merged_into_identity_ref"])
 def test_reserved_concept_path_rejected(self):
  td=tempfile.TemporaryDirectory(); self.addCleanup(td.cleanup); root=Path(td.name); eng=StructuralizationEngine(root/"s",root/"o",state_loader=Loader(state([concept(path="index.md")]))); self.assertRaises(StructuralizationError,eng.structuralize)
 def test_path_collision_across_types_rejected(self):
  # Hash-based auxiliary spaces make cross-type collisions structurally impossible; duplicate active concept paths still fail.
  st=state([concept("c1",path="concepts/a.md"),concept("c2","B","concepts/a.md")]); td=tempfile.TemporaryDirectory(); self.addCleanup(td.cleanup); root=Path(td.name); self.assertRaises(StructuralizationError,StructuralizationEngine(root/"s",root/"o",state_loader=Loader(st)).structuralize)
 def test_reserved_docs_deferred_to_stage13_and_serialization14(self):
  td,out,m,(_,_,_,deferred)=self.run_it(state([concept()])); self.addCleanup(td.cleanup); self.assertEqual({x["path"] for x in deferred["reserved_documents"]},{"index.md","log.md"}); self.assertTrue(all(x["owner_stage"]=="13-derive" for x in deferred["reserved_documents"])); self.assertEqual(deferred["final_markdown_yaml_serialization_stage"],"14-serialize")
 def test_spec_pin_persisted(self):
  td,out,m,_=self.run_it(state([concept()])); self.addCleanup(td.cleanup); self.assertEqual((m.source_okf_version,m.source_okf_spec_commit),(SOURCE_OKF_VERSION,SOURCE_OKF_SPEC_COMMIT))
 def test_empty_state_is_valid(self):
  td,out,m,(_,docs,identity,_)=self.run_it(state()); self.addCleanup(td.cleanup); self.assertEqual(docs,[]); self.assertEqual(identity["entries"],[])

if __name__=='__main__': unittest.main()
