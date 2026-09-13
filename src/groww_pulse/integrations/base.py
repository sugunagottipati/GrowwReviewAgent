from abc import ABC, abstractmethod


class DocsPort(ABC):
    """Port interface for Google Docs delivery via MCP."""

    @abstractmethod
    def create_or_update_document(
        self,
        title: str,
        content: str,
        existing_document_id: str | None = None,
    ) -> tuple[str, str]:
        """Create or update a document and return (document_id, document_url)."""
        ...


class GmailPort(ABC):
    """Port interface for Gmail draft creation via MCP."""

    @abstractmethod
    def create_draft(
        self,
        to_address: str,
        subject: str,
        body: str,
    ) -> str:
        """Create an unsent email draft and return gmail_draft_id."""
        ...
