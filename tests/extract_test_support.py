from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
import zipfile
from pathlib import Path

from okf_generator.extract import ExtractionEngine, ExtractionError
from okf_generator.extractors import extract_pdf


class ExtractionCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.snapshots = self.root / "snapshots"
        self.classifications = self.root / "classifications"
        self.out = self.root / "extractions"
        self.source_id = "source"
        self.snapshot_id = "sha256-" + "a" * 64
        self.ruleset = "builtin-v1"

    def tearDown(self):
        self.tmp.cleanup()

    def _setup(self, artifact_name: str, artifact_kind: str, classification_entries, source_meta=None, version_lock=None):
        snap = self.snapshots / self.source_id / self.snapshot_id
        payload = snap / "payload"
        payload.mkdir(parents=True)
        artifact = payload / artifact_name
        if artifact_kind == "directory":
            artifact.mkdir()
        elif artifact_kind == "bare-git-repository":
            artifact.mkdir()
        else:
            artifact.parent.mkdir(parents=True, exist_ok=True)
        snapshot = {
            "stage": "02-snapshot", "source_id": self.source_id, "snapshot_id": self.snapshot_id,
            "artifact": {"path": f"payload/{artifact_name}", "kind": artifact_kind},
            "version_lock": version_lock or {"kind": "content-digest", "sha256": "a" * 64},
        }
        (snap / "snapshot.json").write_text(json.dumps(snapshot, sort_keys=True), encoding="utf-8")
        cdir = self.classifications / self.source_id / self.snapshot_id / self.ruleset
        cdir.mkdir(parents=True)
        classification = {
            "stage": "03-classify", "ruleset": self.ruleset, "source_id": self.source_id,
            "snapshot_id": self.snapshot_id,
            "source": source_meta or {"kind": artifact_kind, "artifact_kind": artifact_kind,
                                      "primary_format": classification_entries[0]["format"],
                                      "primary_media_type": classification_entries[0]["media_type"],
                                      "primary_route": classification_entries[0]["route"]},
            "entries": classification_entries,
            "summary": {},
        }
        (cdir / "classification.json").write_text(json.dumps(classification, sort_keys=True), encoding="utf-8")
        return artifact, classification

    def _engine(self, classification):
        def verifier(source_id, snapshot_id):
            self.assertEqual(source_id, self.source_id)
            self.assertEqual(snapshot_id, self.snapshot_id)
            return classification
        return ExtractionEngine(self.snapshots, self.classifications, self.out, classification_verifier=verifier)

    @staticmethod
    def _entry(path, fmt, route, media="text/plain", kind="file", detection=None):
        return {"path": path, "entry_kind": kind, "format": fmt, "route": route, "media_type": media,
                "family": "text", "detection": detection or {}}

    def _read_units(self):
        p = self.out / self.source_id / self.snapshot_id / self.ruleset / "builtin-v1" / "units.jsonl"
        return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines()]

