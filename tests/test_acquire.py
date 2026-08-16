from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from okf_generator.acquire import (
    AcquisitionEngine,
    AcquisitionError,
    AcquisitionSpec,
    infer_provider,
    load_receipt,
)


FIXED_TIME = datetime(2026, 8, 16, 12, 0, 0, tzinfo=timezone.utc)


class _Handler(BaseHTTPRequestHandler):
    body = b"source-bytes\x00\xff"

    def do_GET(self):  # noqa: N802
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("ETag", '"fixture-etag"')
        self.send_header("Content-Length", str(len(self.body)))
        self.end_headers()
        self.wfile.write(self.body)

    def log_message(self, format, *args):  # noqa: A003
        return


class AcquisitionTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.out = self.root / "acquired"
        self.engine = AcquisitionEngine(self.out, clock=lambda: FIXED_TIME)

    def tearDown(self):
        self.tempdir.cleanup()

    def test_provider_inference(self):
        self.assertEqual(infer_provider("./paper.pdf"), "local")
        self.assertEqual(infer_provider("file:///tmp/paper.pdf"), "local")
        self.assertEqual(infer_provider("https://example.test/paper.pdf"), "http")
        self.assertEqual(infer_provider("https://github.com/acme/repo.git"), "git")
        self.assertEqual(infer_provider("git+https://github.com/acme/repo"), "git")
        self.assertEqual(infer_provider("git@example.test:repo.git"), "git")

    def test_source_id_is_constrained(self):
        with self.assertRaises(AcquisitionError):
            self.engine.acquire(AcquisitionSpec("../escape", "anything"))

    def test_local_file_preserves_bytes_and_writes_receipt(self):
        source = self.root / "paper.pdf"
        expected = b"%PDF-exact-bytes\r\n\x00\xff"
        source.write_bytes(expected)

        receipt = self.engine.acquire(AcquisitionSpec("paper", str(source)))

        artifact = self.out / "paper" / receipt.artifact["path"]
        self.assertEqual(artifact.read_bytes(), expected)
        saved = load_receipt(self.out / "paper" / "receipt.json")
        self.assertEqual(saved["stage"], "01-acquire")
        self.assertEqual(saved["acquired_at"], "2026-08-16T12:00:00Z")
        self.assertNotIn("sha256", json.dumps(saved))

    def test_local_directory_preserves_tree(self):
        source = self.root / "docs"
        source.mkdir()
        (source / "a.md").write_bytes(b"A")
        nested = source / "nested"
        nested.mkdir()
        (nested / "b.bin").write_bytes(b"B\x00")

        receipt = self.engine.acquire(AcquisitionSpec("docs", str(source)))
        artifact = self.out / "docs" / receipt.artifact["path"]
        self.assertEqual((artifact / "a.md").read_bytes(), b"A")
        self.assertEqual((artifact / "nested" / "b.bin").read_bytes(), b"B\x00")

    @unittest.skipIf(os.name == "nt", "symlink semantics differ on Windows")
    def test_local_symlink_is_preserved_not_followed(self):
        target = self.root / "target.txt"
        target.write_text("secret", encoding="utf-8")
        link = self.root / "link.txt"
        link.symlink_to(target.name)

        receipt = self.engine.acquire(AcquisitionSpec("link", str(link)))
        artifact = self.out / "link" / receipt.artifact["path"]
        self.assertTrue(artifact.is_symlink())
        self.assertEqual(os.readlink(artifact), target.name)

    def test_reject_output_nested_inside_acquired_directory(self):
        source = self.root / "project"
        source.mkdir()
        engine = AcquisitionEngine(source / ".okf-generator" / "acquired", clock=lambda: FIXED_TIME)
        with self.assertRaises(AcquisitionError):
            engine.acquire(AcquisitionSpec("project", str(source)))

    def test_existing_acquisition_requires_explicit_replace(self):
        source = self.root / "x.txt"
        source.write_text("v1", encoding="utf-8")
        self.engine.acquire(AcquisitionSpec("x", str(source)))
        source.write_text("v2", encoding="utf-8")
        with self.assertRaises(AcquisitionError):
            self.engine.acquire(AcquisitionSpec("x", str(source)))

        receipt = self.engine.acquire(AcquisitionSpec("x", str(source)), replace=True)
        artifact = self.out / "x" / receipt.artifact["path"]
        self.assertEqual(artifact.read_text(encoding="utf-8"), "v2")

    def test_ref_with_auto_provider_fails_for_non_git_locator(self):
        source = self.root / "x.txt"
        source.write_text("v1", encoding="utf-8")
        with self.assertRaises(AcquisitionError):
            self.engine.acquire(AcquisitionSpec("x", str(source), provider="auto", ref="main"))

    def test_http_acquisition_preserves_response_body(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{server.server_port}/source.bin"
            receipt = self.engine.acquire(AcquisitionSpec("http", url))
        finally:
            server.shutdown()
            thread.join()
            server.server_close()

        artifact = self.out / "http" / receipt.artifact["path"]
        self.assertEqual(artifact.read_bytes(), _Handler.body)
        self.assertEqual(receipt.observations["etag"], '"fixture-etag"')

    def test_http_size_limit_fails_without_publishing_partial_acquisition(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{server.server_port}/source.bin"
            engine = AcquisitionEngine(self.out, max_http_bytes=2, clock=lambda: FIXED_TIME)
            with self.assertRaises(AcquisitionError):
                engine.acquire(AcquisitionSpec("too-big", url))
        finally:
            server.shutdown()
            thread.join()
            server.server_close()

        self.assertFalse((self.out / "too-big").exists())

    @unittest.skipUnless(shutil.which("git"), "git executable is required")
    def test_git_acquisition_is_bare_and_does_not_checkout_files(self):
        repo = self.root / "repo"
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.test"], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True)
        (repo / "README.md").write_text("hello", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "README.md"], check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "fixture"], check=True)
        branch = subprocess.check_output(
            ["git", "-C", str(repo), "branch", "--show-current"], text=True
        ).strip()

        receipt = self.engine.acquire(
            AcquisitionSpec("repo", str(repo), provider="git", ref=branch)
        )
        artifact = self.out / "repo" / receipt.artifact["path"]
        self.assertTrue((artifact / "HEAD").exists())
        self.assertFalse((artifact / "README.md").exists())
        self.assertEqual(receipt.artifact["kind"], "bare-git-repository")
        self.assertEqual(receipt.requested_ref, branch)
        self.assertNotIn("sha256", receipt.to_json())

    @unittest.skipUnless(shutil.which("git"), "git executable is required")
    def test_git_missing_ref_fails(self):
        repo = self.root / "repo"
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.test"], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True)
        (repo / "x").write_text("x", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "x"], check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "fixture"], check=True)

        with self.assertRaises(AcquisitionError):
            self.engine.acquire(
                AcquisitionSpec("repo", str(repo), provider="git", ref="missing-ref")
            )
        self.assertFalse((self.out / "repo").exists())


if __name__ == "__main__":
    unittest.main()
