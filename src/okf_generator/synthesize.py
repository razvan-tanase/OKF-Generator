from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Callable, Mapping

from .acquire import SOURCE_ID_RE
from .classify import RULESET_ID, SNAPSHOT_ID_RE
from .extract import PROFILE_ID as EXTRACTION_PROFILE_ID
from .normalize import PROFILE_ID as NORMALIZATION_PROFILE_ID, NormalizationEngine, NormalizationError
from .synthesis_artifacts import append_candidates, candidate_counts, jsonl, sha_text
from .synthesis_errors import SynthesisError
from .synthesis_io import load_json, publish_run, sha256_file
from .synthesis_model import SynthesisManifest
from .synthesis_provider import OpenAIResponsesProvider, ProviderRequest, SynthesisProvider
from .synthesis_schema import (
    CANDIDATE_SCHEMA,
    PROMPT_VERSION,
    SCHEMA_VERSION,
    SYSTEM_INSTRUCTIONS,
    canonical_json_bytes,
    prompt_sha256,
    schema_sha256,
    validate_batch_output,
)
from .synthesis_upstream import load_verified_units, make_batches, normalization_dir

PROFILE_ID = "builtin-v1"
PROVIDER_RE = re.compile(r"^[a-z][a-z0-9._-]*$")
DEFAULT_MAX_INPUT_CHARS = 120_000
DEFAULT_MAX_BATCH_UNITS = 50
DEFAULT_MAX_OUTPUT_TOKENS = 8_000


class SynthesisEngine:
    def __init__(
        self,
        snapshot_root: Path | str = Path(".okf-generator/snapshots"),
        classification_root: Path | str = Path(".okf-generator/classifications"),
        extraction_root: Path | str = Path(".okf-generator/extractions"),
        normalization_root: Path | str = Path(".okf-generator/normalized"),
        output_root: Path | str = Path(".okf-generator/syntheses"),
        *,
        ruleset: str = RULESET_ID,
        extraction_profile: str = EXTRACTION_PROFILE_ID,
        normalization_profile: str = NORMALIZATION_PROFILE_ID,
        profile: str = PROFILE_ID,
        provider: SynthesisProvider | None = None,
        normalization_verifier: Callable[[str, str], Mapping[str, Any]] | None = None,
        normalization_engine: NormalizationEngine | None = None,
        max_input_chars: int = DEFAULT_MAX_INPUT_CHARS,
        max_batch_units: int = DEFAULT_MAX_BATCH_UNITS,
        max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
    ) -> None:
        if ruleset != RULESET_ID:
            raise SynthesisError(f"unsupported classification ruleset for Stage 06: {ruleset}")
        if extraction_profile != EXTRACTION_PROFILE_ID:
            raise SynthesisError(f"unsupported extraction profile for Stage 06: {extraction_profile}")
        if normalization_profile != NORMALIZATION_PROFILE_ID:
            raise SynthesisError(f"unsupported normalization profile for Stage 06: {normalization_profile}")
        if profile != PROFILE_ID:
            raise SynthesisError(f"unsupported synthesis profile: {profile}")
        if max_input_chars < 1024:
            raise SynthesisError("max_input_chars must be at least 1024")
        if max_batch_units < 1:
            raise SynthesisError("max_batch_units must be positive")
        if max_output_tokens < 256:
            raise SynthesisError("max_output_tokens must be at least 256")
        self.snapshot_root = Path(snapshot_root)
        self.classification_root = Path(classification_root)
        self.extraction_root = Path(extraction_root)
        self.normalization_root = Path(normalization_root)
        self.output_root = Path(output_root)
        self.ruleset = ruleset
        self.extraction_profile = extraction_profile
        self.normalization_profile = normalization_profile
        self.profile = profile
        self.provider = provider or OpenAIResponsesProvider()
        if not PROVIDER_RE.fullmatch(self.provider.name):
            raise SynthesisError("provider name is unsafe for synthesis output paths")
        self.max_input_chars = max_input_chars
        self.max_batch_units = max_batch_units
        self.max_output_tokens = max_output_tokens
        self.normalization_engine = normalization_engine or NormalizationEngine(
            snapshot_root=self.snapshot_root,
            classification_root=self.classification_root,
            extraction_root=self.extraction_root,
            output_root=self.normalization_root,
            ruleset=self.ruleset,
            extraction_profile=self.extraction_profile,
            profile=self.normalization_profile,
        )
        self.normalization_verifier = normalization_verifier or self._verify_normalization

    def _normalization_dir(self, source_id: str, snapshot_id: str) -> Path:
        return normalization_dir(
            self.normalization_root,
            source_id,
            snapshot_id,
            self.ruleset,
            self.extraction_profile,
            self.normalization_profile,
        )

    def _verify_normalization(self, source_id: str, snapshot_id: str) -> Mapping[str, Any]:
        path = self._normalization_dir(source_id, snapshot_id) / "normalization.json"
        existing = load_json(path, "Stage 05 normalization manifest")
        try:
            derived = self.normalization_engine.normalize(source_id, snapshot_id)
        except NormalizationError as exc:
            raise SynthesisError(f"Stage 05 normalization verification failed: {exc}") from exc
        if json.loads(derived.to_json()) != existing:
            raise SynthesisError("Stage 05 normalization does not match verified upstream inputs")
        return existing

    def _validate_identity(self, source_id: str, snapshot_id: str, model: str) -> None:
        if not SOURCE_ID_RE.fullmatch(source_id):
            raise SynthesisError("source_id must match Stage 01 source identifier rules")
        if not SNAPSHOT_ID_RE.fullmatch(snapshot_id):
            raise SynthesisError("snapshot_id must match Stage 02 content-addressed identifier rules")
        if not isinstance(model, str) or not model.strip() or len(model) > 200 or any(ord(ch) < 32 for ch in model):
            raise SynthesisError("model must be a non-empty printable identifier")

    def _validate_normalization_identity(self, normalization: Mapping[str, Any], source_id: str, snapshot_id: str) -> None:
        if (
            normalization.get("stage") != "05-normalize"
            or normalization.get("source_id") != source_id
            or normalization.get("snapshot_id") != snapshot_id
            or normalization.get("classification_ruleset") != self.ruleset
            or normalization.get("extraction_profile") != self.extraction_profile
            or normalization.get("profile") != self.normalization_profile
        ):
            raise SynthesisError("normalization verifier returned inconsistent identity metadata")

    def _run_batches(self, batches: list[tuple[str, list[dict[str, Any]], str]], model: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        request_rows: list[dict[str, Any]] = []
        response_rows: list[dict[str, Any]] = []
        receipt_rows: list[dict[str, Any]] = []
        candidates: list[dict[str, Any]] = []
        for batch_id, batch_units, input_text in batches:
            anchors = {str(unit["anchor_uri"]) for unit in batch_units}
            request = ProviderRequest(
                batch_id=batch_id,
                model=model,
                instructions=SYSTEM_INSTRUCTIONS,
                input_text=input_text,
                schema_name="okf_stage06_candidates",
                schema=CANDIDATE_SCHEMA,
                max_output_tokens=self.max_output_tokens,
            )
            request_rows.append({
                "batch_id": batch_id,
                "model": model,
                "instructions": SYSTEM_INSTRUCTIONS,
                "input": input_text,
                "max_output_tokens": self.max_output_tokens,
                "text": {"format": {"type": "json_schema", "name": request.schema_name, "schema": CANDIDATE_SCHEMA, "strict": True}},
            })
            result = self.provider.generate(request)
            if result.response_id is not None and not isinstance(result.response_id, str):
                raise SynthesisError("provider response_id must be a string or null")
            if result.resolved_model is not None and not isinstance(result.resolved_model, str):
                raise SynthesisError("provider resolved_model must be a string or null")
            if not isinstance(result.usage, Mapping):
                raise SynthesisError("provider usage metadata must be a mapping")
            validated = validate_batch_output(dict(result.output), anchors)
            response_rows.append({"batch_id": batch_id, "output": validated})
            receipt_rows.append({
                "batch_id": batch_id,
                "provider": self.provider.name,
                "response_id": result.response_id,
                "requested_model": model,
                "resolved_model": result.resolved_model,
                "usage": dict(result.usage),
            })
            append_candidates(candidates, batch_id, validated)
        return request_rows, response_rows, receipt_rows, candidates

    def synthesize(self, source_id: str, snapshot_id: str, *, model: str) -> SynthesisManifest:
        self._validate_identity(source_id, snapshot_id, model)
        normalization = dict(self.normalization_verifier(source_id, snapshot_id))
        self._validate_normalization_identity(normalization, source_id, snapshot_id)
        norm_dir = self._normalization_dir(source_id, snapshot_id)
        units, normalization_manifest_sha, normalization_units_sha = load_verified_units(norm_dir, normalization)
        batches = make_batches(
            normalization,
            units,
            max_input_chars=self.max_input_chars,
            max_batch_units=self.max_batch_units,
        )
        request_rows, response_rows, receipt_rows, candidates = self._run_batches(batches, model)

        normalization_after = dict(self.normalization_verifier(source_id, snapshot_id))
        if (
            normalization_after != normalization
            or sha256_file(norm_dir / "normalization.json") != normalization_manifest_sha
            or sha256_file(norm_dir / "units.jsonl") != normalization_units_sha
        ):
            raise SynthesisError("Stage 05 normalization changed while synthesis was running")

        requests_text = jsonl(request_rows)
        responses_text = jsonl(response_rows)
        receipts_text = jsonl(receipt_rows)
        candidates_text = jsonl(candidates)
        requests_sha = sha_text(requests_text)
        responses_sha = sha_text(responses_text)
        receipts_sha = sha_text(receipts_text)
        candidates_sha = sha_text(candidates_text)
        run_descriptor = {
            "profile": self.profile,
            "source_id": source_id,
            "snapshot_id": snapshot_id,
            "normalization_manifest_sha256": normalization_manifest_sha,
            "normalization_units_sha256": normalization_units_sha,
            "provider": self.provider.name,
            "requested_model": model,
            "prompt_version": PROMPT_VERSION,
            "prompt_sha256": prompt_sha256(),
            "candidate_schema_version": SCHEMA_VERSION,
            "candidate_schema_sha256": schema_sha256(),
            "max_input_chars": self.max_input_chars,
            "max_batch_units": self.max_batch_units,
            "max_output_tokens": self.max_output_tokens,
            "requests_sha256": requests_sha,
            "responses_sha256": responses_sha,
            "receipts_sha256": receipts_sha,
            "candidates_sha256": candidates_sha,
        }
        run_id = "sha256-" + hashlib.sha256(canonical_json_bytes(run_descriptor)).hexdigest()
        manifest = SynthesisManifest(
            schema_version="0.1",
            stage="06-synthesize",
            profile=self.profile,
            run_id=run_id,
            source_id=source_id,
            snapshot_id=snapshot_id,
            classification_ruleset=self.ruleset,
            extraction_profile=self.extraction_profile,
            normalization_profile=self.normalization_profile,
            normalization_manifest_sha256=normalization_manifest_sha,
            normalization_units_sha256=normalization_units_sha,
            provider=self.provider.name,
            requested_model=model,
            prompt_version=PROMPT_VERSION,
            prompt_sha256=prompt_sha256(),
            candidate_schema_version=SCHEMA_VERSION,
            candidate_schema_sha256=schema_sha256(),
            max_input_chars=self.max_input_chars,
            max_batch_units=self.max_batch_units,
            max_output_tokens=self.max_output_tokens,
            batch_count=len(batches),
            requests_path="requests.jsonl",
            requests_sha256=requests_sha,
            responses_path="responses.jsonl",
            responses_sha256=responses_sha,
            receipts_path="receipts.jsonl",
            receipts_sha256=receipts_sha,
            candidates_path="candidates.jsonl",
            candidates_sha256=candidates_sha,
            candidate_counts=candidate_counts(candidates),
        )
        final_dir = (
            self.output_root / source_id / snapshot_id / self.ruleset / self.extraction_profile
            / self.normalization_profile / self.profile / self.provider.name / run_id
        )
        publish_run(final_dir, {
            "requests.jsonl": requests_text,
            "responses.jsonl": responses_text,
            "receipts.jsonl": receipts_text,
            "candidates.jsonl": candidates_text,
            "synthesis.json": manifest.to_json(),
        })
        return manifest


__all__ = ["PROFILE_ID", "SynthesisEngine", "SynthesisError", "SynthesisManifest"]
