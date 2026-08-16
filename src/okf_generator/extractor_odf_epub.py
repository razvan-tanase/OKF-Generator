from __future__ import annotations

import posixpath
import urllib.parse
import zipfile
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from .extractor_core import ExtractorError, ExtractorResult, RawUnit, _package_version, _xml_from_bytes, _zip_guard

def extract_odf(path: Path, entry: Mapping[str, Any]) -> ExtractorResult:
    fmt = str(entry.get("format"))
    units: list[RawUnit] = []
    with zipfile.ZipFile(path) as zf:
        _zip_guard(zf)
        try:
            root = _xml_from_bytes(zf.read("content.xml"))
        except KeyError as exc:
            raise ExtractorError(f"{fmt.upper()} is missing content.xml") from exc
    index = 0
    for node in root.iter():
        if node.tag.endswith("}h") or node.tag.endswith("}p"):
            text = "".join(node.itertext())
            index += 1
            units.append(RawUnit(str(entry["path"]), "paragraph", text,
                                 native_locator={"element": index}, metadata={"format": fmt}))
        elif node.tag.endswith("}table-row"):
            cells = ["".join(c.itertext()) for c in node if c.tag.endswith("}table-cell")]
            index += 1
            units.append(RawUnit(str(entry["path"]), "table-row", "\t".join(cells), data={"cells": cells},
                                 native_locator={"element": index}, metadata={"format": fmt}))
    return ExtractorResult(tuple(units), tools={"defusedxml": _package_version("defusedxml")})


class _TextHTMLParser(HTMLParser):
    BLOCKS = {"p", "div", "section", "article", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "br"}
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
    def handle_data(self, data: str) -> None:
        self.parts.append(data)
    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in self.BLOCKS:
            self.parts.append("\n")
    def handle_endtag(self, tag: str) -> None:
        if tag in self.BLOCKS:
            self.parts.append("\n")
    def text(self) -> str:
        return "".join(self.parts)


def _html_to_text(data: bytes) -> str:
    parser = _TextHTMLParser()
    parser.feed(data.decode("utf-8", errors="replace"))
    parser.close()
    return parser.text()


def extract_epub(path: Path, entry: Mapping[str, Any]) -> ExtractorResult:
    units: list[RawUnit] = []
    diagnostics: list[str] = []
    with zipfile.ZipFile(path) as zf:
        _zip_guard(zf)
        try:
            container = _xml_from_bytes(zf.read("META-INF/container.xml"))
            rootfile = next(n.attrib.get("full-path") for n in container.iter() if n.tag.endswith("}rootfile"))
            opf = _xml_from_bytes(zf.read(rootfile))
        except (KeyError, StopIteration) as exc:
            raise ExtractorError("EPUB package metadata is incomplete") from exc
        parent = PurePosixPath(rootfile).parent
        base = "" if str(parent) == "." else parent.as_posix()
        manifest: dict[str, str] = {}
        for item in (n for n in opf.iter() if n.tag.endswith("}item")):
            if item.attrib.get("id") and item.attrib.get("href"):
                manifest[item.attrib["id"]] = item.attrib["href"]
        spine = [n.attrib.get("idref") for n in opf.iter() if n.tag.endswith("}itemref")]
        for index, item_id in enumerate(spine, start=1):
            href = manifest.get(str(item_id))
            if not href:
                diagnostics.append(f"epub-spine-missing-manifest-item:{item_id}")
                continue
            member = posixpath.normpath(posixpath.join(base, urllib.parse.unquote(href)))
            if member == ".." or member.startswith("../") or member.startswith("/"):
                raise ExtractorError(f"unsafe EPUB spine target: {href}")
            try:
                data = zf.read(member)
            except KeyError:
                diagnostics.append(f"epub-spine-member-missing:{member}")
                continue
            units.append(RawUnit(str(entry["path"]), "epub-spine-item", _html_to_text(data),
                                 native_locator={"spine": index, "member": member}, metadata={"format": "epub"}))
    return ExtractorResult(tuple(units), tuple(diagnostics), {"defusedxml": _package_version("defusedxml")})
