import uuid

from groww_pulse.integrations.base import DocsPort, GmailPort


class FakeDocsPort(DocsPort):
    """Fake Docs adapter for dry-run mode, unit tests, and offline execution."""

    def __init__(self) -> None:
        self.created_docs: list[dict[str, str | None]] = []

    def create_or_update_document(
        self,
        title: str,
        content: str,
        existing_document_id: str | None = None,
    ) -> tuple[str, str]:
        doc_id = existing_document_id or f"fake_doc_{uuid.uuid4().hex[:8]}"
        doc_url = f"https://docs.google.com/document/d/{doc_id}/edit"
        self.created_docs.append(
            {
                "document_id": doc_id,
                "title": title,
                "content": content,
            }
        )
        return doc_id, doc_url


class FakeGmailPort(GmailPort):
    """Fake Gmail adapter for dry-run mode, unit tests, and offline execution."""

    def __init__(self) -> None:
        self.created_drafts: list[dict[str, str]] = []

    def create_draft(
        self,
        to_address: str,
        subject: str,
        body: str,
    ) -> str:
        draft_id = f"fake_draft_{uuid.uuid4().hex[:8]}"
        self.created_drafts.append(
            {
                "draft_id": draft_id,
                "to_address": to_address,
                "subject": subject,
                "body": body,
            }
        )
        return draft_id
