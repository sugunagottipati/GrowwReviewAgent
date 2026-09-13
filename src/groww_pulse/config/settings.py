import os
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_storage_path() -> Path:
    railway_volume = os.getenv("RAILWAY_VOLUME_MOUNT_PATH")
    if railway_volume:
        return Path(railway_volume) / "groww_pulse.db"
    return Path("./data/groww_pulse.db")


class Settings(BaseSettings):
    """Application configuration contract."""

    model_config = SettingsConfigDict(
        env_prefix="GROWW_PULSE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Review source configuration
    app_id: str = Field(
        default="com.nextbillion.groww",
        description="Google Play Store application ID",
    )
    locale: str = Field(
        default="en_IN",
        description="Target review locale code",
    )
    lookback_weeks: int = Field(
        default=12,
        ge=8,
        le=12,
        description="Number of weeks to look back (restricted to 8-12 weeks)",
    )

    # Stakeholder and delivery configuration
    recipient_alias: str = Field(
        default="pulse-subscribers@groww.in",
        description="Email address or alias for weekly pulse distribution draft",
    )
    storage_path: Path = Field(
        default_factory=_default_storage_path,
        description="Filesystem path for the SQLite repository",
    )

    # MCP server and tool names
    mcp_docs_server_name: str = Field(
        default="google_docs",
        description="MCP server identifier for Google Docs operations",
    )
    mcp_docs_tool_create: str = Field(
        default="create_document",
        description="MCP tool name for document creation",
    )
    mcp_docs_tool_update: str = Field(
        default="update_document",
        description="MCP tool name for document updates",
    )
    mcp_gmail_server_name: str = Field(
        default="gmail",
        description="MCP server identifier for Gmail draft operations",
    )
    mcp_gmail_tool_create_draft: str = Field(
        default="create_draft",
        description="MCP tool name for creating unsent drafts",
    )

    # LangChain / AI Model configuration
    model_provider: str = Field(
        default="openai",
        description="LangChain model provider (e.g., 'openai', 'groq', 'gemini', 'fake')",
    )
    model_id: str = Field(
        default="gpt-4o-mini",
        description="Model identifier to use with the selected provider",
    )
    model_temperature: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Sampling temperature for deterministic outputs",
    )
    batch_size: int = Field(
        default=25,
        ge=1,
        le=100,
        description="Batch size for LLM review analysis",
    )
    timeout_seconds: int = Field(
        default=60,
        ge=5,
        le=300,
        description="Timeout in seconds for model invocations and external operations",
    )

    # Provider rate limits (e.g., Groq free tier: openai/gpt-oss-120b)
    model_requests_per_minute: int = Field(
        default=30,
        ge=1,
        description="Provider request-per-minute cap; used to throttle chat model calls",
    )
    model_requests_per_day: int = Field(
        default=1000,
        ge=1,
        description="Provider request-per-day cap (informational; not independently enforced)",
    )
    model_tokens_per_minute: int = Field(
        default=8000,
        ge=1,
        description="Provider token-per-minute cap; guides safe batch_size sizing",
    )
    model_tokens_per_day: int = Field(
        default=200000,
        ge=1,
        description="Provider token-per-day cap (informational; not independently enforced)",
    )

    # Execution flags
    dry_run: bool = Field(
        default=False,
        description="When True, prevents live LLM and MCP calls",
    )
    prompt_version: str = Field(
        default="v1.0",
        description="Version identifier for prompt assets",
    )

    @field_validator("lookback_weeks")
    @classmethod
    def validate_lookback_weeks(cls, v: int) -> int:
        if v < 8 or v > 12:
            raise ValueError(f"lookback_weeks must be between 8 and 12, got {v}")
        return v
