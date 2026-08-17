from __future__ import annotations
import hashlib
from pathlib import PurePosixPath
from .structural_errors import StructuralizationError
from .resolution_catalog import normalize_path_key

RESERVED_BASENAMES={"index.md","log.md"}

def identity_ref(internal_id:str)->str:
    return "idref-sha256-"+hashlib.sha256(internal_id.encode("utf-8")).hexdigest()[:24]

def auxiliary_path(object_type:str, internal_id:str)->str:
    if object_type not in {"summary","claim","relation"}: raise StructuralizationError(f"unsupported auxiliary object type: {object_type}")
    digest=hashlib.sha256(internal_id.encode("utf-8")).hexdigest()[:24]
    folder={"summary":"summaries","claim":"claims","relation":"relations"}[object_type]
    return f"{folder}/sha256-{digest}.md"

def validate_public_path(path:str)->str:
    p=PurePosixPath(path.replace("\\","/"))
    if p.is_absolute() or ".." in p.parts or not p.parts or p.suffix.lower()!=".md":
        raise StructuralizationError(f"unsafe structural document path: {path!r}")
    normalized="/".join(p.parts)
    if p.name.casefold() in RESERVED_BASENAMES:
        raise StructuralizationError(f"canonical object path collides with reserved OKF path: {path}")
    normalize_path_key(normalized)
    return normalized
