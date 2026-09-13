"""Real MCP adapters for Google Docs and Gmail delivery.

These adapters invoke MCP tools through a configured MCP client.
The actual MCP server connection is established externally and passed to these adapters.

MCP Client Interface Requirement:
- The client must support: tool_caller(server_name, tool_name, arguments) -> response_dict
- It should return a structured response with 'success', 'documentId', 'draftId', etc.
- Authentication and server lifecycle are managed outside these adapters
"""

import json
from typing import Any, Callable

from groww_pulse.integrations.base import DocsPort, GmailPort
from groww_pulse.logging_utils.logger import StructuredLogger


class MCPToolError(Exception):
    """Exception raised when MCP tool invocation fails."""

    pass


def _normalize_mcp_response(response: Any) -> dict[str, Any]:
    """Normalize structured and text-only MCP tool result payloads."""
    if not isinstance(response, dict):
        return {}

    result = response.get("result")
    if isinstance(result, dict):
        response = result

    structured = response.get("structuredContent")
    if isinstance(structured, dict):
        normalized = dict(structured)
    else:
        normalized = {}

    content = response.get("content")
    if isinstance(content, str):
        content_items = [{"text": content}]
    elif isinstance(content, list):
        content_items = content
    else:
        content_items = []

    for item in content_items:
        if not isinstance(item, dict) or not isinstance(item.get("text"), str):
            continue
        try:
            text_payload = json.loads(item["text"])
        except json.JSONDecodeError:
            continue
        if isinstance(text_payload, dict):
            for key, value in text_payload.items():
                normalized.setdefault(key, value)

    for key, value in response.items():
        if key not in {"structuredContent", "content", "result"}:
            normalized.setdefault(key, value)
    return normalized


class MCPDocsAdapter(DocsPort):
    """MCP adapter for Google Docs operations (append-only).
    
    GoogMcpServer only supports append operations; documents must be created externally.
    
    The tool_caller should have signature:
        tool_caller(server_name: str, tool_name: str, arguments: dict) -> dict
    """

    @staticmethod
    def _normalize_response(response: Any) -> dict[str, Any]:
        """Normalize either a flat result dict or the server's structuredContent wrapper."""
        return _normalize_mcp_response(response)

    def __init__(
        self,
        tool_caller: Callable[[str, str, dict[str, Any]], dict[str, Any]],
        server_name: str = "google_docs",
        append_tool_name: str = "google_docs_append_content",
    ) -> None:
        self.tool_caller = tool_caller
        self.server_name = server_name
        self.append_tool_name = append_tool_name

    def create_or_update_document(
        self,
        title: str,
        content: str,
        existing_document_id: str | None = None,
    ) -> tuple[str, str]:
        """Append content to an existing Google Doc via MCP.
        
        GoogMcpServer supports append-only operations. Documents must be created externally.
        
        Args:
            title: Document title (for logging; not used in append)
            content: Markdown content to append
            existing_document_id: Required - the Google Doc ID to append to
            
        Returns:
            Tuple of (document_id, document_url)
            
        Raises:
            MCPToolError: If MCP invocation fails or no document_id provided
        """
        if not existing_document_id:
            raise MCPToolError(
                "MCPDocsAdapter requires existing_document_id (GoogMcpServer supports append-only; document must be pre-created)"
            )
        
        # Sanitize sensitive content before logging
        safe_title = title.replace("[DRY RUN]", "").strip()
        
        try:
            StructuredLogger.info(
                "mcp_docs_append_start",
                document_id=existing_document_id,
                title=safe_title[:50],
            )
            
            response = self.tool_caller(
                self.server_name,
                self.append_tool_name,
                {
                    "documentId": existing_document_id,
                    "content": content,
                    "addNewline": True,
                },
            )
            normalized = self._normalize_response(response)
            
            # Validate response
            if not normalized.get("success") or "documentId" not in normalized:
                error_msg = "MCP docs append returned incomplete response (missing success or documentId)"
                StructuredLogger.error(
                    "mcp_docs_append_failed",
                    error=error_msg,
                    response_has_success=normalized.get("success"),
                    response_has_doc_id="documentId" in normalized,
                )
                raise MCPToolError(error_msg)
            
            doc_id = normalized["documentId"]
            doc_url = f"https://docs.google.com/document/d/{doc_id}/edit"
            
            StructuredLogger.info(
                "mcp_docs_append_complete",
                document_id=doc_id,
                appended_characters=normalized.get("appendedCharacters", 0),
            )
            
            return doc_id, doc_url
            
        except MCPToolError:
            raise
        except Exception as exc:
            error_msg = f"MCP docs operation failed: {type(exc).__name__}"
            StructuredLogger.error(
                "mcp_docs_error",
                error=error_msg,
                exception_type=type(exc).__name__,
            )
            raise MCPToolError(error_msg) from exc


class MCPGmailAdapter(GmailPort):
    """MCP adapter for Gmail draft operations.
    
    Creates unsent Gmail drafts via MCP (never sends messages).
    
    The tool_caller should have signature:
        tool_caller(server_name: str, tool_name: str, arguments: dict) -> dict
    """

    @staticmethod
    def _normalize_response(response: Any) -> dict[str, Any]:
        """Normalize either a flat result dict or the server's structuredContent wrapper."""
        return _normalize_mcp_response(response)

    def __init__(
        self,
        tool_caller: Callable[[str, str, dict[str, Any]], dict[str, Any]],
        server_name: str = "gmail",
        create_draft_tool_name: str = "gmail_create_draft",
    ) -> None:
        self.tool_caller = tool_caller
        self.server_name = server_name
        self.create_draft_tool_name = create_draft_tool_name

    def create_draft(
        self,
        to_address: str,
        subject: str,
        body: str,
    ) -> str:
        """Create an unsent Gmail draft via MCP.
        
        Args:
            to_address: Recipient email address
            subject: Draft subject line
            body: Draft message body
            
        Returns:
            Gmail draft ID
            
        Raises:
            MCPToolError: If MCP invocation fails
        """
        # Sanitize sensitive content before logging
        safe_subject = subject.replace("[DRY RUN]", "").strip()
        
        try:
            StructuredLogger.info(
                "mcp_gmail_create_draft_start",
                to_address_domain=to_address.split("@")[1] if "@" in to_address else "unknown",
                subject=safe_subject[:50],  # Log only subject prefix
            )
            
            response = self.tool_caller(
                self.server_name,
                self.create_draft_tool_name,
                {
                    "to": [to_address],
                    "subject": subject,
                    "body": body,
                },
            )
            normalized = self._normalize_response(response)
            
            # Extract safe response fields only
            draft_id = normalized.get("draftId", "")
            
            if not draft_id or not normalized.get("success"):
                error_msg = "MCP gmail create_draft returned no draftId or success=false"
                StructuredLogger.error(
                    "mcp_gmail_create_draft_failed",
                    error=error_msg,
                    response_has_success=normalized.get("success"),
                    response_has_draft_id="draftId" in normalized,
                )
                raise MCPToolError(error_msg)
            
            StructuredLogger.info(
                "mcp_gmail_create_draft_complete",
                draft_id=draft_id,
            )
            
            return draft_id
            
        except MCPToolError:
            raise
        except Exception as exc:
            error_msg = f"MCP gmail operation failed: {type(exc).__name__}"
            StructuredLogger.error(
                "mcp_gmail_error",
                error=error_msg,
                exception_type=type(exc).__name__,
            )
            raise MCPToolError(error_msg) from exc
