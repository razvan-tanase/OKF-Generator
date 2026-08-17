from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from .synthesis_errors import SynthesisError

SCHEMA_VERSION = "candidate-v1"
PROMPT_VERSION = "prompt-v1"
SYSTEM_INSTRUCTIONS = """You are Stage 06 of an evidence-grounded knowledge pipeline.
Produce only source-local candidate summaries, concepts, factual claims, and relations supported by the supplied normalized evidence.
Every candidate must cite one or more anchor URIs exactly as provided in the input. Do not use outside knowledge.
Do not resolve candidates against an existing wiki, merge identities, decide updates, or emit OKF documents; those belong to later stages.
Concepts are local to this batch. Relations use zero-based indices into the concepts array from this same response.
Omit unsupported candidates rather than guessing. Preserve uncertainty in the wording instead of inventing certainty.
"""

EVIDENCE_ARRAY = {
    "type": "array",
    "items": {"type": "string"},
}

CANDIDATE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["summaries", "concepts", "claims", "relations"],
    "properties": {
        "summaries": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["text", "evidence_anchors"],
                "properties": {
                    "text": {"type": "string"},
                    "evidence_anchors": EVIDENCE_ARRAY,
                },
            },
        },
        "concepts": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["name", "description", "evidence_anchors"],
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "evidence_anchors": EVIDENCE_ARRAY,
                },
            },
        },
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["statement", "evidence_anchors"],
                "properties": {
                    "statement": {"type": "string"},
                    "evidence_anchors": EVIDENCE_ARRAY,
                },
            },
        },
        "relations": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["subject_index", "predicate", "object_index", "evidence_anchors"],
                "properties": {
                    "subject_index": {"type": "integer"},
                    "predicate": {"type": "string"},
                    "object_index": {"type": "integer"},
                    "evidence_anchors": EVIDENCE_ARRAY,
                },
            },
        },
    },
}


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def schema_sha256() -> str:
    return hashlib.sha256(canonical_json_bytes(CANDIDATE_SCHEMA)).hexdigest()


def prompt_sha256() -> str:
    return hashlib.sha256(SYSTEM_INSTRUCTIONS.encode("utf-8")).hexdigest()


def _require_exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    actual = set(value)
    if actual != expected:
        raise SynthesisError(f"{label} schema mismatch; missing={sorted(expected-actual)}, extra={sorted(actual-expected)}")


def _validate_evidence(items: Any, allowed: set[str], label: str) -> tuple[str, ...]:
    if not isinstance(items, list) or not items or not all(isinstance(item, str) and item for item in items):
        raise SynthesisError(f"{label} evidence_anchors must be a non-empty string array")
    if len(set(items)) != len(items):
        raise SynthesisError(f"{label} contains duplicate evidence anchors")
    unknown = [item for item in items if item not in allowed]
    if unknown:
        raise SynthesisError(f"{label} cites anchors not present in its batch: {unknown}")
    return tuple(items)


def validate_batch_output(value: Any, allowed_anchors: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SynthesisError("provider output must be a JSON object")
    _require_exact_keys(value, {"summaries", "concepts", "claims", "relations"}, "provider output")
    for name in ("summaries", "concepts", "claims", "relations"):
        if not isinstance(value[name], list):
            raise SynthesisError(f"provider output {name} must be an array")

    summaries = []
    for i, item in enumerate(value["summaries"]):
        if not isinstance(item, dict): raise SynthesisError(f"summary {i} must be an object")
        _require_exact_keys(item, {"text", "evidence_anchors"}, f"summary {i}")
        if not isinstance(item["text"], str) or not item["text"].strip(): raise SynthesisError(f"summary {i} text must be non-empty")
        summaries.append({"text": item["text"], "evidence_anchors": list(_validate_evidence(item["evidence_anchors"], allowed_anchors, f"summary {i}"))})

    concepts = []
    for i, item in enumerate(value["concepts"]):
        if not isinstance(item, dict): raise SynthesisError(f"concept {i} must be an object")
        _require_exact_keys(item, {"name", "description", "evidence_anchors"}, f"concept {i}")
        if not isinstance(item["name"], str) or not item["name"].strip(): raise SynthesisError(f"concept {i} name must be non-empty")
        if not isinstance(item["description"], str) or not item["description"].strip(): raise SynthesisError(f"concept {i} description must be non-empty")
        concepts.append({"name": item["name"], "description": item["description"], "evidence_anchors": list(_validate_evidence(item["evidence_anchors"], allowed_anchors, f"concept {i}"))})

    claims = []
    for i, item in enumerate(value["claims"]):
        if not isinstance(item, dict): raise SynthesisError(f"claim {i} must be an object")
        _require_exact_keys(item, {"statement", "evidence_anchors"}, f"claim {i}")
        if not isinstance(item["statement"], str) or not item["statement"].strip(): raise SynthesisError(f"claim {i} statement must be non-empty")
        claims.append({"statement": item["statement"], "evidence_anchors": list(_validate_evidence(item["evidence_anchors"], allowed_anchors, f"claim {i}"))})

    relations = []
    for i, item in enumerate(value["relations"]):
        if not isinstance(item, dict): raise SynthesisError(f"relation {i} must be an object")
        _require_exact_keys(item, {"subject_index", "predicate", "object_index", "evidence_anchors"}, f"relation {i}")
        if not isinstance(item["subject_index"], int) or isinstance(item["subject_index"], bool): raise SynthesisError(f"relation {i} subject_index must be an integer")
        if not isinstance(item["object_index"], int) or isinstance(item["object_index"], bool): raise SynthesisError(f"relation {i} object_index must be an integer")
        if not (0 <= item["subject_index"] < len(concepts)) or not (0 <= item["object_index"] < len(concepts)):
            raise SynthesisError(f"relation {i} references an out-of-range concept index")
        if not isinstance(item["predicate"], str) or not item["predicate"].strip(): raise SynthesisError(f"relation {i} predicate must be non-empty")
        relations.append({"subject_index": item["subject_index"], "predicate": item["predicate"], "object_index": item["object_index"], "evidence_anchors": list(_validate_evidence(item["evidence_anchors"], allowed_anchors, f"relation {i}"))})

    return {"summaries": summaries, "concepts": concepts, "claims": claims, "relations": relations}
