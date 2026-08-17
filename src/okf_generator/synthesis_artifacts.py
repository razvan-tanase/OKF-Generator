from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from .synthesis_errors import SynthesisError


def jsonl(items: list[Mapping[str, Any]]) -> str:
    try:
        return "".join(
            json.dumps(item, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False) + "\n"
            for item in items
        )
    except (TypeError, ValueError) as exc:
        raise SynthesisError("synthesis run artifact contains a non-canonical JSON value") from exc


def sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def candidate_counts(candidates: list[Mapping[str, Any]]) -> dict[str, int]:
    counts = {"summary": 0, "concept": 0, "claim": 0, "relation": 0}
    for item in candidates:
        counts[str(item["candidate_type"])] += 1
    return counts


def append_candidates(candidates: list[dict[str, Any]], batch_id: str, validated: Mapping[str, Any]) -> None:
    concept_ids = [f"{batch_id}-c{i:04d}" for i in range(1, len(validated["concepts"]) + 1)]
    for i, item in enumerate(validated["summaries"], start=1):
        candidates.append({"candidate_id": f"{batch_id}-s{i:04d}", "candidate_type": "summary", "batch_id": batch_id, **item})
    for i, item in enumerate(validated["concepts"], start=1):
        candidates.append({"candidate_id": concept_ids[i - 1], "candidate_type": "concept", "batch_id": batch_id, **item})
    for i, item in enumerate(validated["claims"], start=1):
        candidates.append({"candidate_id": f"{batch_id}-q{i:04d}", "candidate_type": "claim", "batch_id": batch_id, **item})
    for i, item in enumerate(validated["relations"], start=1):
        candidates.append({
            "candidate_id": f"{batch_id}-r{i:04d}",
            "candidate_type": "relation",
            "batch_id": batch_id,
            "subject_candidate_id": concept_ids[item["subject_index"]],
            "predicate": item["predicate"],
            "object_candidate_id": concept_ids[item["object_index"]],
            "evidence_anchors": item["evidence_anchors"],
        })
