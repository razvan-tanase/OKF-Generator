from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from normalize_test_support import Fixture, SNAPSHOT_ID, SOURCE_ID, unit
from okf_generator.normalize import NormalizationEngine, NormalizationError


class NormalizeIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_units_hash_mismatch_is_rejected(self):
        fixture = Fixture(self.root, [unit()])
        fixture.manifest["units_sha256"] = "0" * 64
        with self.assertRaisesRegex(NormalizationError, "units hash"):
            fixture.engine().normalize(SOURCE_ID, SNAPSHOT_ID)

    def test_unit_count_mismatch_is_rejected(self):
        fixture = Fixture(self.root, [unit()])
        fixture.manifest["unit_count"] = 2
        with self.assertRaisesRegex(NormalizationError, "unit_count"):
            fixture.engine().normalize(SOURCE_ID, SNAPSHOT_ID)

    def test_top_level_and_unit_diagnostics_are_preserved_and_counted(self):
        fixture = Fixture(
            self.root,
            [unit(diagnostics=["unit-warning\u0301"])],
            top_diagnostics=["top-warning\u0301"],
        )
        manifest = fixture.engine().normalize(SOURCE_ID, SNAPSHOT_ID)
        self.assertEqual(manifest.diagnostics, ("top-warninǵ",))
        self.assertEqual(manifest.diagnostic_count, 2)

    def test_upstream_diagnostic_count_mismatch_is_rejected(self):
        fixture = Fixture(self.root, [unit(diagnostics=["warning"])])
        fixture.manifest["diagnostic_count"] = 0
        with self.assertRaisesRegex(NormalizationError, "diagnostic_count"):
            fixture.engine().normalize(SOURCE_ID, SNAPSHOT_ID)

    def test_unknown_stage04_unit_field_is_rejected_instead_of_dropped(self):
        value = unit()
        value["future_field"] = "must-not-disappear"
        fixture = Fixture(self.root, [value])
        with self.assertRaisesRegex(NormalizationError, "schema mismatch"):
            fixture.engine().normalize(SOURCE_ID, SNAPSHOT_ID)

    def test_repeat_normalization_is_byte_idempotent(self):
        fixture = Fixture(self.root, [unit()])
        engine = fixture.engine()
        first = engine.normalize(SOURCE_ID, SNAPSHOT_ID)
        before_manifest = (fixture.out_dir() / "normalization.json").read_bytes()
        before_units = (fixture.out_dir() / "units.jsonl").read_bytes()
        second = engine.normalize(SOURCE_ID, SNAPSHOT_ID)
        self.assertEqual(first, second)
        self.assertEqual(before_manifest, (fixture.out_dir() / "normalization.json").read_bytes())
        self.assertEqual(before_units, (fixture.out_dir() / "units.jsonl").read_bytes())

    def test_existing_output_mutation_is_rejected(self):
        fixture = Fixture(self.root, [unit()])
        engine = fixture.engine()
        engine.normalize(SOURCE_ID, SNAPSHOT_ID)
        (fixture.out_dir() / "units.jsonl").write_text("tampered\n", encoding="utf-8")
        with self.assertRaisesRegex(NormalizationError, "existing normalization differs"):
            engine.normalize(SOURCE_ID, SNAPSHOT_ID)

    def test_input_mutation_during_normalization_is_rejected(self):
        fixture = Fixture(self.root, [unit()])
        calls = 0
        def verifier(source_id, snapshot_id):
            nonlocal calls
            calls += 1
            if calls == 2:
                p = fixture.dir / "units.jsonl"
                p.write_text(p.read_text() + "{}\n", encoding="utf-8")
            return dict(fixture.manifest)
        with self.assertRaisesRegex(NormalizationError, "changed while normalization"):
            fixture.engine(verifier).normalize(SOURCE_ID, SNAPSHOT_ID)
        self.assertFalse(fixture.out_dir().exists())

    def test_profile_and_ruleset_path_components_are_constrained(self):
        with self.assertRaises(NormalizationError):
            NormalizationEngine(ruleset="../escape")
        with self.assertRaises(NormalizationError):
            NormalizationEngine(extraction_profile="../escape")
        with self.assertRaises(NormalizationError):
            NormalizationEngine(profile="../escape")

    def test_invalid_source_and_snapshot_ids_are_rejected_before_paths(self):
        fixture = Fixture(self.root, [unit()])
        engine = fixture.engine()
        with self.assertRaises(NormalizationError):
            engine.normalize("../escape", SNAPSHOT_ID)
        with self.assertRaises(NormalizationError):
            engine.normalize(SOURCE_ID, "not-a-snapshot")
