# Stage 08 — Plan

Stage 08 converts one exact verified Stage 07 resolution run into an immutable, declarative change plan. It decides what Stage 09 may apply to canonical knowledge state, but **never applies the operations itself**.

## Boundary

Allowed:
- reverify Stage 07 and its bound Stage 06 synthesis;
- consume the Stage 07 read-only concept catalog snapshot;
- consume an optional read-only planning-state projection for existing claims and relations;
- consume an optional explicit decision ledger for high-impact semantic decisions;
- allocate deterministic provisional IDs for objects that would be created if the plan is applied;
- propose collision-safe concept paths;
- emit `create`, `update`, `merge`, `contradict`, `supersede`, and `ignore` operations with dependencies.

Forbidden:
- mutate the Stage 07 catalog or planning-state projection;
- create canonical identities immediately;
- modify canonical wiki files or history;
- silently resolve Stage 07 ambiguity;
- infer contradiction, supersession, or multi-identity merge from lexical similarity;
- structuralize or serialize OKF.

Canonical mutation belongs exclusively to Stage 09.

## Inputs

A planning invocation selects one exact Stage 07 resolution run by source, snapshot, synthesis provider/run ID, and resolution run ID. Stage 08 verifies every Stage 07 artifact hash, rederives the Stage 07 content-addressed run ID, and reverifies the Stage 06 synthesis candidates bound by that resolution.

Stage 08 additionally accepts two optional read-only files.

### Planning state v0.1

If omitted, the planning state is the explicit canonical empty value:

```json
{"schema_version":"0.1","claims":[],"relations":[]}
```

A supplied planning state contains existing claim and relation identities. Existing concept identities are deliberately *not duplicated* here: they come from the exact `catalog.json` snapshot embedded in Stage 07, so planning cannot accidentally use a concept universe different from the one used for resolution.

Claim fields:
- `internal_id`
- `statement`
- `evidence_anchors`
- `status`

Relation fields:
- `internal_id`
- `subject_internal_id`
- `predicate`
- `object_internal_id`
- `evidence_anchors`
- `status`

Relation endpoints must exist in the Stage 07 catalog snapshot.

### Decision ledger v0.1

If omitted, the ledger is the explicit canonical empty value:

```json
{"schema_version":"0.1","decisions":[]}
```

The decision ledger is the auditable input for choices that Stage 08 refuses to infer heuristically. Each row contains:
- `candidate_id`
- `action`: `update`, `merge`, `contradict`, `supersede`, or `ignore`
- `target_internal_ids`
- `survivor_internal_id` or `null`
- non-empty `reason`

The ledger can be authored by a human review workflow or by a separately controlled adjudicator. `builtin-v1` itself makes no model call.

## Planning policy

### Concepts

- Stage 07 `matched` → `update` the resolved existing concept.
- Stage 07 `new` → `create` a concept with a deterministic provisional internal ID and proposed canonical path.
- Stage 07 `ambiguous` → `ignore` by default.
- An explicit decision may convert an ambiguous concept into a `merge` of two or more *considered* catalog identities and must name the survivor.
- Two exact same-run new concept candidates are coalesced deterministically: the first creates the provisional concept; the later candidate emits `merge` into that provisional target.

Stage 08 never picks one identity from an ambiguous Stage 07 result. A single-identity match belongs in Stage 07.

### Summaries

A unique source-local summary produces `create`. Exact same-run duplicates merge into the first provisional summary. A decision ledger may explicitly `ignore` a summary.

### Claims

Without an explicit decision:
- an exact normalized statement matching one existing planning-state claim → `update`;
- multiple existing exact matches → `ignore` as ambiguous state duplication;
- no existing match → `create`;
- exact same-run duplicate new claims → `merge` into the first provisional claim.

`contradict` and `supersede` are **never guessed**. They require a decision ledger row targeting one existing claim. The candidate claim receives its own provisional identity, while the operation records the existing target claim.

A decision ledger may also explicitly update or merge existing claims.

### Relations

Stage 08 translates Stage 06 relation endpoints through the concept plan. A relation whose concept endpoint remains unresolved is `ignore` and cannot be overridden into a write.

Otherwise:
- exact existing subject/predicate/object → `update`;
- no existing match → `create`;
- exact same-run duplicate → `merge`;
- multiple exact existing matches → `ignore` unless a later explicit decision resolves the duplicate state.

Relation operations depend on concept operations when their endpoints are provisional or otherwise affected by the current plan.

## Provisional identity and paths

A provisional ID is deterministic SHA-256 over the object type and the candidate descriptor and uses the namespace:

```text
urn:okf-generator:<object-type>:sha256-<digest>
```

It is only a planned identity until Stage 09 applies the plan.

Concept paths use `unicode-nfc-casefold-alnum-v1`: NFC + casefold, alphanumeric characters retained, other runs collapsed to `-`, under `concepts/<slug>.md`. Existing canonical paths and path history are reserved. Collisions receive a deterministic digest suffix. The Python Unicode database version is recorded in the plan manifest because slug behavior depends on Unicode character properties.

## Operations

`operations.jsonl` rows contain:
- `operation_id`
- `operation`
- `object_type`
- `candidate_ids`
- `target_internal_ids`
- `survivor_internal_id`
- `provisional_internal_id`
- `proposed_canonical_path`
- `payload`
- `evidence_anchors`
- `dependencies`
- `reason`

`ignore` is a first-class operation. It preserves why evidence was deliberately not applied rather than silently dropping it.

## Output

```text
.okf-generator/plans/<source-id>/<snapshot-id>/<ruleset>/<extraction-profile>/<normalization-profile>/<synthesis-profile>/<synthesis-provider>/<synthesis-run-id>/<resolution-profile>/<resolution-run-id>/builtin-v1/sha256-<run>/
  plan.json
  planning-state.json
  decisions.json
  operations.jsonl
```

Both optional inputs are copied into canonical snapshots inside the plan run. The run ID binds the exact Stage 07 resolution, Stage 06 candidates, Stage 07 concept catalog, planning-state projection, decision ledger, Unicode/path policy, and operations hash.

Existing content-addressed plan output is verified and never overwritten. All mutable inputs are re-read after planning; mutation during the run fails publication.

## Tool decision

Stage 08 adds no runtime dependency and no OKF-specific ecosystem tool. Python standard-library JSON, SHA-256, Unicode handling, and filesystem primitives are sufficient for the deterministic control plane.

No model is invoked by `builtin-v1`. High-impact semantic choices enter through the explicit decision ledger so their provenance remains separate from planning mechanics. The first OKF-specific ecosystem-tool evaluation remains Stage 10 — Structuralize.

## CLI

```bash
okf-generator plan paper sha256-<snapshot-digest> \
  sha256-<synthesis-run> sha256-<resolution-run> \
  --synthesis-provider openai
```

With canonical-state projections/review decisions:

```bash
okf-generator plan paper sha256-<snapshot-digest> \
  sha256-<synthesis-run> sha256-<resolution-run> \
  --planning-state .okf-generator/state/planning-state.json \
  --decisions reviewed-decisions.json
```

## Completion tests

Stage 08 is complete when:
- Stage 07 and its bound Stage 06 candidates are reverified, including both content-addressed run IDs;
- concept ambiguity is preserved unless an explicit merge decision exists;
- deterministic provisional identities and collision-safe paths are generated for new objects;
- exact existing and same-run duplicates are handled deterministically;
- contradiction and supersession require explicit auditable decisions;
- relation endpoints are translated through the concept plan and unresolved endpoints fail closed to `ignore`;
- planning state and decision-ledger mutation is detected;
- output is immutable and content-addressed;
- no canonical state is mutated and no Stage 09 compilation occurs.
