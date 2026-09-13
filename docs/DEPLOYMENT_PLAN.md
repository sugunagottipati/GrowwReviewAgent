# Phased Deployment Plan: Railway Backend and Vercel Frontend

## Current Deployment Shape

The repository currently has two deployable surfaces:

- **Backend:** Python 3.11+ package exposed through the `groww-pulse` CLI. It can validate configuration, run the review pulse pipeline, backfill data, and run a long-lived weekly scheduler.
- **Frontend:** Static files in `frontend/` (`index.html`, `styles.css`, `app.js`). The UI currently uses representative fixture data and does not call a backend API.

This means the first production deployment should treat Railway as a backend worker/scheduler host. If the frontend must show live pulse data, add a small HTTP API phase before connecting Vercel to Railway.

---

## Phase 0: Pre-Deployment Readiness

**Goal:** Confirm what will run in production and remove ambiguity before touching cloud environments.

### Decisions

1. Choose backend mode for Railway:
   - **Worker-only MVP:** Railway runs scheduled `groww-pulse` jobs that collect reviews, generate pulses, update Google Docs, and create Gmail drafts.
   - **API + worker:** Railway also exposes HTTP endpoints for the Vercel frontend to fetch live pulse data.
2. Choose persistence strategy:
   - Railway volume with SQLite for MVP.
   - Managed Postgres for a more durable multi-instance production setup.
3. Confirm MCP deployment model:
   - MCP servers reachable from Railway over HTTP/JSON-RPC, or
   - MCP tool caller implemented in-process if the MCP runtime supports hosted credentials.
4. Confirm LLM provider and model:
   - `openai`, `groq`, `gemini`, or `fake` for staging.

### Checks

Run locally before creating cloud services:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
groww-pulse validate
groww-pulse run --dry-run --weeks 8
pytest
ruff check .
mypy src tests
```

### Exit Criteria

- Local validation passes.
- Dry run completes successfully.
- Required production secrets are known and owned.
- Backend mode is selected: worker-only or API + worker.

---

## Phase 1: Backend Packaging for Railway

**Goal:** Make the Python backend start reliably on Railway.

### Required Code Readiness Items

Before using Railway for live production delivery, close these backend gaps:

1. Add any runtime-only scheduler dependencies to `pyproject.toml`. The scheduler imports `apscheduler`, so the Railway install must include it.
2. Wire production MCP delivery into the CLI path. `MCPDocsAdapter` and `MCPGmailAdapter` exist, but `RunOrchestrator` defaults to fake ports unless real ports are injected.
3. Pass the Google Doc ID into scheduled runs. The `schedule` command accepts `--doc-id`, but `RunScheduler` currently calls `execute_run()` without forwarding an `existing_document_id`.
4. Add a Railway-friendly production entrypoint after those wiring changes are complete.

Recommended implementation checkpoint:

```bash
pytest tests/integration/test_mcp_delivery.py tests/integration/test_cli.py
groww-pulse validate
groww-pulse run --dry-run --weeks 8
```

### Required Environment Variables

The app reads variables with the `GROWW_PULSE_` prefix.

Recommended Railway variables:

```bash
GROWW_PULSE_APP_ID=com.nextbillion.groww
GROWW_PULSE_LOCALE=en_IN
GROWW_PULSE_LOOKBACK_WEEKS=8
GROWW_PULSE_RECIPIENT_ALIAS=pulse-subscribers@groww.in
GROWW_PULSE_STORAGE_PATH=/data/groww_pulse.db
GROWW_PULSE_MODEL_PROVIDER=groq
GROWW_PULSE_MODEL_ID=mixtral-8x7b-32768
GROWW_PULSE_MODEL_TEMPERATURE=0.0
GROWW_PULSE_BATCH_SIZE=25
GROWW_PULSE_TIMEOUT_SECONDS=60
GROWW_PULSE_DRY_RUN=false
GROWW_PULSE_MCP_DOCS_SERVER_NAME=google_docs
GROWW_PULSE_MCP_DOCS_TOOL_CREATE=create_document
GROWW_PULSE_MCP_DOCS_TOOL_UPDATE=update_document
GROWW_PULSE_MCP_GMAIL_SERVER_NAME=gmail
GROWW_PULSE_MCP_GMAIL_TOOL_CREATE_DRAFT=create_draft
```

Provider secrets depend on the selected model provider. Add only the one being used:

```bash
OPENAI_API_KEY=...
GROQ_API_KEY=...
GOOGLE_API_KEY=...
```

If using a pre-created Google Doc, also store the document ID:

```bash
EXISTING_GOOGLE_DOC_ID=...
```

### Railway Service Setup

1. Create a new Railway project from the GitHub repository.
2. Select the repository root as the service root.
3. Configure Python runtime to use Python 3.11 or 3.12.
4. Add a Railway volume mounted at `/data` if using SQLite.
5. Set the start command based on selected backend mode.

Worker-only start command:

```bash
groww-pulse schedule --day-of-week 0 --hour 9 --minute 0 --doc-id $EXISTING_GOOGLE_DOC_ID
```

Use this command only after the scheduler forwards `--doc-id` into `execute_run(existing_document_id=...)`.

Staging command for first deploy:

```bash
groww-pulse test-schedule --dry-run --doc-id $EXISTING_GOOGLE_DOC_ID
```

### Exit Criteria

- Railway build succeeds.
- `groww-pulse validate` succeeds in Railway logs.
- Dry-run scheduled execution succeeds in Railway logs.
- SQLite database is created under `/data` if using Railway volume.

---

## Phase 2: Production Backend Run and MCP Verification

**Goal:** Prove the real pipeline can run safely from Railway.

### Steps

1. Switch `GROWW_PULSE_DRY_RUN=false` in Railway.
2. Confirm provider API key is present for the selected model provider.
3. Confirm MCP Docs and Gmail services are reachable from Railway.
4. Run a one-time production test:

```bash
groww-pulse test-schedule --doc-id $EXISTING_GOOGLE_DOC_ID
```

5. Inspect Railway logs for:
   - run ID
   - completed status
   - review count
   - document ID or URL
   - Gmail draft ID
6. Verify Google Docs received the pulse.
7. Verify Gmail created a draft only and did not send mail.

### Rollback

Set:

```bash
GROWW_PULSE_DRY_RUN=true
```

Then redeploy or restart the Railway service.

### Exit Criteria

- One live pipeline run completes.
- Docs output contains exactly 3 themes, 3 quotes, and 3 actions.
- Gmail draft exists and is unsent.
- No PII is visible in generated output.

---

## Phase 3: Frontend Deployment to Vercel

**Goal:** Publish the static Review Pulse UI from `frontend/`.

### Vercel Project Settings

Use these settings for the current static frontend:

```text
Framework Preset: Other
Root Directory: frontend
Build Command: None
Output Directory: .
Install Command: None
```

No frontend environment variables are required for the current static fixture UI.

### Steps

1. Create a Vercel project from the GitHub repository.
2. Set root directory to `frontend`.
3. Deploy preview environment.
4. Validate the deployed UI:
   - Weekly Pulse view loads.
   - Navigation between dashboard, detail, reviews, and integrations works.
   - Review filters work.
   - Drawer opens for review rows.
   - Toast actions work.
5. Promote to production after preview validation.

### Exit Criteria

- Vercel preview deploy succeeds.
- Production deploy succeeds.
- UI works on desktop and mobile viewport sizes.

---

## Phase 4: Connect Frontend to Railway API (If Live Data Is Required)

**Goal:** Replace static frontend fixture data with live or latest persisted pulse data.

This phase is only needed if stakeholders expect Vercel to show actual Railway-generated pulse results.

### Backend Work

Add a small HTTP service, for example FastAPI, with endpoints such as:

```text
GET /health
GET /api/pulse/latest
GET /api/runs/latest
GET /api/reviews?sentiment=&rating=&q=
POST /api/runs
```

Recommended Railway API command:

```bash
uvicorn groww_pulse.api:app --host 0.0.0.0 --port $PORT
```

Keep the scheduler as either:

- a second Railway service using `groww-pulse schedule`, or
- a Railway cron/scheduled job that runs `groww-pulse run` weekly.

### Frontend Work

1. Add a Vercel environment variable:

```bash
VITE_API_BASE_URL=https://<railway-service>.up.railway.app
```

For the current vanilla frontend, use a plain runtime config or inject an API base URL during deployment.

2. Replace hardcoded `reviews` and static KPI/theme data in `frontend/app.js` with `fetch()` calls.
3. Add loading, empty, and error states.
4. Configure CORS on Railway to allow only the Vercel production and preview domains.

### Exit Criteria

- Vercel UI reads latest pulse data from Railway.
- Railway API health check passes.
- CORS allows Vercel and blocks unrelated origins.
- UI handles Railway downtime gracefully.

---

## Phase 5: Production Hardening

**Goal:** Make the deployment operationally reliable.

### Backend Hardening

- Use Railway volume backups or migrate from SQLite to Railway Postgres.
- Add a `/health` endpoint if API mode is implemented.
- Add structured logs for run lifecycle events.
- Add alerting for failed or blocked runs.
- Keep `GROWW_PULSE_DRY_RUN=true` in preview/staging environments.
- Restrict MCP permissions to Docs write and Gmail draft creation only.
- Rotate provider and MCP credentials on a fixed schedule.

### Frontend Hardening

- Add production and preview domain checks.
- Add error UI for failed backend fetches.
- Add no-data state for first deployment before any pulse exists.
- Add cache headers appropriate for static assets.

### Exit Criteria

- Failed runs are visible in Railway logs or alerts.
- Secrets are scoped and documented.
- Recovery procedure is tested.
- Staging and production configurations are separated.

---

## Phase 6: Release and Handoff

**Goal:** Make the deployment repeatable for future releases.

### Release Checklist

1. Run local checks: `pytest`, `ruff check .`, `mypy src tests`.
2. Deploy backend to Railway staging or dry-run mode.
3. Run `groww-pulse test-schedule --dry-run` on Railway.
4. Deploy frontend preview to Vercel.
5. Validate preview UI.
6. Enable production backend variables.
7. Run one live backend test.
8. Promote Vercel preview to production.
9. Confirm final URLs:
   - Railway backend or worker logs URL
   - Vercel production URL
   - Google Doc URL
   - Gmail draft ID

### Handoff Artifacts

- Railway project name and service URL.
- Vercel project name and production URL.
- Required environment variable list.
- MCP service ownership and credential rotation process.
- Weekly run schedule and timezone.
- Rollback instructions.

---

## Recommended MVP Sequence

1. Deploy Railway as a **worker-only scheduler** first.
2. Deploy Vercel as a **static frontend** second.
3. Add a Railway API only if the frontend must show live generated pulse data.
4. Migrate persistence to Postgres once more than one Railway instance or long-term audit history is required.
