# OKF-Generator

OKF-Generator is a versioned, stage-driven workflow for turning heterogeneous source material into an Open Knowledge Format (OKF) knowledge bundle.

The pipeline topology is fixed up front and implemented sequentially. External tools are evaluated when a stage needs them rather than selected globally in advance.

## Current implementation

- **Stage 00 — Initialize:** complete. The workflow topology, OKF version pins, and adapter contract are defined.
- **Stage 01 — Acquire:** complete. Sources can be acquired from local paths, single HTTP(S) resources, and Git repositories without semantic transformation.
- **Stage 02 — Snapshot:** complete. Acquisitions are fingerprinted, Git refs are locked to immutable objects/commits, and source versions are preserved in append-only content-addressed storage.
- **Stage 03+**: planned and intentionally not implemented yet.

See [`workflow/stages.yaml`](workflow/stages.yaml) for the complete stage graph, [`docs/stage-01-acquire.md`](docs/stage-01-acquire.md) for acquisition, and [`docs/stage-02-snapshot.md`](docs/stage-02-snapshot.md) for snapshotting.

## Development

Requires Python 3.11+; Git is additionally required for Git acquisition and Git snapshot locking.

```bash
python -m pip install -e .
# In an offline environment with setuptools already installed:
# python -m pip install -e . --no-build-isolation
python -m unittest discover -s tests -v
```

Example:

```bash
okf-generator acquire paper ./paper.pdf
okf-generator snapshot paper
```
