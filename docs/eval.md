# Evaluation Plan: Groww Weekly Review Pulse

## 1. Objective

Evaluate whether the system can reliably turn public Groww Play Store feedback from the preceding 8-12 weeks into a safe, evidence-based weekly pulse, publish it to Google Docs through MCP, and create an unsent Gmail draft through MCP.

Evaluation is release-blocking for privacy, quote fidelity, output contract, and delivery behavior. Insight quality is measured with a curated evaluation set and human review before production release.

## 2. Evaluation Principles

- Test components independently, then test the complete pipeline with fixture and controlled live runs.
- Keep all evaluation fixtures synthetic or irreversibly sanitized; never commit real reviewer PII.
- Treat model output as untrusted: validate it against source evidence and deterministic constraints.
- Evaluate LangChain LCEL chains as typed, versioned components; use fake `BaseChatModel` implementations for deterministic CI tests.
- Separate hard safety requirements from quality targets. A quality target can drive iteration; a hard requirement must prevent publication.
- Test Docs and Gmail through fake MCP ports in CI and through the configured MCP servers only in controlled staging.

## 3. Release Gates

All hard gates must pass for every candidate release.

| Gate | Requirement | Measurement | Pass Condition |
| --- | --- | --- | --- |
| Public-source compliance | Collection uses only an approved public source and never requires store login. | Adapter review and automated configuration test. | Approved adapter is allowlisted; authenticated/browser automation paths are absent. |
| Date-window accuracy | Only reviews from configured 8-12 week window are eligible. | Boundary fixtures and injected clock tests. | 100% correct inclusion/exclusion at cutoff and lookback boundaries. |
| PII safety | No PII or author metadata persists, reaches a model, appears in a Doc, email draft, alert, or log. | PII fixture suite, object-shape assertions, log/output scans. | Zero unredacted seeded PII occurrences. |
| Theme cap | Analysis produces at most five themes; pulse shows top three. | Theme fixtures and pulse validation. | 100% of runs satisfy cap; valid full pulses have exactly three displayed themes. |
| Quote fidelity | Each displayed quote is anonymous and verbatim from sanitized source review text. | Contiguous-substring and provenance assertions. | 100% of displayed quotes have valid source ID and exact sanitized substring match. |
| Action grounding | Each action is concrete and tied to a selected theme/evidence set. | Structured linkage checks plus reviewer rubric. | 100% have a selected-theme ID; human grounding score meets threshold. |
| Pulse contract | Pulse contains required sections and exactly three themes, quotes, and actions, with <=250 words. | `PulseValidator` and golden outputs. | 100% pass; 251-word output is rejected. |
| MCP-only delivery | Docs and Gmail are reached through MCP ports; no direct Google REST/OAuth code exists. | Dependency/code search and MCP contract tests. | No prohibited client/auth code; fake MCP ports receive expected calls. |
| Draft-only email | System creates a Gmail draft but never sends email. | Capability/configuration test and staging observation. | One draft request; zero send capability/calls. |
| Idempotent delivery | Retry cannot create duplicate documents or drafts. | Failure-injection and retry tests. | At most one document and one draft per run identity. |
| LangChain chain contract | LCEL chains receive only sanitized inputs and return validated `ThemeAnalysis`/`PulseDraft` structured outputs. | Fake-model tests, Pydantic schema assertions, and prompt-version checks. | 100% schema validation; zero raw/author fields in chain input; every run records prompt version and model ID. |
| LangChain observability safety | Callbacks, tracing, and provider telemetry do not export review content without approval. | Callback configuration tests and captured telemetry scans. | Zero raw-review/PII occurrences; tracing disabled unless explicitly approved and sanitized. |

## 4. Test Corpus

Build a versioned evaluation corpus under `tests/fixtures/`. Each fixture has a source-like record, expected sanitized record, expected theme/evidence labels, and expected pipeline result. Do not use real usernames, email addresses, phone numbers, or account identifiers.

| Corpus Set | Purpose | Minimum Cases |
| --- | --- | --- |
| `collection` | Verify source parsing, pagination, time window, and deduplication. | Newest-first/unsorted pages, cutoff equality, future/malformed dates, null fields, duplicate IDs, same text with different IDs. |
| `privacy` | Verify all redaction and exclusion paths. | Email, phone, UPI/account/card/PAN-like values, URLs with personal parameters, author fields, cross-title/body PII, text rendered empty by redaction. |
| `analysis` | Verify theme quality and evidence lineage. | Six candidate themes, synonym themes, ties, mixed sentiment, recent severe issue, low confidence, multilingual text. |
| `generation` | Verify note structure and safe model behavior. | Exact 250/251 word pulses, missing sections/items, duplicate quotes/actions, fabricated metrics, prompt-injection content, Markdown escaping. |
| `langchain` | Verify LCEL construction, prompt, structured output, batching, and provider-failure behavior. | Missing/mismatched prompt variables, malformed/extra schema fields, unknown evidence IDs, PII replay, model timeout, context limit, callback leakage. |
| `delivery` | Verify MCP sequencing, error handling, and idempotency. | Docs unavailable, Gmail unavailable after Docs success, lost responses, stale document ID, duplicate retry, recipient configuration drift. |
| `end_to_end` | Verify the stakeholder workflow with fake MCP adapters. | Normal valid run, no eligible reviews, insufficient themes, PII rejection, recovery after crash. |

### Gold Standard Annotation

For the `analysis` corpus, maintain an annotation file containing:

- Allowed canonical theme labels and review-to-theme mapping.
- Expected top-three ordering or an allowed ordering set when scores intentionally tie.
- Approved quote source IDs and valid contiguous excerpts.
- Required action-to-theme relationships.
- Exclusion reasons for records that are unsafe or ineligible.

Two reviewers should independently annotate a representative sample before finalizing the corpus. Resolve differences into the canonical fixture rather than scoring against informal expectations.

## 5. Automated Evaluation Matrix

| Area | Method | Metrics | Hard Threshold |
| --- | --- | --- | --- |
| Configuration | Unit tests with injected environment/config. | Valid/invalid configuration acceptance. | Invalid app ID, lookback, recipient, and MCP config are rejected. |
| Collection | Adapter contract tests using recorded public-shape fixtures. | Date-window precision and recall; duplicate handling. | Precision = 1.0 and recall = 1.0 on annotated fixture data. |
| Privacy | Unit and property tests using seeded PII variants. | PII leakage count; author-field retention count. | Both counts = 0 across storage, logs, prompts, pulse, and email body. |
| Storage | Repository tests and migration tests. | Duplicate records, transaction failures, restart recovery. | No duplicate persisted review/delivery record for a run identity. |
| Theme analysis | Unit tests against annotated corpus. | Theme assignment precision/recall/F1; top-three overlap. | Baseline targets: theme F1 >= 0.80, top-three overlap >= 2 of 3. |
| Ranking | Deterministic repeated-run test. | Rank stability; cap violations. | Identical input gives identical ordering; zero cap violations. |
| Quote selection | Exact-string provenance and diversity tests. | Provenance rate; unique source-review rate. | Provenance = 100%; three quotes must use three source reviews when corpus permits. |
| Action planning | Structural checks and rubric scoring. | Theme linkage; concreteness and grounding scores. | Linkage = 100%; mean reviewer score >= 4/5. |
| LangChain chains | Fake `BaseChatModel` tests for LCEL sequences, prompt assets, and structured schemas. | Schema-valid output rate; unsafe chain-input count; prompt/model metadata completeness. | Output schema rate = 100%; unsafe inputs = 0; metadata completeness = 100%. |
| LangChain resilience | Inject provider errors and constrained batch/context limits. | Fallback correctness; unsafe retry/publish count. | Baseline fallback is used only when valid; otherwise zero publish attempts. |
| LangChain observability | Capture callbacks/traces/logs during fake-model runs. | Raw-review/PII telemetry leakage count. | Leakage count = 0. |
| Pulse composition | Golden/snapshot tests and word-count boundary tests. | Contract pass rate; visible word count. | Contract pass rate = 100%; word count <=250. |
| MCP adapters | Fake-port contract and failure-injection tests. | Docs-before-Gmail ordering; duplicate artifact count. | Ordering = 100%; duplicate count = 0. |
| Orchestration | End-to-end tests with crash/retry injection. | Resumable runs; incorrect publish attempts. | All valid fixtures complete; invalid/blocked fixtures issue zero MCP calls. |

Theme F1 is $F1 = \frac{2PR}{P + R}$, where $P$ is precision and $R$ is recall against the annotated review-to-theme mapping. The quality target is a baseline, not a substitute for the hard output validators.

## 6. Human Evaluation Rubric

Run human review on at least 20 distinct, sanitized weekly-pulse scenarios before initial release and periodically after significant changes to theme or generation logic. Two reviewers from Product/Growth and Support independently score each dimension from 1 to 5.

| Dimension | Score 1 | Score 3 | Score 5 | Release Target |
| --- | --- | --- | --- | --- |
| Theme usefulness | Generic or misleading. | Mostly relevant but broad or partially ranked. | Specific, representative, and correctly prioritized. | Mean >= 4.0 |
| Quote representativeness | Irrelevant, unclear, or overstates theme. | Relevant but not ideal evidence. | Concise, clear, diverse, and directly supports theme. | Mean >= 4.0 |
| Action usefulness | Vague or detached from feedback. | Plausible but lacks specificity. | Concrete next step with clear owner-oriented intent and evidence tie. | Mean >= 4.0 |
| Scanability | Difficult to read quickly. | Generally scannable. | Clear one-page summary readable in a few minutes. | Mean >= 4.0 |
| Factual faithfulness | Unsupported claim or altered quote. | Minor ambiguity. | Every claim follows supplied statistics/evidence. | Mean = 5.0 |
| Privacy safety | Any identifying detail. | N/A: safety has no acceptable partial score. | No identifying detail. | Every reviewer score = 5 |

Release requires no individual scenario below 3 for theme, quote, action, or scanability; factual faithfulness and privacy safety are hard gates.

## 7. Adversarial and Safety Evaluation

Add explicit adversarial tests at each release for these inputs:

- Review text directing the analyzer to ignore prior instructions, reveal configuration, or create/send an email.
- Embedded Markdown/HTML, script-like content, exceptionally long text, repeated characters, and deceptive Unicode.
- PII in titles, bodies, URLs, obfuscated formats, and combined fields.
- Fake support phone numbers, links, refund demands, account details, and financial identifiers.
- Mixed-language and transliterated content with PII or topic words.
- Model outputs that invent quotes, precise metrics, claims, promises, or more than the allowed themes/actions.
- LangChain structured-output failures, prompt-variable mismatches, provider/model drift, context overflow, and callback/tracing configurations that export chain input.
- MCP failures that return ambiguous success, sensitive metadata, stale IDs, or unauthorized responses.

The expected result is sanitized data, rejection, or a blocked/failed run with zero inappropriate delivery calls. No adversarial case may cause the system to execute instructions contained in review text.

## 8. Staged Evaluation Procedure

### Stage A: Local/CI

1. Run unit, type, lint, and formatting checks.
2. Execute all fixture-based component, LangChain-chain, contract, and end-to-end tests using fake collection, `BaseChatModel`, and MCP adapters.
3. Scan source/dependencies for direct Google API clients, OAuth flows, email-send operations, and unapproved LangChain tracing/callback integrations.
4. Publish a machine-readable report containing only pass/fail results, metric aggregates, prompt/model versions, and non-sensitive run IDs.

### Stage B: Controlled Staging

1. Configure approved MCP Docs and Gmail servers with least-privilege access and a staging recipient alias.
2. Execute a controlled run using sanitized fixtures first; verify one readable Doc and one unsent draft.
3. Inject Docs and Gmail failures independently; verify idempotent recovery and correct call order.
4. Execute one compliant live-public-review run only after privacy and source checks pass.
5. Inspect the Doc and draft manually for wording, quote fidelity, PII, and 250-word compliance.

### Stage C: Release Sign-Off

1. Confirm all hard gates pass in CI and staging.
2. Review human-evaluation scores and resolve scenarios below target.
3. Confirm source-compliance review, retention controls, alert redaction, and MCP least privilege.
4. Approve weekly scheduling only after the controlled run produces a valid Doc and unsent draft.

## 9. Reporting and Regression Policy

Every evaluation run records: build/version, fixture-corpus version, LangChain model and prompt versions, configuration profile name, test counts, hard-gate status, quality metrics, and delivery-call counts. Reports must not store raw review content, recipient addresses, chain prompts/outputs, or credentials.

Any change to collection adapters, redaction rules, LangChain chains/models/prompts, theme/ranking logic, MCP adapters, document template, or retry logic requires the full regression suite. A hard-gate regression blocks release. A quality-metric regression of more than 5 percentage points from the accepted baseline requires review and documented approval before release.

## 10. Final Acceptance Checklist

- [ ] Public-source and date-window tests pass with 100% annotated fixture accuracy.
- [ ] PII and author-metadata leakage count is zero across all tested boundaries.
- [ ] Theme output never exceeds five themes; valid pulse output has exactly three top themes.
- [ ] Every displayed quote has exact sanitized-source provenance and no identifier.
- [ ] Every action links to a selected theme and meets human usefulness threshold.
- [ ] LangChain LCEL chains use versioned prompts, schema-validated outputs, sanitized inputs, and no unapproved tracing/callback export.
- [ ] Every delivered pulse meets its required structure and visible word count is <=250.
- [ ] Tests confirm invalid/blocked cases issue no Docs or Gmail MCP requests.
- [ ] Tests confirm valid runs issue Docs before Gmail, create only a draft, and remain idempotent on retry.
- [ ] Staging confirms the configured MCP servers produce a readable Google Doc and unsent Gmail draft.
- [ ] No direct Google REST/OAuth client or application-managed credential flow is present.