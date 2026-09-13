# Phase 6: End-to-End Orchestration and Scheduling

## Summary

Phase 6 completes the GrowwReviewAgent implementation with reliable weekly scheduling, run summary reporting, alert handling, and production-ready MCP integration.

## Completed Features

### 1. MCP Adapter Refinement (GoogMcpServer Compliance)
- **MCPDocsAdapter**: Append-only document operations via `google_docs_append_content` tool
  - Requires pre-created Google Doc ID (external creation needed)
  - Appends markdown content to existing document
  - Returns document ID and sharable URL
  - Error handling for append failures
  
- **MCPGmailAdapter**: Draft creation via `gmail_create_draft` tool
  - Creates unsent Gmail drafts
  - Supports `cc`, `bcc`, HTML formatting
  - Returns draft ID (never sends)
  - Idempotency support via optional `idempotencyKey`

- **Schema Compliance**:
  - Docs tool: `{success: bool, documentId: string, appendedCharacters: number}`
  - Gmail tool: `{success: bool, draftId: string, messageId: string, threadId: string}`
  - Error responses: `{success: false, error: {code, message, retryable, providerStatus}}`
  - All 11 unit tests passing

### 2. RunSummary & Reporting
```python
@dataclass
class RunSummary:
    """Operator-friendly run completion summary"""
    run_id: str
    status: RunStatus  # COMPLETED, BLOCKED, FAILED, IN_PROGRESS
    started_at: datetime
    completed_at: datetime | None
    review_count: int
    selected_theme_labels: list[str]  # Top 3 themes
    document_id: str | None
    document_url: str | None
    gmail_draft_id: str | None
    error_summary: str | None
    
    def operator_message() -> str:
        """Human-readable summary with emoji indicators"""
```

### 3. AlertHandler
- Sends alerts for failed/blocked runs
- Supports multiple channels: 'log', 'slack', 'email' (placeholder)
- Configurable enable/disable
- Safe logging (no sensitive data)

### 4. Scheduler Integration
Two scheduler implementations:

**RunScheduler (Background)** - APScheduler-based
```python
scheduler = RunScheduler(
    orchestrator=orchestrator,
    day_of_week="0",  # Monday
    hour=9,
    minute=0
)
scheduler.start()  # Runs in background
next_run = scheduler.get_next_run_time()
scheduler.stop()
```

**SimpleScheduler (CLI-based)** - No external dependencies
```python
scheduler = SimpleScheduler(...)
if scheduler.should_run():
    run, pulse = orchestrator.execute_run()
```

### 5. Orchestrator Enhancement
Updated `execute_run()` to support production MCP delivery:
```python
run, pulse = orchestrator.execute_run(
    week_ending=date(2025, 8, 31),
    existing_document_id="doc_1a2b3c4d5e6f",  # Required for MCP production
    override_raw_reviews=None  # Optional: for testing
)
```

### 6. CLI Integration
New commands for production operations:

**schedule** - Start background scheduler
```bash
groww-pulse schedule \
  --day-of-week 0 \
  --hour 9 \
  --minute 0 \
  --doc-id "google_doc_id" \
  --dry-run false
```

**test-schedule** - Single scheduled run
```bash
groww-pulse test-schedule \
  --doc-id "google_doc_id" \
  --dry-run false
```

## Architecture

```
┌─────────────────────────────────────────┐
│         CLI Entry Points                │
│  run | validate | schedule | test-sch   │
└────────────────┬────────────────────────┘
                 │
        ┌────────▼────────┐
        │  RunOrchestrator │
        └────────┬────────┘
                 │
         ┌───────┴──────────┐
         │                  │
    ┌────▼────┐      ┌─────▼──────┐
    │RunSched  │      │RunSummary  │
    │uler      │      │AlertHandler│
    └─────────┘      └────────────┘
         │
         └─────────────────┐
                          │
              ┌───────────▼────────────┐
              │  Stage 6: MCP Delivery │
              └───────────┬────────────┘
                          │
        ┌─────────────────┼─────────────────┐
        │                 │                 │
   ┌────▼─────┐   ┌──────▼──────┐   ┌─────▼────┐
   │MCPDocs   │   │MCPGmail     │   │ToolCaller│
   │Adapter   │   │Adapter      │   │(HTTP/MCP)│
   └──────────┘   └─────────────┘   └──────────┘
```

## Operation Flow

### Production Weekly Run

1. **Scheduler triggers** at configured time (e.g., Monday 09:00)
2. **Orchestrator.execute_run()** called with `existing_document_id`
3. **Stages 1-5** execute (collection through composition)
4. **Stage 6 (Delivery)**:
   - Pre-validation: check that `existing_document_id` provided
   - Call `MCPDocsAdapter.create_or_update_document()` → appends to existing Doc
   - Call `MCPGamailAdapter.create_draft()` → creates draft
   - Store IDs in Run record (idempotent)
5. **RunSummary** generated with operation results
6. **Alerts sent** if run failed/blocked
7. **CLI displays** operator message with URLs and draft ID

### Dry-Run Mode

```bash
groww-pulse test-schedule --dry-run true
```

- Uses `FakeDocsPort` and `FakeGmailPort` (no MCP calls)
- Simulates delivery locally
- Useful for testing full pipeline without external dependencies

## Production Setup Checklist

### Before First Production Run

- [ ] Create weekly Google Doc externally (or via GDocs API)
- [ ] Share Doc with service account email (MCP OAuth credentials)
- [ ] Get Document ID from Doc URL: `https://docs.google.com/document/d/{DOC_ID}/edit`
- [ ] Verify MCP OAuth scopes include `https://www.googleapis.com/auth/documents` and `https://www.googleapis.com/auth/gmail.compose`
- [ ] Test single run: `groww-pulse test-schedule --doc-id "YOUR_DOC_ID"`
- [ ] Verify document updated and draft created
- [ ] Configure AlertHandler for failure notifications
- [ ] Review operator_message() output format
- [ ] Start scheduler: `groww-pulse schedule --doc-id "YOUR_DOC_ID" --day-of-week 0 --hour 9`

### Production Delivery Contract

```
Input:
  - existing_document_id: str (required, no create)
  - pulse.markdown: str (content to append)
  - recipient_alias: str (from settings)

Output:
  - run.document_id: str (same as input)
  - run.document_url: str (constructed from document_id)
  - run.gmail_draft_id: str (created draft, not sent)

Guarantees:
  - Append-only (never creates new docs)
  - Draft-only (never sends emails)
  - Idempotent (same pulse.markdown appends on retry)
  - No direct Google API calls (MCP-mediated)
```

## Error Handling

### Retryable Errors
- `RATE_LIMITED`: Exponential backoff (scheduler will retry next week)
- `PROVIDER_ERROR`: Transient issue (retry next scheduled run)
- `TIMEOUT`: Network timeout (future run will attempt again)
- HTTP 5xx: Server error (retry on next cycle)

### Permanent Errors
- `AUTHENTICATION_REQUIRED`: Invalid MCP credentials
- `AUTHORIZATION_DENIED`: Missing scopes for document
- `RESOURCE_NOT_FOUND`: Document ID doesn't exist (provide valid pre-created Doc)
- `INVALID_INPUT`: Malformed markdown or email addresses
- `CONFLICT`: Document/draft state conflict

### Error Recovery
1. RunSummary.error_summary captured
2. AlertHandler notifies operator
3. Run marked as FAILED or BLOCKED
4. Operator reviews error_summary
5. Operator corrects (e.g., provide new doc ID)
6. Run can be retried with `groww-pulse test-schedule --doc-id "new_doc_id"`

## Testing

### Unit Tests (11/11 passing)
```bash
pytest tests/unit/test_mcp_adapters.py -v
```

- Docs adapter: append, missing doc ID, error handling, custom server names
- Gmail adapter: draft creation, missing draft ID, error handling, custom server names
- MCPToolError exception handling

### Integration Tests
```bash
pytest tests/integration/test_mcp_delivery.py -v
```

- E2E orchestrator with mock tool_caller
- Dry-run mode verification
- Alert generation

### Manual Validation
```bash
# Validate configuration
groww-pulse validate

# Test single run
groww-pulse test-schedule --doc-id "test_doc_id" --dry-run true

# Run single cycle with real MCP
groww-pulse test-schedule --doc-id "production_doc_id" --dry-run false

# Start scheduler
groww-pulse schedule --doc-id "production_doc_id" --dry-run false
```

## Configuration Reference

### Environment Variables
```bash
GROWW_APP_ID="com.nextbillion.groww"
GROWW_LOOKBACK_WEEKS=8
GROWW_DRY_RUN=false
GROWW_MODEL_ID="gpt-4o-mini"
GROWW_RECIPIENT_ALIAS="team@groww.in"
GROWW_STORAGE_PATH="./data/runs.db"
```

### CLI Arguments

**schedule command:**
- `--day-of-week`: 0-6 (Monday-Sunday, default: 0)
- `--hour`: 0-23 (default: 9)
- `--minute`: 0-59 (default: 0)
- `--doc-id`: Google Doc ID (required for production)
- `--dry-run`: boolean (default: false)

**test-schedule command:**
- `--doc-id`: Google Doc ID
- `--dry-run`: boolean (default: false)

## Limitations & Future Work

### Current Limitations
1. **Append-only Docs**: Cannot update existing content (by design)
2. **Draft-only Gmail**: Cannot send messages directly (by design)
3. **No rescheduling**: Failed runs don't auto-retry (operator must manually rerun)
4. **Single scheduler process**: No distributed scheduling

### Future Enhancements
1. Add exponential backoff retry logic for transient errors
2. Support multiple recipients (CC/BCC expansion)
3. Add run history and analytics dashboard
4. Implement scheduled retry queue
5. Support distributed scheduling (Kubernetes cron)
6. Add webhook integration for external run triggering
7. Document versioning (append with "Week N" markers)

## Troubleshooting

### "Production delivery requires existing_document_id"
**Solution**: Pass `--doc-id` or provide `existing_document_id` to `execute_run()`

### "MCP gmail create_draft returned no draftId"
**Solution**: Check MCP server OAuth permissions, verify recipient email valid

### "MCP docs append returned incomplete response"
**Solution**: Verify document ID is valid and shared with MCP service account

### AlertHandler not sending alerts
**Solution**: Set `AlertHandler(enabled=True, channel='log')` in handle_test_schedule()

### Scheduler not triggering at expected time
**Solution**: Verify system timezone, check `scheduler.get_next_run_time()`, review logs

## References

- GoogMcpServer: https://github.com/sugunagottipati/GoogMcpServer
- APScheduler: https://apscheduler.readthedocs.io/
- Google Docs API: https://developers.google.com/docs
- Gmail API: https://developers.google.com/gmail
