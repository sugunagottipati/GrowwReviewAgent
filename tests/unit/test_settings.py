from pathlib import Path

import pytest
from pydantic import ValidationError

from groww_pulse.config.settings import Settings


def test_default_settings() -> None:
    settings = Settings()
    assert settings.app_id == "com.nextbillion.groww"
    assert settings.lookback_weeks == 12
    assert settings.locale == "en_IN"
    assert settings.model_provider == "openai"
    assert settings.model_id == "gpt-4o-mini"
    assert settings.dry_run is False
    assert settings.mcp_docs_server_name == "google_docs"
    assert settings.mcp_gmail_server_name == "gmail"


def test_default_model_rate_limits() -> None:
    settings = Settings()
    assert settings.model_requests_per_minute == 30
    assert settings.model_requests_per_day == 1000
    assert settings.model_tokens_per_minute == 8000
    assert settings.model_tokens_per_day == 200000


def test_lookback_weeks_boundary() -> None:
    # 8 and 12 are valid
    s8 = Settings(lookback_weeks=8)
    assert s8.lookback_weeks == 8

    s12 = Settings(lookback_weeks=12)
    assert s12.lookback_weeks == 12

    # < 8 or > 12 are invalid
    with pytest.raises(ValidationError):
        Settings(lookback_weeks=7)

    with pytest.raises(ValidationError):
        Settings(lookback_weeks=13)


def test_custom_environment_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROWW_PULSE_LOOKBACK_WEEKS", "10")
    monkeypatch.setenv("GROWW_PULSE_DRY_RUN", "true")
    monkeypatch.setenv("GROWW_PULSE_MODEL_ID", "gpt-4o")

    settings = Settings()
    assert settings.lookback_weeks == 10
    assert settings.dry_run is True
    assert settings.model_id == "gpt-4o"


def test_railway_volume_defaults_storage_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("GROWW_PULSE_STORAGE_PATH", raising=False)
    monkeypatch.setenv("RAILWAY_VOLUME_MOUNT_PATH", str(tmp_path))

    settings = Settings()

    assert settings.storage_path == tmp_path / "groww_pulse.db"


def test_storage_path_env_overrides_railway_volume(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    explicit_path = tmp_path / "explicit.db"
    monkeypatch.setenv("RAILWAY_VOLUME_MOUNT_PATH", str(tmp_path / "volume"))
    monkeypatch.setenv("GROWW_PULSE_STORAGE_PATH", str(explicit_path))

    settings = Settings()

    assert settings.storage_path == explicit_path
