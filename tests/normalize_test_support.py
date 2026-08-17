from __future__ import annotations

import hashlib
import json
from pathlib import Path

from okf_generator.normalize import NormalizationEngine, PROFILE_ID

SOURCE_ID = "paper"
SNAPSHOT_ID = "sha256-" + "a" * 64
RULESET = "builtin-v1"
EXTRACTION_PROFILE = "builtin-v1"


def unit(unit_id="u000001", source_path="paper.txt", kind="text-document", text="hello", *, locator=None,
         data=None, metadata=None, diagnostics=None):
    return {
        "unit_id": unit_id,
        "source_path": source_path,
        "kind": kind,
        "text": text,
        "data": {} if data is None else data,
        "native_locator": {"path": source_path} if locator is None else locator,
        "metadata": {} if metadata is None else metadata,
        "diagnostics": [] if diagnostics is None else diagnostics,
    }


class Fixture:
    def __init__(self, root: Path, units, *, top_diagnostics=None):
        self.root = root
        self.extraction_root = root / "extractions"
        self.output_root = root / "normalized"
        self.dir = self.extraction_root / SOURCE_ID / SNAPSHOT_ID / RULESET / EXTRACTION_PROFILE
        self.dir.mkdir(parents=True)
        units_text = "".join(
            json.dumps(u, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
            for u in units
        )
        (self.dir / "units.jsonl").write_text(units_text, encoding="utf-8")
        self.manifest = {
            "schema_version": "0.1",
            "stage": "04-extract",
            "profile": EXTRACTION_PROFILE,
            "source_id": SOURCE_ID,
            "snapshot_id": SNAPSHOT_ID,
            "classification_ruleset": RULESET,
            "snapshot_manifest_sha256": "1" * 64,
            "classification_sha256": "2" * 64,
            "units_path": "units.jsonl",
            "units_sha256": hashlib.sha256(units_text.encode()).hexdigest(),
            "unit_count": len(units),
            "diagnostic_count": len(top_diagnostics or []) + sum(len(u["diagnostics"]) for u in units),
            "diagnostics": top_diagnostics or [],
            "tools": {},
            "routes": {},
        }
        (self.dir / "extraction.json").write_text(
            json.dumps(self.manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    def verifier(self, source_id, snapshot_id):
        return dict(self.manifest)

    def engine(self, verifier=None):
        return NormalizationEngine(
            extraction_root=self.extraction_root,
            output_root=self.output_root,
            extraction_verifier=verifier or self.verifier,
        )

    def out_dir(self):
        return self.output_root / SOURCE_ID / SNAPSHOT_ID / RULESET / EXTRACTION_PROFILE / PROFILE_ID
