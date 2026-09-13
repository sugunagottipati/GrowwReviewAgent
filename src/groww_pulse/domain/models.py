from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from groww_pulse.domain.enums import RunStatus, Sentiment


class Review(BaseModel):
    """Normalized and privacy-filtered safe review."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_review_id: str = Field(
        ...,
        description="Internal deduplication key. Never exposed in stakeholder artifacts.",
    )
    rating: int = Field(..., ge=1, le=5, description="Star rating from 1 to 5")
    title: str | None = Field(default=None, description="Sanitized review title if available")
    text: str = Field(..., min_length=1, description="Sanitized and PII-redacted review text")
    reviewed_at: datetime = Field(..., description="Timestamp when the review was posted")
    locale: str | None = Field(default=None, description="Review locale code, e.g., 'en_IN'")
    source_url: str = Field(default="", description="Public source reference URL")
    content_hash: str = Field(
        ...,
        description="Stable content hash for deduplication fallback",
    )


class Theme(BaseModel):
    """Ranked aggregate theme derived from review feedback."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(..., description="Unique identifier for the theme")
    label: str = Field(..., description="Concise, product-oriented label")
    review_count: int = Field(..., ge=0, description="Number of reviews grouped in this theme")
    share_of_reviews: float = Field(
        ..., ge=0.0, le=1.0, description="Proportion of total reviews in this theme"
    )
    average_rating: float = Field(
        ..., ge=1.0, le=5.0, description="Average star rating for reviews in this theme"
    )
    sentiment: Sentiment = Field(..., description="Dominant sentiment for the theme")
    evidence_review_ids: list[str] = Field(
        default_factory=list,
        description="Internal review IDs supporting this theme",
    )


class Quote(BaseModel):
    """Verbatim quote excerpted from a sanitized review."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_review_id: str = Field(
        ...,
        description="Internal source review ID for provenance tracking",
    )
    text: str = Field(..., min_length=1, description="Verbatim sanitized quote excerpt")
    theme_id: str | None = Field(default=None, description="Associated theme ID if assigned")
    rating: int | None = Field(default=None, ge=1, le=5, description="Rating of the source review")


class Action(BaseModel):
    """Actionable recommendation tied to a specific theme."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    theme_id: str = Field(..., description="ID of the theme this action addresses")
    description: str = Field(..., min_length=1, description="Concrete, grounded action description")
    rationale: str | None = Field(
        default=None, description="Evidence-based reasoning for the action"
    )
    evidence_review_ids: list[str] = Field(
        default_factory=list,
        description="Internal review IDs supporting this action",
    )


class CandidateTheme(BaseModel):
    """Candidate theme output from LangChain analysis chain."""

    model_config = ConfigDict(extra="forbid")

    label: str = Field(..., description="Product-oriented theme label")
    review_ids: list[str] = Field(
        default_factory=list,
        description="List of sanitized review IDs associated with this candidate theme",
    )
    sentiment: Sentiment = Field(
        ..., description="Sentiment of reviews in this theme (positive, mixed, negative)"
    )
    summary: str = Field(..., description="Brief factual summary of user feedback")
    action_rationale: str = Field(
        ..., description="Practical justification for a potential engineering/product action"
    )


class ThemeAnalysis(BaseModel):
    """Structured output contract for LangChain theme analysis."""

    model_config = ConfigDict(extra="forbid")

    candidate_themes: list[CandidateTheme] = Field(
        ...,
        max_length=10,
        description="Candidate themes identified from the review batch",
    )
    unassigned_review_ids: list[str] = Field(
        default_factory=list,
        description="Review IDs not fitting into any prominent theme",
    )


class ThemeSummaryDraft(BaseModel):
    """Theme summary component in a pulse draft."""

    model_config = ConfigDict(extra="forbid")

    theme_id: str = Field(..., min_length=1, description="Theme identifier")
    label: str = Field(..., min_length=1, description="Theme label")
    summary: str = Field(
        ..., min_length=1, description="Short evidence-based summary with volume/sentiment context"
    )


class QuoteDraft(BaseModel):
    """Quote component in a pulse draft."""

    model_config = ConfigDict(extra="forbid")

    source_review_id: str = Field(..., min_length=1, description="Source review ID for provenance")
    quote_text: str = Field(..., min_length=1, description="Verbatim sanitized quote text")


class ActionDraft(BaseModel):
    """Action component in a pulse draft."""

    model_config = ConfigDict(extra="forbid")

    theme_id: str = Field(..., min_length=1, description="Associated theme ID")
    action_text: str = Field(..., min_length=1, description="Concrete action item")


class PulseDraft(BaseModel):
    """Structured output contract for LangChain weekly pulse generation."""

    model_config = ConfigDict(extra="forbid")

    themes: list[ThemeSummaryDraft] = Field(
        ..., min_length=3, max_length=3, description="Exactly 3 top theme summaries"
    )
    quotes: list[QuoteDraft] = Field(
        ..., min_length=3, max_length=3, description="Exactly 3 verbatim quotes"
    )
    actions: list[ActionDraft] = Field(
        ..., min_length=3, max_length=3, description="Exactly 3 recommended actions"
    )


class WeeklyPulse(BaseModel):
    """Completed, validated weekly pulse ready for stakeholder delivery."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    week_ending: date = Field(..., description="Date marking the end of the pulse week")
    top_themes: list[Theme] = Field(
        ..., min_length=3, max_length=3, description="Exactly three ranked top themes"
    )
    quotes: list[Quote] = Field(
        ..., min_length=3, max_length=3, description="Exactly three selected quotes"
    )
    actions: list[Action] = Field(
        ..., min_length=3, max_length=3, description="Exactly three grounded actions"
    )
    markdown: str = Field(..., min_length=1, description="Rendered Markdown note")
    word_count: int = Field(
        ..., ge=1, le=250, description="Word count of stakeholder text (must be <= 250)"
    )


class Run(BaseModel):
    """Execution record for an end-to-end pulse run."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., description="Unique run identifier (e.g., UUID)")
    started_at: datetime = Field(..., description="Run start timestamp")
    cutoff_date: date = Field(..., description="Earliest review date included in the run")
    status: RunStatus = Field(default=RunStatus.RUNNING, description="Current execution status")
    review_count: int = Field(default=0, ge=0, description="Number of safe reviews processed")
    document_id: str | None = Field(default=None, description="Google Doc ID created via MCP")
    document_url: str | None = Field(default=None, description="Google Doc URL created via MCP")
    gmail_draft_id: str | None = Field(default=None, description="Gmail draft ID created via MCP")
    error_summary: str | None = Field(
        default=None, description="Non-sensitive error summary if failed/blocked"
    )
    model_id: str | None = Field(
        default=None, description="Identifier of the LLM used (e.g., gpt-4o-mini)"
    )
    prompt_version: str | None = Field(
        default=None, description="Version of the prompt templates used"
    )
