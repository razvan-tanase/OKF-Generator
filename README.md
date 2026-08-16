# OKF-Generator

OKF-Generator is a versioned, stage-driven workflow for turning heterogeneous source material into an Open Knowledge Format (OKF) knowledge bundle.

The pipeline topology is fixed up front and implemented sequentially. External tools are evaluated when a stage needs them rather than selected globally in advance.

## Current implementation

- **Stage 00 — Initialize:** complete. The workflow topology, OKF version pins, and adapter contract are defined.
- **Stage 01 — Acquire:** complete. Sources can be acquired from local paths, single HTTP(S) resources, and Git repositories without semantic transformation.
- **Stage 02+**: planned and intentionally not implemented yet.

See [`workflow/stages.yaml`](workflow/stages.yaml) for the complete stage graph and [`docs/stage-01-acquire.md`](docs/stage-01-acquire.md) for the Stage 01 contract.

## Development

Requires Python 3.11+; Git is additionally required for the Git acquisition provider.

```bash
python -m pip install -e .
# In an offline environment with setuptools already installed:
# python -m pip install -e . --no-build-isolation
python -m unittest discover -s tests -v
```

Example acquisition:

```bash
okf-generator acquire paper ./paper.pdf
```
