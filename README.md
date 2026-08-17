# OKF-Generator

OKF-Generator is a versioned, stage-driven workflow for turning heterogeneous source material into an Open Knowledge Format (OKF) knowledge bundle.

The pipeline topology is fixed up front and implemented sequentially. External tools are evaluated when a stage needs them rather than selected globally in advance.

## Current implementation

- **Stage 00 — Initialize:** complete. The workflow topology, OKF version pins, and adapter contract are defined.
- **Stage 01 — Acquire:** complete. Sources can be acquired from local paths, single HTTP(S) resources, and Git repositories without semantic transformation.
- **Stage 02 — Snapshot:** complete. Acquisitions are fingerprinted, Git refs are locked to immutable objects/commits, and source versions are preserved in append-only content-addressed storage.
- **Stage 03 — Classify:** complete. Verified snapshots are deterministically classified with a versioned routing ruleset, bounded signature/container inspection, conflict diagnostics, and no semantic extraction.
- **Stage 04 — Extract:** complete. Classified immutable snapshots are converted into evidence-oriented source units with native locators, bounded document/archive/Git extraction, explicit unsupported-route diagnostics, and no normalization or synthesis.
- **Stage 05 — Normalize:** complete. Verified extraction units are deterministically canonicalized to NFC/LF text, stable logical/version source URIs, collision-checked native-locator anchors, and immutable canonical JSONL without semantic rewriting.
- **Stage 06 — Synthesize:** complete. Verified normalized evidence is deterministically batched and sent through a strict structured-output provider contract to produce immutable, evidence-addressed candidate summaries, concepts, claims, and relations; model variability is preserved as separate content-addressed runs.
- **Stage 07 — Resolve:** complete. Stage 06 concept candidates are matched conservatively against a read-only identity catalog using exact identity evidence, deterministic similarity shortlists, and optional constrained adjudication; resolution never mutates canonical state.
- **Stage 08 — Plan:** complete. Verified resolution runs are converted into immutable declarative change plans with deterministic provisional identities and paths, explicit auditable semantic decision ledgers, and no canonical-state mutation.
- **Stage 09+**: planned and intentionally not implemented yet.

See [`workflow/stages.yaml`](workflow/stages.yaml) for the complete stage graph, [`docs/stage-01-acquire.md`](docs/stage-01-acquire.md) for acquisition, [`docs/stage-02-snapshot.md`](docs/stage-02-snapshot.md) for snapshotting, [`docs/stage-03-classify.md`](docs/stage-03-classify.md) for classification, [`docs/stage-04-extract.md`](docs/stage-04-extract.md) for extraction, [`docs/stage-05-normalize.md`](docs/stage-05-normalize.md) for normalization, [`docs/stage-06-synthesize.md`](docs/stage-06-synthesize.md) for synthesis, [`docs/stage-07-resolve.md`](docs/stage-07-resolve.md) for identity resolution, and [`docs/stage-08-plan.md`](docs/stage-08-plan.md) for change planning.

## Development

Requires Python 3.11+; Git is additionally required for Git acquisition, Git snapshot locking, and Git source extraction. Stage 04 pins its Python extraction dependencies in `pyproject.toml`; Stages 05–08 add no runtime Python dependency. The Stage 06 OpenAI adapter calls the Responses API over the standard library HTTPS client and reads `OPENAI_API_KEY` from the environment; Stage 07 optionally reuses that adapter only for unresolved identity adjudication. Stage 08 makes no model call in `builtin-v1`.

```bash
python -m pip install -e .
# In an offline environment with all pinned dependencies already installed:
# python -m pip install -e . --no-build-isolation
python -m unittest discover -s tests -v
```

Example:

```bash
okf-generator acquire paper ./paper.pdf
okf-generator snapshot paper
okf-generator classify paper sha256-<snapshot-digest>
okf-generator extract paper sha256-<snapshot-digest>
okf-generator normalize paper sha256-<snapshot-digest>
OPENAI_API_KEY=... okf-generator synthesize paper sha256-<snapshot-digest> --model <explicit-model-id>
okf-generator resolve paper sha256-<snapshot-digest> sha256-<synthesis-run> --synthesis-provider openai
okf-generator plan paper sha256-<snapshot-digest> sha256-<synthesis-run> sha256-<resolution-run> --synthesis-provider openai
```
