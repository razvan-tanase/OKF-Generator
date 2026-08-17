import json, tempfile, unittest
from pathlib import Path
from okf_generator.resolution_catalog import validate_catalog, load_catalog
from okf_generator.resolution_errors import ResolutionError
from resolution_test_support import concept, write_catalog

class CatalogTests(unittest.TestCase):
    def test_empty_catalog(self):
        cat, mode, source_sha, canonical_sha = load_catalog(None)
        self.assertEqual(mode,'empty'); self.assertIsNone(source_sha); self.assertEqual(cat['concepts'],[]); self.assertEqual(len(canonical_sha),64)
    def test_duplicate_internal_id_rejected(self):
        with self.assertRaises(ResolutionError): validate_catalog({'schema_version':'0.1','concepts':[concept('x','A'),concept('x','B')]})
    def test_duplicate_normalized_path_rejected(self):
        with self.assertRaises(ResolutionError): validate_catalog({'schema_version':'0.1','concepts':[concept('x','A',path='Foo'),concept('y','B',path='foo')]})
    def test_unsafe_path_rejected(self):
        with self.assertRaises(ResolutionError): validate_catalog({'schema_version':'0.1','concepts':[concept('x','A',path='../A')]})
    def test_file_hash_changes_with_bytes(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'c.json'; write_catalog(p,[concept('x','A')]); a=load_catalog(p); p.write_text(p.read_text()+' '); b=load_catalog(p)
            self.assertNotEqual(a[2],b[2]); self.assertEqual(a[3],b[3])

if __name__=='__main__': unittest.main()
