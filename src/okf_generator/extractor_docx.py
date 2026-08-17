from __future__ import annotations

import posixpath
import urllib.parse
import zipfile
from pathlib import Path
from typing import Any, Mapping

from .extractor_core import ExtractorError, ExtractorResult, RawUnit, _package_version, _xml_from_bytes, _xml_text, _zip_guard

def extract_docx(path: Path, entry: Mapping[str, Any]) -> ExtractorResult:
    units: list[RawUnit] = []
    with zipfile.ZipFile(path) as zf:
        _zip_guard(zf)
        try:
            root = _xml_from_bytes(zf.read("word/document.xml"))
        except KeyError as exc:
            raise ExtractorError("DOCX is missing word/document.xml") from exc
    body = next((node for node in root.iter() if node.tag.endswith("}body")), root)
    p_index = 0
    table_index = 0
    for child in list(body):
        if child.tag.endswith("}p"):
            p_index += 1
            units.append(RawUnit(str(entry["path"]), "paragraph", _xml_text(child),
                                 native_locator={"paragraph": p_index}, metadata={"format": "docx"}))
        elif child.tag.endswith("}tbl"):
            table_index += 1
            row_index = 0
            for row in [n for n in child if n.tag.endswith("}tr")]:
                row_index += 1
                cells = [_xml_text(cell) for cell in row if cell.tag.endswith("}tc")]
                units.append(RawUnit(str(entry["path"]), "table-row", "\t".join(cells),
                                     data={"cells": cells}, native_locator={"table": table_index, "row": row_index},
                                     metadata={"format": "docx"}))
    return ExtractorResult(tuple(units), tools={"defusedxml": _package_version("defusedxml")})


def _relationship_targets(zf: zipfile.ZipFile, rels_path: str, base_dir: str) -> dict[str, str]:
    try:
        root = _xml_from_bytes(zf.read(rels_path))
    except KeyError as exc:
        raise ExtractorError(f"package relationships missing: {rels_path}") from exc
    result: dict[str, str] = {}
    for rel in root.iter():
        if not rel.tag.endswith("}Relationship"):
            continue
        rid = rel.attrib.get("Id")
        target = rel.attrib.get("Target")
        mode = rel.attrib.get("TargetMode")
        if not rid or not target or mode == "External":
            continue
        target = urllib.parse.unquote(target)
        joined = posixpath.normpath(target.lstrip("/")) if target.startswith("/") else posixpath.normpath(posixpath.join(base_dir, target))
        if joined == ".." or joined.startswith("../") or joined.startswith("/"):
            raise ExtractorError(f"unsafe package relationship target: {target}")
        result[rid] = joined
    return result


