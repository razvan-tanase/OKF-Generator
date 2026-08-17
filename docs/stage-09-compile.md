# Stage 09 — Compile

Stage 09 is the sole mutation boundary for the canonical internal knowledge state. It consumes one exact verified Stage 08 plan and applies that plan atomically to a versioned state generation. It does not emit an OKF bundle or apply LLM-Wiki/OKF structural conventions; Stage 10 owns that projection.

## Boundary

Allowed:

- reverify the complete Stage 08 → Stage 07 → Stage 06 chain;
- reject stale plans whose embedded resolution/planning projections are not the current canonical projections;
- finalize Stage 08 provisional identities deterministically;
- apply `create`, `update`, `merge`, `contradict`, `supersede`, and `ignore` operations;
- preserve concept title/path history and merge tombstones;
- rewrite existing relation endpoints when concept identities merge;
- preserve claim contradiction/supersession links;
- append an immutable event for every planned operation, including ignored operations;
- publish an immutable content-addressed canonical state generation;
- atomically switch the canonical `current.json` pointer.

Forbidden:

- new semantic decisions not present in Stage 08;
- LLM/model inference;
- path moves that were not planned;
- OKF structuralization, version migration, enrichment, or serialization;
- partial mutation of the active canonical generation.

## Canonical state layout

```text
.okf-generator/state/
  current.json
  .compile.lock
  generations/
    sha256-<generation>/
      state.json
      concepts.jsonl
      summaries.jsonl
      claims.jsonl
      relations.jsonl
      identity-registry.json
      events.jsonl
      resolution-catalog.json
      planning-state.json
```

Generations are immutable. `current.json` is the only mutable canonical pointer and is replaced atomically after the new generation has been fully materialized and verified.

A failed pointer activation leaves the previous `current.json` authoritative. A content-addressed generation that was materialized before a failed pointer switch is harmless and remains unreachable until explicitly referenced.

## First compilation

If no canonical `current.json` exists, Stage 09 bootstraps the base state from the exact Stage 07 catalog snapshot and Stage 08 planning-state snapshot bound into the selected plan. This preserves pre-existing identities supplied to the first resolution/planning cycle without silently inventing additional state.

After the first compilation, subsequent Stage 07 and Stage 08 runs should use the generated:

- `resolution-catalog.json` as the Stage 07 identity catalog;
- `planning-state.json` as the Stage 08 claims/relations projection.

Stage 09 refuses to apply a later plan if either projection differs from the active canonical generation. This is the stale-plan/optimistic-concurrency guard.

## Identity finalization

Stage 08 provisional identities are not canonical IDs. Stage 09 finalizes every planned `create`, `contradict`, or `supersede` identity using:

`stage09-final-id-v1`

The final ID is SHA-256 over the object type and provisional identity. The mapping is deterministic and type-scoped. Relations whose Stage 08 payload references a provisional concept ID are rewritten to its finalized canonical ID before validation.

Existing internal IDs are never reallocated.

## Operation semantics

### Concepts

`create` adds a new active concept using the Stage 08 proposed path. The proposed path is checked against every canonical and historical concept path.

`update` changes title/description and adds the prior title to `title_history` when the title changes. Canonical paths do not move.

`merge` keeps the declared survivor, records non-survivors as `status: merged` with `merged_into`, carries aliases/title/path history/resource URIs/source anchors into the survivor, and rewrites active relations that referenced merged concept IDs.

### Summaries

`create` adds an active summary. `merge` consolidates duplicate summary evidence into the declared survivor and leaves merge tombstones for non-survivors when applicable.

### Claims

`create` and `update` preserve evidence anchors.

`contradict` creates the planned new claim and records reciprocal `contradicts` / `contradicted_by` links.

`supersede` creates the planned replacement, records reciprocal `supersedes` / `superseded_by` links, and marks the target `superseded`.

`merge` consolidates evidence and claim relationship links into the survivor, rewrites references to merged claim IDs, and removes self-links created solely by identity collapse.

### Relations

Relation endpoints must resolve to active concepts after provisional-ID translation and concept-merge rewriting. `create`, `update`, and `merge` preserve evidence anchors. Relation merges retain a survivor and merge tombstones.

`ignore` never changes semantic state, but its operation remains in `events.jsonl` for auditability.

## Persistent knowledge-state envelope

The Stage 09 generation carries the workflow's canonical persistent state:

- semantic knowledge: concepts, summaries, claims, relations;
- source evidence: evidence anchors and concept source anchors;
- provenance/history: append-only events plus plan/generation ancestry;
- private stable identity registry: `identity-registry.json`;
- identity/path history and merge tombstones;
- deterministic Stage 07/08 projections.

This is deliberately richer than any single OKF serialization version. Stage 10+ operate on projections of this state rather than treating an older serialized OKF bundle as the information universe.

## Atomicity and concurrency

Stage 09 uses a standard-library advisory file lock for compiler coordination. Under the lock it:

1. verifies the selected Stage 08 plan;
2. verifies the current canonical generation, if present;
3. checks that plan base projections equal current projections;
4. applies all operations in memory;
5. reverifies the complete Stage 08 plan/upstream chain;
6. validates every resulting canonical object and cross-reference;
7. materializes an immutable content-addressed generation;
8. rechecks that `current.json` has not changed unexpectedly;
9. atomically replaces `current.json`.

If any earlier step fails, `current.json` is unchanged.

## Replay behavior

Re-running the plan that produced the active generation is idempotent only when the plan manifest and operations hashes still match the generation provenance.

A plan already applied to an ancestor generation is rejected. This prevents duplicate semantic effects and preserves append-only history.

## Output projections

`resolution-catalog.json` contains non-merged concepts in the exact Stage 07 catalog schema.

`planning-state.json` contains non-merged claims and relations in the exact Stage 08 planning-state schema. Superseded claims remain visible with their status so later semantic decisions can reference them.

These projections make the next source-ingestion cycle deterministic and avoid an external synchronization layer between Stages 09, 07, and 08.

## CLI

```bash
okf-generator compile paper sha256-<snapshot> \
  sha256-<synthesis-run> sha256-<resolution-run> sha256-<plan-run> \
  --synthesis-provider openai
```

State is written under `.okf-generator/state` by default.

## Tool decision

No new runtime dependency is selected. Stage 09 uses Python standard-library JSON/SHA-256, filesystem primitives, temporary files, atomic rename, and OS-provided advisory file locking (`fcntl` on POSIX; `msvcrt` fallback on Windows).

No OKF ecosystem tool is selected here because Stage 09 remains format-neutral canonical-state compilation. The first OKF-specific ecosystem-tool evaluation remains Stage 10 — Structuralize.

## Completion criteria

Stage 09 is complete when:

- Stage 08 artifact hashes and content-addressed plan identity are reverified;
- the bound Stage 07/06 chain is reverified;
- stale plans cannot mutate a newer canonical generation;
- provisional identities are deterministically finalized;
- all six Stage 08 operation kinds are applied with object-type-specific constraints;
- merges preserve identity/path/history information and required cross-reference rewrites;
- contradiction/supersession semantics are explicit and reciprocal;
- every operation appends an auditable event;
- every state generation is immutable and content-addressed;
- the current pointer is atomically updated only after complete generation validation;
- replay and ancestor-plan protection are enforced;
- Stage 09 introduces no Stage 10 structuralization or OKF serialization.
