# Stage 10 — Structuralize

Stage 10 projects one verified immutable Stage 09 canonical-state generation into a deterministic LLM-Wiki / Open Knowledge Format structural intermediate representation. It is the first stage that is intentionally OKF-aware.

Stage 10 does **not** emit the final Markdown/YAML bundle. Stage 14 owns canonical serialization. A test-only materializer is used by the ecosystem compatibility suite so external OKF tools can exercise the Stage 10 structure without moving serialization into this stage.

## Structural baseline

`builtin-v1` targets the repository-pinned OKF v0.1 structural contract at commit `ee67a5ca27044ebe7c38385f5b6cffc2305a9c1a`.

The projection follows these base rules:

- every active projected document has an OKF `type`;
- optional `title` and `description` are emitted when deterministically available;
- concept pages preserve their canonical Stage 09 paths;
- relationships are represented as typed structural links that Stage 14 can serialize as Markdown links;
- `index.md` and `log.md` remain reserved but are not produced here, because Stage 13 owns derived indexes/logs;
- final Markdown/YAML rendering is explicitly deferred to Stage 14;
- unknown/private workflow identity data is kept outside public frontmatter.

## Input

Stage 10 reads `.okf-generator/state`.

If `--generation-id` is omitted, the atomically active Stage 09 generation from `current.json` is selected. The selected generation is then fully verified and bound into the structural run. An explicit content-addressed Stage 09 generation may instead be supplied.

Stage 09 verification includes the state manifest, object JSONL files, identity registry, event ledger, resolver/planner projections, recorded hashes, object counts, generation ID derivation, and internal cross-references.

The same exact generation is reverified after structural projection and before publication. Mutation therefore fails without publishing a structural run.

## Public documents and private identity

The Stage 10 IR has one document for each non-merged canonical object:

- `concept` → OKF type `Concept`;
- `summary` → OKF type `Summary`;
- `claim` → OKF type `Claim`;
- `relation` → OKF type `Relation`.

Concept documents preserve the canonical paths already frozen by Stage 09. Other canonical object types do not yet have public paths in Stage 09, so Stage 10 assigns stable auxiliary paths of the form:

```text
summaries/sha256-<24-hex>.md
claims/sha256-<24-hex>.md
relations/sha256-<24-hex>.md
```

The suffix is deterministically derived from the stable private internal identity. The raw private identity is never placed in public frontmatter or the public path.

`identity-map.json` is a private sidecar that maps stable `identity_ref` values to canonical private IDs, object type, status, public path, and merge target. Merged/tombstoned objects remain in the identity map but do not produce public documents.

## Structural document IR

`documents.jsonl` is sorted by public path. Each row contains:

- `document_id` — public OKF ID, equal to the path without `.md`;
- `path`;
- private `identity_ref` used only inside the structural control plane;
- canonical `object_type`;
- projected `okf_type`;
- `frontmatter` — structural field map, not YAML text;
- `body` — typed blocks rather than serialized Markdown.

Supported `builtin-v1` body blocks are:

- `heading`;
- `paragraph`;
- `list`;
- `links`;
- `relation`.

Stage 14 will own the canonical byte-level rendering of these blocks.

## Semantic projection

Concept documents retain title, description, aliases, resource URIs, and evidence anchors. Claims retain their statement, evidence, and links to active contradictory/superseding claims. Relation documents link the active subject and object concept documents around the canonical predicate. Summaries retain their text and evidence.

Stage 10 does not invent timestamps, tags, resources, trust fields, descriptions, claims, or relationships that are absent from canonical state.

## Reserved documents and stage ownership

`deferred.json` explicitly records:

- `index.md` → Stage 13 Derive;
- `log.md` → Stage 13 Derive;
- final Markdown/YAML serialization → Stage 14 Serialize.

This preserves the fixed pipeline boundary while still allowing Stage 10 to model the OKF document tree.

## Output

```text
.okf-generator/structural/
  <stage09-generation-id>/
    <structuralization-profile>/
      sha256-<run>/
        structuralization.json
        documents.jsonl
        identity-map.json
        deferred.json
```

The run ID binds the Stage 09 generation and manifest hash, structuralization profile, OKF v0.1 spec pin, and exact output artifact hashes.

Existing content-addressed output is immutable. Re-running identical input returns the same run only after exact-file verification.

## Ecosystem evaluation

Stage 10 is the first stage that evaluates OKF-specific ecosystem tools.

### OKFy

Target:

- repository: `0dust/OKFy`;
- source commit: `c73caa4fb7fdb0e2a6f69f2c677a4b632df4b226`;
- npm package: `okfy-ai@0.3.5`.

Its Stage 10 role is independent structural validation. The local test suite replays the structural requirements from the pinned validator source. The PR ecosystem workflow additionally installs the real pinned npm package and executes `okfy validate` against a temporary bundle materialized from the Stage 10 IR.

### OpenWiki

Target:

- repository: `langchain-ai/openwiki`;
- source commit: `79dd5fc2b3561c723c9abcfadb5359a0234f1221`;
- npm package: `openwiki@0.3.3`.

OpenWiki remains a producer/design comparison rather than a runtime dependency. The local suite replays its pinned OKF frontmatter contract. The PR ecosystem workflow installs the real npm package and directly executes OpenWiki's published `validateOkfFrontmatter` implementation against every materialized concept page.

Native npm execution cannot run in the current local container because registry DNS resolution is unavailable. That environmental failure is not treated as a compatibility result; native package acceptance is therefore run in GitHub Actions.

Neither ecosystem package becomes a Stage 10 runtime dependency.

## Failure semantics

Stage 10 fails without publication when:

- Stage 09 current/generation verification fails;
- an object path is unsafe or collides with `index.md` / `log.md`;
- two active projected objects collide on a public path;
- a merged identity references an unknown target;
- an active relation lacks active public endpoints;
- canonical state changes while structuralization is running;
- an existing content-addressed run differs from the derived result.

## CLI

Use the active state generation:

```bash
okf-generator structuralize
```

Use an exact immutable generation:

```bash
okf-generator structuralize --generation-id sha256-<stage09-generation>
```
