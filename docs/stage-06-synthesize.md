# Stage 06 — Synthesize

Stage 06 is the first intentionally non-deterministic stage. It converts verified Stage 05 normalized evidence into **source-local candidate** summaries, concepts, factual claims, and relations. It does not decide whether a candidate matches an existing wiki concept and it does not modify canonical knowledge state.

## Boundary

Allowed:
- deterministic selection and batching of complete normalized units;
- LLM inference over those units;
- source-local summaries, concepts, claims, and concept-to-concept relations;
- strict structural validation and evidence-anchor validation;
- immutable capture of model requests, parsed responses, provider receipts, and candidates.

Forbidden:
- resolving candidates to existing concept IDs;
- create/update/merge/contradict/supersede decisions;
- changing canonical wiki state;
- OKF structuralization, migration, or serialization;
- silent truncation of normalized evidence;
- ungrounded candidates that cite no supplied evidence anchor.

Those operations belong to Stage 07 and later.

## Input

The input is one immutable Stage 05 normalization:

```text
.okf-generator/normalized/<source-id>/<snapshot-id>/<classification-ruleset>/<extraction-profile>/<normalization-profile>/
  normalization.json
  units.jsonl
```

Stage 06 verifies the Stage 05 manifest and units hash, validates the normalized unit schema and source identities, and runs the Stage 05 verifier before model calls. It verifies the same files again after all calls; mutation during synthesis fails the run.

## Deterministic orchestration, variable inference

`builtin-v1` fixes:
- prompt text (`prompt-v1`) and its SHA-256;
- candidate JSON schema (`candidate-v1`) and its SHA-256;
- exact full-unit input rendering;
- greedy input-order batching;
- maximum input characters, units per batch, and output tokens;
- candidate ID assignment and relation-index translation;
- evidence-validation rules;
- canonical JSON serialization.

Model output is not assumed to be byte-deterministic. A synthesis invocation therefore produces a content-addressed **run** after the provider responses are known. Distinct responses or provider receipts coexist rather than overwriting each other.

## Batching

Units remain intact. Stage 06 greedily packs normalized units in their existing order until either `max_input_chars` or `max_batch_units` would be exceeded. A unit that cannot fit by itself causes an error; Stage 06 never truncates or silently drops evidence.

This first profile deliberately does not split units or perform semantic chunking. `max_input_chars` is a provider-neutral orchestration bound, not a promise that a particular model accepts that context size; provider context-limit errors fail the run. If a later profile introduces deterministic fragmenting, that is an explicit profile change.

## Candidate schema

Each provider response contains four arrays:
- `summaries`: concise source-local summaries;
- `concepts`: names and descriptions of candidate concepts;
- `claims`: factual candidate statements;
- `relations`: predicates between concepts in the same batch.

Every item must cite at least one `evidence_anchors` value and every cited anchor must have been supplied in that exact batch. Duplicate or unknown anchors are rejected.

Relations reference zero-based indices into that response's `concepts` array. The control plane validates bounds and converts those indices to workflow-owned candidate IDs such as `b0001-c0001`. The model never invents persistent wiki identities.

Evidence-anchor validation is a structural grounding control, not a proof that the model's wording is entailed by the evidence. Later quality/evaluation stages can apply stronger factual-support checks.

## Output

```text
.okf-generator/syntheses/<source-id>/<snapshot-id>/<ruleset>/<extraction-profile>/<normalization-profile>/builtin-v1/<provider>/sha256-<run>/
  synthesis.json
  requests.jsonl
  responses.jsonl
  receipts.jsonl
  candidates.jsonl
```

`requests.jsonl` records the exact Stage 06 prompt/input/schema presented to the provider abstraction. `responses.jsonl` records the parsed strict-schema response for each batch. `receipts.jsonl` records provider response IDs, requested/resolved model identifiers, and usage observations. `candidates.jsonl` contains workflow-owned candidate IDs and validated evidence anchors.

The run ID is SHA-256 over the upstream evidence hashes, profile/prompt/schema configuration, batching limits, and the four canonical run-artifact hashes. Existing run directories are verified and never overwritten.

## OpenAI adapter

The initial concrete adapter uses the OpenAI Responses API directly over HTTPS and requires `OPENAI_API_KEY`. It requests strict JSON Schema output and sets `store=false`. No OpenAI SDK dependency is required. The adapter performs one request per batch and does not retry implicitly; an operator can rerun explicitly, producing a separately auditable run.

The CLI requires an explicit `--model` rather than silently selecting a moving model alias. Prefer a pinned model snapshot when the provider exposes one. The requested model and provider-resolved model are both recorded in run provenance.

Stage 06 intentionally does not enable provider web search, file search, code execution, or other tools: candidates must be based only on the normalized Stage 05 evidence supplied by this pipeline.

## CLI

```bash
export OPENAI_API_KEY=...
okf-generator synthesize paper sha256-<snapshot-digest> --model <explicit-model-id>
```

Optional batching controls:

```bash
okf-generator synthesize paper sha256-<snapshot-digest> \
  --model <explicit-model-id> \
  --max-input-chars 120000 \
  --max-batch-units 50 \
  --max-output-tokens 8000
```

## Tool decision

OpenAI's Responses API is the first provider adapter because it supports strict JSON-Schema structured output. The pipeline retains a small provider protocol so another provider can be added later without changing the 00–18 topology or the Stage 06 candidate contract.

No LangChain, agent framework, vector store, or model-driven tool orchestration is selected here. Stage 06 already owns evidence selection, batching, schema validation, and provenance; adding a second orchestration layer would make those controls less explicit. Retrieval from the evolving wiki belongs to later resolution/query workflows, not source-local synthesis.

## Completion tests

Stage 06 is complete when:
- only verified Stage 05 normalized evidence is accepted;
- prompt/schema versions and hashes are persisted;
- batching is deterministic and never truncates a unit;
- exact provider requests, parsed responses, receipts, and candidates are immutable run artifacts;
- every candidate cites only anchors from its own batch;
- malformed output, duplicate/unknown evidence, invalid relation indices, refusals, and incomplete provider responses fail closed;
- model relations are translated to workflow-owned local candidate IDs;
- distinct model runs coexist without overwriting prior runs;
- mutation of Stage 05 evidence during model calls is detected;
- Stage 06 performs no Stage 07 identity resolution or Stage 08 planning.
