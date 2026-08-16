from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any, Mapping

from .extractor_core import ExtractorError, ExtractorResult, RawUnit, _package_version, _xml_from_bytes, _xml_text, _zip_guard
from .extractor_docx import _relationship_targets

def _ordered_pptx_slides(zf: zipfile.ZipFile) -> list[str]:
    try:
        root = _xml_from_bytes(zf.read("ppt/presentation.xml"))
    except KeyError as exc:
        raise ExtractorError("PPTX is missing ppt/presentation.xml") from exc
    rels = _relationship_targets(zf, "ppt/_rels/presentation.xml.rels", "ppt")
    ordered: list[str] = []
    for node in root.iter():
        if node.tag.endswith("}sldId"):
            rid = next((value for key, value in node.attrib.items() if key.endswith("}id")), None)
            if rid and rid in rels:
                ordered.append(rels[rid])
    if not ordered:
        raise ExtractorError("PPTX presentation has no resolvable slides")
    return ordered


def _ordered_xlsx_sheets(zf: zipfile.ZipFile) -> list[tuple[str, str]]:
    try:
        root = _xml_from_bytes(zf.read("xl/workbook.xml"))
    except KeyError as exc:
        raise ExtractorError("XLSX is missing xl/workbook.xml") from exc
    rels = _relationship_targets(zf, "xl/_rels/workbook.xml.rels", "xl")
    ordered: list[tuple[str, str]] = []
    for node in root.iter():
        if node.tag.endswith("}sheet"):
            rid = next((value for key, value in node.attrib.items() if key.endswith("}id")), None)
            name = node.attrib.get("name") or f"Sheet{len(ordered)+1}"
            if rid and rid in rels:
                ordered.append((name, rels[rid]))
    if not ordered:
        raise ExtractorError("XLSX workbook has no resolvable worksheets")
    return ordered


def extract_pptx(path: Path, entry: Mapping[str, Any]) -> ExtractorResult:
    units: list[RawUnit] = []
    with zipfile.ZipFile(path) as zf:
        _zip_guard(zf)
        slides = _ordered_pptx_slides(zf)
        for slide_no, name in enumerate(slides, start=1):
            root = _xml_from_bytes(zf.read(name))
            paragraph_no = 0
            for p in (n for n in root.iter() if n.tag.endswith("}p")):
                text = _xml_text(p)
                if text or list(p):
                    paragraph_no += 1
                    units.append(RawUnit(str(entry["path"]), "slide-paragraph", text,
                                         native_locator={"slide": slide_no, "paragraph": paragraph_no},
                                         metadata={"format": "pptx"}))
    return ExtractorResult(tuple(units), tools={"defusedxml": _package_version("defusedxml")})


def _xlsx_shared_strings(zf: zipfile.ZipFile) -> list[str]:
    try:
        root = _xml_from_bytes(zf.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    result: list[str] = []
    for si in [n for n in root if n.tag.endswith("}si")]:
        result.append("".join(n.text or "" for n in si.iter() if n.tag.endswith("}t")))
    return result


def extract_xlsx(path: Path, entry: Mapping[str, Any]) -> ExtractorResult:
    units: list[RawUnit] = []
    with zipfile.ZipFile(path) as zf:
        _zip_guard(zf)
        shared = _xlsx_shared_strings(zf)
        sheets = _ordered_xlsx_sheets(zf)
        for sheet_no, (sheet_name, name) in enumerate(sheets, start=1):
            root = _xml_from_bytes(zf.read(name))
            for row in (n for n in root.iter() if n.tag.endswith("}row")):
                row_no_raw = row.attrib.get("r")
                row_no = int(row_no_raw) if row_no_raw and row_no_raw.isdigit() else None
                cells: list[Mapping[str, Any]] = []
                text_cells: list[str] = []
                for cell in (n for n in row if n.tag.endswith("}c")):
                    coord = cell.attrib.get("r")
                    ctype = cell.attrib.get("t")
                    value_node = next((n for n in cell if n.tag.endswith("}v")), None)
                    formula_node = next((n for n in cell if n.tag.endswith("}f")), None)
                    inline = next((n for n in cell if n.tag.endswith("}is")), None)
                    raw = value_node.text if value_node is not None else None
                    value: Any = raw
                    if ctype == "s" and raw is not None and raw.isdigit():
                        idx = int(raw)
                        value = shared[idx] if idx < len(shared) else raw
                    elif ctype == "inlineStr" and inline is not None:
                        value = "".join(n.text or "" for n in inline.iter() if n.tag.endswith("}t"))
                    cells.append({"coordinate": coord, "type": ctype, "value": value,
                                  "formula": formula_node.text if formula_node is not None else None})
                    text_cells.append("" if value is None else str(value))
                units.append(RawUnit(str(entry["path"]), "worksheet-row", "\t".join(text_cells),
                                     data={"cells": cells}, native_locator={"sheet": sheet_no, "sheet_name": sheet_name, "row": row_no},
                                     metadata={"format": "xlsx"}))
    return ExtractorResult(tuple(units), tools={"defusedxml": _package_version("defusedxml")})


