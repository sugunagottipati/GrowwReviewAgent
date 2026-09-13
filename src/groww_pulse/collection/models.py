from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CollectionMetrics(BaseModel):
    """Provider-safe collection metrics for a single collect_reviews call."""

    model_config = ConfigDict(extra="ignore")

    pages_read: int = Field(default=0, ge=0, description="Number of source pages fetched")
    records_received: int = Field(
        default=0, ge=0, description="Total records received from the source, before filtering"
    )
    records_in_window: int = Field(
        default=0, ge=0, description="Records within the configured cutoff date window"
    )
    provider_errors: list[str] = Field(
        default_factory=list,
        description="Provider-safe error type descriptions encountered during collection",
    )


class CollectionError(Exception):
    """Raised when a source page cannot be retrieved after the retry budget is exhausted."""


class RawReview(BaseModel):
    """In-memory representation of a public review prior to privacy filtering and normalization."""

    model_config = ConfigDict(extra="ignore")

    review_id: str = Field(..., description="Source review ID from public store")
    rating: int = Field(..., ge=1, le=5, description="Star rating 1-5")
    title: str | None = Field(default=None, description="Review title if provided")
    text: str = Field(..., description="Review body text")
    reviewed_at: datetime = Field(..., description="Timestamp of the review")
    locale: str | None = Field(default="en_IN", description="Review locale")
    source_url: str = Field(default="", description="Public review URL")
