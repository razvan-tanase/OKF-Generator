# Stage 01 — Acquire

Stage 01 obtains source material without interpreting, summarizing, normalizing, fingerprinting, or converting it to OKF. Its output is an ephemeral acquisition workspace consumed by Stage 02.

## Boundary

Stage 01 is intentionally narrow:

- **Allowed:** read/copy/fetch source bytes, clone git object data, preserve source names and symlinks, record retrieval observations, validate that a requested git ref exists.
- **Forbidden:** hashing as the canonical source identity, immutable snapshot creation, media classification, text extraction, crawling implicit related pages, concept generation, provenance inference, or OKF serialization.

The implementation follows the useful separation visible in OpenWiki's connector architecture: credentialed/deterministic fetch happens before model-driven synthesis. OKFy is not used here because its current crawl/import commands already convert sources into OKF concepts and therefore span later pipeline stages.

## Workspace contract

Each acquisition is published atomically at:

```text
.okf-generator/acquired/<source-id>/
  receipt.json
  payload/
    ... acquired material ...
```

A failed provider run leaves no published `<source-id>` directory. Replacing an existing acquisition requires an explicit `--replace` operation.

`receipt.json` records how the source was acquired and where the payload is located. It deliberately does **not** contain a source hash. Stage 02 owns immutable fingerprinting and source-version locking.

## Initial providers

### `local`

Copies one explicit local file or directory without changing file contents. Directory symlinks are preserved as symlinks instead of being dereferenced. Acquiring a directory into an output root nested inside that same directory is rejected to prevent recursive self-ingestion.

### `http`

Fetches exactly one explicit HTTP(S) resource. The response body is written byte-for-byte. A bounded response-size limit defaults to 100 MiB. The receipt records a small non-secret observation set such as final URL, status, content type, ETag, and Last-Modified when available.

This provider is not a website crawler. Discovering and acquiring a site corpus can later be implemented as another Stage 01 provider if the project needs it.

### `git`

Clones a repository as a **bare repository**. Stage 01 intentionally does not checkout a working tree, recursively fetch submodules, or select an immutable commit. This preserves Git object data without line-ending or checkout transformations. An optional requested ref may be required to exist, but Stage 02 resolves and locks the immutable commit identity.

The dangerous `ext::` Git transport is disabled and terminal credential prompting is disabled for non-interactive execution.

## CLI

```bash
python -m okf_generator.cli acquire paper ./paper.pdf
python -m okf_generator.cli acquire spec https://example.org/spec.pdf
python -m okf_generator.cli acquire code https://github.com/example/project.git --provider git --ref main
```

By default the workspace is `.okf-generator/acquired`. Use `--replace` only when a prior acquisition has already been snapshotted or is intentionally disposable.

## Extension rule

New source systems do not require a new pipeline stage. They add a Stage 01 provider when they can satisfy the common contract:

1. read-only source access;
2. no semantic transformation;
3. common acquisition receipt;
4. no partially published output after failure.

This allows later source types—MCP-backed knowledge, SaaS APIs, database exports, conversation archives, object stores—to be added only when they become relevant.

## Completion tests

Stage 01 is complete when:

- local file and directory bytes are preserved;
- symlinks are preserved instead of silently followed;
- HTTP response bytes are preserved and bounded;
- Git repositories are acquired without checkout transformations;
- existing acquisitions are not overwritten implicitly;
- provider failure does not publish partial output;
- receipts contain acquisition observations but no Stage 02 fingerprint;
- the provider interface can be extended without changing the workflow topology.
