from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from okf_generator.snapshot import SnapshotEngine, SnapshotError, fingerprint_payload


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.acquired = self.root / "acquired"
        self.snapshots = self.root / "snapshots"
        self.engine = SnapshotEngine(self.acquired, self.snapshots)

    def tearDown(self):
        self.tempdir.cleanup()

    def make_acquisition(self, source_id: str, artifact_name: str, kind: str, data: bytes = b"abc") -> Path:
        base = self.acquired / source_id
        payload = base / "payload"
        payload.mkdir(parents=True)
        artifact = payload / artifact_name
        artifact.write_bytes(data)
        receipt = {
            "schema_version": "0.1",
            "stage": "01-acquire",
            "source_id": source_id,
            "provider": "local",
            "locator": f"/{artifact_name}",
            "acquired_at": "2026-08-16T12:00:00Z",
            "artifact": {"path": f"payload/{artifact_name}", "kind": kind},
            "observations": {},
            "requested_ref": None,
        }
        (base / "receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
        return artifact

    def test_file_snapshot_is_content_addressed_and_preserves_bytes(self):
        artifact = self.make_acquisition("paper", "paper.pdf", "file", b"%PDF\x00\xff")
        expected = fingerprint_payload(artifact).digest
        manifest = self.engine.snapshot("paper")
        self.assertEqual(manifest.snapshot_id, f"sha256-{expected}")
        snapshot_dir = self.snapshots / "paper" / manifest.snapshot_id
        copied = snapshot_dir / manifest.artifact["path"]
        self.assertEqual(copied.read_bytes(), b"%PDF\x00\xff")
        self.assertEqual(manifest.source_fingerprint["value"], expected)
        self.assertEqual(manifest.version_lock["kind"], "content-digest")

    @unittest.skipIf(os.name == "nt", "portable executable-bit semantics differ on Windows")
    def test_file_fingerprint_includes_executable_bit(self):
        path = self.root / "script.sh"
        path.write_bytes(b"#!/bin/sh\n")
        path.chmod(0o644)
        first = fingerprint_payload(path).digest
        path.chmod(0o755)
        second = fingerprint_payload(path).digest
        self.assertNotEqual(first, second)

    def test_repeat_snapshot_is_idempotent(self):
        self.make_acquisition("x", "x.bin", "file", b"same")
        first = self.engine.snapshot("x")
        second = self.engine.snapshot("x")
        self.assertEqual(first.snapshot_id, second.snapshot_id)
        self.assertEqual(len(list((self.snapshots / "x").iterdir())), 1)

    def test_changed_acquisition_creates_new_version_without_overwrite(self):
        artifact = self.make_acquisition("x", "x.bin", "file", b"v1")
        first = self.engine.snapshot("x")
        artifact.write_bytes(b"v2")
        second = self.engine.snapshot("x")
        self.assertNotEqual(first.snapshot_id, second.snapshot_id)
        self.assertTrue((self.snapshots / "x" / first.snapshot_id).is_dir())
        self.assertTrue((self.snapshots / "x" / second.snapshot_id).is_dir())

    def test_directory_fingerprint_ignores_mtime_but_includes_empty_directories(self):
        left = self.root / "left"
        right = self.root / "right"
        for base in (left, right):
            (base / "empty").mkdir(parents=True)
            (base / "a.txt").write_bytes(b"A")
        os.utime(left / "a.txt", (1, 1))
        os.utime(right / "a.txt", (999999, 999999))
        self.assertEqual(fingerprint_payload(left).digest, fingerprint_payload(right).digest)
        (right / "empty").rmdir()
        self.assertNotEqual(fingerprint_payload(left).digest, fingerprint_payload(right).digest)

    @unittest.skipIf(os.name == "nt", "symlink semantics differ on Windows")
    def test_symlink_fingerprint_does_not_follow_target(self):
        base = self.acquired / "link"
        payload = base / "payload"
        payload.mkdir(parents=True)
        target = self.root / "outside.txt"
        target.write_text("one", encoding="utf-8")
        link = payload / "link.txt"
        link.symlink_to(target)
        receipt = {
            "schema_version": "0.1",
            "stage": "01-acquire",
            "source_id": "link",
            "provider": "local",
            "locator": "link",
            "acquired_at": "2026-08-16T12:00:00Z",
            "artifact": {"path": "payload/link.txt", "kind": "symlink"},
            "observations": {},
            "requested_ref": None,
        }
        (base / "receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
        first = self.engine.snapshot("link")
        target.write_text("two", encoding="utf-8")
        second = self.engine.snapshot("link")
        self.assertEqual(first.snapshot_id, second.snapshot_id)
        saved = self.snapshots / "link" / first.snapshot_id / first.artifact["path"]
        self.assertTrue(saved.is_symlink())
        self.assertEqual(os.readlink(saved), str(target))

    def test_tampered_snapshot_is_detected(self):
        self.make_acquisition("x", "x.bin", "file", b"original")
        manifest = self.engine.snapshot("x")
        snapshot_dir = self.snapshots / "x" / manifest.snapshot_id
        (snapshot_dir / manifest.artifact["path"]).write_bytes(b"tampered")
        with self.assertRaises(SnapshotError):
            self.engine.snapshot("x")

    def test_unsafe_artifact_path_is_rejected(self):
        base = self.acquired / "x"
        base.mkdir(parents=True)
        receipt = {
            "stage": "01-acquire",
            "source_id": "x",
            "artifact": {"path": "../escape", "kind": "file"},
        }
        (base / "receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
        with self.assertRaises(SnapshotError):
            self.engine.snapshot("x")

    def test_wrong_receipt_stage_is_rejected(self):
        base = self.acquired / "x"
        payload = base / "payload"
        payload.mkdir(parents=True)
        (payload / "x").write_bytes(b"x")
        (base / "receipt.json").write_text(
            json.dumps(
                {
                    "stage": "02-snapshot",
                    "source_id": "x",
                    "artifact": {"path": "payload/x", "kind": "file"},
                }
            ),
            encoding="utf-8",
        )
        with self.assertRaises(SnapshotError):
            self.engine.snapshot("x")

    @unittest.skipUnless(shutil.which("git"), "git executable is required")
    def test_git_snapshot_locks_requested_ref_to_immutable_commit(self):
        work = self.root / "work"
        subprocess.run(["git", "init", "-q", str(work)], check=True)
        subprocess.run(["git", "-C", str(work), "config", "user.email", "test@example.test"], check=True)
        subprocess.run(["git", "-C", str(work), "config", "user.name", "Test"], check=True)
        (work / "a.txt").write_text("A", encoding="utf-8")
        subprocess.run(["git", "-C", str(work), "add", "a.txt"], check=True)
        subprocess.run(["git", "-C", str(work), "commit", "-q", "-m", "first"], check=True)
        branch = subprocess.check_output(
            ["git", "-C", str(work), "branch", "--show-current"], text=True
        ).strip()
        commit = subprocess.check_output(
            ["git", "-C", str(work), "rev-parse", "HEAD"], text=True
        ).strip()

        base = self.acquired / "repo"
        payload = base / "payload"
        payload.mkdir(parents=True)
        bare = payload / "repository.git"
        subprocess.run(["git", "clone", "-q", "--bare", str(work), str(bare)], check=True)
        receipt = {
            "schema_version": "0.1",
            "stage": "01-acquire",
            "source_id": "repo",
            "provider": "git",
            "locator": str(work),
            "acquired_at": "2026-08-16T12:00:00Z",
            "artifact": {"path": "payload/repository.git", "kind": "bare-git-repository"},
            "observations": {"bare": True},
            "requested_ref": branch,
        }
        (base / "receipt.json").write_text(json.dumps(receipt), encoding="utf-8")

        manifest = self.engine.snapshot("repo")
        self.assertEqual(manifest.version_lock["commit"], commit)
        self.assertEqual(manifest.version_lock["selected_ref"], branch)
        self.assertEqual(manifest.source_fingerprint["basis"], "git-object-lock-v1")
        self.assertNotEqual(
            manifest.source_fingerprint["value"], manifest.storage_fingerprint["value"]
        )

    @unittest.skipUnless(shutil.which("git"), "git executable is required")
    def test_git_snapshot_preserves_annotated_tag_object(self):
        work = self.root / "tag-work"
        subprocess.run(["git", "init", "-q", str(work)], check=True)
        subprocess.run(["git", "-C", str(work), "config", "user.email", "test@example.test"], check=True)
        subprocess.run(["git", "-C", str(work), "config", "user.name", "Test"], check=True)
        (work / "a").write_text("a", encoding="utf-8")
        subprocess.run(["git", "-C", str(work), "add", "a"], check=True)
        subprocess.run(["git", "-C", str(work), "commit", "-q", "-m", "first"], check=True)
        subprocess.run(["git", "-C", str(work), "tag", "-a", "v1", "-m", "release"], check=True)
        tag_oid = subprocess.check_output(
            ["git", "-C", str(work), "rev-parse", "v1"], text=True
        ).strip()
        commit = subprocess.check_output(
            ["git", "-C", str(work), "rev-parse", "v1^{}"], text=True
        ).strip()

        base = self.acquired / "tagged"
        payload = base / "payload"
        payload.mkdir(parents=True)
        bare = payload / "repository.git"
        subprocess.run(["git", "clone", "-q", "--bare", str(work), str(bare)], check=True)
        (base / "receipt.json").write_text(
            json.dumps(
                {
                    "schema_version": "0.1",
                    "stage": "01-acquire",
                    "source_id": "tagged",
                    "provider": "git",
                    "locator": str(work),
                    "acquired_at": "2026-08-16T12:00:00Z",
                    "artifact": {
                        "path": "payload/repository.git",
                        "kind": "bare-git-repository",
                    },
                    "observations": {"bare": True},
                    "requested_ref": "v1",
                }
            ),
            encoding="utf-8",
        )
        manifest = self.engine.snapshot("tagged")
        self.assertEqual(manifest.version_lock["selected_object"], tag_oid)
        self.assertEqual(manifest.version_lock["selected_object_type"], "tag")
        self.assertEqual(manifest.version_lock["commit"], commit)


if __name__ == "__main__":
    unittest.main()
