# OKF version-adapter contract

Every canonical OKF version transition is implemented as an adjacent-version adapter. The adapter changes representation; it does not invent knowledge.

## Required metadata

Each adapter declares:

- `id`
- `from_version`
- `to_version`
- immutable upstream specification commit(s)
- preconditions and postconditions
- structural changes
- deprecated, superseded, or removed constructs
- compatibility fallbacks
- known lossiness conditions
- applicable validators
- golden fixtures

## Required behavior

A canonical migration MUST be deterministic and idempotent for the same input state and configuration. It MUST preserve unknown extension data, concept identity, source evidence, and internal workflow metadata unless the target specification explicitly forbids doing so.

An adapter MUST NOT fabricate semantics. In particular, migration and enrichment are separate operations. If a target version introduces a field whose value is not implied by the source version or workflow evidence, the migration leaves it absent and emits an enrichment opportunity or diagnostic.

Examples for OKF 0.1 -> 0.2:

- legacy `timestamp` may migrate to `generated.at`;
- `generated.by` is populated only when actual workflow provenance identifies the actor;
- legacy body citations may be converted into `sources` only to the extent that the original citation data supports the mapping;
- `verified`, `status`, `stale_after`, and Attested Computation contracts are not inferred merely because v0.2 supports them.

## Knowledge-state envelope

Canonical adapters operate on a persistent knowledge-state envelope rather than treating an older serialized OKF bundle as the complete information universe. This prevents an older OKF version from becoming an information-loss bottleneck.

The envelope may carry information that is not serializable in an intermediate OKF version, including:

- stable internal concept identities and path history;
- source evidence and immutable source identifiers;
- workflow provenance;
- event history;
- extension data;
- diagnostics and unresolved enrichment candidates.

The serialized bundle for a particular OKF version is therefore a projection of the canonical state at that version boundary.

## Invariants

For canonical migration `M` and valid input state `X`:

1. `M(M(X))` MUST be equivalent to `M(X)` when the second application recognizes the target state.
2. No semantic fact may appear solely because the adapter guessed it.
3. Unknown extension data MUST survive unless explicitly prohibited by the target specification.
4. Concept identity and paths MUST NOT change unless the migration specification requires a path change.
5. A failed migration MUST NOT partially replace canonical input state.
6. Every untranslatable or ambiguous construct MUST produce a machine-readable diagnostic.
7. The serialized target projection MUST be checked with target-version conformance tooling when such tooling is available.

## Migration versus enrichment

`MIGRATE` is structural and deterministic. `ENRICH` is a later pipeline stage and may use deterministic inspection, an LLM, human review, or a combination of them.

An enrichment operation MUST record its evidence and actor. It MUST NOT masquerade as an automatic consequence of a version migration.

## Compatibility projections

A compatibility projection allows a newer canonical state to be exposed temporarily to an older consumer. It is not a reverse canonical migration.

A compatibility projection:

- MAY be lossy;
- MUST report known lossiness;
- MUST be read-only with respect to canonical state;
- MUST NOT become the source of truth after a legacy tool consumes it.

This permits useful older-version tools to remain part of the ecosystem without weakening the forward version chain.

## Test requirements

Each adapter will eventually include fixtures for at least:

- minimal valid input;
- representative full input;
- legacy constructs;
- unknown extensions;
- ambiguous migration;
- malformed input;
- idempotence;
- round-trip preservation where applicable;
- target-version conformance.
