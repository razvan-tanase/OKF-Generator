from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any, Mapping

from .resolution_catalog import normalize_label, path_basename_key

TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)


def resource_bases(anchors: list[str]) -> set[str]:
    return {anchor.split("#", 1)[0] for anchor in anchors if "#" in anchor}


def title_keys(concept: Mapping[str, Any]) -> set[str]:
    values = [concept["title"], *concept["aliases"], *concept["title_history"]]
    return {normalize_label(value) for value in values if normalize_label(value)}


def path_keys(concept: Mapping[str, Any]) -> set[str]:
    values = [concept["canonical_path"], *concept["path_history"]]
    return {path_basename_key(value) for value in values}


def name_compatible(candidate_name: str, concept: Mapping[str, Any]) -> bool:
    key = normalize_label(candidate_name)
    return key in title_keys(concept) or key in path_keys(concept)


def _tokens(text: str) -> set[str]:
    return {match.group(0).casefold() for match in TOKEN_RE.finditer(normalize_label(text)) if len(match.group(0)) > 1}


def similarity(candidate: Mapping[str, Any], concept: Mapping[str, Any]) -> float:
    candidate_name = normalize_label(candidate["name"])
    candidate_text = f"{candidate['name']} {candidate['description']}"
    catalog_text = " ".join([concept["title"], concept["description"], *concept["aliases"], *concept["title_history"]])
    a = _tokens(candidate_text)
    b = _tokens(catalog_text)
    jaccard = len(a & b) / len(a | b) if a or b else 0.0
    name_score = max(
        [SequenceMatcher(None, candidate_name, key).ratio() for key in (title_keys(concept) | path_keys(concept))]
        or [0.0]
    )
    return round(0.55 * name_score + 0.45 * jaccard, 6)


def deterministic_signals(candidate: Mapping[str, Any], concept: Mapping[str, Any]) -> list[str]:
    signals: list[str] = []
    anchors = set(candidate["evidence_anchors"])
    if anchors & set(concept["source_anchors"]):
        signals.append("source-anchor-overlap")
    if resource_bases(candidate["evidence_anchors"]) & set(concept["resource_uris"]):
        signals.append("resource-uri-overlap")
    name_key = normalize_label(candidate["name"])
    if name_key in {normalize_label(value) for value in [*concept["aliases"], *concept["title_history"]]}:
        signals.append("alias-history-exact")
    if name_key == normalize_label(concept["title"]):
        signals.append("title-exact")
    if name_key in path_keys(concept):
        signals.append("path-title-exact")
    return signals
