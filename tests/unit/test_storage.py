from datetime import date, datetime
from pathlib import Path

from groww_pulse.domain.enums import RunStatus
from groww_pulse.domain.models import Review, Run
from groww_pulse.storage.in_memory_repository import InMemoryRepository
from groww_pulse.storage.sqlite_repository import SQLiteRepository


def test_sqlite_repository_save_and_retrieve(tmp_path: Path) -> None:
    db_file = tmp_path / "test_pulse.db"
    repo = SQLiteRepository(db_file)

    review1 = Review(
        source_review_id="r1",
        rating=1,
        title="UPI fail",
        text="Payment failed in UPI transfer",
        reviewed_at=datetime(2026, 8, 20, 10, 0, 0),
        locale="en_IN",
        source_url="https://play.google.com/store",
        content_hash="hash1",
    )
    review2 = Review(
        source_review_id="r2",
        rating=5,
        title="Good app",
        text="Very fast stock orders",
        reviewed_at=datetime(2026, 8, 21, 10, 0, 0),
        locale="en_IN",
        source_url="https://play.google.com/store",
        content_hash="hash2",
    )

    # First save
    saved = repo.save_reviews([review1, review2])
    assert saved == 2

    # Idempotent re-save of same source IDs
    saved_again = repo.save_reviews([review1])
    assert saved_again == 0

    retrieved = repo.get_reviews()
    assert len(retrieved) == 2
    assert retrieved[0].source_review_id in ("r1", "r2")


def test_sqlite_repository_run_lifecycle(tmp_path: Path) -> None:
    db_file = tmp_path / "test_pulse.db"
    repo = SQLiteRepository(db_file)

    run = Run(
        id="run_100",
        started_at=datetime(2026, 8, 30, 9, 0, 0),
        cutoff_date=date(2026, 6, 7),
        status=RunStatus.RUNNING,
        review_count=0,
    )
    repo.create_run(run)

    fetched = repo.get_run("run_100")
    assert fetched is not None
    assert fetched.status == RunStatus.RUNNING

    # Update run
    run.status = RunStatus.COMPLETED
    run.review_count = 50
    run.document_id = "doc_xyz"
    run.document_url = "https://docs.google.com/doc_xyz"
    run.gmail_draft_id = "draft_abc"
    repo.update_run(run)

    updated = repo.get_run("run_100")
    assert updated is not None
    assert updated.status == RunStatus.COMPLETED
    assert updated.document_id == "doc_xyz"
    assert updated.gmail_draft_id == "draft_abc"
    assert updated.review_count == 50


def test_in_memory_repository() -> None:
    repo = InMemoryRepository()
    review = Review(
        source_review_id="r1",
        rating=4,
        title=None,
        text="Good investing experience",
        reviewed_at=datetime.now(),
        locale="en_IN",
        source_url="",
        content_hash="hash",
    )
    assert repo.save_reviews([review]) == 1
    assert repo.save_reviews([review]) == 0
    assert len(repo.get_reviews()) == 1
