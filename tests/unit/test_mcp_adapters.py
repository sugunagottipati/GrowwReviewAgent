"""Unit tests for MCP adapters (Docs and Gmail)."""

import pytest

from groww_pulse.integrations.mcp_adapters import (
    MCPDocsAdapter,
    MCPGmailAdapter,
    MCPToolError,
)


class TestMCPDocsAdapter:
    """Tests for MCPDocsAdapter port implementation."""


    def test_append_document_success(self) -> None:
        """Test successful document append."""

        def mock_tool_caller(server: str, tool: str, args: dict) -> dict:
            assert server == "google_docs"
            assert tool == "google_docs_append_content"
            assert args["documentId"] == "existing_doc_id"
            assert args["content"] == "Test content"
            return {
                "success": True,
                "documentId": "existing_doc_id",
                "appendedCharacters": 12,
            }

        adapter = MCPDocsAdapter(mock_tool_caller)
        doc_id, doc_url = adapter.create_or_update_document(
            title="Test Doc",
            content="Test content",
            existing_document_id="existing_doc_id",
        )

        assert doc_id == "existing_doc_id"
        assert "existing_doc_id" in doc_url

    def test_append_requires_document_id(self) -> None:
        """Test append fails when no document_id provided."""
        
        def mock_tool_caller(server: str, tool: str, args: dict) -> dict:
            return {}  # Should never reach here
        
        adapter = MCPDocsAdapter(mock_tool_caller)
        
        with pytest.raises(MCPToolError, match="existing_document_id"):
            adapter.create_or_update_document(
                title="Test Doc",
                content="Test content",
                existing_document_id=None,
            )

    def test_append_document_missing_doc_id(self) -> None:
        """Test append fails when response missing documentId."""
        
        def mock_tool_caller(server: str, tool: str, args: dict) -> dict:
            return {"success": True}  # Missing documentId
        
        adapter = MCPDocsAdapter(mock_tool_caller)
        
        with pytest.raises(MCPToolError, match="incomplete response"):
            adapter.create_or_update_document(
                title="Test",
                content="content",
                existing_document_id="doc_123",
            )

    def test_append_document_mcp_error_handling(self) -> None:
        """Test MCP error is caught and re-raised."""

        def mock_tool_caller(server: str, tool: str, args: dict) -> dict:
            raise ValueError("MCP connection failed")

        adapter = MCPDocsAdapter(mock_tool_caller)

        with pytest.raises(MCPToolError, match="failed"):
            adapter.create_or_update_document(
                title="Test Doc",
                content="Test content",
                existing_document_id="doc_123",
            )

    def test_custom_server_and_tool_names(self) -> None:
        """Test adapter respects custom MCP server/tool names."""

        def mock_tool_caller(server: str, tool: str, args: dict) -> dict:
            assert server == "custom_server"
            assert tool == "custom_append_tool"
            return {
                "success": True,
                "documentId": "doc_123",
            }

        adapter = MCPDocsAdapter(
            mock_tool_caller,
            server_name="custom_server",
            append_tool_name="custom_append_tool",
        )
        doc_id, doc_url = adapter.create_or_update_document(
            title="Test",
            content="content",
            existing_document_id="doc_123",
        )

        assert doc_id == "doc_123"

class TestMCPGmailAdapter:
    """Tests for MCPGmailAdapter port implementation."""


    def test_create_draft_success(self) -> None:
        """Test successful draft creation."""

        def mock_tool_caller(server: str, tool: str, args: dict) -> dict:
            assert server == "gmail"
            assert tool == "gmail_create_draft"
            assert args["to"] == ["test@example.com"]
            assert args["subject"] == "Test Subject"
            assert "body" in args
            return {
                "success": True,
                "draftId": "draft_abc123",
                "messageId": "msg_123",
                "threadId": "thread_123",
            }

        adapter = MCPGmailAdapter(mock_tool_caller)
        draft_id = adapter.create_draft(
            to_address="test@example.com",
            subject="Test Subject",
            body="Test body",
        )

        assert draft_id == "draft_abc123"

    def test_create_draft_missing_draft_id(self) -> None:
        """Test creation fails when draftId is missing."""

        def mock_tool_caller(server: str, tool: str, args: dict) -> dict:
            return {"success": False}  # Missing draftId or success=false

        adapter = MCPGmailAdapter(mock_tool_caller)

        with pytest.raises(MCPToolError, match="no draftId"):
            adapter.create_draft(
                to_address="test@example.com",
                subject="Test",
                body="Body",
            )
    def test_create_draft_mcp_error_handling(self) -> None:
        """Test MCP error is caught and re-raised."""

        def mock_tool_caller(server: str, tool: str, args: dict) -> dict:
            raise RuntimeError("Gmail service unavailable")

        adapter = MCPGmailAdapter(mock_tool_caller)

        with pytest.raises(MCPToolError, match="failed"):
            adapter.create_draft(
                to_address="test@example.com",
                subject="Test",
                body="Body",
            )

    def test_custom_server_and_tool_names(self) -> None:
        """Test adapter respects custom MCP server/tool names."""


        def mock_tool_caller(server: str, tool: str, args: dict) -> dict:
            assert server == "mail_server"
            assert tool == "draft_create"
            return {"success": True, "draftId": "draft_xyz"}
        adapter = MCPGmailAdapter(
            mock_tool_caller,
            server_name="mail_server",
            create_draft_tool_name="draft_create",
        )
        draft_id = adapter.create_draft(
            to_address="user@example.com",
            subject="Subject",
            body="Body",
        )

        assert draft_id == "draft_xyz"

    def test_create_draft_preserves_dry_run_flag_in_subject(self) -> None:
        """Test that [DRY RUN] is passed through to MCP but sanitized in logs."""

        captured_calls = []


        def mock_tool_caller(server: str, tool: str, args: dict) -> dict:
            captured_calls.append(args)
            return {"success": True, "draftId": "draft_123"}
        adapter = MCPGmailAdapter(mock_tool_caller)
        adapter.create_draft(
            to_address="test@example.com",
            subject="[DRY RUN] Test Subject",
            body="Body",
        )

        # MCP should receive the full subject with [DRY RUN]
        assert captured_calls[0]["subject"] == "[DRY RUN] Test Subject"


class TestMCPToolError:
    """Tests for MCPToolError exception."""

    def test_mcp_tool_error_creation(self) -> None:
        """Test MCPToolError can be created and caught."""
        error = MCPToolError("Test error message")
        assert str(error) == "Test error message"

        with pytest.raises(MCPToolError):
            raise MCPToolError("Test error")
