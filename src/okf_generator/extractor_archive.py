from __future__ import annotations

import bz2
import gzip
import hashlib
import lzma
import tarfile
import zipfile
from pathlib import Path
from typing import Any, Mapping

from .extractor_core import ExtractorError, ExtractorResult, RawUnit, _maybe_text, _zip_guard, MAX_ARCHIVE_MEMBERS, MAX_MEMBER_BYTES, MAX_TOTAL_UNCOMPRESSED_BYTES

def _archive_member_unit(source_path: str, name: str, size: int, data: bytes | None) -> RawUnit:
    sha = hashlib.sha256(data).hexdigest() if data is not None else None
    text = None
    diagnostics: tuple[str, ...] = ()
    if data is not None:
        text = _maybe_text(data)
        if text is None:
            diagnostics = ("archive-member-binary-not-decoded",)
    return RawUnit(source_path, "archive-member", text, data={"size": size, "sha256": sha},
                   native_locator={"member": name}, diagnostics=diagnostics)


def extract_archive(path: Path, entry: Mapping[str, Any]) -> ExtractorResult:
    fmt = str(entry.get("format"))
    units: list[RawUnit] = []
    if fmt == "zip":
        with zipfile.ZipFile(path) as zf:
            infos = _zip_guard(zf)
            for info in infos:
                if info.is_dir():
                    units.append(RawUnit(str(entry["path"]), "archive-directory", native_locator={"member": info.filename}))
                    continue
                data = zf.read(info)
                units.append(_archive_member_unit(str(entry["path"]), info.filename, info.file_size, data))
    elif fmt == "tar":
        with tarfile.open(path, "r:*") as tf:
            members = tf.getmembers()
            if len(members) > MAX_ARCHIVE_MEMBERS:
                raise ExtractorError("tar member limit exceeded")
            total = 0
            for member in members:
                if member.isfile():
                    if member.size > MAX_MEMBER_BYTES:
                        raise ExtractorError(f"tar member exceeds size limit: {member.name}")
                    total += member.size
                    if total > MAX_TOTAL_UNCOMPRESSED_BYTES:
                        raise ExtractorError("tar total uncompressed-size limit exceeded")
                    handle = tf.extractfile(member)
                    data = handle.read() if handle is not None else b""
                    units.append(_archive_member_unit(str(entry["path"]), member.name, member.size, data))
                else:
                    units.append(RawUnit(str(entry["path"]), "archive-entry", native_locator={"member": member.name},
                                         metadata={"tar_type": member.type.decode("latin1") if isinstance(member.type, bytes) else str(member.type)}))
    elif fmt in {"gzip", "bzip2", "xz"}:
        opener = {"gzip": gzip.open, "bzip2": bz2.open, "xz": lzma.open}[fmt]
        with opener(path, "rb") as handle:
            data = handle.read(MAX_MEMBER_BYTES + 1)
        if len(data) > MAX_MEMBER_BYTES:
            raise ExtractorError(f"{fmt} decompressed stream exceeds size limit")
        units.append(_archive_member_unit(str(entry["path"]), path.stem, len(data), data))
    else:
        return ExtractorResult((RawUnit(str(entry["path"]), "unsupported", native_locator={"path": str(entry["path"])},
                                        metadata={"format": fmt, "route": "archive"},
                                        diagnostics=(f"archive-format-not-supported:{fmt}",)),),
                               (f"archive-format-not-supported:{fmt}",))
    return ExtractorResult(tuple(units))


