"""Integration tests for MCP delivery through the orchestrator."""

import json
from datetime import date, datetime
from pathlib import Path
from unittest.mock import MagicMock

from groww_pulse.collection.fixture_collector import FixtureReviewCollector
from groww_pulse.collection.models import RawReview
from groww_pulse.config.settings import Settings
from groww_pulse.domain.enums import RunStatus
from groww_pulse.integrations.fake_ports import FakeDocsPort, FakeGmailPort
from groww_pulse.integrations.mcp_adapters import MCPDocsAdapter, MCPGmailAdapter
from groww_pulse.orchestration.orchestrator import RunOrchestrator
from groww_pulse.storage.sqlite_repository import SQLiteRepository


def load_synthetic_fixtures() -> list[RawReview]:
    """Load synthetic test fixtures."""
    fixture_path = Path(__file__).parents[1] / "fixtures" / "synthetic_reviews.json"
    with open(fixture_path, encoding="utf-8") as f:
        data = json.load(f)

    return [
        RawReview(
            review_id=item["review_id"],
            rating=item["rating"],
            title=item.get("title"),
            text=item["text"],
            reviewed_at=datetime.fromisoformat(item["reviewed_at"]),
            locale=item.get("locale", "en_IN"),
            source_url=item.get("source_url", ""),
        )
        for item in data
    ]


def test_mcp_delivery_with_mock_tools(tmp_path: Path) -> None:
    """Test end-to-end delivery with mocked MCP tools.
    
    Verifies:
    - Docs append is called exactly once before Gmail draft
    - Gmail draft is called exactly once
    - Document ID and URL are persisted in run
    - Draft ID is persisted in run
    """
    db_path = tmp_path / "pulse_test.db"
    settings = Settings(
        dry_run=False,
        storage_path=db_path,
        lookback_weeks=12,
        model_provider="fake",
    )

    raw_fixtures = load_synthetic_fixtures()
    collector = FixtureReviewCollector(fixtures=raw_fixtures)

    # Mock MCP tool calls
    mcp_calls = {"docs": [], "gmail": []}

    def mock_docs_tool_caller(server: str, tool: str, args: dict) -> dict:
        mcp_calls["docs"].append({"server": server, "tool": tool, "args": args})
        return {
            "success": True,
            "documentId": "mcp_doc_12345",
            "appendedCharacters": len(args.get("content", "")),
        }

    def mock_gmail_tool_caller(server: str, tool: str, args: dict) -> dict:
        mcp_calls["gmail"].append({"server": server, "tool": tool, "args": args})
        return {
            "success": True,
            "draftId": "mcp_draft_xyz789",
            "messageId": "msg_xyz",
            "threadId": "thread_xyz",
        }

    docs_port = MCPDocsAdapter(mock_docs_tool_caller)
    gmail_port = MCPGmailAdapter(mock_gmail_tool_caller)
    sqlite_repo = SQLiteRepository(db_path)

    orchestrator = RunOrchestrator(
        settings=settings,
        collector=collector,
        docs_port=docs_port,
        gmail_port=gmail_port,
        review_repo=sqlite_repo,
        run_repo=sqlite_repo,
    )

    run, pulse = orchestrator.execute_run(
        week_ending=date(2026, 8, 30),
        existing_document_id="pre_created_doc_id"
    )

    # Assert run completed
    assert run.status == RunStatus.COMPLETED
    assert pulse is not None

    # Assert MCP calls were made correctly
    assert len(mcp_calls["docs"]) == 1, "Docs append should be called exactly once"
    assert len(mcp_calls["gmail"]) == 1, "Gmail draft should be called exactly once"

    # Verify Docs call arguments
    docs_call = mcp_calls["docs"][0]
    assert docs_call["server"] == "google_docs"
    assert docs_call["tool"] == "google_docs_append_content"
    assert docs_call["args"]["documentId"] == "pre_created_doc_id"
    assert "## Top Themes" in docs_call["args"]["content"]

    # Verify Gmail call arguments
    gmail_call = mcp_calls["gmail"][0]
    assert gmail_call["server"] == "gmail"
    assert gmail_call["tool"] == "gmail_create_draft"
    assert "Groww Weekly Review Pulse" in gmail_call["args"]["subject"]
    assert gmail_call["args"]["to"] == [settings.recipient_alias]  # Note: to is converted to list by adapter

    # Assert delivery IDs are persisted
    assert run.document_id == "mcp_doc_12345"
    assert run.gmail_draft_id == "mcp_draft_xyz789"


def test_delivery_docs_then_gmail_ordering(tmp_path: Path) -> None:
    """Test that Docs are created before Gmail draft (ordering constraint).
    
    This ensures idempotency: if delivery fails after creating the doc,
    we can retry without duplicating the document.
    """
    db_path = tmp_path / "pulse_test.db"
    settings = Settings(
        dry_run=False,
        storage_path=db_path,
        lookback_weeks=12,
        model_provider="fake",
    )

    raw_fixtures = load_synthetic_fixtures()
    collector = FixtureReviewCollector(fixtures=raw_fixtures)

    # Track call order
    call_order = []

    def mock_docs_tool_caller(server: str, tool: str, args: dict) -> dict:
        call_order.append("docs")
        return {
            "success": True,
            "documentId": "doc_id",
            "appendedCharacters": 100,
        }

    def mock_gmail_tool_caller(server: str, tool: str, args: dict) -> dict:
        call_order.append("gmail")
        return {
            "success": True,
            "draftId": "draft_id",
            "messageId": "msg_id",
            "threadId": "thread_id",
        }

    docs_port = MCPDocsAdapter(mock_docs_tool_caller)
    gmail_port = MCPGmailAdapter(mock_gmail_tool_caller)
    sqlite_repo = SQLiteRepository(db_path)

    orchestrator = RunOrchestrator(
        settings=settings,
        collector=collector,
        docs_port=docs_port,
        gmail_port=gmail_port,
        review_repo=sqlite_repo,
        run_repo=sqlite_repo,
    )

    run, pulse = orchestrator.execute_run(
        week_ending=date(2026, 8, 30),
        existing_document_id="pre_created_doc_id"
    )

    # Assert Docs was called before Gmail
    assert call_order == ["docs", "gmail"], "Docs must be created before Gmail draft"
    assert run.status == RunStatus.COMPLETED


def test_delivery_with_fake_ports_still_works(tmp_path: Path) -> None:
    """Test that fake ports work in parallel with MCP adapters."""
    db_path = tmp_path / "pulse_test.db"
    settings = Settings(
        dry_run=True,
        storage_path=db_path,
        lookback_weeks=12,
        model_provider="fake",
    )

    raw_fixtures = load_synthetic_fixtures()
    collector = FixtureReviewCollector(fixtures=raw_fixtures)
    docs_port = FakeDocsPort()
    gmail_port = FakeGmailPort()
    sqlite_repo = SQLiteRepository(db_path)

    orchestrator = RunOrchestrator(
        settings=settings,
        collector=collector,
        docs_port=docs_port,
        gmail_port=gmail_port,
        review_repo=sqlite_repo,
        run_repo=sqlite_repo,
    )

    run, pulse = orchestrator.execute_run(week_ending=date(2026, 8, 30))

    # Assert fake ports were used
    assert run.status == RunStatus.COMPLETED
    assert len(docs_port.created_docs) == 1
    assert len(gmail_port.created_drafts) == 1
    assert "[DRY RUN]" in docs_port.created_docs[0]["title"]


def test_delivery_no_calls_when_no_eligible_reviews(tmp_path: Path) -> None:
    """Test that no MCP calls are made when reviews are blocked.
    
    This verifies the constraint: never create synthetic content.
    """
    db_path = tmp_path / "pulse_test.db"
    settings = Settings(
        dry_run=False,
        storage_path=db_path,
        lookback_weeks=12,
        model_provider="fake",
    )

    # Empty review list
    collector = FixtureReviewCollector(fixtures=[])
    mcp_calls = {"docs": 0, "gmail": 0}

    def mock_docs_tool_caller(server: str, tool: str, args: dict) -> dict:
        mcp_calls["docs"] += 1
        return {"document_id": "doc_id", "document_url": "url"}

    def mock_gmail_tool_caller(server: str, tool: str, args: dict) -> dict:
        mcp_calls["gmail"] += 1
        return {"draft_id": "draft_id"}

    docs_port = MCPDocsAdapter(mock_docs_tool_caller)
    gmail_port = MCPGmailAdapter(mock_gmail_tool_caller)
    sqlite_repo = SQLiteRepository(db_path)

    orchestrator = RunOrchestrator(
        settings=settings,
        collector=collector,
        docs_port=docs_port,
        gmail_port=gmail_port,
        review_repo=sqlite_repo,
        run_repo=sqlite_repo,
    )

    run, pulse = orchestrator.execute_run(week_ending=date(2026, 8, 30))

    # Assert no MCP calls were made
    assert run.status == RunStatus.BLOCKED
    assert mcp_calls["docs"] == 0
    assert mcp_calls["gmail"] == 0
    assert pulse is None
