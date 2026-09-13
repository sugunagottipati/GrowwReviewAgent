import json
from datetime import date, datetime
from pathlib import Path

from groww_pulse.collection.fixture_collector import FixtureReviewCollector
from groww_pulse.collection.models import RawReview
from groww_pulse.config.settings import Settings
from groww_pulse.domain.enums import RunStatus
from groww_pulse.integrations.fake_ports import FakeDocsPort, FakeGmailPort
from groww_pulse.orchestration.orchestrator import RunOrchestrator
from groww_pulse.storage.sqlite_repository import SQLiteRepository


def load_synthetic_fixtures() -> list[RawReview]:
    fixture_path = Path(__file__).parents[1] / "fixtures" / "synthetic_reviews.json"
    with open(fixture_path, encoding="utf-8") as f:
        data = json.load(f)

    return [
        RawReview(
            review_id=item["review_id"],
            rating=item["rating"],
            title=item.get("title"),
            text=item["text"],
            reviewed_at=datetime.fromisoformat(item["reviewed_at"]),
            locale=item.get("locale", "en_IN"),
            source_url=item.get("source_url", ""),
        )
        for item in data
    ]


def test_pipeline_dry_run_with_synthetic_fixtures(tmp_path: Path) -> None:
    db_path = tmp_path / "pulse_test.db"
    settings = Settings(
        dry_run=True,
        storage_path=db_path,
        lookback_weeks=12,
        model_provider="fake",
    )

    raw_fixtures = load_synthetic_fixtures()
    collector = FixtureReviewCollector(fixtures=raw_fixtures)
    docs_port = FakeDocsPort()
    gmail_port = FakeGmailPort()
    sqlite_repo = SQLiteRepository(db_path)

    orchestrator = RunOrchestrator(
        settings=settings,
        collector=collector,
        docs_port=docs_port,
        gmail_port=gmail_port,
        review_repo=sqlite_repo,
        run_repo=sqlite_repo,
    )

    run, pulse = orchestrator.execute_run(week_ending=date(2026, 8, 30))

    # Assert run completed successfully
    assert run.status == RunStatus.COMPLETED
    assert run.review_count == len(raw_fixtures)
    assert run.document_id is not None
    assert run.gmail_draft_id is not None
    assert run.error_summary is None

    # Assert pulse content constraints
    assert pulse is not None
    assert len(pulse.top_themes) == 3
    assert len(pulse.quotes) == 3
    assert len(pulse.actions) == 3
    assert pulse.word_count <= 250
    assert "## Top Themes" in pulse.markdown
    assert "## What Users Said" in pulse.markdown
    assert "## Recommended Actions" in pulse.markdown

    # Assert Docs and Gmail fake ports received requests
    assert len(docs_port.created_docs) == 1
    assert len(gmail_port.created_drafts) == 1

    # Assert reviews are persisted in database without PII (email / phone)
    persisted_reviews = sqlite_repo.get_reviews()
    assert len(persisted_reviews) == len(raw_fixtures)
    for r in persisted_reviews:
        assert "user.test@example.com" not in r.text
        assert "9876543210" not in r.text
