from __future__ import annotations
import hashlib, re, unicodedata
from typing import Any
from .planning_io import canonical_json_bytes
from .resolution_catalog import normalize_path_key

SLUG_BASIS='unicode-nfc-casefold-alnum-v1'

def provisional_id(object_type:str, descriptor:Any)->str:
    digest=hashlib.sha256(canonical_json_bytes({'object_type':object_type,'descriptor':descriptor})).hexdigest()
    return f'urn:okf-generator:{object_type}:sha256-{digest}'

def slugify(name:str)->str:
    text=unicodedata.normalize('NFC',name).casefold()
    out=[]; dash=False
    for ch in text:
        if ch.isalnum():
            out.append(ch); dash=False
        else:
            if out and not dash:
                out.append('-'); dash=True
    slug=''.join(out).strip('-')
    return slug

def propose_concept_path(name:str, descriptor:Any, used_path_keys:set[str])->str:
    digest=hashlib.sha256(canonical_json_bytes(descriptor)).hexdigest()
    slug=slugify(name) or f'concept-{digest[:12]}'
    base=f'concepts/{slug}.md'
    candidate=base; key=normalize_path_key(candidate)
    if key in used_path_keys:
        candidate=f'concepts/{slug}--{digest[:10]}.md'; key=normalize_path_key(candidate)
        counter=1
        while key in used_path_keys:
            candidate=f'concepts/{slug}--{digest[:10]}-{counter}.md'; key=normalize_path_key(candidate); counter+=1
    used_path_keys.add(key)
    return candidate
