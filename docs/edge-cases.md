# Edge Cases: Groww Weekly Review Pulse

## Policy for Safe Failure

The pipeline must fail closed. A review, quote, action, pulse, Google Doc, or Gmail draft may proceed only after its preceding validation boundary succeeds. `blocked` denotes an expected data/quality condition requiring review; `failed` denotes an unexpected technical or configuration error. Neither state may create a Gmail draft.

## Run Configuration and Scheduling

| Case | Expected Behavior | Test / Verification |
| --- | --- | --- |
| Lookback is less than 8 or greater than 12 weeks | Reject configuration before collection. | Boundary tests for 7, 8, 12, and 13 weeks. |
| Lookback is missing | Default to 12 weeks and log the effective non-sensitive configuration. | Configuration default test. |
| App ID is missing or not the Groww package | Reject configuration before any source request. | Invalid app ID test. |
| Locale is missing | Use documented default locale or fail configuration; never infer silently. | Default/error behavior test. |
| Recipient alias is empty or malformed | Block before Docs/Gmail delivery with a non-sensitive configuration error. | Recipient validation test. |
| MCP server/tool name is missing | Fail before delivery, retaining validated local pulse content for retry. | Missing tool configuration test. |
| Scheduler invokes overlapping runs for the same week | Acquire a per-week lock or reuse the existing running/completed run; do not create duplicate Docs or drafts. | Concurrent-run integration test. |
| Manual backfill overlaps with scheduled window | Use explicit `week_ending` as idempotency key; retain distinct run IDs while reusing the correct weekly artifact. | Backfill idempotency test. |
| Job runs at a DST boundary or midnight | Calculate cutoff and week ending in one configured timezone and persist both dates. | Timezone/DST boundary test. |
| Host clock is significantly incorrect | Record run time, detect impossible future cutoff/source dates where possible, and block operator-visible delivery. | Clock-skew test with injected clock. |

## Public Review Collection

| Case | Expected Behavior | Test / Verification |
| --- | --- | --- |
| Provider returns no reviews | Mark run `blocked`; do not synthesize content or call MCP. | Empty-source integration test. |
| No reviews fall within window | Mark run `blocked` and record eligible count as zero. | Date-filter fixture test. |
| Review date equals cutoff | Include it when cutoff semantics are inclusive and document that convention. | Exact-cutoff test. |
| Review date lacks timezone | Parse using the source's documented timezone; reject ambiguous/unparseable values. | Naive timestamp test. |
| Review date is malformed | Exclude record, increment rejection count, and continue. | Invalid-date fixture test. |
| Source returns future-dated review | Exclude it and record a provider-safe anomaly. | Future-date test. |
| Source pages are newest-first | Stop only when the page and remaining pagination guarantee records are older than cutoff. | Ordered-pagination test. |
| Source pages are unsorted | Continue through available pages; never stop solely after one old record. | Unsorted-page test. |
| Same review appears across pages | Deduplicate by source ID before persistence and analysis. | Duplicate-ID pagination test. |
| Source IDs are absent or unstable | Use content hash plus date/rating fallback; retain provenance only when safe. | Missing-ID test. |
| Identical text from distinct reviews | Preserve distinct records when IDs differ; avoid treating all repeated text as one review. | Same-text/different-ID test. |
| Empty title, null text, or whitespace-only text | Normalize null title; exclude reviews without usable text. | Empty-field tests. |
| Rating is null, string, decimal, or outside 1-5 | Normalize valid integer forms; exclude invalid ratings or mark unavailable only if policy permits. | Rating coercion tests. |
| Non-English or mixed-language reviews | Preserve sanitized original text; classify only if supported, otherwise assign `unclassified` internally without inventing meaning. | Multilingual fixtures. |
| Emoji, HTML, markup, or unusual Unicode | Normalize safely; escape content in rendered artifacts; preserve quote wording after sanitization. | Rendering and Unicode tests. |
| Malicious review text contains prompt instructions | Treat source text as data, never instructions; isolate/quote it in model input and output rendering. | Prompt-injection fixture test. |
| Provider rate limits, times out, or returns 5xx | Use bounded exponential backoff; fail after retry budget without publishing. | Retry policy test. |
| Provider returns 401/403 or login page | Treat as unsupported/non-public source; fail configuration/source compliance check. | Auth-required response test. |
| Provider response schema changes | Fail adapter contract validation with an actionable, provider-safe error. | Schema-contract test. |
| Network fails after partial collection | Do not publish partial data unless an explicit completeness threshold is met; otherwise retry/fail and retain only safe checkpoint state. | Partial-fetch failure test. |

## Normalization, Privacy, and Storage

| Case | Expected Behavior | Test / Verification |
| --- | --- | --- |
| Source includes author name, avatar, profile URL, or device metadata | Drop fields before any persistence, logging, model input, Docs content, or email content. | Object-shape and log-capture tests. |
| Text contains an email address | Replace with a neutral redaction token before downstream use. | Email redaction test. |
| Text contains phone numbers in varied local/international formats | Redact conservatively; exclude when confidence is insufficient. | Phone-format fixture suite. |
| Text contains account, card, PAN, UPI, order, or device identifiers | Redact matching sensitive patterns; exclude review if unredacted sensitive data remains. | Identifier fixture suite. |
| Text contains a personal name but no obvious pattern | Use optional approved PII detector; if uncertain, exclude from quotes and flag for review. | Name-detection policy test. |
| URL embeds a token, email, or account value | Replace URL with a redaction token or drop the review. | URL query/fragment redaction test. |
| PII spans title and body | Process concatenated stakeholder-visible text and validate both fields. | Cross-field PII test. |
| PII redaction leaves quote unintelligible | Do not select it as a quote; retain only if remaining review text remains useful for aggregate themes. | Quote-quality test. |
| Review includes only PII after redaction | Exclude it from storage and analysis. | Fully-redacted review test. |
| Content hash is calculated before redaction | Never persist or expose a hash derived from secret-bearing raw text if it can be correlated; hash normalized safe content or use ephemeral deduplication handling. | Storage schema review. |
| Database write fails | Mark run `failed`; do not continue to analysis using unpersisted/unknown state. | Repository-failure test. |
| Database is locked during concurrent run | Retry boundedly or use transaction/lock strategy; never duplicate review or delivery records. | SQLite-lock integration test. |
| Migration is partially applied | Stop startup, report failed migration, and require recovery before a run. | Migration rollback test. |
| Retention job runs during analysis | Use transaction/snapshot isolation so evidence records remain available until run completion. | Concurrent retention test. |
| Retention deletion fails | Alert without exposing content; do not delete unrelated records. | Retention failure test. |

## Analysis, Themes, Quotes, and Actions

| Case | Expected Behavior | Test / Verification |
| --- | --- | --- |
| Fewer than three usable reviews | Block by default; never invent themes or reuse old quotes. | Low-volume fixture test. |
| Fewer than three viable themes | Block unless a documented product policy permits fewer; downstream contract must match that policy. | One/two-theme tests. |
| More than five strong themes | Rank deterministically and retain at most five internally. | Six-theme fixture test. |
| Multiple theme labels describe the same issue | Consolidate before scoring and preserve all evidence IDs. | Synonym merge test. |
| One generic theme dominates all reviews | Prefer specific subthemes when evidence supports them; otherwise retain a truthful generic label. | Dominant-theme fixture test. |
| Tie in theme scores | Apply deterministic tiebreakers: low-rating concentration, recency, then stable label/ID ordering. | Equal-score repeatability test. |
| Positive and negative reviews share a topic | Keep one theme with mixed sentiment or split only when product meaning differs. | Mixed-sentiment fixture test. |
| New issue appears in few recent 1-star reviews | Scoring must allow recency/severity to surface it without overstating volume. | Recent-severe issue test. |
| Classifier confidence is low | Assign `unclassified`/manual-review internally; do not fabricate a precise label. | Low-confidence model stub test. |
| LLM/embedding service is unavailable | Use deterministic baseline if available; otherwise fail before composition. | Dependency outage test. |
| Model returns malformed data or more than five themes | Validate schema and caps; retry with correction or reject output. | Malformed model-output test. |
| Model attempts to follow review-embedded instructions | Keep model prompt instructions authoritative; validate output against schema and source evidence. | Injection-output test. |
| Selected quote is paraphrased, reordered, or translated | Reject it. Quotes must be contiguous substrings of sanitized original text. | Exact-substring test. |
| Selected quote exceeds display budget | Select another quote or use a contiguous shorter excerpt; never add ellipses inside a purported verbatim quote. | Long-quote test. |
| Three selected quotes come from one review or one theme | Enforce diversity across reviews and prefer top-theme coverage where sufficient evidence exists. | Quote-diversity test. |
| Best quote contains unresolved PII | Exclude it, even if it is highly representative. | PII quote selection test. |
| Action is vague, unsupported, or unrelated to a top theme | Reject/regenerate; require linked theme/evidence IDs and concrete next step. | Action-grounding test. |
| Action makes a delivery date, policy change, or product commitment | Reject it unless supplied as an approved structured fact. | Unsupported-commitment test. |

## LangChain Chains and Model Boundary

| Case | Expected Behavior | Test / Verification |
| --- | --- | --- |
| LangChain model provider or model ID is missing | Reject configuration before invoking an LCEL chain. | Model configuration test. |
| Provider returns a timeout, rate limit, or transient error | Retry within the configured budget; use the deterministic baseline for analysis when available, otherwise fail before composition/delivery. | Fake-model retry/fallback test. |
| Provider is unavailable during pulse composition | Mark run `failed`; do not publish a pulse assembled from incomplete model output. | Pulse-chain outage test. |
| `with_structured_output` returns malformed, incomplete, or extra fields | Reject schema validation failure; retry only through the defined correction path or fail the stage. | Pydantic structured-output contract test. |
| Model returns theme/action counts outside contract | Reject before deterministic ranking/composition; no Docs or Gmail call may occur. | Cardinality contract test. |
| Model returns a source review ID absent from sanitized input | Reject output as ungrounded; never resolve evidence from raw data. | Unknown-evidence-ID test. |
| Model repeats PII supplied in a redacted placeholder or invents PII | Final PII validator rejects output and excludes/regenerates unsafe content. | Model PII-leakage test. |
| Prompt asset is missing, empty, or changed without a version | Fail startup or deployment validation; do not use an implicit default prompt. | Prompt registry/version test. |
| Prompt template variables do not match provided LCEL input | Fail chain construction before a run; expose no review content in the error. | Template-variable contract test. |
| LCEL batch contains an unsafe/raw review due to wiring defect | Block model invocation and fail the privacy boundary. | Chain-input object-shape test. |
| LCEL batch exceeds configured size/concurrency or context budget | Split into bounded batches, preserve source IDs, and fail safely if a complete analysis cannot be produced. | Batch-limit and context-overflow test. |
| LangChain callback/tracing exports prompts or outputs | Disable it by default; permit only approved sanitized, retention-limited telemetry. | Callback configuration and log-scan test. |
| Provider/model changes between retry attempts | Freeze prompt version and model identifier in the run record; require an explicit new run/version to change them. | Model-drift retry test. |
| Chain is given a Docs/Gmail tool or sending capability | Reject chain construction; only `McpPublisher` may invoke MCP delivery after validation. | Tool allowlist test. |

## Pulse Composition and Validation

| Case | Expected Behavior | Test / Verification |
| --- | --- | --- |
| Rendered note is 250 words | Accept if all other validators pass. | Exact-boundary test. |
| Rendered note is 251 words | Reject and regenerate/shorten summaries/actions; do not truncate quotes. | Exact-boundary test. |
| Word counter differs between Markdown and plain text | Count the stakeholder-visible rendered form using one canonical implementation. | Cross-renderer count test. |
| Required section is absent or renamed | Reject output before any MCP operation. | Required-section tests. |
| Count differs from exactly three themes, quotes, or actions | Reject output before delivery. | Cardinality tests. |
| Theme summary claims a metric not in computed statistics | Reject/regenerate based on structured source data. | Hallucinated-metric test. |
| Quote is modified by Markdown escaping/normalization | Validate rendered quote against sanitized source after approved escaping rules. | Quote-rendering test. |
| Markdown text breaks table/list/heading layout | Escape review-derived markdown and render through a safe formatter. | Markdown-injection fixture test. |
| Generated text exposes author identity or PII | Reject output, exclude offending evidence, and rerun selection/composition. | Final-output PII test. |
| Duplicate quote/action is generated | Reject duplicates and select/regenerate alternatives. | Duplicate-content test. |
| Output validator itself fails unexpectedly | Mark run `failed`; no artifact is delivered. | Validator exception test. |

## Google Docs and Gmail Delivery Through MCP

| Case | Expected Behavior | Test / Verification |
| --- | --- | --- |
| Docs MCP tool unavailable | Fail delivery after safe retries; preserve validated pulse and do not call Gmail. | Tool-unavailable test. |
| Gmail MCP tool unavailable after Doc success | Retain document ID/URL and retry only draft creation. | Partial-delivery retry test. |
| MCP returns an authentication/authorization error | Mark run `failed` with non-sensitive error; do not attempt direct OAuth/REST fallback. | Permission-error test. |
| MCP invocation times out with unknown result | Query/reconcile through permitted MCP capabilities or use idempotency key; do not blindly create duplicates. | Timeout reconciliation test. |
| Docs create succeeds but response is lost | Reuse deterministic run/week identity or search/update existing artifact through MCP before retrying create. | Lost-response test. |
| Document update targets wrong week | Validate stored week-ending metadata/title before update; create the correct artifact when mismatch is detected. | Wrong-document test. |
| Stored document ID is deleted or inaccessible | Create a replacement document, update run record, then draft email using replacement URL. | Stale-document test. |
| Gmail draft create succeeds but response is lost | Reconcile with a run idempotency marker in the subject/body; do not produce duplicate drafts. | Lost-draft-response test. |
| Recipient alias changes between retries | Freeze recipient on run creation; require a new run or explicit operator override. | Config-drift retry test. |
| Email body and Google Doc differ | Build both from the same validated `WeeklyPulse`; validate shared content hash/version. | Content-parity test. |
| Email tool offers send operation | Use only a draft-creation capability; fail configuration if draft-only control is unavailable. | Permission/capability test. |
| MCP response includes sensitive metadata | Sanitize before persistence/logging; keep only document ID/URL and draft ID. | Response-redaction test. |

## Recovery, Auditing, and Release

| Case | Expected Behavior | Test / Verification |
| --- | --- | --- |
| Process crashes between stages | Resume from last committed safe stage using the run record. | Crash/restart integration test. |
| Process crashes after document ID persistence | Resume at Gmail draft creation without recollection or duplicate document creation. | Checkpoint recovery test. |
| Re-run uses changed analysis logic, LangChain model, or prompt version | Create a new run/version or explicitly mark replacement lineage; do not overwrite audit evidence silently. | Version-lineage test. |
| Operator requests replay of a completed week | Require explicit backfill/replay flag and preserve prior document/draft IDs in history. | Replay audit test. |
| Logs are forwarded to third-party monitoring | Enforce the same no-raw-review/no-PII logging policy and test logging adapters. | Telemetry redaction test. |
| Alert contains review text or recipient identity | Emit run ID, stage, counts, and error class only. | Alert-content test. |
| A source/compliance policy changes | Disable affected collector adapter by allowlist/config until re-approved. | Adapter allowlist test. |
| Staging accidentally points to production recipient | Require environment-specific recipient allowlist and a dry-run/draft-only safety check. | Environment guard test. |

## Minimum Regression Suite

Before every release, run fixtures that cover: empty collection; cutoff boundaries; duplicates; malformed and multilingual text; PII variants; prompt injection; six themes; low-volume reviews; quote provenance; 250/251-word output; malformed LangChain structured output; prompt/template failures; callback/tracing controls; model outage/fallback; Docs failure; Gmail failure after Docs success; idempotent retry; and crash recovery. The release gate passes only when all invalid-content cases produce no document or Gmail draft.