# Stage 04 — Extract

Stage 04 converts a verified Stage 02 snapshot, routed by its immutable Stage 03 classification, into a structured source representation. It extracts source-native units and locators while deliberately avoiding the canonicalization, anchor normalization, deduplication, or semantic synthesis owned by later stages.

## Boundary

Stage 04 is evidence-preserving and may be tool-backed.

- **Allowed:** decode classified text, parse document containers, extract embedded PDF text, enumerate archive members, read the locked Git tree, retain page/slide/sheet/cell/paragraph/member/blob locators, and emit explicit diagnostics for unsupported or lossy cases.
- **Forbidden:** whitespace normalization, canonical source IDs or anchors, semantic chunking, OCR/vision interpretation, entity/concept extraction, summarization, contradiction resolution, or OKF serialization.

Stage 04 consumes only an already-published Stage 03 classification. Before and after extraction it re-verifies that classification, which in turn verifies the immutable Stage 02 snapshot.

## Output contract

For classification ruleset `builtin-v1` and extraction profile `builtin-v1`:

```text
.okf-generator/extractions/<source-id>/<snapshot-id>/builtin-v1/builtin-v1/
  extraction.json
  units.jsonl
```

`extraction.json` binds the result to the exact SHA-256 of both `snapshot.json` and `classification.json`, records the units-file hash, unit/diagnostic counts, route counts, and the exact external parser versions actually used.

`units.jsonl` contains one canonical JSON object per source-native unit. Each unit has:

- deterministic `unit_id` within the extraction;
- `source_path` from Stage 03 or the locked Git tree;
- `kind` such as `page`, `paragraph`, `table-row`, `worksheet-row`, `archive-member`, or `git-blob`;
- extracted `text` when available, without Stage 05 whitespace normalization;
- structured `data` that preserves useful native values such as spreadsheet cells/formulas;
- `native_locator` such as page, slide, sheet/row, package member, or Git commit/path;
- source-format metadata and diagnostics.

The output is immutable for a fixed snapshot/ruleset/profile. If an existing extraction differs, the command fails instead of overwriting it.

## `builtin-v1` extractors

### Text routes

`text`, `markdown`, `markup`, `structured-text`, and `text-source` preserve the decoded source text as one unit. UTF-8, UTF-8 BOM, and UTF-16 BOM inputs are supported without replacement-character guessing. Stage 05 decides canonical text formatting and finer anchors.

### PDF

PDF uses `pypdf` for embedded text, one unit per page. Empty extracted pages receive `pdf-page-has-no-embedded-text`; Stage 04 does not OCR them. Password-protected PDFs that cannot be opened with an empty password fail explicitly rather than prompting or inventing credentials.

### Open document containers

The initial office/container parsers are intentionally structural and local:

- DOCX: body paragraphs and table rows;
- PPTX: slide paragraphs in presentation relationship order;
- XLSX: worksheet rows in workbook relationship order, retaining cell coordinates, raw values, types, and formulas;
- ODT/ODS/ODP: paragraphs/headings and table rows from `content.xml`;
- EPUB: text from spine items in package order.

XML is parsed with `defusedxml`. ZIP/container parsing has member, individual-size, and total-uncompressed-size limits.

### Archives

ZIP and TAR enumerate members; GZIP, BZIP2, and XZ expose their single decompressed stream. UTF-compatible member bytes may be represented as text; binary members retain size/hash metadata and an explicit diagnostic. RAR and 7z are currently represented as unsupported rather than invoking an unpinned external binary.

### Git

Git extraction operates on the Stage 02 locked commit, never on a mutable branch name. `git ls-tree` enumerates the complete committed tree; text blobs are preserved as text and binary blobs as metadata/hash units. Blob-count, per-blob, total-byte, and subprocess-time limits are enforced. Gitlinks remain reference units.

### Explicitly unsupported in this profile

Image OCR, audio/video transcription, SQLite/Parquet semantic extraction, legacy binary Office (`.doc`, `.xls`, `.ppt`), and RTF parsing are not silently approximated. They produce `no-stage-04-extractor:*` diagnostics. Future extractors extend Stage 04 without changing workflow topology.

## Tool decision

The stage-local tool audit selected only two new dependencies:

- `pypdf==6.16.1` for embedded PDF text. Its parser version is recorded in each extraction that uses it.
- `defusedxml==0.7.1` for hardened XML parsing of package formats.

The existing Git CLI is reused for locked-tree reads and its runtime version is recorded. Heavy document-ETL/OCR frameworks are deferred until a concrete unsupported route needs them. Tools that directly compile raw documents into OKF are also deferred because that would span extraction, normalization, synthesis, and serialization in one opaque step.

## Safety limits

`builtin-v1` fails rather than silently truncating when configured hard limits are exceeded. The initial fixed limits include 256 MiB for a text source, 512 MiB/10,000 pages/256 MiB extracted text for PDF, 20,000 archive members, 64 MiB per archive member or Git blob, 512 MiB total archive/Git bytes, and 100,000 Git tree entries.

## CLI

```bash
okf-generator extract paper sha256-<snapshot-digest>
```

The command expects the matching Stage 03 classification to exist. It prints `extraction.json` to stdout.

## Completion tests

Stage 04 is complete when:

- extraction can consume only a valid immutable Stage 02 + Stage 03 pair;
- output is bound to the exact snapshot and classification hashes;
- text is preserved without Stage 05 normalization;
- PDF page locators and no-embedded-text diagnostics are preserved;
- DOCX/PPTX/XLSX and ODF/EPUB native ordering/locators are represented;
- common archives are bounded and member identity is retained;
- locked Git commits are enumerated without re-resolving mutable refs;
- every classified entry is either represented or explicitly diagnosed as unsupported;
- symlinks are never dereferenced;
- input mutation during extraction is detected;
- an existing extraction is never overwritten;
- Stage 04 introduces no normalization, synthesis, or OKF serialization.
