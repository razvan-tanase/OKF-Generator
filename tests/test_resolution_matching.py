import json, tempfile, unittest
from pathlib import Path
from okf_generator.resolve import ResolutionEngine
from resolution_test_support import *

class MatchingTests(unittest.TestCase):
    def run_engine(self, candidates, catalog_concepts=None, **kwargs):
        td=tempfile.TemporaryDirectory(); root=Path(td.name); synth=root/'s'; out=root/'o'; _,run_id=make_synthesis(synth,candidates)
        catalog=None
        if catalog_concepts is not None:
            catalog=root/'catalog.json'; write_catalog(catalog,catalog_concepts)
        m=ResolutionEngine(synthesis_root=synth,output_root=out,**kwargs).resolve(SOURCE,SNAP,run_id,synthesis_provider='openai',catalog_path=catalog)
        run=out/SOURCE/SNAP/'builtin-v1'/'builtin-v1'/'builtin-v1'/'builtin-v1'/'openai'/run_id/'builtin-v1'/m.run_id
        rows=[json.loads(x) for x in (run/'resolutions.jsonl').read_text().splitlines()]
        return td,m,rows,run
    def test_empty_catalog_marks_new(self):
        td,m,rows,_=self.run_engine([candidate_concept('b-c0001','Alpha')]); self.addCleanup(td.cleanup)
        self.assertEqual(rows[0]['status'],'new'); self.assertEqual(m.resolution_counts['new'],1)
    def test_exact_title_matches(self):
        td,_,rows,_=self.run_engine([candidate_concept('b-c0001','Alpha')],[concept('k1','Alpha')]); self.addCleanup(td.cleanup)
        self.assertEqual((rows[0]['status'],rows[0]['resolved_internal_id'],rows[0]['method']),('matched','k1','title-path-exact'))
    def test_alias_history_matches(self):
        td,_,rows,_=self.run_engine([candidate_concept('b-c0001','Old Alpha')],[concept('k1','Alpha',aliases=['Old Alpha'])]); self.addCleanup(td.cleanup)
        self.assertEqual(rows[0]['resolved_internal_id'],'k1'); self.assertEqual(rows[0]['method'],'alias-history-exact')
    def test_path_history_matches(self):
        td,_,rows,_=self.run_engine([candidate_concept('b-c0001','Old Alpha')],[concept('k1','Alpha',path_history=['old-alpha'])]); self.addCleanup(td.cleanup)
        self.assertEqual(rows[0]['resolved_internal_id'],'k1'); self.assertEqual(rows[0]['method'],'title-path-exact')
    def test_anchor_plus_name_precedes_title(self):
        a='okf-source:paper@sha256-'+('1'*64)+'#a1'
        cats=[concept('k1','Alpha',path='alpha-1',anchors=[a]),concept('k2','Alpha',path='alpha-2')]
        td,_,rows,_=self.run_engine([candidate_concept('b-c0001','Alpha',anchors=[a])],cats); self.addCleanup(td.cleanup)
        self.assertEqual(rows[0]['resolved_internal_id'],'k1'); self.assertEqual(rows[0]['method'],'source-anchor+name')
    def test_resource_plus_name(self):
        base='okf-source:paper@sha256-'+('1'*64)
        cats=[concept('k1','Alpha',path='alpha-1',resources=[base]),concept('k2','Alpha',path='alpha-2')]
        td,_,rows,_=self.run_engine([candidate_concept('b-c0001','Alpha')],cats); self.addCleanup(td.cleanup)
        self.assertEqual(rows[0]['resolved_internal_id'],'k1'); self.assertEqual(rows[0]['method'],'resource-uri+name')
    def test_duplicate_alias_is_ambiguous(self):
        cats=[concept('k1','A',aliases=['Shared']),concept('k2','B',aliases=['Shared'])]
        td,_,rows,_=self.run_engine([candidate_concept('b-c0001','Shared')],cats); self.addCleanup(td.cleanup)
        self.assertEqual(rows[0]['status'],'ambiguous'); self.assertEqual(rows[0]['considered_internal_ids'],['k1','k2'])
    def test_similarity_shortlist_is_not_auto_match(self):
        cats=[concept('k1','Distributed Cache',description='cache nodes distributed across cluster')]
        td,_,rows,_=self.run_engine([candidate_concept('b-c0001','Distributed caching',desc='cluster cache nodes')],cats,similarity_threshold=.2); self.addCleanup(td.cleanup)
        self.assertEqual(rows[0]['status'],'ambiguous'); self.assertEqual(rows[0]['method'],'similarity-shortlist')
    def test_no_concepts_emits_zero_rows(self):
        td,m,rows,_=self.run_engine([]); self.addCleanup(td.cleanup)
        self.assertEqual(rows,[]); self.assertEqual(m.resolution_counts,{'matched':0,'new':0,'ambiguous':0})

if __name__=='__main__': unittest.main()
