# Stage 07 — Resolve

Stage 07 matches source-local concept candidates from one immutable Stage 06 synthesis run against a read-only catalog of existing canonical concept identities. It produces resolution evidence only. It does not create identities, merge concepts, update pages, or mutate canonical knowledge state.

## Boundary

Stage 07 consumes one verified Stage 06 synthesis run. Only `concept` candidates are identity-resolved. Summaries and claims remain evidence-grounded Stage 06 candidates, and relations continue to reference Stage 06 concept candidate IDs. Stage 08 can combine those candidates with the Stage 07 resolution map when deciding operations.

Stage 07 never:

- creates a new stable internal concept ID;
- changes an existing canonical path or alias;
- decides create/update/merge/contradict/supersede/ignore operations;
- edits the identity catalog;
- compiles canonical wiki state;
- emits OKF documents.

Those operations remain Stage 08/09 or later responsibilities.

## Input selection

A resolution invocation identifies:

- `source_id` and immutable `snapshot_id`;
- the Stage 06 synthesis provider;
- the exact content-addressed Stage 06 `synthesis_run_id`;
- optionally, a read-only resolution catalog;
- optionally, an explicit adjudication model.

Stage 07 verifies every Stage 06 run artifact hash and rederives the Stage 06 content-addressed run ID from its manifest. A coordinated manifest/artifact edit therefore cannot remain under the original synthesis run identifier.

If `--catalog` is omitted, Stage 07 uses an explicit canonical empty catalog. This is the first-run mode: every concept candidate without a catalog match is `new`, but Stage 07 still does not allocate an internal identity. Once canonical state exists, later stages can provide a generated catalog to Stage 07.

## Resolution catalog v0.1

The catalog has exactly:

```json
{
  "schema_version": "0.1",
  "concepts": []
}
```

Each concept record contains exactly:

- `internal_id` — private stable workflow identity;
- `title`;
- `description`;
- `canonical_path`;
- `aliases`;
- `title_history`;
- `path_history`;
- `resource_uris`;
- `source_anchors`;
- `status`.

Internal IDs and normalized canonical paths must be unique. Catalog paths must be relative and may not contain `..`. The catalog is normalized only for matching and canonical snapshotting; Stage 07 does not rewrite the source catalog file.

The exact source-file SHA-256 and the canonical catalog SHA-256 are both recorded. If the catalog changes while resolution is running, publication fails.

## Matching ladder

The `builtin-v1` resolver is deliberately conservative.

1. **Source-anchor + name** — a known source-anchor overlap may resolve only when the candidate name is also compatible with the catalog title/alias/path identity.
2. **Resource-URI + name** — a source-version/resource URI overlap may resolve only with compatible name identity.
3. **Alias/title history exact match.**
4. **Current title or path-title exact match.**
5. **Deterministic lexical shortlist** — Unicode/case-normalized token overlap plus name similarity generates candidate identities but never auto-merges them.
6. **Optional adjudication** — only unresolved/ambiguous shortlisted cases are sent to the configured adjudicator.
7. **Ambiguous** — if no safe decision exists, the ambiguity is preserved for later review/planning.

Stage 06 `candidate-v1` provides evidence anchors but does not assert a concept-level external resource identity. For that reason, anchor/resource overlap alone is not sufficient to merge identities in this profile.

## Optional OpenAI adjudication

The provider-neutral adjudicator interface is optional. The initial CLI implementation can reuse the Stage 06 OpenAI Responses API provider when `--adjudication-model` is supplied.

The adjudicator receives only:

- the unresolved Stage 06 concept candidate;
- the deterministic shortlist of catalog concepts;
- no external retrieval or tools.

It must return exactly one of `match`, `new`, or `ambiguous`. A `match` must select an `internal_id` from the supplied shortlist. `new` and `ambiguous` return an empty internal ID. Local validation rejects any provider output that exceeds that authority.

If no adjudication model is supplied, the stage is fully deterministic: strong exact matches become `matched`, no-candidate cases become `new`, and approximate/tied cases remain `ambiguous`.

## Output

Stage 07 publishes a content-addressed run under:

```text
.okf-generator/resolutions/
  <source-id>/<snapshot-id>/<ruleset>/<extraction-profile>/<normalization-profile>/
  <synthesis-profile>/<synthesis-provider>/<synthesis-run-id>/<resolution-profile>/sha256-<run>/
```

Each run contains:

- `resolution.json` — manifest and upstream/catalog/adjudication hashes;
- `catalog.json` — canonical read-only catalog snapshot used for the run;
- `resolutions.jsonl` — one row per Stage 06 concept candidate;
- `adjudication-requests.jsonl`;
- `adjudication-responses.jsonl`;
- `adjudication-receipts.jsonl`.

Resolution rows contain the Stage 06 `candidate_id`, candidate name, `matched|new|ambiguous` status, resolution method, optional resolved internal ID, considered internal IDs, source evidence anchors, and deterministic shortlist signals/scores.

Distinct adjudication results create distinct content-addressed Stage 07 runs instead of overwriting one another.

## Determinism

Without adjudication, a fixed Stage 06 run, catalog bytes, profile, threshold, and shortlist limit produce byte-identical Stage 07 artifacts.

With adjudication, orchestration, shortlist construction, schemas, validation, provenance, and artifact addressing remain deterministic, while model output itself may vary. The model result is therefore part of the content-addressed run identity.

## Failure semantics

Stage 07 fails without publication when:

- the Stage 06 run ID or any recorded artifact hash is inconsistent;
- Stage 06 candidate structure or relation endpoints are malformed;
- the catalog is malformed, has duplicate identities/paths, or changes during a run;
- source/provider/run identifiers are unsafe;
- an adjudicator selects an ID outside its shortlist;
- an adjudicator is configured without an explicit model or vice versa;
- existing content-addressed output differs from the newly derived output;
- Stage 06 artifacts mutate while resolution is running.

## CLI

Deterministic first-run resolution:

```bash
okf-generator resolve paper sha256-<snapshot> sha256-<synthesis-run> \
  --synthesis-provider openai
```

Resolution against an existing catalog:

```bash
okf-generator resolve paper sha256-<snapshot> sha256-<synthesis-run> \
  --synthesis-provider openai \
  --catalog .okf-generator/state/resolution-catalog.json
```

Optional model adjudication of only unresolved cases:

```bash
OPENAI_API_KEY=... okf-generator resolve paper sha256-<snapshot> sha256-<synthesis-run> \
  --synthesis-provider openai \
  --catalog .okf-generator/state/resolution-catalog.json \
  --adjudication-model <explicit-model-id>
```
