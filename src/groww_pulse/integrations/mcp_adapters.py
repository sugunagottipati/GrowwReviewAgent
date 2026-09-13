"""Real MCP adapters for Google Docs and Gmail delivery.

These adapters invoke MCP tools through a configured MCP client.
The actual MCP server connection is established externally and passed to these adapters.

MCP Client Interface Requirement:
- The client must support: tool_caller(server_name, tool_name, arguments) -> response_dict
- It should return a structured response with 'success', 'documentId', 'draftId', etc.
- Authentication and server lifecycle are managed outside these adapters
"""

from typing import Any, Callable

from groww_pulse.integrations.base import DocsPort, GmailPort
from groww_pulse.logging_utils.logger import StructuredLogger


class MCPToolError(Exception):
    """Exception raised when MCP tool invocation fails."""

    pass


class MCPDocsAdapter(DocsPort):
    """MCP adapter for Google Docs operations (append-only).
    
    GoogMcpServer only supports append operations; documents must be created externally.
    
    The tool_caller should have signature:
        tool_caller(server_name: str, tool_name: str, arguments: dict) -> dict
    """

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
            
            # Validate response
            if not response.get("success") or "documentId" not in response:
                error_msg = "MCP docs append returned incomplete response (missing success or documentId)"
                StructuredLogger.error(
                    "mcp_docs_append_failed",
                    error=error_msg,
                    response_has_success=response.get("success"),
                    response_has_doc_id="documentId" in response,
                )
                raise MCPToolError(error_msg)
            
            doc_id = response["documentId"]
            doc_url = f"https://docs.google.com/document/d/{doc_id}/edit"
            
            StructuredLogger.info(
                "mcp_docs_append_complete",
                document_id=doc_id,
                appended_characters=response.get("appendedCharacters", 0),
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
            
            # Extract safe response fields only
            draft_id = response.get("draftId", "")
            
            if not draft_id or not response.get("success"):
                error_msg = "MCP gmail create_draft returned no draftId or success=false"
                StructuredLogger.error(
                    "mcp_gmail_create_draft_failed",
                    error=error_msg,
                    response_has_success=response.get("success"),
                    response_has_draft_id="draftId" in response,
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
