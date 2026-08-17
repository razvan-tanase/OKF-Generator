# Stage 05 — Normalize

Stage 05 converts immutable Stage 04 extraction evidence into a deterministic canonical source representation. It standardizes only representation-level differences needed by later stages: Unicode composition, line endings, JSON metadata form, source identifiers, and source anchors.

## Boundary

Stage 05 is deterministic and non-semantic.

Allowed operations:

- verify the exact Stage 04 extraction manifest and `units.jsonl`;
- normalize textual content to Unicode NFC and LF line endings;
- canonicalize JSON-compatible data, locators, metadata, and diagnostics to NFC;
- create workflow-local source and source-version URIs;
- derive stable content hashes and native-locator anchors;
- validate collision and schema invariants;
- publish immutable canonical JSONL.

Forbidden operations include trimming or collapsing whitespace, semantic chunking, stemming, translation, entity extraction, summarization, claim generation, inferred metadata, concept resolution, or OKF serialization. Those belong to later stages.

Stage 04 remains the raw extraction evidence. Stage 05 is a deterministic projection over it, not a replacement.

## Input

The input is one existing Stage 04 output for a fixed source, snapshot, classification ruleset, and extraction profile:

```text
.okf-generator/extractions/<source-id>/<snapshot-id>/<ruleset>/<extraction-profile>/
  extraction.json
  units.jsonl
```

Before normalization, Stage 05 re-verifies Stage 04 through the Stage 04 engine, verifies the exact `units.jsonl` SHA-256 and unit count, and checks the Stage 04 unit schema. The extraction is verified again after normalization; mutation during a run aborts publication.

## Output

The initial normalization profile is `builtin-v1`:

```text
.okf-generator/normalized/<source-id>/<snapshot-id>/<ruleset>/<extraction-profile>/builtin-v1/
  normalization.json
  units.jsonl
```

Existing output is never overwritten. Repeating the same normalization is an idempotent no-op after byte comparison. Intentional behavior changes require a new normalization profile.

## Text normalization

`unicode-nfc+lf-v1` applies exactly two transformations to Stage 04 text:

1. CRLF and CR line endings become LF.
2. Unicode is normalized to NFC.

Spaces, tabs, blank lines, leading/trailing whitespace, and terminal newlines are preserved. No text is semantically rewritten. Unpaired Unicode surrogate code points are rejected instead of being propagated into later stages.

## Structured metadata

`data`, `native_locator`, and `metadata` remain JSON structures. Stage 05:

- normalizes every string and object key to NFC;
- preserves list order and scalar values;
- rejects non-finite numbers;
- rejects object-key collisions created by NFC normalization;
- rejects unknown Stage 04 unit fields instead of silently dropping them.

Distinct Stage 04 source paths that collapse to the same NFC path are also rejected.

## Canonical source identity

Stage 05 introduces workflow-local identifiers; they are not claims about an OKF-standard URI scheme.

For source ID `paper`:

```text
source_uri = okf-source:paper
source_version_uri = okf-source:paper@sha256-<snapshot-digest>
```

`source_uri` is stable across snapshots for the same declared source ID. `source_version_uri` identifies the immutable Stage 02 version.

## Stable anchors

Each unit receives an anchor derived from canonical JSON over:

- anchor basis `native-locator-v1`;
- normalized source path;
- unit kind;
- normalized Stage 04 native locator.

The resulting ID is:

```text
a-sha256-<64-hex-digest>
```

and the complete anchor URI is the source-version URI plus that fragment.

The Stage 04 sequence `unit_id` is retained for traceability but does not participate in anchor identity. Therefore extractor ordering changes do not automatically change anchors when the native locator is unchanged. Duplicate anchor descriptors within one source version are rejected because they would make evidence addressing ambiguous.

Each unit also receives `content_sha256`, calculated over its normalized source path, kind, text, data, native locator, metadata, and diagnostics.

## Diagnostics

Per-unit diagnostics and Stage 04 top-level diagnostics are preserved after NFC normalization. Stage 05 validates the Stage 04 diagnostic count rather than silently repairing inconsistencies.

## Tool decision

No third-party normalization library is selected. Python standard-library `unicodedata`, `json`, `hashlib`, and URI escaping provide the required deterministic operations. Transliteration, locale-sensitive case conversion, tokenizers, NLP libraries, and LLMs are outside the Stage 05 boundary because they can introduce semantic or lossy transformations.

## CLI

```bash
okf-generator normalize paper sha256-<64-hex-digest>
```

Optional roots and profiles are explicit:

```bash
okf-generator normalize paper sha256-<digest> \
  --snapshots-root .okf-generator/snapshots \
  --classifications-root .okf-generator/classifications \
  --extractions-root .okf-generator/extractions \
  --out .okf-generator/normalized \
  --ruleset builtin-v1 \
  --extraction-profile builtin-v1 \
  --profile builtin-v1
```

## Completion criteria

Stage 05 is complete when:

- only verified Stage 04 outputs are accepted;
- the extraction manifest hash, units hash, counts, diagnostics, and unit schema are validated;
- text normalization is limited to NFC and line-ending canonicalization;
- whitespace and source evidence are not semantically rewritten;
- structured metadata is canonicalized without list reordering or field loss;
- logical source and immutable source-version URIs are deterministic;
- native-locator anchors are stable and collision-checked;
- output is byte-deterministic and immutable for a fixed upstream extraction/profile;
- mutation during normalization is detected;
- Stage 05 introduces no Stage 06 synthesis behavior.
