"""Run summary and reporting for orchestrator operations."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from groww_pulse.domain.enums import RunStatus


class RunStatusSummary(Enum):
    """Human-readable run status for operators."""
    
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"
    IN_PROGRESS = "in_progress"


@dataclass
class RunSummary:
    """Summary of a completed orchestrator run for operator visibility."""
    
    run_id: str
    status: RunStatus
    started_at: datetime
    completed_at: datetime | None
    review_count: int
    selected_theme_labels: list[str]  # Top 3 theme labels
    document_id: str | None
    document_url: str | None
    gmail_draft_id: str | None
    error_summary: str | None
    
    def operator_message(self) -> str:
        """Generate a human-readable summary for operators."""
        lines = [
            f"📊 GrowwReviewAgent Run Summary",
            f"Run ID: {self.run_id}",
            f"Status: {self.status.value.upper()}",
        ]
        
        if self.started_at:
            lines.append(f"Started: {self.started_at.isoformat()}")
        
        if self.completed_at:
            duration = (self.completed_at - self.started_at).total_seconds()
            lines.append(f"Duration: {duration:.1f}s")
        
        lines.append(f"Reviews Collected: {self.review_count}")
        
        if self.selected_theme_labels:
            lines.append(f"Top Themes: {', '.join(self.selected_theme_labels)}")
        
        if self.status == RunStatus.COMPLETED:
            lines.append("")
            lines.append("✅ Delivery Successful")
            if self.document_url:
                lines.append(f"Google Doc: {self.document_url}")
            if self.gmail_draft_id:
                lines.append(f"Gmail Draft ID: {self.gmail_draft_id}")
        
        elif self.status == RunStatus.BLOCKED:
            lines.append("")
            lines.append(f"⚠️ Run Blocked: {self.error_summary}")
        
        elif self.status == RunStatus.FAILED:
            lines.append("")
            lines.append(f"❌ Run Failed: {self.error_summary}")
        
        return "\n".join(lines)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "run_id": self.run_id,
            "status": self.status.value,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "review_count": self.review_count,
            "selected_theme_labels": self.selected_theme_labels,
            "document_id": self.document_id,
            "document_url": self.document_url,
            "gmail_draft_id": self.gmail_draft_id,
            "error_summary": self.error_summary,
        }


class AlertHandler:
    """Sends alerts for failed or blocked runs."""
    
    def __init__(self, enabled: bool = False, channel: str | None = None) -> None:
        """Initialize alert handler.
        
        Args:
            enabled: Whether alerts are enabled
            channel: Alert destination ('slack', 'email', 'log', etc.)
        """
        self.enabled = enabled
        self.channel = channel or 'log'
    
    def alert_failed_run(self, summary: RunSummary) -> None:
        """Send alert for failed run."""
        if not self.enabled:
            return
        
        message = f"❌ GrowwReviewAgent run {summary.run_id} FAILED: {summary.error_summary}"
        self._send_alert(message, severity="error")
    
    def alert_blocked_run(self, summary: RunSummary) -> None:
        """Send alert for blocked run."""
        if not self.enabled:
            return
        
        message = f"⚠️ GrowwReviewAgent run {summary.run_id} BLOCKED: {summary.error_summary}"
        self._send_alert(message, severity="warning")
    
    def _send_alert(self, message: str, severity: str = "info") -> None:
        """Send alert through configured channel."""
        if self.channel == 'log':
            import logging
            logger = logging.getLogger(__name__)
            if severity == "error":
                logger.error(message)
            elif severity == "warning":
                logger.warning(message)
            else:
                logger.info(message)
        else:
            # Placeholder for other channels (Slack, email, etc.)
            pass
