from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol

from .resolution_errors import ResolutionError

ADJUDICATION_SCHEMA_VERSION = "adjudication-v1"
ADJUDICATION_PROMPT_VERSION = "adjudication-prompt-v1"
ADJUDICATION_INSTRUCTIONS = """You are Stage 07 identity adjudication in a knowledge pipeline.
Decide whether one source-local concept candidate is the same concept as exactly one shortlisted canonical concept, is a genuinely new concept, or remains ambiguous.
Use only the supplied candidate and catalog records. Do not use outside knowledge. Prefer ambiguous over a weak identity guess.
A match decision must return one internal_id from the supplied shortlist. New or ambiguous must return an empty internal_id string.
Do not decide create/update/merge operations; Stage 08 owns planning.
"""

ADJUDICATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["decision", "internal_id", "reason"],
    "properties": {
        "decision": {"type": "string", "enum": ["match", "new", "ambiguous"]},
        "internal_id": {"type": "string"},
        "reason": {"type": "string"},
    },
}


@dataclass(frozen=True)
class AdjudicationRequest:
    candidate_id: str
    model: str
    input_text: str


@dataclass(frozen=True)
class AdjudicationResult:
    output: Mapping[str, Any]
    response_id: str | None = None
    resolved_model: str | None = None
    usage: Mapping[str, Any] = field(default_factory=dict)


class ResolutionAdjudicator(Protocol):
    name: str
    def adjudicate(self, request: AdjudicationRequest) -> AdjudicationResult: ...


def adjudication_input(candidate: Mapping[str, Any], shortlist: list[Mapping[str, Any]]) -> str:
    payload = {
        "candidate": {
            "candidate_id": candidate["candidate_id"],
            "name": candidate["name"],
            "description": candidate["description"],
            "evidence_anchors": candidate["evidence_anchors"],
        },
        "shortlist": shortlist,
    }
    return json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False)


def validate_adjudication(value: Any, allowed_ids: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"decision", "internal_id", "reason"}:
        raise ResolutionError("adjudication output schema mismatch")
    decision = value["decision"]
    internal_id = value["internal_id"]
    reason = value["reason"]
    if decision not in {"match", "new", "ambiguous"}:
        raise ResolutionError("adjudication decision is invalid")
    if not isinstance(reason, str) or not reason.strip():
        raise ResolutionError("adjudication reason must be non-empty")
    if decision == "match":
        if not isinstance(internal_id, str) or internal_id not in allowed_ids:
            raise ResolutionError("adjudication match must select an internal_id from its shortlist")
    elif internal_id != "":
        raise ResolutionError("new/ambiguous adjudication must return an empty internal_id")
    return {"decision": decision, "internal_id": internal_id, "reason": reason}


class OpenAIResolutionAdjudicator:
    name = "openai"

    def __init__(self, provider=None) -> None:
        if provider is None:
            from .synthesis_provider import OpenAIResponsesProvider
            provider = OpenAIResponsesProvider()
        self.provider = provider

    def adjudicate(self, request: AdjudicationRequest) -> AdjudicationResult:
        from .synthesis_provider import ProviderRequest
        try:
            result = self.provider.generate(ProviderRequest(
                batch_id=request.candidate_id,
                model=request.model,
                instructions=ADJUDICATION_INSTRUCTIONS,
                input_text=request.input_text,
                schema_name="okf_stage07_adjudication",
                schema=ADJUDICATION_SCHEMA,
                max_output_tokens=1200,
            ))
        except Exception as exc:
            from .synthesis_errors import SynthesisError
            if isinstance(exc, SynthesisError):
                raise ResolutionError(f"resolution adjudication provider failed: {exc}") from exc
            raise
        return AdjudicationResult(
            output=dict(result.output),
            response_id=result.response_id,
            resolved_model=result.resolved_model,
            usage=dict(result.usage),
        )
