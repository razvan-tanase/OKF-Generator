from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from normalize_test_support import Fixture, SNAPSHOT_ID, SOURCE_ID, unit
from okf_generator.normalize import ANCHOR_BASIS, TEXT_NORMALIZATION, NormalizationError, normalize_text


class NormalizeIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_text_normalization_is_nfc_and_lf_without_trimming(self):
        self.assertEqual(normalize_text("  Cafe\u0301\r\nline\r\n"), "  Café\nline\n")

    def test_normalizes_units_and_preserves_spacing(self):
        fixture = Fixture(self.root, [unit(text="  Cafe\u0301\r\nline\r\n")])
        manifest = fixture.engine().normalize(SOURCE_ID, SNAPSHOT_ID)
        line = json.loads((fixture.out_dir() / "units.jsonl").read_text().splitlines()[0])
        self.assertEqual(line["text"], "  Café\nline\n")
        self.assertEqual(manifest.text_normalization, TEXT_NORMALIZATION)
        self.assertEqual(manifest.anchor_basis, ANCHOR_BASIS)

    def test_source_and_version_uris_are_deterministic(self):
        fixture = Fixture(self.root, [unit()])
        manifest = fixture.engine().normalize(SOURCE_ID, SNAPSHOT_ID)
        self.assertEqual(manifest.source_uri, "okf-source:paper")
        self.assertEqual(manifest.source_version_uri, f"okf-source:paper@{SNAPSHOT_ID}")
        line = json.loads((fixture.out_dir() / "units.jsonl").read_text().splitlines()[0])
        self.assertEqual(line["source_uri"], manifest.source_uri)
        self.assertEqual(line["source_version_uri"], manifest.source_version_uri)
        self.assertTrue(line["anchor_uri"].startswith(manifest.source_version_uri + "#a-sha256-"))

    def test_anchor_does_not_depend_on_extraction_unit_id(self):
        one = Fixture(self.root / "one", [unit(unit_id="u000001", locator={"page": 1})])
        one.engine().normalize(SOURCE_ID, SNAPSHOT_ID)
        anchor1 = json.loads((one.out_dir() / "units.jsonl").read_text().splitlines()[0])["anchor_id"]
        two = Fixture(self.root / "two", [unit(unit_id="u999999", locator={"page": 1})])
        two.engine().normalize(SOURCE_ID, SNAPSHOT_ID)
        anchor2 = json.loads((two.out_dir() / "units.jsonl").read_text().splitlines()[0])["anchor_id"]
        self.assertEqual(anchor1, anchor2)

    def test_different_native_locator_changes_anchor(self):
        fixture = Fixture(self.root, [
            unit("u000001", locator={"page": 1}),
            unit("u000002", locator={"page": 2}),
        ])
        fixture.engine().normalize(SOURCE_ID, SNAPSHOT_ID)
        lines = [json.loads(x) for x in (fixture.out_dir() / "units.jsonl").read_text().splitlines()]
        self.assertNotEqual(lines[0]["anchor_id"], lines[1]["anchor_id"])

    def test_duplicate_native_anchor_is_rejected(self):
        fixture = Fixture(self.root, [
            unit("u000001", locator={"page": 1}),
            unit("u000002", locator={"page": 1}),
        ])
        with self.assertRaisesRegex(NormalizationError, "native locator collision"):
            fixture.engine().normalize(SOURCE_ID, SNAPSHOT_ID)

    def test_duplicate_unit_id_is_rejected(self):
        fixture = Fixture(self.root, [
            unit("u000001", locator={"page": 1}),
            unit("u000001", locator={"page": 2}),
        ])
        with self.assertRaisesRegex(NormalizationError, "duplicate Stage 04 unit_id"):
            fixture.engine().normalize(SOURCE_ID, SNAPSHOT_ID)

    def test_metadata_and_data_strings_are_nfc_lists_keep_order(self):
        fixture = Fixture(self.root, [unit(data={"items": ["e\u0301", "a"]}, metadata={"title": "Cafe\u0301"})])
        fixture.engine().normalize(SOURCE_ID, SNAPSHOT_ID)
        line = json.loads((fixture.out_dir() / "units.jsonl").read_text().splitlines()[0])
        self.assertEqual(line["data"]["items"], ["é", "a"])
        self.assertEqual(line["metadata"]["title"], "Café")

    def test_nfc_object_key_collision_is_rejected(self):
        fixture = Fixture(self.root, [unit(metadata={"é": 1, "e\u0301": 2})])
        with self.assertRaisesRegex(NormalizationError, "collide after Unicode NFC"):
            fixture.engine().normalize(SOURCE_ID, SNAPSHOT_ID)

    def test_nfc_source_path_collision_is_rejected(self):
        fixture = Fixture(self.root, [
            unit("u000001", source_path="café.txt", locator={"path": "one"}),
            unit("u000002", source_path="cafe\u0301.txt", locator={"path": "two"}),
        ])
        with self.assertRaisesRegex(NormalizationError, "source paths collide"):
            fixture.engine().normalize(SOURCE_ID, SNAPSHOT_ID)

    def test_nonfinite_metadata_number_is_rejected(self):
        fixture = Fixture(self.root, [unit(metadata={"score": float("nan")})])
        with self.assertRaisesRegex(NormalizationError, "non-finite"):
            fixture.engine().normalize(SOURCE_ID, SNAPSHOT_ID)

    def test_unpaired_unicode_surrogate_is_rejected(self):
        fixture = Fixture(self.root, [unit(text="bad\ud800")])
        with self.assertRaisesRegex(NormalizationError, "surrogate"):
            fixture.engine().normalize(SOURCE_ID, SNAPSHOT_ID)
