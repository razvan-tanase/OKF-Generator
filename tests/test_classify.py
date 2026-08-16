import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path

from okf_generator.classify import ClassificationEngine, ClassificationError, RULESET_ID
from okf_generator.snapshot import SnapshotManifest


def fake_manifest(root: Path, source_id: str, snapshot_id: str, artifact: Path, kind: str, version_lock=None):
    snapdir = root / source_id / snapshot_id
    snapdir.mkdir(parents=True, exist_ok=True)
    rel = artifact.relative_to(snapdir).as_posix()
    data = {
        "schema_version": "0.1", "stage": "02-snapshot", "source_id": source_id, "snapshot_id": snapshot_id,
        "artifact": {"path": rel, "kind": kind},
        "source_fingerprint": {"algorithm":"sha256","value":snapshot_id.removeprefix('sha256-'),"basis":"x"},
        "storage_fingerprint": {}, "acquisition": {}, "version_lock": version_lock or {"kind":"content-digest"}
    }
    (snapdir / "snapshot.json").write_text(json.dumps(data, sort_keys=True) + "\n")
    return SnapshotManifest(schema_version="0.1", stage="02-snapshot", source_id=source_id, snapshot_id=snapshot_id,
                            artifact=data["artifact"], source_fingerprint=data["source_fingerprint"], storage_fingerprint={},
                            acquisition={}, version_lock=data["version_lock"])


class ClassifyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.snapshots = self.root / "snapshots"
        self.out = self.root / "classified"
        self.sid = "sha256-" + "a" * 64
    def tearDown(self):
        self.tmp.cleanup()

    def engine_for(self, manifest):
        return ClassificationEngine(self.snapshots, self.out, snapshot_verifier=lambda s, i: manifest)

    def test_pdf_magic_overrides_wrong_extension(self):
        snapdir = self.snapshots / "paper" / self.sid
        artifact = snapdir / "payload" / "paper.zip"
        artifact.parent.mkdir(parents=True)
        artifact.write_bytes(b"%PDF-1.7\nbody")
        manifest = fake_manifest(self.snapshots, "paper", self.sid, artifact, "file")
        result = self.engine_for(manifest).classify("paper", self.sid)
        self.assertEqual(result.entries[0]["format"], "pdf")
        self.assertIn("extension-conflict:zip->pdf", result.entries[0]["diagnostics"])

    def test_markdown_requires_text_compatibility(self):
        snapdir = self.snapshots / "note" / self.sid
        artifact = snapdir / "payload" / "note.md"
        artifact.parent.mkdir(parents=True)
        artifact.write_text("# title\n")
        manifest = fake_manifest(self.snapshots, "note", self.sid, artifact, "file")
        result = self.engine_for(manifest).classify("note", self.sid)
        self.assertEqual(result.entries[0]["format"], "markdown")
        self.assertEqual(result.entries[0]["detection"]["basis"], "extension+text")

    def test_binary_markdown_is_not_routed_as_markdown(self):
        snapdir = self.snapshots / "bad" / self.sid
        artifact = snapdir / "payload" / "bad.md"
        artifact.parent.mkdir(parents=True)
        artifact.write_bytes(b"\x00\xff\x00\x80")
        manifest = fake_manifest(self.snapshots, "bad", self.sid, artifact, "file")
        result = self.engine_for(manifest).classify("bad", self.sid)
        self.assertEqual(result.entries[0]["format"], "binary")
        self.assertIn("extension-binary-conflict:markdown", result.entries[0]["diagnostics"])

    def test_docx_detected_by_container_structure_even_without_extension(self):
        snapdir = self.snapshots / "office" / self.sid
        artifact = snapdir / "payload" / "blob"
        artifact.parent.mkdir(parents=True)
        with zipfile.ZipFile(artifact, "w") as z:
            z.writestr("[Content_Types].xml", "x")
            z.writestr("word/document.xml", "x")
        manifest = fake_manifest(self.snapshots, "office", self.sid, artifact, "file")
        result = self.engine_for(manifest).classify("office", self.sid)
        self.assertEqual(result.entries[0]["format"], "docx")
        self.assertEqual(result.entries[0]["detection"]["basis"], "container")

    def test_fake_docx_zip_does_not_claim_docx(self):
        snapdir = self.snapshots / "office" / self.sid
        artifact = snapdir / "payload" / "fake.docx"
        artifact.parent.mkdir(parents=True)
        with zipfile.ZipFile(artifact, "w") as z:
            z.writestr("x.txt", "x")
        manifest = fake_manifest(self.snapshots, "office", self.sid, artifact, "file")
        result = self.engine_for(manifest).classify("office", self.sid)
        self.assertEqual(result.entries[0]["format"], "zip")
        self.assertIn("extension-conflict:docx->zip", result.entries[0]["diagnostics"])

    def test_directory_inventory_is_sorted_and_symlink_not_followed(self):
        snapdir = self.snapshots / "tree" / self.sid
        artifact = snapdir / "payload" / "tree"
        artifact.mkdir(parents=True)
        (artifact / "b.json").write_text("{}")
        (artifact / "a.md").write_text("A")
        if os.name != "nt":
            (artifact / "link").symlink_to("a.md")
        manifest = fake_manifest(self.snapshots, "tree", self.sid, artifact, "directory")
        result = self.engine_for(manifest).classify("tree", self.sid)
        paths = [e["path"] for e in result.entries]
        self.assertEqual(paths[:3], [".", "a.md", "b.json"])
        if os.name != "nt":
            self.assertEqual(result.entries[-1]["entry_kind"], "symlink")

    def test_sqlite_magic_classifies_database(self):
        snapdir = self.snapshots / "db" / self.sid
        artifact = snapdir / "payload" / "store.bin"
        artifact.parent.mkdir(parents=True)
        artifact.write_bytes(b"SQLite format 3\x00" + b"x" * 20)
        manifest = fake_manifest(self.snapshots, "db", self.sid, artifact, "file")
        result = self.engine_for(manifest).classify("db", self.sid)
        self.assertEqual(result.entries[0]["family"], "database")
        self.assertEqual(result.entries[0]["format"], "sqlite")

    def test_git_is_classified_at_repository_level_only(self):
        snapdir = self.snapshots / "repo" / self.sid
        artifact = snapdir / "payload" / "repository.git"
        artifact.mkdir(parents=True)
        (artifact / "objects").mkdir()
        manifest = fake_manifest(self.snapshots, "repo", self.sid, artifact, "bare-git-repository",
                                 {"kind":"git","object_format":"sha1","selected_object_type":"commit"})
        result = self.engine_for(manifest).classify("repo", self.sid)
        self.assertEqual(len(result.entries), 1)
        self.assertEqual(result.entries[0]["format"], "git")

    def test_output_has_no_time_and_is_idempotent(self):
        snapdir = self.snapshots / "x" / self.sid
        artifact = snapdir / "payload" / "x.txt"
        artifact.parent.mkdir(parents=True)
        artifact.write_text("hello")
        manifest = fake_manifest(self.snapshots, "x", self.sid, artifact, "file")
        engine = self.engine_for(manifest)
        a = engine.classify("x", self.sid)
        b = engine.classify("x", self.sid)
        self.assertEqual(a.to_json(), b.to_json())
        self.assertNotIn("timestamp", a.to_json().lower())
        self.assertNotIn("classified_at", a.to_json())

    def test_same_ruleset_output_cannot_be_overwritten(self):
        snapdir = self.snapshots / "x" / self.sid
        artifact = snapdir / "payload" / "x.txt"
        artifact.parent.mkdir(parents=True)
        artifact.write_text("hello")
        manifest = fake_manifest(self.snapshots, "x", self.sid, artifact, "file")
        engine = self.engine_for(manifest)
        engine.classify("x", self.sid)
        output = self.out / "x" / self.sid / RULESET_ID / "classification.json"
        output.write_text("{}\n")
        with self.assertRaises(ClassificationError):
            engine.classify("x", self.sid)

    def test_inconsistent_verifier_identity_is_rejected(self):
        snapdir = self.snapshots / "x" / self.sid
        artifact = snapdir / "payload" / "x.txt"
        artifact.parent.mkdir(parents=True)
        artifact.write_text("hello")
        manifest = fake_manifest(self.snapshots, "x", self.sid, artifact, "file")
        wrong = SnapshotManifest(**{**manifest.__dict__, "source_id":"other"})
        with self.assertRaises(ClassificationError):
            self.engine_for(wrong).classify("x", self.sid)

    def test_odt_detected_from_zip_mimetype(self):
        snapdir = self.snapshots / "odt" / self.sid
        artifact = snapdir / "payload" / "blob"
        artifact.parent.mkdir(parents=True)
        with zipfile.ZipFile(artifact, "w") as z:
            z.writestr("mimetype", "application/vnd.oasis.opendocument.text")
            z.writestr("content.xml", "x")
        manifest = fake_manifest(self.snapshots, "odt", self.sid, artifact, "file")
        result = self.engine_for(manifest).classify("odt", self.sid)
        self.assertEqual(result.entries[0]["format"], "odt")
        self.assertEqual(result.entries[0]["detection"]["basis"], "container")

    def test_snapshot_manifest_change_during_scan_is_rejected(self):
        snapdir = self.snapshots / "race" / self.sid
        artifact = snapdir / "payload" / "x.txt"
        artifact.parent.mkdir(parents=True)
        artifact.write_text("hello")
        manifest = fake_manifest(self.snapshots, "race", self.sid, artifact, "file")
        calls = {"n": 0}
        def verifier(source_id, snapshot_id):
            calls["n"] += 1
            if calls["n"] == 2:
                p = snapdir / "snapshot.json"
                p.write_text(p.read_text() + " ")
            return manifest
        engine = ClassificationEngine(self.snapshots, self.out, snapshot_verifier=verifier)
        with self.assertRaises(ClassificationError):
            engine.classify("race", self.sid)

    def test_default_verifier_rejects_snapshot_path_identity_mismatch(self):
        sid = "sha256-" + "b" * 64
        snapdir = self.snapshots / "x" / sid
        artifact = snapdir / "payload" / "x.txt"
        artifact.parent.mkdir(parents=True)
        artifact.write_text("hello")
        manifest = fake_manifest(self.snapshots, "x", sid, artifact, "file")
        data = json.loads((snapdir / "snapshot.json").read_text())
        data["source_fingerprint"]["value"] = "c" * 64
        (snapdir / "snapshot.json").write_text(json.dumps(data))
        engine = ClassificationEngine(self.snapshots, self.out)
        with self.assertRaises(ClassificationError):
            engine.classify("x", sid)

if __name__ == "__main__":
    unittest.main()
