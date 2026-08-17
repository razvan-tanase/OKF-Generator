from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .extractor_core import ExtractorError, ExtractorResult, RawUnit, extract_pdf, extract_text_file
from .extractor_docx import extract_docx
from .extractor_pptx_xlsx import extract_pptx, extract_xlsx
from .extractor_odf_epub import extract_odf, extract_epub
from .extractor_archive import extract_archive
from .extractor_git import extract_git


def extract_unsupported(path: Path, entry: Mapping[str, Any]) -> ExtractorResult:
    route = str(entry.get("route"))
    fmt = str(entry.get("format"))
    diagnostic = f"no-stage-04-extractor:{route}:{fmt}"
    return ExtractorResult((RawUnit(str(entry["path"]), "unsupported", native_locator={"path": str(entry["path"])},
                                    metadata={"route": route, "format": fmt, "media_type": entry.get("media_type")},
                                    diagnostics=(diagnostic,)),), (diagnostic,))


def dispatch_file(path: Path, entry: Mapping[str, Any]) -> ExtractorResult:
    route = str(entry.get("route"))
    fmt = str(entry.get("format"))
    if route in {"text", "markdown", "markup", "structured-text", "text-source"}:
        return extract_text_file(path, entry)
    if route == "pdf":
        return extract_pdf(path, entry)
    if route == "office":
        if fmt == "docx":
            return extract_docx(path, entry)
        if fmt == "pptx":
            return extract_pptx(path, entry)
        if fmt == "xlsx":
            return extract_xlsx(path, entry)
        if fmt in {"odt", "ods", "odp"}:
            return extract_odf(path, entry)
        return extract_unsupported(path, entry)
    if route == "archive-document" and fmt == "epub":
        return extract_epub(path, entry)
    if route == "archive":
        return extract_archive(path, entry)
    return extract_unsupported(path, entry)


__all__ = [
    "ExtractorError", "ExtractorResult", "RawUnit", "extract_text_file", "extract_pdf",
    "extract_docx", "extract_pptx", "extract_xlsx", "extract_odf", "extract_epub",
    "extract_archive", "extract_git", "extract_unsupported", "dispatch_file",
]
