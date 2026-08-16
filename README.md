# OKF-Generator

OKF-Generator is a staged, version-aware workflow for turning heterogeneous source material into maintainable Open Knowledge Format (OKF) knowledge bundles.

The project treats the workflow structure as deterministic: the ordered stages, contracts, version transitions, validation gates, and artifacts are fixed and auditable. Individual synthesis stages may use LLMs and are not required to be byte-deterministic.

## Development principle

The pipeline is implemented sequentially. A stage is specified, implemented, tested, and considered complete before implementation proceeds to the next stage. External tools are evaluated only when a current stage needs them; the project does not attempt to rank the entire OKF ecosystem up front.

The canonical stage graph is defined in [`workflow/stages.yaml`](workflow/stages.yaml). OKF version pins and supported transitions are defined in [`specs/okf/versions.yaml`](specs/okf/versions.yaml). Every version transition follows [`docs/adapter-contract.md`](docs/adapter-contract.md).

## Current implementation status

- Stage 00 — Initialize: in implementation
- Stage 01 and later: specified in the stage graph but intentionally not implemented yet

The initial supported OKF version chain is:

```text
base LLM-Wiki model -> OKF 0.1 -> OKF 0.2
```

Future OKF versions extend this chain through explicit adjacent-version adapters rather than replacing earlier versions.
