# Groww Weekly Review Pulse

A Python-based system that uses LangChain to turn recent public Google Play reviews for Groww (`com.nextbillion.groww`) into a weekly product-health pulse delivered via MCP to Google Docs and Gmail.

## Requirements & Environment

- **Python:** Python 3.11+ (recommended: 3.11 or 3.12)
- **Package Manager:** `uv` (recommended) or `pip` / `venv`

## Local Setup

### Using `uv` (Recommended)

```bash
# Create and activate virtual environment
uv venv --python 3.12 .venv
source .venv/bin/activate

# Install editable package with dev dependencies
uv pip install -e ".[dev]"
```

### Using standard `python3` venv

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Running the CLI

The project provides the `groww-pulse` command line tool:

```bash
# Dry run (safe mode: no live LLM or MCP calls)
groww-pulse run --dry-run

# Validate configuration and components
groww-pulse validate

# Backfill reviews over a specific lookback window (8-12 weeks)
groww-pulse backfill --weeks 12 --dry-run
```

## Running Tests, Linting, and Type Checking

```bash
# Run unit and integration tests
pytest

# Run tests with coverage
pytest --cov=src

# Run linter
ruff check .

# Run static type checking
mypy src tests
```

## Security & Privacy Highlights

- **Privacy before persistence:** Reviewer names, emails, avatars, and device IDs are stripped/redacted before any storage or LLM prompt.
- **Strict Guardrails:** Output is validated to ensure verbatim quote provenance, <= 250 words, exactly 3 themes, 3 quotes, and 3 actions.
- **MCP-Only Delivery:** No direct Google API credentials or REST clients are embedded in the application.
