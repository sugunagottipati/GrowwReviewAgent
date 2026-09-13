# Phase 6 Operations Runbook

## Overview

This runbook provides step-by-step procedures for operating the Groww Weekly Review Pulse system in production. It covers setup, execution, monitoring, troubleshooting, and recovery procedures.

**System Version**: Phase 6 (Orchestration & Scheduling)
**Last Updated**: 2026-01-14
**Owner**: Groww Data & Insights Team

---

## Table of Contents

1. [Pre-Production Setup](#pre-production-setup)
2. [Manual Execution](#manual-execution)
3. [Scheduled Execution](#scheduled-execution)
4. [Monitoring & Observability](#monitoring--observability)
5. [Failure Scenarios & Recovery](#failure-scenarios--recovery)
6. [Blocked Run Triage](#blocked-run-triage)
7. [Runbook Examples](#runbook-examples)

---

## Pre-Production Setup

### 1. Environment Configuration

Create a `.env` file in the project root with the following variables:

```bash
# Google Docs Configuration (pre-created document)
EXISTING_GOOGLE_DOC_ID="1a2b3c4d5e6f7g8h9i0j1k2l3m4n5o6p"

# Gmail Configuration
RECIPIENT_ALIAS="pulse-subscribers@groww.in"

# Scheduling
SCHEDULE_ENABLED=true
SCHEDULE_DAY_OF_WEEK=0  # Monday
SCHEDULE_HOUR=9
SCHEDULE_MINUTE=0
SCHEDULE_TIMEZONE="Asia/Kolkata"

# Review Collection
LOOKBACK_WEEKS=8  # Default: 8-12 weeks
BATCH_SIZE=25  # Reviews per LLM analysis batch

# Model Configuration
MODEL_PROVIDER="groq"  # or "openai" / "fake" for testing
MODEL_ID="mixtral-8x7b-32768"
MODEL_TEMPERATURE=0.0
MODEL_TIMEOUT_SEC=60

# Storage
STORAGE_PATH="/var/lib/groww/pulse_runs.db"

# Logging
LOG_LEVEL="INFO"
DRY_RUN=false
```

### 2. Create Pre-requisite Google Doc

The system uses **append-only** Docs delivery (MCP constraint):

1. Create a new Google Doc in Groww's shared drive
2. Title: "Groww Weekly Review Pulse - Master"
3. Copy the document ID from the URL:
   ```
   https://docs.google.com/document/d/{DOCUMENT_ID}/edit
   ```
4. Share document with MCP service account (read+write permissions)
5. Add document ID to environment as `EXISTING_GOOGLE_DOC_ID`

### 3. Validate MCP Server Configuration

Before production deployment, verify MCP servers are running:

```bash
# Test Google Docs MCP server
curl -X POST http://localhost:3000/mcp/invoke \
  -H "Content-Type: application/json" \
  -d '{
    "server": "google_docs",
    "tool": "google_docs_append_content",
    "arguments": {
      "documentId": "'"$EXISTING_GOOGLE_DOC_ID"'",
      "content": "[Test] Pulse system initialized",
      "addNewline": true
    }
  }'

# Test Gmail MCP server
curl -X POST http://localhost:3000/mcp/invoke \
  -H "Content-Type: application/json" \
  -d '{
    "server": "gmail",
    "tool": "gmail_create_draft",
    "arguments": {
      "to": ["pulse-subscribers@groww.in"],
      "subject": "[Test] MCP Gmail Configuration",
      "body": "This is a test email to verify MCP Gmail integration."
    }
  }'
```

### 4. Initialize Database

```bash
python -m groww_pulse.orchestration.cli validate

# Output should show:
# ✓ Configuration loaded successfully
# ✓ Storage path configured
# ✓ Model factory initialized
# ✓ Versioned prompt templates verified
# ✓ All configuration and component contracts are VALID
```

---

## Manual Execution

### Single Run (Dry-Run Mode)

For testing without calling external APIs:

```bash
python -m groww_pulse.orchestration.cli run \
  --dry-run \
  --weeks 8 \
  --week-ending 2026-01-14
```

**Expected output**:
```
Starting Groww Review Pulse run (dry_run=True, lookback_weeks=8)...
Run ID: run_08cde04f107f
Status: completed
Reviews Processed: 5

Document ID: fake_doc_12345
Gmail Draft ID: fake_draft_xyz789

--- Pulse Markdown ---
## Groww Weekly Review Pulse - Week Ending 2026-01-14
...
```

### Single Run (Production Mode)

For live review collection and MCP delivery:

```bash
# Must provide existing_document_id
python -m groww_pulse.orchestration.cli test-schedule \
  --doc-id $EXISTING_GOOGLE_DOC_ID

# Alternative with explicit parameters
python -m groww_pulse.orchestration.cli run \
  --weeks 8 \
  --week-ending 2026-01-14
```

**What happens**:
1. Stage 1: Collects reviews from Google Play Store (last 8 weeks)
2. Stage 2: Sanitizes PII and applies quality filters
3. Stage 3: Persists reviews to SQLite database
4. Stage 4: Analyzes themes using LLM (Groq mixtral-8x7b)
5. Stage 5: Selects top 3 quotes and recommended actions
6. Stage 6: Composes markdown pulse report
7. Stage 7: Validates pulse (word count ≤250)
8. Stage 8: Appends to Google Doc via MCP
9. Stage 9: Creates Gmail draft via MCP

### Backfill Multiple Periods

```bash
python -m groww_pulse.orchestration.cli backfill \
  --weeks 12 \
  --dry-run \
  --week-ending 2026-01-14
```

This executes the full pipeline in dry-run mode for historical analysis.

---

## Scheduled Execution

### Start Weekly Scheduler (Background Daemon)

```bash
# Start background scheduler for Monday 09:00 Asia/Kolkata
python -m groww_pulse.orchestration.cli schedule \
  --day-of-week 0 \
  --hour 9 \
  --minute 0

# Output:
# Starting background scheduler (day=0, hour=9:0)...
# ✓ Scheduler started. Next run: 2026-01-20 09:00:00 (Asia/Kolkata)
# (Press Ctrl+C to stop)
```

### Supervisor/Systemd Integration

For persistent background execution, create a systemd service:

**File**: `/etc/systemd/system/groww-pulse-scheduler.service`

```ini
[Unit]
Description=Groww Weekly Review Pulse Scheduler
After=network.target

[Service]
Type=simple
User=groww
WorkingDirectory=/opt/groww/review-pulse
Environment="PYTHONUNBUFFERED=1"
Environment="EXISTING_GOOGLE_DOC_ID=1a2b3c4d5e6f7g8h9i0j1k2l3m4n5o6p"
Environment="RECIPIENT_ALIAS=pulse-subscribers@groww.in"
EnvironmentFile=/etc/groww/pulse.env
ExecStart=/usr/bin/python -m groww_pulse.orchestration.cli schedule --day-of-week 0 --hour 9 --minute 0
Restart=always
RestartSec=60
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

**Enable and start**:

```bash
sudo systemctl daemon-reload
sudo systemctl enable groww-pulse-scheduler
sudo systemctl start groww-pulse-scheduler

# Monitor logs
sudo journalctl -u groww-pulse-scheduler -f
```

---

## Monitoring & Observability

### View Recent Runs

```bash
# Query SQLite database for recent runs
sqlite3 /var/lib/groww/pulse_runs.db <<EOF
SELECT 
  id, 
  status, 
  started_at, 
  completed_at, 
  review_count, 
  document_id, 
  error_summary
FROM runs
ORDER BY started_at DESC
LIMIT 10;
EOF
```

### Live Log Monitoring

The system uses structured JSON logging (newline-delimited JSON, NDJSON):

```bash
# Follow live logs with filtering
tail -f /var/log/groww/pulse.log | jq '.event'

# Filter by severity
tail -f /var/log/groww/pulse.log | jq 'select(.level=="ERROR")'

# Filter by run_id
RUN_ID="run_08cde04f107f"
tail -f /var/log/groww/pulse.log | jq "select(.run_id==\"$RUN_ID\")"
```

### Key Metrics

Monitor these metrics in production dashboards:

| Metric | Threshold | Action |
|--------|-----------|--------|
| **Collection success rate** | < 90% | Investigate API quota/timeout issues |
| **Theme analysis success** | < 95% | Check LLM model availability |
| **Delivery success** | < 100% | Verify MCP server uptime |
| **Average run duration** | > 120s | Profile bottleneck stage |
| **Word count validation** | 100-250 | Monitor pulse quality |

### Sample Structured Log Entry

```json
{
  "timestamp": "2026-01-14T09:15:30+05:30",
  "level": "INFO",
  "event": "stage_completed:delivery",
  "run_id": "run_08cde04f107f",
  "stage": "delivery",
  "status": "success",
  "duration_ms": 0.09,
  "document_id": "mcp_doc_12345",
  "gmail_draft_id": "mcp_draft_xyz789"
}
```

---

## Failure Scenarios & Recovery

### Scenario 1: Collection Timeout (Google Play API)

**Symptoms**:
```
TimeoutError: Request to Google Play Store API exceeded 60 seconds
```

**Root Causes**:
- Google Play API is slow or throttling
- Network latency to Google
- Review batch size too large

**Recovery Steps**:

1. Check Google Play API status:
   ```bash
   # Manually test with smaller batch
   curl -X POST http://google-play-api/reviews \
     -d '{"app_id": "com.nextbillion.groww", "batch_size": 10}'
   ```

2. Retry with extended timeout:
   ```bash
   # Increase timeout temporarily
   export MODEL_TIMEOUT_SEC=90
   python -m groww_pulse.orchestration.cli test-schedule \
     --doc-id $EXISTING_GOOGLE_DOC_ID
   ```

3. Reduce batch size if issue persists:
   ```bash
   # Edit environment
   BATCH_SIZE=10  # Reduced from 25
   ```

4. If repeatedly failing, escalate to Google Play team

**Prevention**:
- Monitor collection latency in metrics
- Set alert if avg collection time > 30s
- Implement exponential backoff retry (already configured)

---

### Scenario 2: LLM Theme Analysis Fails

**Symptoms**:
```
RuntimeError: Groq API rate limit exceeded
```

**Root Causes**:
- LLM rate limit hit (too many concurrent requests)
- LLM model overloaded
- LLM API authentication expired

**Recovery Steps**:

1. Check LLM API status:
   ```bash
   curl -H "Authorization: Bearer $GROQ_API_KEY" \
     https://api.groq.com/health
   ```

2. Retry manually with fallback:
   ```bash
   # Force baseline classifier (no LLM call)
   export MODEL_PROVIDER="fake"
   python -m groww_pulse.orchestration.cli test-schedule
   ```

3. If using fallback, pulse will include:
   ```
   **Note**: Themes classified using baseline model (LLM unavailable)
   ```

4. Re-run after rate limit window (typically 1 hour)

**Prevention**:
- Set up LLM request rate alerts
- Monitor `theme_analysis` stage duration
- Use fallback classifier during high-load periods

---

### Scenario 3: MCP Delivery Fails

**Symptoms**:
```
MCPToolError: MCP docs append returned incomplete response
```

**Root Causes**:
- MCP server is down
- Google Docs API permissions insufficient
- Document ID is invalid or deleted
- Network connectivity issue

**Recovery Steps**:

1. Verify MCP server is running:
   ```bash
   curl http://localhost:3000/health
   # Expected: {"status": "ok"}
   ```

2. Validate document ID still exists:
   ```bash
   curl -H "Authorization: Bearer $GOOGLE_SERVICE_ACCOUNT_TOKEN" \
     "https://docs.googleapis.com/v1/documents/$EXISTING_GOOGLE_DOC_ID"
   ```

3. Test append manually:
   ```bash
   curl -X POST http://localhost:3000/mcp/invoke \
     -H "Content-Type: application/json" \
     -d '{
       "server": "google_docs",
       "tool": "google_docs_append_content",
       "arguments": {
         "documentId": "'$EXISTING_GOOGLE_DOC_ID'",
         "content": "[Recovery Test]",
         "addNewline": true
       }
     }'
   ```

4. If test succeeds, re-run the pulse:
   ```bash
   python -m groww_pulse.orchestration.cli test-schedule \
     --doc-id $EXISTING_GOOGLE_DOC_ID
   ```

5. If MCP server is down, restart it:
   ```bash
   # Assuming Docker container
   docker restart groww-mcp-server
   
   # Verify startup
   sleep 5
   curl http://localhost:3000/health
   ```

**Prevention**:
- Set up MCP server health check (every 5 min)
- Use a load balancer in front of MCP server
- Set alert if MCP server is unreachable for > 2 min

---

### Scenario 4: Insufficient Reviews for Pulse

**Symptoms**:
```
Status: blocked
Rejection reason: Insufficient safe reviews to generate pulse (found 2, minimum required is 3)
```

**Root Causes**:
- Review collection period has < 3 reviews
- Privacy filter rejected too many reviews (PII detected)
- Quality filter rejected too many reviews (too short, non-English)

**Recovery Steps**:

1. Check review statistics:
   ```bash
   sqlite3 /var/lib/groww/pulse_runs.db <<EOF
   SELECT status, COUNT(*) FROM reviews GROUP BY status;
   EOF
   ```

2. If low collection: Increase lookback window:
   ```bash
   export LOOKBACK_WEEKS=12
   python -m groww_pulse.orchestration.cli run --weeks 12
   ```

3. If privacy/quality filter too aggressive:
   ```bash
   # Review filter settings
   # Lower minimum word count threshold temporarily
   # Re-run will re-process with new thresholds
   ```

4. If still insufficient after 12 weeks, escalate:
   - Check if app has active reviews
   - Verify review collection API has access
   - Contact Play Store team

**Prevention**:
- Monitor review collection rate weekly
- Alert if weekly reviews < 10
- Alert if privacy filter rejection rate > 50%

---

## Blocked Run Triage

When a run status is `BLOCKED`, use this checklist:

```yaml
Blocked Run Triage Checklist:
├─ 1. Retrieve error_summary
│   └─ Query: SELECT error_summary FROM runs WHERE status='BLOCKED'
│
├─ 2. Classify block type
│   ├─ "Insufficient safe reviews" → Increase lookback_weeks
│   ├─ "Validation failed" → Check pulse markdown (word count, formatting)
│   ├─ "Privacy filter" → Review settings
│   └─ "Other" → Check logs for details
│
├─ 3. Determine recovery path
│   ├─ Fixable by settings change → Update ENV and retry
│   ├─ Fixable by manual action → Document and escalate
│   └─ Informational → Log and monitor
│
└─ 4. Document in incident tracker
    └─ Include: run_id, timestamp, error, action taken
```

### Triage Example

```bash
#!/bin/bash
# Triage last blocked run

RUN=$(sqlite3 /var/lib/groww/pulse_runs.db \
  "SELECT id, status, error_summary FROM runs 
   WHERE status='BLOCKED' 
   ORDER BY started_at DESC LIMIT 1")

echo "Blocked Run Analysis:"
echo "ID: $(echo $RUN | cut -d'|' -f1)"
echo "Status: $(echo $RUN | cut -d'|' -f2)"
echo "Error: $(echo $RUN | cut -d'|' -f3)"

# Recommend action based on error
ERROR=$(echo $RUN | cut -d'|' -f3)

if [[ $ERROR == *"Insufficient"* ]]; then
  echo "RECOMMENDATION: Increase LOOKBACK_WEEKS to 12"
fi

if [[ $ERROR == *"Validation"* ]]; then
  echo "RECOMMENDATION: Check pulse markdown for formatting/length issues"
fi
```

---

## Runbook Examples

### Example 1: Emergency Run (Override Scheduler)

Scenario: Need to generate pulse immediately outside regular schedule.

```bash
# Execute manual run
python -m groww_pulse.orchestration.cli test-schedule \
  --doc-id $EXISTING_GOOGLE_DOC_ID

# Monitor execution
tail -f /var/log/groww/pulse.log | jq '.event'
```

### Example 2: Test Configuration Before Production

```bash
# Run in dry-run mode with small backfill
python -m groww_pulse.orchestration.cli backfill \
  --dry-run \
  --weeks 8 \
  --week-ending 2026-01-14

# If successful, run validation
python -m groww_pulse.orchestration.cli validate

# If validation passes, schedule production run
python -m groww_pulse.orchestration.cli schedule \
  --day-of-week 0 \
  --hour 9 \
  --minute 0
```

### Example 3: Debug a Failed Run

```bash
#!/bin/bash
# Get details for a specific run

RUN_ID="run_08cde04f107f"

echo "=== Run Details ==="
sqlite3 /var/lib/groww/pulse_runs.db \
  "SELECT id, status, started_at, completed_at, review_count, error_summary 
   FROM runs WHERE id = '$RUN_ID';"

echo -e "\n=== Structured Logs for Run ==="
grep "$RUN_ID" /var/log/groww/pulse.log | jq '.'

echo -e "\n=== Reviews Processed ==="
sqlite3 /var/lib/groww/pulse_runs.db \
  "SELECT COUNT(*) FROM reviews WHERE run_id = '$RUN_ID';"
```

### Example 4: Restart Scheduler After Maintenance

```bash
# Check if scheduler is running
systemctl status groww-pulse-scheduler

# If not running, start it
sudo systemctl start groww-pulse-scheduler

# Verify it's running and logs are flowing
sudo journalctl -u groww-pulse-scheduler -n 50 -f
```

---

## Escalation & Support

### When to Escalate

| Issue | Escalation Path | SLA |
|-------|-----------------|-----|
| Repeated collection failures | Google Play Team | 2h |
| LLM repeatedly timing out | Groq Support | 1h |
| MCP server crashes | Platform/Infrastructure | CRITICAL |
| > 50% runs blocked | Product Team | 4h |
| Gmail drafts not created | Gmail/MCP Team | 2h |

### Support Contact Matrix

```
Collection Issues → playstore-support@groww.in
LLM/AI Issues → ai-platform@groww.in  
MCP/Infrastructure → platform-ops@groww.in
Gmail Integration → workspace-admin@groww.in
Data/Analytics → data-team@groww.in
```

---

## Appendix: Configuration Reference

### Environment Variables

```bash
# Deployment
EXISTING_GOOGLE_DOC_ID=      # Pre-created Google Doc ID
RECIPIENT_ALIAS=              # Email alias for Gmail drafts

# Schedule (if using APScheduler daemon)
SCHEDULE_DAY_OF_WEEK=0        # 0=Monday, 6=Sunday
SCHEDULE_HOUR=9               # 0-23
SCHEDULE_MINUTE=0             # 0-59
SCHEDULE_TIMEZONE=Asia/Kolkata

# Collection
LOOKBACK_WEEKS=8              # 8-12 weeks
BATCH_SIZE=25                 # Reviews per LLM batch

# Model
MODEL_PROVIDER=groq           # groq, openai, fake
MODEL_ID=mixtral-8x7b-32768
MODEL_TEMPERATURE=0.0
MODEL_TIMEOUT_SEC=60

# Storage
STORAGE_PATH=/var/lib/groww/pulse_runs.db

# Logging
LOG_LEVEL=INFO
DRY_RUN=false
```

### Database Schema

```sql
-- Runs table
CREATE TABLE runs (
  id TEXT PRIMARY KEY,
  status TEXT,           -- RUNNING, COMPLETED, BLOCKED, FAILED
  started_at TIMESTAMP,
  completed_at TIMESTAMP,
  review_count INTEGER,
  document_id TEXT,
  document_url TEXT,
  gmail_draft_id TEXT,
  error_summary TEXT
);

-- Reviews table
CREATE TABLE reviews (
  id TEXT PRIMARY KEY,
  run_id TEXT,
  rating INTEGER,
  title TEXT,
  text TEXT,
  reviewed_at TIMESTAMP,
  status TEXT,           -- ACCEPTED, REDACTED, REJECTED
  reason TEXT            -- Why rejected (too_short, non_english, etc.)
);
```

---

**End of Runbook**

For updates or corrections, contact: data-team@groww.in
