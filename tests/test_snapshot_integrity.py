from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from okf_generator.snapshot import SnapshotEngine, SnapshotError, fingerprint_payload


class SnapshotIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.acquired = self.root / "acquired"
        self.snapshots = self.root / "snapshots"
        self.engine = SnapshotEngine(self.acquired, self.snapshots)

    def tearDown(self):
        self.tempdir.cleanup()

    def _make_file_acquisition(self, source_id: str, data: bytes = b"original") -> None:
        base = self.acquired / source_id
        payload = base / "payload"
        payload.mkdir(parents=True)
        (payload / "x.bin").write_bytes(data)
        (base / "receipt.json").write_text(
            json.dumps(
                {
                    "schema_version": "0.1",
                    "stage": "01-acquire",
                    "source_id": source_id,
                    "provider": "local",
                    "locator": "x.bin",
                    "acquired_at": "2026-08-16T12:00:00Z",
                    "artifact": {"path": "payload/x.bin", "kind": "file"},
                    "observations": {},
                    "requested_ref": None,
                }
            ),
            encoding="utf-8",
        )

    def test_integrity_entry_manifest_is_verified(self):
        self._make_file_acquisition("entries")
        manifest = self.engine.snapshot("entries")
        snapshot_dir = self.snapshots / "entries" / manifest.snapshot_id
        integrity_path = snapshot_dir / "integrity.json"
        integrity = json.loads(integrity_path.read_text(encoding="utf-8"))
        integrity["entries"] = []
        integrity_path.write_text(json.dumps(integrity), encoding="utf-8")

        with self.assertRaises(SnapshotError):
            self.engine.snapshot("entries")

    def test_coordinated_storage_metadata_rewrite_cannot_change_content_address(self):
        self._make_file_acquisition("locked")
        manifest = self.engine.snapshot("locked")
        snapshot_dir = self.snapshots / "locked" / manifest.snapshot_id
        saved = snapshot_dir / manifest.artifact["path"]
        saved.write_bytes(b"replacement")
        replacement = fingerprint_payload(saved)

        snapshot_path = snapshot_dir / "snapshot.json"
        snapshot_data = json.loads(snapshot_path.read_text(encoding="utf-8"))
        snapshot_data["storage_fingerprint"]["value"] = replacement.digest
        snapshot_path.write_text(json.dumps(snapshot_data), encoding="utf-8")

        integrity_path = snapshot_dir / "integrity.json"
        integrity = json.loads(integrity_path.read_text(encoding="utf-8"))
        integrity["sha256"] = replacement.digest
        integrity["entries"] = list(replacement.entries)
        integrity_path.write_text(json.dumps(integrity), encoding="utf-8")

        with self.assertRaises(SnapshotError):
            self.engine.snapshot("locked")


if __name__ == "__main__":
    unittest.main()
