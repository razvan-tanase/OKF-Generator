from __future__ import annotations

import importlib.metadata
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

MAX_TEXT_BYTES = 256 * 1024 * 1024
MAX_PDF_BYTES = 512 * 1024 * 1024
MAX_PDF_PAGES = 10_000
MAX_PDF_TEXT_CHARS = 256 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 20_000
MAX_MEMBER_BYTES = 64 * 1024 * 1024
MAX_TOTAL_UNCOMPRESSED_BYTES = 512 * 1024 * 1024
MAX_GIT_BLOBS = 100_000
MAX_GIT_BLOB_BYTES = 64 * 1024 * 1024
MAX_GIT_TOTAL_BYTES = 512 * 1024 * 1024


class ExtractorError(RuntimeError):
    pass


@dataclass(frozen=True)
class RawUnit:
    source_path: str
    kind: str
    text: str | None = None
    data: Mapping[str, Any] = field(default_factory=dict)
    native_locator: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    diagnostics: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExtractorResult:
    units: tuple[RawUnit, ...]
    diagnostics: tuple[str, ...] = ()
    tools: Mapping[str, str] = field(default_factory=dict)


def _package_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "unavailable"


def _decode_text(data: bytes, encoding_hint: str | None = None) -> tuple[str, str]:
    candidates: list[str] = []
    if encoding_hint and encoding_hint != "empty":
        candidates.append(encoding_hint)
    if data.startswith(b"\xef\xbb\xbf"):
        candidates.append("utf-8-sig")
    elif data.startswith((b"\xff\xfe", b"\xfe\xff")):
        candidates.insert(0, "utf-16")
    candidates.append("utf-8")
    seen: set[str] = set()
    for encoding in candidates:
        if encoding in seen:
            continue
        seen.add(encoding)
        try:
            return data.decode(encoding), encoding
        except UnicodeDecodeError:
            pass
    raise ExtractorError("classified text could not be decoded without replacement characters")


def _maybe_text(data: bytes) -> str | None:
    try:
        text, _ = _decode_text(data)
    except ExtractorError:
        return None
    controls = sum(ord(ch) < 32 and ch not in "\t\n\r\f\b" for ch in text[:65536])
    if controls > max(1, len(text[:65536]) // 100):
        return None
    return text


def _is_text_bytes(data: bytes) -> bool:
    return _maybe_text(data) is not None


def extract_text_file(path: Path, entry: Mapping[str, Any]) -> ExtractorResult:
    if path.stat().st_size > MAX_TEXT_BYTES:
        raise ExtractorError(f"text source exceeds size limit: {path.stat().st_size} > {MAX_TEXT_BYTES}")
    text, encoding = _decode_text(path.read_bytes(), entry.get("detection", {}).get("encoding_hint"))
    return ExtractorResult((RawUnit(
        source_path=str(entry["path"]),
        kind="text-document",
        text=text,
        native_locator={"path": str(entry["path"])},
        metadata={"format": entry.get("format"), "media_type": entry.get("media_type"), "encoding": encoding},
    ),))


def extract_pdf(path: Path, entry: Mapping[str, Any]) -> ExtractorResult:
    if path.stat().st_size > MAX_PDF_BYTES:
        raise ExtractorError(f"PDF exceeds size limit: {path.stat().st_size} > {MAX_PDF_BYTES}")
    try:
        import pypdf
        from pypdf import PdfReader
    except ImportError as exc:
        raise ExtractorError("PDF extraction requires pypdf") from exc
    try:
        reader = PdfReader(str(path), strict=False)
        if getattr(reader, "is_encrypted", False):
            try:
                unlocked = reader.decrypt("")
            except Exception:
                unlocked = 0
            if not unlocked:
                raise ExtractorError("encrypted PDF requires a password; Stage 04 does not supply credentials")
    except ExtractorError:
        raise
    except Exception as exc:
        raise ExtractorError(f"pypdf could not open PDF: {exc}") from exc
    if len(reader.pages) > MAX_PDF_PAGES:
        raise ExtractorError(f"PDF page limit exceeded: {len(reader.pages)} > {MAX_PDF_PAGES}")
    units: list[RawUnit] = []
    diagnostics: list[str] = []
    total_chars = 0
    for index, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception as exc:
            text = ""
            diagnostics.append(f"pdf-page-extraction-failed:{index}:{type(exc).__name__}")
        total_chars += len(text)
        if total_chars > MAX_PDF_TEXT_CHARS:
            raise ExtractorError("PDF extracted-text size limit exceeded")
        page_diagnostics: list[str] = []
        if not text.strip():
            page_diagnostics.append("pdf-page-has-no-embedded-text")
        units.append(RawUnit(
            source_path=str(entry["path"]),
            kind="page",
            text=text,
            native_locator={"page": index},
            metadata={"format": "pdf", "media_type": "application/pdf"},
            diagnostics=tuple(page_diagnostics),
        ))
    return ExtractorResult(tuple(units), tuple(diagnostics), {"pypdf": getattr(pypdf, "__version__", _package_version("pypdf"))})


def _xml_from_bytes(data: bytes):
    try:
        from defusedxml import ElementTree as ET
    except ImportError as exc:
        raise ExtractorError("Office/EPUB extraction requires defusedxml") from exc
    try:
        return ET.fromstring(data)
    except Exception as exc:
        raise ExtractorError(f"XML parse failed: {exc}") from exc


def _xml_text(element, text_tag_suffix: str = "}t") -> str:
    parts: list[str] = []
    for node in element.iter():
        if node.tag.endswith(text_tag_suffix) and node.text:
            parts.append(node.text)
        elif node.tag.endswith("}tab"):
            parts.append("\t")
        elif node.tag.endswith("}br"):
            parts.append("\n")
    return "".join(parts)


def _zip_guard(archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    infos = archive.infolist()
    if len(infos) > MAX_ARCHIVE_MEMBERS:
        raise ExtractorError(f"archive member limit exceeded: {len(infos)} > {MAX_ARCHIVE_MEMBERS}")
    total = 0
    for info in infos:
        if info.file_size > MAX_MEMBER_BYTES:
            raise ExtractorError(f"archive member exceeds size limit: {info.filename}")
        total += info.file_size
        if total > MAX_TOTAL_UNCOMPRESSED_BYTES:
            raise ExtractorError("archive total uncompressed-size limit exceeded")
    return infos
