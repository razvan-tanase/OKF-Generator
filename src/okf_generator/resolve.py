from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping

from .acquire import SOURCE_ID_RE
from .classify import RULESET_ID, SNAPSHOT_ID_RE
from .extract import PROFILE_ID as EXTRACTION_PROFILE_ID
from .normalize import PROFILE_ID as NORMALIZATION_PROFILE_ID
from .resolution_adjudication import (
    ADJUDICATION_PROMPT_VERSION,
    ADJUDICATION_SCHEMA_VERSION,
    AdjudicationRequest,
    OpenAIResolutionAdjudicator,
    ResolutionAdjudicator,
    adjudication_input,
    validate_adjudication,
)
from .resolution_catalog import canonical_json_bytes, catalog_indexes, load_catalog
from .resolution_errors import ResolutionError
from .resolution_io import publish_run
from .resolution_model import ResolutionManifest
from .resolution_similarity import deterministic_signals, name_compatible, similarity
from .resolution_upstream import RUN_ID_RE, load_verified_synthesis, sha256_file, synthesis_run_dir
from .synthesize import PROFILE_ID as SYNTHESIS_PROFILE_ID, PROVIDER_RE

PROFILE_ID = "builtin-v1"
DEFAULT_SIMILARITY_THRESHOLD = 0.40
DEFAULT_SHORTLIST_LIMIT = 5
RESOLUTION_RUN_RE = re.compile(r"^sha256-[0-9a-f]{64}$")


def _jsonl(rows: list[Mapping[str, Any]]) -> str:
    try:
        return "".join(json.dumps(row, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False) + "\n" for row in rows)
    except (TypeError, ValueError) as exc:
        raise ResolutionError("resolution artifact contains a non-canonical JSON value") from exc


def _sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _resolution_counts(rows: list[Mapping[str, Any]]) -> dict[str, int]:
    counts = {"matched": 0, "new": 0, "ambiguous": 0}
    for row in rows:
        counts[str(row["status"])] += 1
    return counts


def _candidate_shortlist(candidate: Mapping[str, Any], concepts: list[Mapping[str, Any]], threshold: float, limit: int) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    for concept in concepts:
        score = similarity(candidate, concept)
        signals = deterministic_signals(candidate, concept)
        if score >= threshold or signals:
            ranked.append({
                "internal_id": concept["internal_id"],
                "title": concept["title"],
                "description": concept["description"],
                "canonical_path": concept["canonical_path"],
                "aliases": concept["aliases"],
                "title_history": concept["title_history"],
                "path_history": concept["path_history"],
                "resource_uris": concept["resource_uris"],
                "source_anchors": concept["source_anchors"],
                "status": concept["status"],
                "similarity": score,
                "signals": signals,
            })
    ranked.sort(key=lambda item: (-item["similarity"], item["internal_id"]))
    return ranked[:limit]


def _strong_match(candidate: Mapping[str, Any], concepts: list[Mapping[str, Any]]) -> tuple[str | None, list[str], str | None]:
    # Stage 06 candidate-v1 provides evidence anchors, not a concept-level resource identity.
    # Anchor/resource overlap therefore narrows or supports identity; it is never sufficient alone.
    compatible = [concept for concept in concepts if name_compatible(candidate["name"], concept)]
    anchor_compatible = [
        concept for concept in compatible
        if set(candidate["evidence_anchors"]) & set(concept["source_anchors"])
    ]
    if len(anchor_compatible) == 1:
        return anchor_compatible[0]["internal_id"], [], "source-anchor+name"
    if len(anchor_compatible) > 1:
        return None, sorted(item["internal_id"] for item in anchor_compatible), "source-anchor+name"

    bases = {anchor.split("#", 1)[0] for anchor in candidate["evidence_anchors"] if "#" in anchor}
    resource_compatible = [concept for concept in compatible if bases & set(concept["resource_uris"])]
    if len(resource_compatible) == 1:
        return resource_compatible[0]["internal_id"], [], "resource-uri+name"
    if len(resource_compatible) > 1:
        return None, sorted(item["internal_id"] for item in resource_compatible), "resource-uri+name"

    alias_history = []
    title_path = []
    from .resolution_catalog import normalize_label, path_basename_key
    key = normalize_label(candidate["name"])
    for concept in concepts:
        aliases = {normalize_label(x) for x in [*concept["aliases"], *concept["title_history"]]}
        if key in aliases:
            alias_history.append(concept)
            continue
        if key == normalize_label(concept["title"]) or key in {path_basename_key(x) for x in [concept["canonical_path"], *concept["path_history"]]}:
            title_path.append(concept)
    if len(alias_history) == 1:
        return alias_history[0]["internal_id"], [], "alias-history-exact"
    if len(alias_history) > 1:
        return None, sorted(item["internal_id"] for item in alias_history), "alias-history-exact"
    if len(title_path) == 1:
        return title_path[0]["internal_id"], [], "title-path-exact"
    if len(title_path) > 1:
        return None, sorted(item["internal_id"] for item in title_path), "title-path-exact"
    return None, [], None


class ResolutionEngine:
    def __init__(
        self,
        synthesis_root: Path | str = Path(".okf-generator/syntheses"),
        output_root: Path | str = Path(".okf-generator/resolutions"),
        *,
        ruleset: str = RULESET_ID,
        extraction_profile: str = EXTRACTION_PROFILE_ID,
        normalization_profile: str = NORMALIZATION_PROFILE_ID,
        synthesis_profile: str = SYNTHESIS_PROFILE_ID,
        profile: str = PROFILE_ID,
        similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
        shortlist_limit: int = DEFAULT_SHORTLIST_LIMIT,
        adjudicator: ResolutionAdjudicator | None = None,
    ) -> None:
        if ruleset != RULESET_ID or extraction_profile != EXTRACTION_PROFILE_ID or normalization_profile != NORMALIZATION_PROFILE_ID or synthesis_profile != SYNTHESIS_PROFILE_ID:
            raise ResolutionError("Stage 07 supports only the currently pinned upstream builtin-v1 profiles")
        if profile != PROFILE_ID:
            raise ResolutionError(f"unsupported resolution profile: {profile}")
        if not (0.0 <= similarity_threshold <= 1.0):
            raise ResolutionError("similarity_threshold must be between 0 and 1")
        if shortlist_limit < 1 or shortlist_limit > 50:
            raise ResolutionError("shortlist_limit must be between 1 and 50")
        self.synthesis_root = Path(synthesis_root)
        self.output_root = Path(output_root)
        self.ruleset = ruleset
        self.extraction_profile = extraction_profile
        self.normalization_profile = normalization_profile
        self.synthesis_profile = synthesis_profile
        self.profile = profile
        self.similarity_threshold = similarity_threshold
        self.shortlist_limit = shortlist_limit
        self.adjudicator = adjudicator

    def _validate_identity(self, source_id: str, snapshot_id: str, synthesis_provider: str, synthesis_run_id: str, adjudication_model: str | None) -> None:
        if not SOURCE_ID_RE.fullmatch(source_id):
            raise ResolutionError("source_id must match Stage 01 source identifier rules")
        if not SNAPSHOT_ID_RE.fullmatch(snapshot_id):
            raise ResolutionError("snapshot_id must match Stage 02 content-addressed identifier rules")
        if not PROVIDER_RE.fullmatch(synthesis_provider):
            raise ResolutionError("synthesis_provider is unsafe for resolution paths")
        if not RUN_ID_RE.fullmatch(synthesis_run_id):
            raise ResolutionError("synthesis_run_id must be a Stage 06 content-addressed identifier")
        if adjudication_model is not None and (not adjudication_model.strip() or len(adjudication_model) > 200 or any(ord(ch) < 32 for ch in adjudication_model)):
            raise ResolutionError("adjudication_model must be a printable non-empty identifier")
        if adjudication_model is not None and self.adjudicator is None:
            raise ResolutionError("adjudication_model requires an adjudicator")
        if adjudication_model is None and self.adjudicator is not None:
            raise ResolutionError("an adjudicator requires an explicit adjudication_model")

    def resolve(
        self,
        source_id: str,
        snapshot_id: str,
        synthesis_run_id: str,
        *,
        synthesis_provider: str,
        catalog_path: Path | str | None = None,
        adjudication_model: str | None = None,
    ) -> ResolutionManifest:
        self._validate_identity(source_id, snapshot_id, synthesis_provider, synthesis_run_id, adjudication_model)
        run_dir = synthesis_run_dir(
            self.synthesis_root, source_id, snapshot_id, self.ruleset, self.extraction_profile,
            self.normalization_profile, self.synthesis_profile, synthesis_provider, synthesis_run_id,
        )
        expected = {
            "source_id": source_id, "snapshot_id": snapshot_id, "ruleset": self.ruleset,
            "extraction_profile": self.extraction_profile, "normalization_profile": self.normalization_profile,
            "synthesis_profile": self.synthesis_profile, "synthesis_provider": synthesis_provider, "run_id": synthesis_run_id,
        }
        synthesis, candidates, synthesis_manifest_sha, synthesis_candidates_sha = load_verified_synthesis(run_dir, expected)
        concept_candidates = [item for item in candidates if item["candidate_type"] == "concept"]

        resolved_catalog_path = Path(catalog_path) if catalog_path is not None else None
        catalog, catalog_mode, catalog_source_sha, catalog_canonical_sha = load_catalog(resolved_catalog_path)
        indexes = catalog_indexes(catalog)
        concepts = indexes["concepts"]
        canonical_catalog_text = json.dumps(catalog, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n"

        resolution_rows: list[dict[str, Any]] = []
        request_rows: list[dict[str, Any]] = []
        response_rows: list[dict[str, Any]] = []
        receipt_rows: list[dict[str, Any]] = []

        for candidate in concept_candidates:
            matched_id, ambiguous_ids, method = _strong_match(candidate, concepts)
            shortlist = _candidate_shortlist(candidate, concepts, self.similarity_threshold, self.shortlist_limit)
            if matched_id is not None:
                status = "matched"
                resolved_id = matched_id
                considered = [matched_id]
                method_value = method
            else:
                if ambiguous_ids:
                    considered = ambiguous_ids
                    method_value = method or "deterministic-ambiguous"
                else:
                    considered = [item["internal_id"] for item in shortlist]
                    method_value = "similarity-shortlist" if shortlist else "no-catalog-candidate"

                if not considered:
                    status, resolved_id = "new", None
                elif self.adjudicator is None:
                    status, resolved_id = "ambiguous", None
                else:
                    shortlist_map = {item["internal_id"]: item for item in shortlist}
                    for internal_id in ambiguous_ids:
                        if internal_id not in shortlist_map:
                            concept = indexes["by_id"][internal_id]
                            shortlist_map[internal_id] = {
                                "internal_id": internal_id,
                                "title": concept["title"],
                                "description": concept["description"],
                                "canonical_path": concept["canonical_path"],
                                "aliases": concept["aliases"],
                                "title_history": concept["title_history"],
                                "path_history": concept["path_history"],
                                "resource_uris": concept["resource_uris"],
                                "source_anchors": concept["source_anchors"],
                                "status": concept["status"],
                                "similarity": similarity(candidate, concept),
                                "signals": deterministic_signals(candidate, concept),
                            }
                    adjudication_shortlist = [shortlist_map[i] for i in sorted(set(considered))]
                    input_text = adjudication_input(candidate, adjudication_shortlist)
                    request_rows.append({
                        "candidate_id": candidate["candidate_id"],
                        "model": adjudication_model,
                        "prompt_version": ADJUDICATION_PROMPT_VERSION,
                        "schema_version": ADJUDICATION_SCHEMA_VERSION,
                        "input": input_text,
                    })
                    result = self.adjudicator.adjudicate(AdjudicationRequest(candidate["candidate_id"], str(adjudication_model), input_text))
                    validated = validate_adjudication(dict(result.output), set(considered))
                    response_rows.append({"candidate_id": candidate["candidate_id"], "output": validated})
                    receipt_rows.append({
                        "candidate_id": candidate["candidate_id"],
                        "provider": self.adjudicator.name,
                        "response_id": result.response_id,
                        "requested_model": adjudication_model,
                        "resolved_model": result.resolved_model,
                        "usage": dict(result.usage),
                    })
                    if validated["decision"] == "match":
                        status, resolved_id, method_value = "matched", validated["internal_id"], "adjudicated-match"
                    elif validated["decision"] == "new":
                        status, resolved_id, method_value = "new", None, "adjudicated-new"
                    else:
                        status, resolved_id, method_value = "ambiguous", None, "adjudicated-ambiguous"

            signals = []
            for item in shortlist:
                signals.append({"internal_id": item["internal_id"], "similarity": item["similarity"], "signals": item["signals"]})
            resolution_rows.append({
                "candidate_id": candidate["candidate_id"],
                "candidate_name": candidate["name"],
                "status": status,
                "method": method_value,
                "resolved_internal_id": resolved_id,
                "considered_internal_ids": sorted(set(considered)),
                "evidence_anchors": candidate["evidence_anchors"],
                "signals": signals,
            })

        synthesis_after, _, synthesis_manifest_sha_after, synthesis_candidates_sha_after = load_verified_synthesis(run_dir, expected)
        if synthesis_after != synthesis or synthesis_manifest_sha_after != synthesis_manifest_sha or synthesis_candidates_sha_after != synthesis_candidates_sha:
            raise ResolutionError("Stage 06 synthesis changed while resolution was running")
        if resolved_catalog_path is not None:
            _, _, source_sha_after, canonical_sha_after = load_catalog(resolved_catalog_path)
            if source_sha_after != catalog_source_sha or canonical_sha_after != catalog_canonical_sha:
                raise ResolutionError("resolution catalog changed while resolution was running")

        resolutions_text = _jsonl(resolution_rows)
        adjudication_requests_text = _jsonl(request_rows)
        adjudication_responses_text = _jsonl(response_rows)
        adjudication_receipts_text = _jsonl(receipt_rows)
        resolution_sha = _sha_text(resolutions_text)
        request_sha = _sha_text(adjudication_requests_text)
        response_sha = _sha_text(adjudication_responses_text)
        receipt_sha = _sha_text(adjudication_receipts_text)
        run_descriptor = {
            "profile": self.profile,
            "synthesis_manifest_sha256": synthesis_manifest_sha,
            "synthesis_candidates_sha256": synthesis_candidates_sha,
            "catalog_source_sha256": catalog_source_sha,
            "catalog_canonical_sha256": catalog_canonical_sha,
            "similarity_threshold": self.similarity_threshold,
            "shortlist_limit": self.shortlist_limit,
            "adjudication_provider": self.adjudicator.name if self.adjudicator else None,
            "adjudication_model": adjudication_model,
            "resolutions_sha256": resolution_sha,
            "adjudication_requests_sha256": request_sha,
            "adjudication_responses_sha256": response_sha,
            "adjudication_receipts_sha256": receipt_sha,
        }
        resolution_run_id = "sha256-" + hashlib.sha256(canonical_json_bytes(run_descriptor)).hexdigest()
        if not RESOLUTION_RUN_RE.fullmatch(resolution_run_id):
            raise ResolutionError("internal resolution run identity failure")
        manifest = ResolutionManifest(
            schema_version="0.1", stage="07-resolve", profile=self.profile, run_id=resolution_run_id,
            source_id=source_id, snapshot_id=snapshot_id, classification_ruleset=self.ruleset,
            extraction_profile=self.extraction_profile, normalization_profile=self.normalization_profile,
            synthesis_profile=self.synthesis_profile, synthesis_provider=synthesis_provider,
            synthesis_run_id=synthesis_run_id, synthesis_manifest_sha256=synthesis_manifest_sha,
            synthesis_candidates_sha256=synthesis_candidates_sha, catalog_mode=catalog_mode,
            catalog_source_sha256=catalog_source_sha, catalog_canonical_sha256=catalog_canonical_sha,
            catalog_path="catalog.json", similarity_threshold=self.similarity_threshold, shortlist_limit=self.shortlist_limit,
            adjudication_provider=self.adjudicator.name if self.adjudicator else None,
            adjudication_model=adjudication_model, resolutions_path="resolutions.jsonl", resolutions_sha256=resolution_sha,
            resolution_counts=_resolution_counts(resolution_rows), adjudication_requests_path="adjudication-requests.jsonl",
            adjudication_requests_sha256=request_sha, adjudication_responses_path="adjudication-responses.jsonl",
            adjudication_responses_sha256=response_sha, adjudication_receipts_path="adjudication-receipts.jsonl",
            adjudication_receipts_sha256=receipt_sha,
        )
        final_dir = (
            self.output_root / source_id / snapshot_id / self.ruleset / self.extraction_profile / self.normalization_profile
            / self.synthesis_profile / synthesis_provider / synthesis_run_id / self.profile / resolution_run_id
        )
        publish_run(final_dir, {
            "catalog.json": canonical_catalog_text,
            "resolutions.jsonl": resolutions_text,
            "adjudication-requests.jsonl": adjudication_requests_text,
            "adjudication-responses.jsonl": adjudication_responses_text,
            "adjudication-receipts.jsonl": adjudication_receipts_text,
            "resolution.json": manifest.to_json(),
        })
        return manifest


__all__ = [
    "DEFAULT_SHORTLIST_LIMIT", "DEFAULT_SIMILARITY_THRESHOLD", "PROFILE_ID", "ResolutionEngine",
    "ResolutionError", "ResolutionManifest", "OpenAIResolutionAdjudicator",
]
