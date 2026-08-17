from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .synthesis_errors import SynthesisError
from .synthesis_io import load_jsonl, sha256_file

EXPECTED_NORMALIZED_UNIT_FIELDS = {
    "unit_id", "anchor_id", "source_uri", "source_version_uri", "anchor_uri",
    "source_path", "kind", "text", "data", "native_locator", "metadata",
    "diagnostics", "content_sha256",
}


def normalization_dir(root: Path, source_id: str, snapshot_id: str, ruleset: str, extraction_profile: str, normalization_profile: str) -> Path:
    return root / source_id / snapshot_id / ruleset / extraction_profile / normalization_profile


def load_verified_units(directory: Path, normalization: Mapping[str, Any]) -> tuple[list[dict[str, Any]], str, str]:
    manifest_path = directory / "normalization.json"
    units_path = directory / "units.jsonl"
    manifest_hash = sha256_file(manifest_path)
    units_hash = sha256_file(units_path)
    if normalization.get("units_path") != "units.jsonl" or normalization.get("units_sha256") != units_hash:
        raise SynthesisError("Stage 05 units hash/path is inconsistent")
    units = load_jsonl(units_path, "Stage 05 normalized units")
    if normalization.get("unit_count") != len(units):
        raise SynthesisError("Stage 05 unit_count does not match normalized units")
    source_uri = normalization.get("source_uri")
    source_version_uri = normalization.get("source_version_uri")
    if not isinstance(source_uri, str) or not isinstance(source_version_uri, str):
        raise SynthesisError("Stage 05 source URIs are malformed")
    seen_anchors: set[str] = set()
    seen_unit_ids: set[str] = set()
    for i, unit in enumerate(units, start=1):
        if set(unit) != EXPECTED_NORMALIZED_UNIT_FIELDS:
            raise SynthesisError(f"normalized unit {i} schema mismatch")
        if unit.get("source_uri") != source_uri or unit.get("source_version_uri") != source_version_uri:
            raise SynthesisError(f"normalized unit {i} has inconsistent source identity")
        anchor = unit.get("anchor_uri")
        unit_id = unit.get("unit_id")
        if not isinstance(anchor, str) or not anchor.startswith(source_version_uri + "#"):
            raise SynthesisError(f"normalized unit {i} has invalid anchor_uri")
        if anchor in seen_anchors:
            raise SynthesisError(f"duplicate normalized anchor_uri: {anchor}")
        seen_anchors.add(anchor)
        if not isinstance(unit_id, str) or not unit_id or unit_id in seen_unit_ids:
            raise SynthesisError(f"normalized unit {i} has invalid/duplicate unit_id")
        seen_unit_ids.add(unit_id)
        if unit.get("text") is not None and not isinstance(unit.get("text"), str):
            raise SynthesisError(f"normalized unit {i} has non-string text")
        for field in ("data", "native_locator", "metadata"):
            if not isinstance(unit.get(field), dict):
                raise SynthesisError(f"normalized unit {i} {field} must be an object")
        diagnostics = unit.get("diagnostics")
        if not isinstance(diagnostics, list) or not all(isinstance(x, str) for x in diagnostics):
            raise SynthesisError(f"normalized unit {i} diagnostics are malformed")
    return units, manifest_hash, units_hash


def unit_context(unit: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "unit_id": unit["unit_id"],
        "anchor_uri": unit["anchor_uri"],
        "source_path": unit["source_path"],
        "kind": unit["kind"],
        "text": unit["text"],
        "data": unit["data"],
        "native_locator": unit["native_locator"],
        "metadata": unit["metadata"],
        "diagnostics": unit["diagnostics"],
        "content_sha256": unit["content_sha256"],
    }


def render_batch(normalization: Mapping[str, Any], units: list[Mapping[str, Any]]) -> str:
    payload = {
        "source_uri": normalization["source_uri"],
        "source_version_uri": normalization["source_version_uri"],
        "units": [unit_context(unit) for unit in units],
    }
    return json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False)


def make_batches(normalization: Mapping[str, Any], units: list[dict[str, Any]], *, max_input_chars: int, max_batch_units: int) -> list[tuple[str, list[dict[str, Any]], str]]:
    if not units:
        return []
    batches: list[tuple[str, list[dict[str, Any]], str]] = []
    current: list[dict[str, Any]] = []
    for unit in units:
        single = render_batch(normalization, [unit])
        if len(single) > max_input_chars:
            raise SynthesisError(f"normalized unit {unit['unit_id']} exceeds max_input_chars by itself; choose a larger model/context budget")
        if not current:
            current = [unit]
            continue
        proposal = current + [unit]
        rendered = render_batch(normalization, proposal)
        if len(proposal) <= max_batch_units and len(rendered) <= max_input_chars:
            current = proposal
            continue
        batch_id = f"b{len(batches)+1:04d}"
        batches.append((batch_id, current, render_batch(normalization, current)))
        current = [unit]
    if current:
        batch_id = f"b{len(batches)+1:04d}"
        batches.append((batch_id, current, render_batch(normalization, current)))
    return batches
