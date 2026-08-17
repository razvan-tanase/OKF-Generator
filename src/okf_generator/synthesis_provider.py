from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol

from .synthesis_errors import SynthesisError

OPENAI_RESPONSES_ENDPOINT = "https://api.openai.com/v1/responses"


@dataclass(frozen=True)
class ProviderRequest:
    batch_id: str
    model: str
    instructions: str
    input_text: str
    schema_name: str
    schema: Mapping[str, Any]
    max_output_tokens: int


@dataclass(frozen=True)
class ProviderResult:
    output: Mapping[str, Any]
    response_id: str | None = None
    resolved_model: str | None = None
    usage: Mapping[str, Any] = field(default_factory=dict)


class SynthesisProvider(Protocol):
    name: str
    def generate(self, request: ProviderRequest) -> ProviderResult: ...


class OpenAIResponsesProvider:
    name = "openai"

    def __init__(self, *, api_key: str | None = None, timeout: float = 120.0, opener=None) -> None:
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.timeout = timeout
        self.opener = opener or urllib.request.urlopen

    def generate(self, request: ProviderRequest) -> ProviderResult:
        if not self.api_key:
            raise SynthesisError("OpenAI synthesis requires OPENAI_API_KEY")
        payload = {
            "model": request.model,
            "instructions": request.instructions,
            "input": request.input_text,
            "max_output_tokens": request.max_output_tokens,
            "store": False,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": request.schema_name,
                    "schema": dict(request.schema),
                    "strict": True,
                }
            },
        }
        body = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
        req = urllib.request.Request(
            OPENAI_RESPONSES_ENDPOINT,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with self.opener(req, timeout=self.timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            raise SynthesisError(f"OpenAI Responses API HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise SynthesisError(f"OpenAI Responses API request failed: {exc}") from exc
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SynthesisError("OpenAI Responses API returned unreadable JSON") from exc
        if not isinstance(data, dict):
            raise SynthesisError("OpenAI Responses API returned a non-object response")
        if data.get("status") != "completed":
            reason = data.get("incomplete_details") or data.get("error") or data.get("status")
            raise SynthesisError(f"OpenAI response did not complete: {reason}")

        texts: list[str] = []
        refusals: list[str] = []
        output = data.get("output")
        if not isinstance(output, list):
            raise SynthesisError("OpenAI response output is malformed")
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for part in content:
                if not isinstance(part, dict):
                    continue
                if part.get("type") == "output_text" and isinstance(part.get("text"), str):
                    texts.append(part["text"])
                elif part.get("type") == "refusal" and isinstance(part.get("refusal"), str):
                    refusals.append(part["refusal"])
        if refusals:
            raise SynthesisError(f"OpenAI model refused synthesis: {refusals[0]}")
        if len(texts) != 1:
            raise SynthesisError(f"OpenAI structured response must contain exactly one output_text item; got {len(texts)}")
        try:
            parsed = json.loads(texts[0])
        except json.JSONDecodeError as exc:
            raise SynthesisError("OpenAI structured output was not valid JSON") from exc
        if not isinstance(parsed, dict):
            raise SynthesisError("OpenAI structured output must be a JSON object")
        usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
        return ProviderResult(
            output=parsed,
            response_id=data.get("id") if isinstance(data.get("id"), str) else None,
            resolved_model=data.get("model") if isinstance(data.get("model"), str) else None,
            usage=usage,
        )
