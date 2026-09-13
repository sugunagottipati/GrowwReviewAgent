import sqlite3
from collections.abc import Sequence
from datetime import date, datetime
from pathlib import Path

from groww_pulse.domain.enums import RunStatus
from groww_pulse.domain.models import Review, Run
from groww_pulse.storage.base import ReviewRepository, RunRepository


class SQLiteRepository(ReviewRepository, RunRepository):
    """SQLite-backed persistent store for sanitized reviews and pipeline runs."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sanitized_reviews (
                    source_review_id TEXT PRIMARY KEY,
                    rating INTEGER NOT NULL,
                    title TEXT,
                    text TEXT NOT NULL,
                    reviewed_at TEXT NOT NULL,
                    locale TEXT,
                    source_url TEXT,
                    content_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY,
                    started_at TEXT NOT NULL,
                    cutoff_date TEXT NOT NULL,
                    status TEXT NOT NULL,
                    review_count INTEGER NOT NULL DEFAULT 0,
                    document_id TEXT,
                    document_url TEXT,
                    gmail_draft_id TEXT,
                    error_summary TEXT,
                    model_id TEXT,
                    prompt_version TEXT
                )
                """
            )
            conn.commit()

    def save_reviews(self, reviews: Sequence[Review]) -> int:
        if not reviews:
            return 0

        now_iso = datetime.now().isoformat()
        inserted_count = 0

        with self._get_connection() as conn:
            for r in reviews:
                cursor = conn.execute(
                    """
                    INSERT INTO sanitized_reviews (
                        source_review_id, rating, title, text, reviewed_at,
                        locale, source_url, content_hash, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(source_review_id) DO NOTHING
                    """,
                    (
                        r.source_review_id,
                        r.rating,
                        r.title,
                        r.text,
                        r.reviewed_at.isoformat(),
                        r.locale,
                        r.source_url,
                        r.content_hash,
                        now_iso,
                    ),
                )
                inserted_count += cursor.rowcount
            conn.commit()

        return inserted_count

    def get_reviews(self, limit: int = 1000) -> Sequence[Review]:
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT source_review_id, rating, title, text, reviewed_at, locale, source_url, content_hash
                FROM sanitized_reviews
                ORDER BY reviewed_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

            return [
                Review(
                    source_review_id=row["source_review_id"],
                    rating=row["rating"],
                    title=row["title"],
                    text=row["text"],
                    reviewed_at=datetime.fromisoformat(row["reviewed_at"]),
                    locale=row["locale"],
                    source_url=row["source_url"],
                    content_hash=row["content_hash"],
                )
                for row in rows
            ]

    def create_run(self, run: Run) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO runs (
                    id, started_at, cutoff_date, status, review_count,
                    document_id, document_url, gmail_draft_id, error_summary,
                    model_id, prompt_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run.id,
                    run.started_at.isoformat(),
                    run.cutoff_date.isoformat(),
                    run.status.value,
                    run.review_count,
                    run.document_id,
                    run.document_url,
                    run.gmail_draft_id,
                    run.error_summary,
                    run.model_id,
                    run.prompt_version,
                ),
            )
            conn.commit()

    def update_run(self, run: Run) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE runs SET
                    status = ?,
                    review_count = ?,
                    document_id = ?,
                    document_url = ?,
                    gmail_draft_id = ?,
                    error_summary = ?,
                    model_id = ?,
                    prompt_version = ?
                WHERE id = ?
                """,
                (
                    run.status.value,
                    run.review_count,
                    run.document_id,
                    run.document_url,
                    run.gmail_draft_id,
                    run.error_summary,
                    run.model_id,
                    run.prompt_version,
                    run.id,
                ),
            )
            conn.commit()

    def get_run(self, run_id: str) -> Run | None:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()

            if not row:
                return None

            return Run(
                id=row["id"],
                started_at=datetime.fromisoformat(row["started_at"]),
                cutoff_date=date.fromisoformat(row["cutoff_date"]),
                status=RunStatus(row["status"]),
                review_count=row["review_count"],
                document_id=row["document_id"],
                document_url=row["document_url"],
                gmail_draft_id=row["gmail_draft_id"],
                error_summary=row["error_summary"],
                model_id=row["model_id"],
                prompt_version=row["prompt_version"],
            )

    def list_runs(self, limit: int = 50) -> Sequence[Run]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM runs ORDER BY started_at DESC LIMIT ?", (limit,)
            ).fetchall()

            return [
                Run(
                    id=row["id"],
                    started_at=datetime.fromisoformat(row["started_at"]),
                    cutoff_date=date.fromisoformat(row["cutoff_date"]),
                    status=RunStatus(row["status"]),
                    review_count=row["review_count"],
                    document_id=row["document_id"],
                    document_url=row["document_url"],
                    gmail_draft_id=row["gmail_draft_id"],
                    error_summary=row["error_summary"],
                    model_id=row["model_id"],
                    prompt_version=row["prompt_version"],
                )
                for row in rows
            ]
