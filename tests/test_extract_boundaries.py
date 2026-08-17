from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import types
import unittest
import zipfile
from pathlib import Path

from okf_generator.extract import ExtractionEngine, ExtractionError
from okf_generator.extractors import extract_pdf
from extract_test_support import ExtractionCase


class ExtractionBoundaryTests(ExtractionCase):
    def test_zip_archive_preserves_member_identity_and_text(self):
        entry = self._entry(".", "zip", "archive", "application/zip")
        artifact, classification = self._setup("a.zip", "file", [entry])
        with zipfile.ZipFile(artifact, "w") as zf:
            zf.writestr("a.txt", b"hello")
            zf.writestr("b.bin", b"\x00\xff")
        self._engine(classification).extract(self.source_id, self.snapshot_id)
        units = self._read_units()
        self.assertEqual(units[0]["text"], "hello")
        self.assertIsNone(units[1]["text"])
        self.assertIn("archive-member-binary-not-decoded", units[1]["diagnostics"])

    @unittest.skipUnless(shutil.which("git"), "git required")
    def test_git_extracts_locked_commit_tree(self):
        entry = {"path":".","entry_kind":"directory","format":"git","route":"git","media_type":"application/x-git-repository","family":"repository","detection":{}}
        artifact, classification = self._setup("repository.git", "bare-git-repository", [entry],
            source_meta={"kind":"git-repository","artifact_kind":"bare-git-repository","primary_format":"git","primary_media_type":"application/x-git-repository","primary_route":"git"},
            version_lock={"kind":"git","commit":"placeholder"})
        work = self.root / "work"
        subprocess.run(["git","init","-q",str(work)], check=True)
        subprocess.run(["git","-C",str(work),"config","user.email","t@example.test"], check=True)
        subprocess.run(["git","-C",str(work),"config","user.name","T"], check=True)
        (work/"README.md").write_text("hello git", encoding="utf-8")
        subprocess.run(["git","-C",str(work),"add","README.md"], check=True)
        subprocess.run(["git","-C",str(work),"commit","-q","-m","x"], check=True)
        commit = subprocess.check_output(["git","-C",str(work),"rev-parse","HEAD"], text=True).strip()
        shutil.rmtree(artifact)
        subprocess.run(["git","clone","-q","--bare",str(work),str(artifact)], check=True)
        snap_path = self.snapshots/self.source_id/self.snapshot_id/"snapshot.json"
        snap = json.loads(snap_path.read_text())
        snap["version_lock"] = {"kind":"git","commit":commit}
        snap_path.write_text(json.dumps(snap, sort_keys=True))
        self._engine(classification).extract(self.source_id, self.snapshot_id)
        units = self._read_units()
        self.assertEqual(len(units), 1)
        self.assertEqual(units[0]["text"], "hello git")
        self.assertEqual(units[0]["native_locator"]["commit"], commit)

    def test_pdf_adapter_records_tool_and_empty_page_diagnostic_with_fake_reader(self):
        fake = types.ModuleType("pypdf")
        fake.__version__ = "6.16.1-test"
        class Page:
            def __init__(self, text): self._text = text
            def extract_text(self): return self._text
        class Reader:
            def __init__(self, *a, **k): self.pages = [Page("p1"), Page("")]
        fake.PdfReader = Reader
        old = sys.modules.get("pypdf")
        sys.modules["pypdf"] = fake
        try:
            path = self.root / "x.pdf"; path.write_bytes(b"%PDF-fake")
            result = extract_pdf(path, self._entry(".", "pdf", "pdf", "application/pdf"))
        finally:
            if old is None: sys.modules.pop("pypdf", None)
            else: sys.modules["pypdf"] = old
        self.assertEqual(result.tools["pypdf"], "6.16.1-test")
        self.assertIn("pdf-page-has-no-embedded-text", result.units[1].diagnostics)

    def test_idempotent_repeat_and_mutation_rejected(self):
        entry = self._entry(".", "text", "text", detection={"encoding_hint":"utf-8"})
        artifact, classification = self._setup("a.txt", "file", [entry]); artifact.write_text("x")
        engine = self._engine(classification)
        first = engine.extract(self.source_id, self.snapshot_id)
        second = engine.extract(self.source_id, self.snapshot_id)
        self.assertEqual(first, second)
        units_path = self.out/self.source_id/self.snapshot_id/self.ruleset/"builtin-v1"/"units.jsonl"
        units_path.write_text("tampered\n")
        with self.assertRaises(ExtractionError): engine.extract(self.source_id, self.snapshot_id)

    def test_mutation_during_extraction_is_rejected(self):
        entry = self._entry(".", "text", "text", detection={"encoding_hint":"utf-8"})
        artifact, classification = self._setup("a.txt", "file", [entry]); artifact.write_text("x")
        calls = 0
        def verifier(source_id, snapshot_id):
            nonlocal calls
            calls += 1
            if calls == 2:
                changed = dict(classification); changed["summary"] = {"changed": True}; return changed
            return classification
        engine = ExtractionEngine(self.snapshots, self.classifications, self.out, classification_verifier=verifier)
        with self.assertRaises(ExtractionError): engine.extract(self.source_id, self.snapshot_id)
        self.assertFalse((self.out/self.source_id/self.snapshot_id/self.ruleset/"builtin-v1").exists())

    def test_source_id_path_traversal_rejected(self):
        engine = ExtractionEngine(self.snapshots, self.classifications, self.out, classification_verifier=lambda *_: {})
        with self.assertRaises(ExtractionError): engine.extract("../escape", self.snapshot_id)

    def test_bad_classification_entry_path_rejected(self):
        entry = self._entry("../escape", "text", "text", detection={"encoding_hint":"utf-8"})
        artifact, classification = self._setup("docs", "directory", [self._entry(".","directory","directory",kind="directory"), entry])
        with self.assertRaises(ExtractionError): self._engine(classification).extract(self.source_id, self.snapshot_id)


if __name__ == "__main__":
    unittest.main()
