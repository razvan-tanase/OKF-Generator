# Stage 03 — Classify

Stage 03 deterministically classifies the immutable source material produced by Stage 02 so later extraction can be routed without guessing. It does not parse document semantics or produce extracted text.

## Boundary

Stage 03 accepts only a verified Stage 02 snapshot identified by both `source_id` and immutable `snapshot_id`. The Stage 02 verifier runs before classification and again after the scan; if the snapshot or its manifest changes during classification, the operation fails without publishing output.

Allowed operations are limited to filesystem entry inspection, bounded prefix reads, file-signature checks, filename-extension checks, and bounded container metadata inspection needed to identify a format. Stage 03 may inspect ZIP member names and a tiny standardized `mimetype` marker, but it does not extract archive members, parse office XML, read Git source blobs, summarize content, or infer concepts.

## Versioned classification rules

The initial ruleset is `builtin-v1`. Ruleset identity is part of the output path and manifest:

```text
.okf-generator/classifications/<source-id>/<snapshot-id>/builtin-v1/
  classification.json
```

For a fixed snapshot and ruleset, output is byte-deterministic. Existing output is never overwritten. If classification behavior changes intentionally, the ruleset ID must change; changing the implementation while retaining the same ruleset and producing different output is an error.

The classification manifest contains no clock time. It binds itself to the exact Stage 02 `snapshot.json` with SHA-256 and records source-level routing plus a complete deterministic entry inventory for ordinary directory snapshots.

## Precedence

Classification evidence is applied in this order:

1. Stage 02 artifact kind (`bare-git-repository`, directory, file, symlink).
2. Strong binary signatures and bounded container structure probes.
3. Extension plus compatible signature family, where a legacy/container format needs both signals.
4. Extension plus a bounded text/encoding probe for textual formats.
5. Generic text or binary fallback.

A stronger signal overrides a conflicting extension and records a diagnostic. For example, a file named `paper.zip` beginning with a PDF signature is classified as PDF with an `extension-conflict` diagnostic. A binary file named `notes.md` is not routed as Markdown.

## Initial routing families

`builtin-v1` covers the formats needed for the early general-purpose pipeline without depending on a host MIME database:

- plain text, Markdown/MDX, reStructuredText, LaTeX, HTML/XML/SVG;
- JSON/JSONL, YAML, TOML, CSV/TSV, Jupyter notebooks;
- common source-code extensions;
- PDF and RTF;
- OOXML Word/Excel/PowerPoint containers;
- ODF text/spreadsheet/presentation and EPUB containers;
- legacy OLE Word/Excel/PowerPoint when both OLE signature and extension agree;
- ZIP/TAR/GZIP/BZIP2/XZ/7z/RAR;
- common PNG/JPEG/GIF/WebP/TIFF image signatures;
- WAV/MP3/Ogg/MP4 media signatures;
- SQLite and Parquet binary data signatures;
- generic text and binary fallback.

This registry is deliberately finite. A future source requirement may add formats through a new ruleset without changing pipeline topology.

## Bounded inspection

Ordinary files are inspected using at most the first 64 KiB for signature/text classification. ZIP container probing reads central-directory metadata but never extracts members. Deep ZIP probing is skipped for containers larger than 256 MiB or with more than 20,000 members; the classification records a diagnostic and falls back to the safe signature/extension result.

Symlinks are classified as symlinks and never followed.

## Git snapshots

A Stage 02 bare Git snapshot is classified once at repository level as `git`. Stage 03 records the locked Git object format and selected object type as routing evidence but does not inspect Git blobs or enumerate the committed source tree. Repository materialization and file extraction belong to Stage 04.

## Tool decision

No new third-party tool is selected for Stage 03. A pinned in-project signature/extension registry plus Python's standard library is preferable at this stage because it is deterministic and sufficient for routing. Host `mimetypes` databases are not used for authoritative classification, and system `libmagic`/`file` is deferred because its external magic database would need its own version pin and compatibility contract before it could become a canonical classifier.

## CLI

```bash
okf-generator classify paper sha256-<64-hex-digest>
```

Optional paths:

```bash
okf-generator classify paper sha256-<digest> \
  --snapshots-root .okf-generator/snapshots \
  --out .okf-generator/classifications \
  --ruleset builtin-v1
```

## Completion tests

Stage 03 is complete when:

- only verified Stage 02 snapshots are accepted;
- the same snapshot and ruleset reproduce byte-identical output;
- prior output for a ruleset cannot be silently replaced;
- strong signatures override conflicting extensions with diagnostics;
- textual extension routing is rejected for binary payloads;
- OOXML and ODF/EPUB containers are distinguishable without extracting their content;
- directory inventories are deterministic and symlinks are never followed;
- Git snapshots are routed at repository level without source-tree extraction;
- snapshot mutation during classification is detected;
- classification output contains no nondeterministic clock fields;
- Stage 03 introduces no Stage 04 parsing or extraction.
