# MCP (Model Context Protocol) Setup Guide

## Overview

The Groww Weekly Review Pulse system uses MCP to deliver validated pulses to Google Docs and Gmail. MCP provides a standardized interface for calling external tools without embedding authentication credentials or HTTP plumbing directly in the application.

This guide describes how to set up MCP servers for Docs and Gmail delivery.

## Architecture

```
Orchestrator
    ↓
DocsPort/GmailPort (interfaces)
    ↓
MCPDocsAdapter/MCPGmailAdapter (MCP implementations)
    ↓
MCP Tool Caller (your MCP client)
    ↓
MCP Servers (Google Docs, Gmail)
```

The application defines narrow port interfaces and remains independent of MCP implementation details. Adapters map these operations to configured MCP servers and tools.

## Configuration

MCP server and tool names are configured via environment variables:

```bash
# Google Docs MCP configuration
export GROWW_PULSE_MCP_DOCS_SERVER_NAME=google_docs
export GROWW_PULSE_MCP_DOCS_TOOL_CREATE=create_document
export GROWW_PULSE_MCP_DOCS_TOOL_UPDATE=update_document

# Gmail MCP configuration
export GROWW_PULSE_MCP_GMAIL_SERVER_NAME=gmail
export GROWW_PULSE_MCP_GMAIL_TOOL_CREATE_DRAFT=create_draft

# Or in .env:
MCP_DOCS_SERVER_NAME=google_docs
MCP_DOCS_TOOL_CREATE=create_document
MCP_DOCS_TOOL_UPDATE=update_document
MCP_GMAIL_SERVER_NAME=gmail
MCP_GMAIL_TOOL_CREATE_DRAFT=create_draft
```

## Implementing an MCP Tool Caller

The `MCPDocsAdapter` and `MCPGmailAdapter` require a `tool_caller` callable with signature:

```python
def tool_caller(
    server_name: str,
    tool_name: str,
    arguments: dict[str, Any]
) -> dict[str, Any]:
    """Call an MCP tool and return response."""
    ...
```

### Example: Using Anthropic's MCP SDK

```python
from mcp import create_client

# Initialize MCP client (handles authentication)
mcp_client = await create_client("mcp.json")  # config with servers

def make_mcp_tool_caller(client):
    def tool_caller(server_name: str, tool_name: str, arguments: dict):
        response = client.call_tool(server_name, tool_name, arguments)
        return response
    return tool_caller

docs_port = MCPDocsAdapter(
    tool_caller=make_mcp_tool_caller(mcp_client),
    server_name="google_docs",
    create_tool_name="create_document",
    update_tool_name="update_document",
)

gmail_port = MCPGmailAdapter(
    tool_caller=make_mcp_tool_caller(mcp_client),
    server_name="gmail",
    create_draft_tool_name="create_draft",
)
```

### Example: Using HTTP/JSON-RPC to MCP Server

```python
import httpx
import json

def make_http_mcp_tool_caller(mcp_server_url: str):
    """Create a tool caller that invokes MCP over HTTP."""
    async def tool_caller(server_name: str, tool_name: str, arguments: dict):
        payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "server": server_name,
                "tool": tool_name,
                "arguments": arguments,
            },
            "id": uuid.uuid4().hex,
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(mcp_server_url, json=payload)
            data = response.json()
            if "error" in data:
                raise MCPToolError(data["error"]["message"])
            return data.get("result", {})
    return tool_caller

docs_port = MCPDocsAdapter(make_http_mcp_tool_caller("http://localhost:3000/mcp"))
```

## Google Docs Tool Schema

The Docs MCP server should expose these tools:

### `create_document`

**Arguments:**
- `title` (string): Document title
- `content` (string): Markdown content for the document

**Response:**
- `document_id` (string): ID of the created document
- `document_url` (string): Shareable URL to the document

**Example:**
```json
{
  "title": "Groww Weekly Review Pulse - Week Ending 2026-08-30",
  "content": "# Groww Weekly Review Pulse\n\n## Top Themes\n..."
}
```

### `update_document`

**Arguments:**
- `document_id` (string): ID of the document to update
- `title` (string): Updated document title
- `content` (string): Updated Markdown content

**Response:**
- `document_id` (string): ID of the updated document
- `document_url` (string): Shareable URL to the document

## Gmail Tool Schema

The Gmail MCP server should expose this tool:

### `create_draft`

**Arguments:**
- `to` (string): Recipient email address
- `subject` (string): Draft subject line
- `body` (string): Draft message body (plain text or HTML)

**Response:**
- `draft_id` (string): ID of the created draft

**Important:** The tool must create an unsent draft only. It must not send the email.

**Example:**
```json
{
  "to": "pulse-subscribers@groww.in",
  "subject": "Groww Weekly Review Pulse - Week Ending 2026-08-30",
  "body": "Google Doc: https://...\n\n# Groww Weekly Review Pulse\n..."
}
```

## Security Considerations

### Principle of Least Privilege

Configure MCP servers with minimal required permissions:

- **Google Docs:** Restrict write access to a specific folder or document space. Do not grant global Docs permission.
- **Gmail:** Restrict to draft creation only. Never grant send permission.

### Authentication

- Authentication is managed by the MCP server, not by this application.
- Application code does not handle credentials, tokens, or OAuth secrets.
- MCP server is configured with service account credentials or other secure mechanisms outside the application.

### Logging and Auditing

- MCP responses are sanitized before logging; only non-sensitive fields (IDs, URLs) are logged.
- Email addresses in MCP calls are sanitized; only the domain is logged.
- Raw MCP responses and credentials are never logged.

## Error Handling and Retry

The orchestrator implements a retry policy:

1. **Docs failures:** Fail immediately; do not proceed to Gmail.
2. **Gmail failures after Docs success:** Run is marked failed, but document is retained. Retry can attempt Gmail delivery only.
3. **Transient errors:** Retry with bounded exponential backoff up to the configured `timeout_seconds`.

## Staging and Testing

### Dry-Run Mode (Local Development)

```bash
export GROWW_PULSE_DRY_RUN=true
python -m groww_pulse.orchestration.cli run
```

Dry-run mode:
- Uses `FakeDocsPort` and `FakeGmailPort` instead of MCP adapters
- Generates fake document IDs and draft IDs
- Never calls external services
- Allows testing the full pipeline without MCP servers

### Staging with MCP Servers

```bash
# Export MCP credentials (mechanism depends on your MCP server setup)
export MCP_GOOGLE_DOCS_CREDENTIALS=...
export MCP_GMAIL_CREDENTIALS=...

# Run against staging MCP servers
python -m groww_pulse.orchestration.cli run --week 2026-08-30
```

### Verification Checklist

After a staging run:

1. ✅ Document was created in the expected folder
2. ✅ Document contains three themes, three quotes, three actions
3. ✅ Document word count is ≤ 250 words
4. ✅ No PII (email addresses, phone numbers, usernames) is visible
5. ✅ All quotes are verbatim from anonymized reviews
6. ✅ Gmail draft was created (not sent)
7. ✅ Draft contains the document link
8. ✅ Draft subject includes the week ending date

## Testing MCP Adapters

### Unit Tests

Unit tests use mock `tool_caller` functions:

```bash
pytest tests/unit/test_mcp_adapters.py -v
```

### Integration Tests

Integration tests use mocked MCP tool calls with the full orchestrator:

```bash
pytest tests/integration/test_mcp_delivery.py -v
```

Tests verify:
- ✅ Docs are created exactly once before Gmail
- ✅ Gmail draft is created exactly once
- ✅ No MCP calls when reviews are blocked
- ✅ Document IDs and URLs are persisted in run records
- ✅ Draft IDs are persisted in run records

## Common Issues

### MCP Server Connection Refused

**Symptom:** `MCPToolError: MCP operation failed (ConnectionError)`

**Solution:**
1. Verify MCP server is running: `curl http://localhost:3000/health`
2. Check server URL in environment variables
3. Verify firewall rules allow connection
4. Check MCP server logs for errors

### Invalid Tool Name

**Symptom:** `MCPToolError: MCP operation failed (ToolNotFound)`

**Solution:**
1. Verify tool name matches MCP server schema: `curl http://localhost:3000/tools`
2. Check environment variables `MCP_DOCS_TOOL_CREATE`, `MCP_GMAIL_TOOL_CREATE_DRAFT`
3. Consult MCP server documentation

### Authentication Failure

**Symptom:** `MCPToolError: MCP operation failed (Unauthorized)`

**Solution:**
1. Verify MCP server credentials are configured (outside application code)
2. Check token/credential expiration
3. Verify MCP server has permission to access target Docs/Gmail account
4. Check MCP server logs for auth errors

### Incomplete MCP Response

**Symptom:** `MCPToolError: MCP docs create returned incomplete response`

**Solution:**
1. Verify MCP server returns both `document_id` and `document_url` for Docs
2. Verify MCP server returns `draft_id` for Gmail
3. Check MCP server response format matches schema above

## Scheduled Delivery

To deliver the pulse weekly:

```bash
# Add to crontab or scheduler
0 9 * * MON /path/to/groww-pulse run
```

The CLI will:
1. Collect reviews from the past 12 weeks
2. Process and analyze them
3. Create/update the weekly Google Doc
4. Create an unsent Gmail draft
5. Log completion with document URL and draft ID

An operator can then review the unsent draft before sending if needed.

## Integration with CI/CD

```yaml
# Example GitHub Actions workflow
name: Weekly Pulse Delivery
on:
  schedule:
    - cron: '0 9 * * MON'
  workflow_dispatch:

jobs:
  deliver-pulse:
    runs-on: ubuntu-latest
    environment: production
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - run: pip install -e .
      - run: python -m groww_pulse.orchestration.cli run
        env:
          MCP_DOCS_SERVER_NAME: ${{ secrets.MCP_DOCS_SERVER }}
          MCP_GMAIL_SERVER_NAME: ${{ secrets.MCP_GMAIL_SERVER }}
          MCP_CREDENTIALS: ${{ secrets.MCP_CREDENTIALS }}
```
