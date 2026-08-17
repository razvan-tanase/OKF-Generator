from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import types
import unittest
import zipfile
from pathlib import Path

from okf_generator.extract import ExtractionEngine, ExtractionError
from okf_generator.extractors import extract_pdf
from extract_test_support import ExtractionCase


class ExtractionFormatTests(ExtractionCase):
    def test_text_preserves_text_and_native_path(self):
        entry = self._entry(".", "markdown", "markdown", "text/markdown", detection={"encoding_hint": "utf-8"})
        artifact, classification = self._setup("doc.md", "file", [entry])
        artifact.write_bytes(b"# Title\n\nA  B\n")
        manifest = self._engine(classification).extract(self.source_id, self.snapshot_id)
        units = self._read_units()
        self.assertEqual(manifest.unit_count, 1)
        self.assertEqual(units[0]["text"], "# Title\n\nA  B\n")
        self.assertEqual(units[0]["native_locator"], {"path": "."})

    def test_utf16_bom_is_consumed(self):
        entry = self._entry(".", "text", "text", detection={"encoding_hint": "utf-16-le"})
        artifact, classification = self._setup("doc.txt", "file", [entry])
        artifact.write_bytes("Hello".encode("utf-16"))
        self._engine(classification).extract(self.source_id, self.snapshot_id)
        self.assertEqual(self._read_units()[0]["text"], "Hello")

    def test_directory_symlink_and_unsupported_are_explicit(self):
        entries = [
            self._entry(".", "directory", "directory", "inode/directory", kind="directory"),
            self._entry("a.txt", "text", "text", detection={"encoding_hint": "utf-8"}),
            {"path":"link","entry_kind":"symlink","format":"symlink","route":"symlink","media_type":"inode/symlink","family":"reference","detection":{"target":"a.txt"}},
            {"path":"img.png","entry_kind":"file","format":"png","route":"image","media_type":"image/png","family":"image","detection":{}},
        ]
        artifact, classification = self._setup("docs", "directory", entries)
        (artifact / "a.txt").write_text("hello", encoding="utf-8")
        if os.name != "nt":
            (artifact / "link").symlink_to("a.txt")
        else:
            self.skipTest("symlink test")
        (artifact / "img.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        self._engine(classification).extract(self.source_id, self.snapshot_id)
        units = self._read_units()
        self.assertEqual([u["kind"] for u in units], ["directory", "text-document", "symlink", "unsupported"])
        self.assertIn("no-stage-04-extractor:image:png", units[-1]["diagnostics"])

    def test_docx_extracts_paragraph_and_table_row(self):
        entry = self._entry(".", "docx", "office", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        artifact, classification = self._setup("a.docx", "file", [entry])
        xml = b'''<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Hello</w:t></w:r></w:p><w:tbl><w:tr><w:tc><w:p><w:r><w:t>A</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>B</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>'''
        with zipfile.ZipFile(artifact, "w") as zf:
            zf.writestr("word/document.xml", xml)
        self._engine(classification).extract(self.source_id, self.snapshot_id)
        units = self._read_units()
        self.assertEqual([u["kind"] for u in units], ["paragraph", "table-row"])
        self.assertEqual(units[1]["data"]["cells"], ["A", "B"])

    def test_pptx_extracts_slide_paragraphs(self):
        entry = self._entry(".", "pptx", "office", "application/vnd.openxmlformats-officedocument.presentationml.presentation")
        artifact, classification = self._setup("a.pptx", "file", [entry])
        xml = b'''<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><p:cSld><p:spTree><p:sp><p:txBody><a:p><a:r><a:t>Slide text</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld></p:sld>'''
        pres = b'<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><p:sldIdLst><p:sldId id="256" r:id="rId2"/></p:sldIdLst></p:presentation>'
        rels = b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId2" Target="slides/slide1.xml" Type="slide"/></Relationships>'
        with zipfile.ZipFile(artifact, "w") as zf:
            zf.writestr("ppt/presentation.xml", pres)
            zf.writestr("ppt/_rels/presentation.xml.rels", rels)
            zf.writestr("ppt/slides/slide1.xml", xml)
        self._engine(classification).extract(self.source_id, self.snapshot_id)
        unit = self._read_units()[0]
        self.assertEqual(unit["text"], "Slide text")
        self.assertEqual(unit["native_locator"]["slide"], 1)

    def test_xlsx_extracts_rows_and_formulas(self):
        entry = self._entry(".", "xlsx", "office", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        artifact, classification = self._setup("a.xlsx", "file", [entry])
        sheet = b'''<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1"><f>1+1</f><v>2</v></c></row></sheetData></worksheet>'''
        shared = b'''<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><si><t>Name</t></si></sst>'''
        workbook = b'<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Data" sheetId="1" r:id="rId1"/></sheets></workbook>'
        rels = b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml" Type="worksheet"/></Relationships>'
        with zipfile.ZipFile(artifact, "w") as zf:
            zf.writestr("xl/workbook.xml", workbook)
            zf.writestr("xl/_rels/workbook.xml.rels", rels)
            zf.writestr("xl/worksheets/sheet1.xml", sheet)
            zf.writestr("xl/sharedStrings.xml", shared)
        self._engine(classification).extract(self.source_id, self.snapshot_id)
        unit = self._read_units()[0]
        self.assertEqual(unit["text"], "Name\t2")
        self.assertEqual(unit["data"]["cells"][1]["formula"], "1+1")
        self.assertEqual(unit["native_locator"]["sheet_name"], "Data")

    def test_odt_extracts_content_xml(self):
        entry = self._entry(".", "odt", "office", "application/vnd.oasis.opendocument.text")
        artifact, classification = self._setup("a.odt", "file", [entry])
        xml = b'''<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"><office:body><office:text><text:p>Hello ODT</text:p></office:text></office:body></office:document-content>'''
        with zipfile.ZipFile(artifact, "w") as zf:
            zf.writestr("content.xml", xml)
        self._engine(classification).extract(self.source_id, self.snapshot_id)
        self.assertEqual(self._read_units()[0]["text"], "Hello ODT")

    def test_epub_uses_spine_order(self):
        entry = self._entry(".", "epub", "archive-document", "application/epub+zip")
        artifact, classification = self._setup("a.epub", "file", [entry])
        container = b'''<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OEBPS/content.opf"/></rootfiles></container>'''
        opf = b'''<package xmlns="http://www.idpf.org/2007/opf"><manifest><item id="c1" href="one.xhtml"/></manifest><spine><itemref idref="c1"/></spine></package>'''
        with zipfile.ZipFile(artifact, "w") as zf:
            zf.writestr("META-INF/container.xml", container)
            zf.writestr("OEBPS/content.opf", opf)
            zf.writestr("OEBPS/one.xhtml", b"<html><body><p>Hello EPUB</p></body></html>")
        self._engine(classification).extract(self.source_id, self.snapshot_id)
        self.assertIn("Hello EPUB", self._read_units()[0]["text"])



if __name__ == "__main__":
    unittest.main()
