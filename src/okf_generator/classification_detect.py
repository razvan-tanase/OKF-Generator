from __future__ import annotations

import os
import stat
import zipfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from .classification_rules import FORMAT_BY_EXTENSION, SIGNATURE_RULES, FormatRule

PREFIX_BYTES = 64 * 1024
MAX_ZIP_PROBE_BYTES = 256 * 1024 * 1024
MAX_ZIP_MEMBERS = 20_000


class ClassificationDetectionError(RuntimeError):
    pass


@dataclass(frozen=True)
class EntryClassification:
    path: str
    entry_kind: str
    media_type: str
    format: str
    family: str
    route: str
    detection: Mapping[str, Any]
    diagnostics: tuple[str, ...] = ()


def _entry_kind(path: Path) -> str:
    mode = os.lstat(path).st_mode
    if stat.S_ISLNK(mode):
        return "symlink"
    if stat.S_ISREG(mode):
        return "file"
    if stat.S_ISDIR(mode):
        return "directory"
    raise ClassificationDetectionError(f"unsupported snapshot entry: {path}")


def _extension(path: Path) -> str:
    name = path.name.lower()
    if name.endswith(".tar.gz"):
        return ".gz"
    return path.suffix.lower()


def _text_probe(prefix: bytes) -> tuple[bool, str | None]:
    if not prefix:
        return True, "empty"
    if prefix.startswith(b"\xef\xbb\xbf"):
        try:
            prefix[3:].decode("utf-8")
            return True, "utf-8-sig"
        except UnicodeDecodeError:
            return False, None
    if prefix.startswith((b"\xff\xfe", b"\xfe\xff")):
        encoding = "utf-16-le" if prefix.startswith(b"\xff\xfe") else "utf-16-be"
        try:
            prefix[2:].decode(encoding)
            return True, encoding
        except UnicodeDecodeError:
            return False, None
    if b"\x00" in prefix:
        return False, None
    try:
        text = prefix.decode("utf-8")
    except UnicodeDecodeError:
        return False, None
    controls = sum(ord(ch) < 32 and ch not in "\t\n\r\f\b" for ch in text)
    return controls <= max(1, len(text) // 100), "utf-8"


def _tar_signature(prefix: bytes) -> bool:
    return len(prefix) >= 265 and prefix[257:262] == b"ustar"


def _zip_rule(path: Path, extension_rule: FormatRule | None) -> tuple[FormatRule, str, list[str]]:
    diagnostics: list[str] = []
    if path.stat().st_size > MAX_ZIP_PROBE_BYTES:
        diagnostics.append("zip-container-probe-skipped-size-limit")
        if extension_rule and extension_rule.signature_family == "zip":
            return extension_rule, "signature+extension", diagnostics
        return FORMAT_BY_EXTENSION[".zip"], "magic", diagnostics
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_ZIP_MEMBERS:
                diagnostics.append("zip-container-probe-member-limit")
                if extension_rule and extension_rule.signature_family == "zip":
                    return extension_rule, "signature+extension", diagnostics
                return FORMAT_BY_EXTENSION[".zip"], "magic", diagnostics
            names = {info.filename for info in infos}
            if "[Content_Types].xml" in names:
                if any(name.startswith("word/") for name in names):
                    return FORMAT_BY_EXTENSION[".docx"], "container", diagnostics
                if any(name.startswith("xl/") for name in names):
                    return FORMAT_BY_EXTENSION[".xlsx"], "container", diagnostics
                if any(name.startswith("ppt/") for name in names):
                    return FORMAT_BY_EXTENSION[".pptx"], "container", diagnostics
            try:
                info = archive.getinfo("mimetype")
            except KeyError:
                info = None
            if info is not None and info.file_size <= 128:
                value = archive.read(info).strip()
                zip_mimetypes = {
                    b"application/epub+zip": FORMAT_BY_EXTENSION[".epub"],
                    b"application/vnd.oasis.opendocument.text": FORMAT_BY_EXTENSION[".odt"],
                    b"application/vnd.oasis.opendocument.spreadsheet": FORMAT_BY_EXTENSION[".ods"],
                    b"application/vnd.oasis.opendocument.presentation": FORMAT_BY_EXTENSION[".odp"],
                }
                detected = zip_mimetypes.get(value)
                if detected is not None:
                    return detected, "container", diagnostics
    except (OSError, zipfile.BadZipFile):
        diagnostics.append("invalid-zip-container")
    return FORMAT_BY_EXTENSION[".zip"], "magic", diagnostics


def _classify_file(path: Path, relative: str) -> EntryClassification:
    with path.open("rb") as handle:
        prefix = handle.read(PREFIX_BYTES)
    ext = _extension(path)
    extension_rule = FORMAT_BY_EXTENSION.get(ext)
    diagnostics: list[str] = []

    if prefix.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")):
        rule, basis, zip_diagnostics = _zip_rule(path, extension_rule)
        diagnostics.extend(zip_diagnostics)
        if extension_rule and extension_rule.format != rule.format and basis != "signature+extension":
            diagnostics.append(f"extension-conflict:{extension_rule.format}->{rule.format}")
        return EntryClassification(relative, "file", rule.media_type, rule.format, rule.family, rule.route,
                                   {"basis": basis, "strength": "exact" if basis == "container" else "supported", "extension": ext or None}, tuple(diagnostics))

    if prefix.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        if extension_rule and extension_rule.signature_family == "ole":
            rule = extension_rule
            basis = "signature+extension"
        else:
            rule = FormatRule("ole-compound", "application/x-ole-storage", "binary", "binary")
            basis = "magic"
        return EntryClassification(relative, "file", rule.media_type, rule.format, rule.family, rule.route,
                                   {"basis": basis, "strength": "supported", "extension": ext or None}, ())

    if _tar_signature(prefix):
        rule = FORMAT_BY_EXTENSION[".tar"]
        if extension_rule and extension_rule.format != rule.format:
            diagnostics.append(f"extension-conflict:{extension_rule.format}->{rule.format}")
        return EntryClassification(relative, "file", rule.media_type, rule.format, rule.family, rule.route,
                                   {"basis": "magic", "strength": "exact", "extension": ext or None}, tuple(diagnostics))

    for signature_name, predicate, rule in SIGNATURE_RULES:
        if predicate(prefix):
            if extension_rule and extension_rule.format != rule.format:
                diagnostics.append(f"extension-conflict:{extension_rule.format}->{rule.format}")
            return EntryClassification(relative, "file", rule.media_type, rule.format, rule.family, rule.route,
                                       {"basis": "magic", "strength": "exact", "signature": signature_name, "extension": ext or None}, tuple(diagnostics))

    text_like, encoding = _text_probe(prefix)
    if extension_rule is not None:
        if extension_rule.text:
            if text_like:
                return EntryClassification(relative, "file", extension_rule.media_type, extension_rule.format,
                                           extension_rule.family, extension_rule.route,
                                           {"basis": "extension+text", "strength": "supported", "extension": ext, "encoding_hint": encoding}, ())
            diagnostics.append(f"extension-binary-conflict:{extension_rule.format}")
        elif extension_rule.signature_family:
            diagnostics.append(f"extension-signature-mismatch:{extension_rule.format}")

    if text_like:
        return EntryClassification(relative, "file", "text/plain", "text", "text", "text",
                                   {"basis": "text-probe", "strength": "generic", "extension": ext or None, "encoding_hint": encoding}, tuple(diagnostics))
    return EntryClassification(relative, "file", "application/octet-stream", "binary", "binary", "binary",
                               {"basis": "fallback", "strength": "generic", "extension": ext or None}, tuple(diagnostics))


def _walk_classifications(path: Path, relative: str = ".") -> Iterable[EntryClassification]:
    kind = _entry_kind(path)
    if kind == "symlink":
        yield EntryClassification(relative, kind, "inode/symlink", "symlink", "reference", "symlink",
                                  {"basis": "filesystem", "strength": "exact", "target": os.readlink(path)}, ())
        return
    if kind == "file":
        yield _classify_file(path, relative)
        return
    yield EntryClassification(relative, kind, "inode/directory", "directory", "container", "directory",
                              {"basis": "filesystem", "strength": "exact"}, ())
    with os.scandir(path) as iterator:
        children = sorted(iterator, key=lambda item: os.fsencode(item.name))
    for child in children:
        child_rel = child.name if relative == "." else f"{relative}/{child.name}"
        yield from _walk_classifications(Path(child.path), child_rel)


def _summary(entries: tuple[EntryClassification, ...]) -> Mapping[str, Any]:
    kinds = Counter(entry.entry_kind for entry in entries)
    families = Counter(entry.family for entry in entries)
    formats = Counter(entry.format for entry in entries)
    diagnostics = sum(len(entry.diagnostics) for entry in entries)
    return {
        "entry_count": len(entries),
        "diagnostic_count": diagnostics,
        "by_entry_kind": dict(sorted(kinds.items())),
        "by_family": dict(sorted(families.items())),
        "by_format": dict(sorted(formats.items())),
    }

