from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping

from .resolution_errors import ResolutionError

RUN_ID_RE = re.compile(r"^sha256-[0-9a-f]{64}$")
EXPECTED_CANDIDATE_FIELDS = {
    "summary": {"candidate_id", "candidate_type", "batch_id", "text", "evidence_anchors"},
    "concept": {"candidate_id", "candidate_type", "batch_id", "name", "description", "evidence_anchors"},
    "claim": {"candidate_id", "candidate_type", "batch_id", "statement", "evidence_anchors"},
    "relation": {"candidate_id", "candidate_type", "batch_id", "subject_candidate_id", "predicate", "object_candidate_id", "evidence_anchors"},
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise ResolutionError(f"{label} is missing: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResolutionError(f"{label} is unreadable") from exc
    if not isinstance(value, dict):
        raise ResolutionError(f"{label} must be a JSON object")
    return value


def load_jsonl(path: Path, label: str) -> list[dict[str, Any]]:
    if not path.is_file():
        raise ResolutionError(f"{label} is missing: {path}")
    rows: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            for number, line in enumerate(handle, start=1):
                if not line.endswith("\n"):
                    raise ResolutionError(f"{label} line {number} is not LF-terminated")
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ResolutionError(f"{label} line {number} must be an object")
                rows.append(value)
    except (OSError, json.JSONDecodeError) as exc:
        raise ResolutionError(f"{label} is unreadable") from exc
    return rows


def validate_candidates(rows: list[dict[str, Any]], expected_counts: Mapping[str, Any]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    concept_ids: set[str] = set()
    counts = {"summary": 0, "concept": 0, "claim": 0, "relation": 0}
    for index, row in enumerate(rows):
        candidate_type = row.get("candidate_type")
        if candidate_type not in EXPECTED_CANDIDATE_FIELDS:
            raise ResolutionError(f"candidate {index} has unsupported candidate_type")
        if set(row) != EXPECTED_CANDIDATE_FIELDS[candidate_type]:
            raise ResolutionError(f"candidate {index} schema mismatch")
        candidate_id = row.get("candidate_id")
        if not isinstance(candidate_id, str) or not candidate_id or candidate_id in seen:
            raise ResolutionError(f"candidate {index} has invalid or duplicate candidate_id")
        seen.add(candidate_id)
        if not isinstance(row.get("batch_id"), str) or not row["batch_id"]:
            raise ResolutionError(f"candidate {candidate_id} has invalid batch_id")
        anchors = row.get("evidence_anchors")
        if not isinstance(anchors, list) or not anchors or not all(isinstance(x, str) and x for x in anchors):
            raise ResolutionError(f"candidate {candidate_id} has invalid evidence_anchors")
        if len(set(anchors)) != len(anchors):
            raise ResolutionError(f"candidate {candidate_id} has duplicate evidence_anchors")
        if candidate_type == "concept":
            if not isinstance(row["name"], str) or not row["name"].strip() or not isinstance(row["description"], str) or not row["description"].strip():
                raise ResolutionError(f"concept candidate {candidate_id} is malformed")
            concept_ids.add(candidate_id)
        elif candidate_type == "summary":
            if not isinstance(row["text"], str) or not row["text"].strip():
                raise ResolutionError(f"summary candidate {candidate_id} is malformed")
        elif candidate_type == "claim":
            if not isinstance(row["statement"], str) or not row["statement"].strip():
                raise ResolutionError(f"claim candidate {candidate_id} is malformed")
        else:
            if not isinstance(row["predicate"], str) or not row["predicate"].strip():
                raise ResolutionError(f"relation candidate {candidate_id} is malformed")
        counts[candidate_type] += 1
    for row in rows:
        if row["candidate_type"] == "relation":
            if row["subject_candidate_id"] not in concept_ids or row["object_candidate_id"] not in concept_ids:
                raise ResolutionError(f"relation candidate {row['candidate_id']} references an unknown concept candidate")
    if dict(expected_counts) != counts:
        raise ResolutionError(f"Stage 06 candidate_counts mismatch: expected {dict(expected_counts)}, actual {counts}")
    return rows



def canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ResolutionError("Stage 06 synthesis manifest contains non-canonical values") from exc


def rederive_synthesis_run_id(manifest: Mapping[str, Any]) -> str:
    fields = [
        "profile", "source_id", "snapshot_id", "normalization_manifest_sha256", "normalization_units_sha256",
        "provider", "requested_model", "prompt_version", "prompt_sha256", "candidate_schema_version",
        "candidate_schema_sha256", "max_input_chars", "max_batch_units", "max_output_tokens", "requests_sha256",
        "responses_sha256", "receipts_sha256", "candidates_sha256",
    ]
    missing = [field for field in fields if field not in manifest]
    if missing:
        raise ResolutionError(f"Stage 06 synthesis manifest is missing run identity fields: {missing}")
    descriptor = {field: manifest[field] for field in fields}
    return "sha256-" + hashlib.sha256(canonical_json_bytes(descriptor)).hexdigest()

def synthesis_run_dir(root: Path, source_id: str, snapshot_id: str, ruleset: str, extraction_profile: str,
                      normalization_profile: str, synthesis_profile: str, synthesis_provider: str, run_id: str) -> Path:
    return root / source_id / snapshot_id / ruleset / extraction_profile / normalization_profile / synthesis_profile / synthesis_provider / run_id


def load_verified_synthesis(run_dir: Path, expected: Mapping[str, str]) -> tuple[dict[str, Any], list[dict[str, Any]], str, str]:
    manifest_path = run_dir / "synthesis.json"
    manifest = load_json(manifest_path, "Stage 06 synthesis manifest")
    required_identity = {
        "stage": "06-synthesize",
        "source_id": expected["source_id"],
        "snapshot_id": expected["snapshot_id"],
        "classification_ruleset": expected["ruleset"],
        "extraction_profile": expected["extraction_profile"],
        "normalization_profile": expected["normalization_profile"],
        "profile": expected["synthesis_profile"],
        "provider": expected["synthesis_provider"],
        "run_id": expected["run_id"],
    }
    for field, value in required_identity.items():
        if manifest.get(field) != value:
            raise ResolutionError(f"Stage 06 synthesis identity mismatch for {field}")
    if not RUN_ID_RE.fullmatch(expected["run_id"]):
        raise ResolutionError("synthesis run_id must be content-addressed")
    if manifest.get("schema_version") != "0.1":
        raise ResolutionError("unsupported Stage 06 synthesis schema_version")
    for name in ("requests", "responses", "receipts", "candidates"):
        if manifest.get(f"{name}_path") != f"{name}.jsonl":
            raise ResolutionError(f"Stage 06 {name}_path is unexpected")
        actual = sha256_file(run_dir / f"{name}.jsonl")
        if manifest.get(f"{name}_sha256") != actual:
            raise ResolutionError(f"Stage 06 {name} hash mismatch")
    if rederive_synthesis_run_id(manifest) != expected["run_id"]:
        raise ResolutionError("Stage 06 synthesis run_id does not match its content-addressed descriptor")
    candidates = load_jsonl(run_dir / "candidates.jsonl", "Stage 06 candidates")
    validate_candidates(candidates, manifest.get("candidate_counts", {}))
    return manifest, candidates, sha256_file(manifest_path), sha256_file(run_dir / "candidates.jsonl")
