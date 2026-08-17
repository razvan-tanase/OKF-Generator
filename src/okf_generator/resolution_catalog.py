from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from .resolution_errors import ResolutionError

CATALOG_SCHEMA_VERSION = "0.1"
INTERNAL_ID_RE = re.compile(r"^[^\x00-\x1f\x7f]{1,200}$")


def canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ResolutionError("resolution catalog contains a non-canonical JSON value") from exc


def normalize_label(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).casefold().split())


def normalize_path_key(value: str) -> str:
    text = unicodedata.normalize("NFC", value).replace("\\", "/")
    path = PurePosixPath(text)
    if path.is_absolute() or ".." in path.parts or text in {"", "."}:
        raise ResolutionError(f"catalog path is unsafe: {value!r}")
    return "/".join(part.casefold() for part in path.parts)


def path_basename_key(value: str) -> str:
    last = PurePosixPath(value).name
    if last.endswith(".md"):
        last = last[:-3]
    last = re.sub(r"[-_]+", " ", last)
    return normalize_label(last)


def _string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ResolutionError(f"{label} must be an array of non-empty strings")
    if len(set(value)) != len(value):
        raise ResolutionError(f"{label} contains duplicate values")
    return list(value)


def empty_catalog() -> dict[str, Any]:
    return {"schema_version": CATALOG_SCHEMA_VERSION, "concepts": []}


def validate_catalog(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"schema_version", "concepts"}:
        raise ResolutionError("resolution catalog must contain exactly schema_version and concepts")
    if value.get("schema_version") != CATALOG_SCHEMA_VERSION:
        raise ResolutionError(f"unsupported resolution catalog schema: {value.get('schema_version')!r}")
    concepts = value.get("concepts")
    if not isinstance(concepts, list):
        raise ResolutionError("resolution catalog concepts must be an array")

    expected = {
        "internal_id", "title", "description", "canonical_path", "aliases", "title_history",
        "path_history", "resource_uris", "source_anchors", "status",
    }
    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    clean: list[dict[str, Any]] = []
    for index, item in enumerate(concepts):
        if not isinstance(item, dict) or set(item) != expected:
            actual = set(item) if isinstance(item, dict) else set()
            raise ResolutionError(
                f"catalog concept {index} schema mismatch; missing={sorted(expected-actual)}, extra={sorted(actual-expected)}"
            )
        internal_id = item["internal_id"]
        if not isinstance(internal_id, str) or not INTERNAL_ID_RE.fullmatch(internal_id):
            raise ResolutionError(f"catalog concept {index} has invalid internal_id")
        if internal_id in seen_ids:
            raise ResolutionError(f"duplicate catalog internal_id: {internal_id}")
        seen_ids.add(internal_id)
        for field in ("title", "description", "canonical_path", "status"):
            if not isinstance(item[field], str) or not item[field]:
                raise ResolutionError(f"catalog concept {internal_id} field {field} must be non-empty")
        canonical_path_key = normalize_path_key(item["canonical_path"])
        if canonical_path_key in seen_paths:
            raise ResolutionError(f"duplicate normalized catalog canonical_path: {item['canonical_path']}")
        seen_paths.add(canonical_path_key)
        clean.append({
            "internal_id": internal_id,
            "title": unicodedata.normalize("NFC", item["title"]),
            "description": unicodedata.normalize("NFC", item["description"]),
            "canonical_path": unicodedata.normalize("NFC", item["canonical_path"]),
            "aliases": [unicodedata.normalize("NFC", x) for x in _string_list(item["aliases"], f"catalog concept {internal_id} aliases")],
            "title_history": [unicodedata.normalize("NFC", x) for x in _string_list(item["title_history"], f"catalog concept {internal_id} title_history")],
            "path_history": [unicodedata.normalize("NFC", x) for x in _string_list(item["path_history"], f"catalog concept {internal_id} path_history")],
            "resource_uris": [unicodedata.normalize("NFC", x) for x in _string_list(item["resource_uris"], f"catalog concept {internal_id} resource_uris")],
            "source_anchors": [unicodedata.normalize("NFC", x) for x in _string_list(item["source_anchors"], f"catalog concept {internal_id} source_anchors")],
            "status": unicodedata.normalize("NFC", item["status"]),
        })
    clean.sort(key=lambda item: item["internal_id"])
    return {"schema_version": CATALOG_SCHEMA_VERSION, "concepts": clean}


def load_catalog(path: Path | None) -> tuple[dict[str, Any], str, str | None, str]:
    if path is None:
        catalog = empty_catalog()
        canonical = canonical_json_bytes(catalog)
        return catalog, "empty", None, hashlib.sha256(canonical).hexdigest()
    if not path.is_file():
        raise ResolutionError(f"resolution catalog is missing: {path}")
    raw = path.read_bytes()
    source_sha = hashlib.sha256(raw).hexdigest()
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ResolutionError("resolution catalog is unreadable JSON") from exc
    catalog = validate_catalog(value)
    canonical_sha = hashlib.sha256(canonical_json_bytes(catalog)).hexdigest()
    return catalog, "file", source_sha, canonical_sha


def catalog_indexes(catalog: Mapping[str, Any]) -> dict[str, Any]:
    concepts = list(catalog["concepts"])
    by_id = {item["internal_id"]: item for item in concepts}
    return {"concepts": concepts, "by_id": by_id}
