from __future__ import annotations

import hashlib
import json
import math
import unicodedata
from pathlib import PurePosixPath
from typing import Any, Mapping
from urllib.parse import quote

from .normalization_errors import NormalizationError

ANCHOR_BASIS = "native-locator-v1"
TEXT_NORMALIZATION = "unicode-nfc+lf-v1"


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def normalize_unicode(value: str) -> str:
    normalized = unicodedata.normalize("NFC", value)
    if any(0xD800 <= ord(ch) <= 0xDFFF for ch in normalized):
        raise NormalizationError("text contains an unpaired Unicode surrogate")
    return normalized


def normalize_text(value: str) -> str:
    # Preserve all spacing and terminal newlines. Only Unicode composition and
    # platform line-ending differences are canonicalized.
    return normalize_unicode(value.replace("\r\n", "\n").replace("\r", "\n"))


def canonicalize_json(value: Any, *, label: str) -> Any:
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise NormalizationError(f"{label} contains a non-finite number")
        return value
    if isinstance(value, str):
        return normalize_unicode(value)
    if isinstance(value, list):
        return [
            canonicalize_json(item, label=f"{label}[{index}]")
            for index, item in enumerate(value)
        ]
    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        original_by_key: dict[str, str] = {}
        for raw_key, raw_value in value.items():
            if not isinstance(raw_key, str):
                raise NormalizationError(f"{label} contains a non-string object key")
            key = normalize_unicode(raw_key)
            if key in normalized and original_by_key[key] != raw_key:
                raise NormalizationError(
                    f"{label} contains object keys that collide after Unicode NFC normalization"
                )
            normalized[key] = canonicalize_json(raw_value, label=f"{label}.{key}")
            original_by_key[key] = raw_key
        return normalized
    raise NormalizationError(
        f"{label} contains unsupported JSON value type: {type(value).__name__}"
    )


def normalize_source_path(value: str) -> str:
    normalized = normalize_unicode(value)
    candidate = PurePosixPath(normalized)
    if candidate.is_absolute() or ".." in candidate.parts or normalized == "":
        raise NormalizationError(f"unsafe normalized source path: {value!r}")
    return normalized


def source_uri(source_id: str) -> str:
    encoded_source = quote(source_id, safe="-._~")
    return f"okf-source:{encoded_source}"


def source_version_uri(logical_source_uri: str, snapshot_id: str) -> str:
    return f"{logical_source_uri}@{snapshot_id}"


def anchor_id(source_path: str, kind: str, native_locator: Mapping[str, Any]) -> str:
    descriptor = {
        "basis": ANCHOR_BASIS,
        "source_path": source_path,
        "kind": kind,
        "native_locator": native_locator,
    }
    digest = hashlib.sha256(canonical_json_bytes(descriptor)).hexdigest()
    return f"a-sha256-{digest}"
