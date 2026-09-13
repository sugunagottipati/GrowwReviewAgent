import uuid
from collections.abc import Sequence
from datetime import date, datetime, timedelta

from groww_pulse.analysis.base import ActionPlanner, QuoteSelector, ThemeAnalyzer
from groww_pulse.analysis.baseline import (
    BaselineActionPlanner,
    BaselineQuoteSelector,
    BaselineThemeAnalyzer,
)
from groww_pulse.collection.base import ReviewCollector
from groww_pulse.collection.fixture_collector import FixtureReviewCollector
from groww_pulse.collection.models import RawReview
from groww_pulse.config.settings import Settings
from groww_pulse.domain.enums import RunStatus
from groww_pulse.domain.models import Run, WeeklyPulse
from groww_pulse.generation.base import PulseComposer, PulseValidator
from groww_pulse.generation.composer import StandardPulseComposer
from groww_pulse.generation.validator import StandardPulseValidator
from groww_pulse.integrations.base import DocsPort, GmailPort
from groww_pulse.integrations.fake_ports import FakeDocsPort, FakeGmailPort
from groww_pulse.logging_utils.logger import StructuredLogger, timed_stage
from groww_pulse.processing.base import PrivacyFilter, ReviewNormalizer, ReviewQualityFilter
from groww_pulse.processing.normalizer import StandardReviewNormalizer
from groww_pulse.processing.privacy_filter import DeterministicPrivacyFilter
from groww_pulse.processing.quality_filter import StandardReviewQualityFilter
from groww_pulse.storage.base import ReviewRepository, RunRepository
from groww_pulse.storage.sqlite_repository import SQLiteRepository


class RunOrchestrator:
    """Coordinates weekly review pulse execution across all pipeline stages."""

    def __init__(
        self,
        settings: Settings | None = None,
        collector: ReviewCollector | None = None,
        normalizer: ReviewNormalizer | None = None,
        privacy_filter: PrivacyFilter | None = None,
        quality_filter: ReviewQualityFilter | None = None,
        theme_analyzer: ThemeAnalyzer | None = None,
        quote_selector: QuoteSelector | None = None,
        action_planner: ActionPlanner | None = None,
        composer: PulseComposer | None = None,
        validator: PulseValidator | None = None,
        docs_port: DocsPort | None = None,
        gmail_port: GmailPort | None = None,
        review_repo: ReviewRepository | None = None,
        run_repo: RunRepository | None = None,
    ) -> None:
        self.settings = settings or Settings()
        self.normalizer = normalizer or StandardReviewNormalizer()
        self.privacy_filter = privacy_filter or DeterministicPrivacyFilter()
        self.quality_filter = quality_filter or StandardReviewQualityFilter()
        self.theme_analyzer = theme_analyzer or BaselineThemeAnalyzer()
        self.quote_selector = quote_selector or BaselineQuoteSelector()
        self.action_planner = action_planner or BaselineActionPlanner()
        self.composer = composer or StandardPulseComposer()
        self.validator = validator or StandardPulseValidator()

        # Wire collector
        self.collector = collector or FixtureReviewCollector()

        # Wire ports (fake in dry-run mode or defaults)
        self.docs_port = docs_port or FakeDocsPort()
        self.gmail_port = gmail_port or FakeGmailPort()

        # Wire repositories
        sqlite_repo = SQLiteRepository(self.settings.storage_path)
        self.review_repo = review_repo or sqlite_repo
        self.run_repo = run_repo or sqlite_repo


    def execute_run(
        self,
        week_ending: date | None = None,
        override_raw_reviews: Sequence[RawReview] | None = None,
        existing_document_id: str | None = None,
    ) -> tuple[Run, WeeklyPulse | None]:
        """Execute the full review pulse pipeline."""
        target_week_ending = week_ending or date.today()
        cutoff_date = target_week_ending - timedelta(weeks=self.settings.lookback_weeks)
        run_id = f"run_{uuid.uuid4().hex[:12]}"
        started_at = datetime.now()
        run = Run(
            id=run_id,
            started_at=started_at,
            cutoff_date=cutoff_date,
            status=RunStatus.RUNNING,
            model_id=self.settings.model_id,
            prompt_version=self.settings.prompt_version,
        )
        self.run_repo.create_run(run)

        StructuredLogger.info(
            "run_started",
            run_id=run.id,
            lookback_weeks=self.settings.lookback_weeks,
            dry_run=self.settings.dry_run,
        )

        try:
            # Stage 1: Collection
            with timed_stage("collection", run_id=run.id) as metrics:
                if override_raw_reviews is not None:
                    raw_reviews = override_raw_reviews
                else:
                    raw_reviews = self.collector.collect_reviews(
                        app_id=self.settings.app_id,
                        cutoff_date=cutoff_date,
                        locale=self.settings.locale,
                    )
                metrics["records_received"] = len(raw_reviews)

            # Stage 2: Normalization & Privacy Filtering
            with timed_stage("normalization_and_privacy", run_id=run.id) as metrics:
                normalized = self.normalizer.normalize(raw_reviews)
                privacy_safe_reviews, redacted_count, dropped_count = self.privacy_filter.sanitize(
                    normalized
                )
                safe_reviews, too_short_count, non_english_count = self.quality_filter.filter(
                    privacy_safe_reviews
                )
                metrics["sanitized_count"] = len(safe_reviews)
                metrics["redacted_count"] = redacted_count
                metrics["dropped_count"] = dropped_count
                metrics["too_short_count"] = too_short_count
                metrics["non_english_count"] = non_english_count

            # Stage 3: Persistence
            with timed_stage("persistence", run_id=run.id) as metrics:
                saved_count = self.review_repo.save_reviews(safe_reviews)
                metrics["count"] = saved_count
                run.review_count = len(safe_reviews)

            if len(safe_reviews) < 3:
                run.status = RunStatus.BLOCKED
                run.error_summary = f"Insufficient safe reviews to generate pulse (found {len(safe_reviews)}, minimum required is 3)"
                self.run_repo.update_run(run)
                StructuredLogger.warning(
                    "run_blocked",
                    run_id=run.id,
                    review_count=len(safe_reviews),
                    rejection_reason=run.error_summary,
                )
                return run, None

            # Stage 4: Theme Analysis & Evidence Selection
            with timed_stage("theme_analysis", run_id=run.id) as metrics:
                ranked_themes = self.theme_analyzer.analyze_themes(safe_reviews)
                metrics["theme_count"] = len(ranked_themes)

            if len(ranked_themes) < 3:
                run.status = RunStatus.BLOCKED
                run.error_summary = f"Insufficient distinct themes identified ({len(ranked_themes)} found, 3 required)"
                self.run_repo.update_run(run)
                return run, None

            # Top 3 themes
            top_3_themes = list(ranked_themes[:3])

            with timed_stage("quote_selection", run_id=run.id) as metrics:
                selected_quotes = self.quote_selector.select_quotes(
                    top_3_themes, safe_reviews, target_count=3
                )
                metrics["quote_count"] = len(selected_quotes)

            with timed_stage("action_planning", run_id=run.id) as metrics:
                actions = self.action_planner.plan_actions(top_3_themes, safe_reviews)
                metrics["action_count"] = len(actions)

            # Stage 5: Pulse Composition & Validation
            with timed_stage("pulse_composition", run_id=run.id) as metrics:
                pulse = self.composer.compose(
                    week_ending=target_week_ending,
                    themes=top_3_themes,
                    quotes=selected_quotes,
                    actions=actions,
                )
                metrics["word_count"] = pulse.word_count

            with timed_stage("pulse_validation", run_id=run.id) as metrics:
                is_valid, validation_errors = self.validator.validate(pulse, selected_quotes)
                if not is_valid:
                    run.status = RunStatus.FAILED
                    run.error_summary = f"Validation failed: {'; '.join(validation_errors)}"
                    self.run_repo.update_run(run)
                    StructuredLogger.error(
                        "pulse_validation_failed",
                        run_id=run.id,
                        error_summary=run.error_summary,
                    )
                    return run, None

            # Stage 6: Delivery via MCP (Google Docs and Gmail Draft)
            with timed_stage("delivery", run_id=run.id) as metrics:
                # Determine document ID for MCP delivery
                doc_id_to_use = existing_document_id
                if not doc_id_to_use and not self.settings.dry_run:
                    raise ValueError(
                        "Production MCP delivery requires existing_document_id (pre-created Google Doc ID). "
                        "Pass existing_document_id parameter to execute_run()."
                    )
                
                if not self.settings.dry_run:
                    doc_id, doc_url = self.docs_port.create_or_update_document(
                        title=f"Groww Weekly Review Pulse - Week Ending {target_week_ending.strftime('%Y-%m-%d')}",
                        content=pulse.markdown,
                        existing_document_id=doc_id_to_use,
                    )
                    run.document_id = doc_id
                    run.document_url = doc_url

                    email_body = (
                        self.composer.render_email_body(pulse, doc_url)
                        if hasattr(self.composer, "render_email_body")
                        else pulse.markdown
                    )
                    draft_id = self.gmail_port.create_draft(
                        to_address=self.settings.recipient_alias,
                        subject=f"Groww Weekly Review Pulse - Week Ending {target_week_ending.strftime('%Y-%m-%d')}",
                        body=email_body,
                    )
                    run.gmail_draft_id = draft_id
                else:
                    # In dry run, simulate delivery using fake ports without external API calls
                    doc_id, doc_url = self.docs_port.create_or_update_document(
                        title=f"[DRY RUN] Groww Weekly Review Pulse - Week Ending {target_week_ending.strftime('%Y-%m-%d')}",
                        content=pulse.markdown,
                        existing_document_id=doc_id_to_use,
                    )
                    run.document_id = doc_id
                    run.document_url = doc_url
                    draft_id = self.gmail_port.create_draft(
                        to_address=self.settings.recipient_alias,
                        subject=f"[DRY RUN] Groww Weekly Review Pulse - Week Ending {target_week_ending.strftime('%Y-%m-%d')}",
                        body=pulse.markdown,
                    )
                    run.gmail_draft_id = draft_id

                metrics["document_id"] = run.document_id
                metrics["gmail_draft_id"] = run.gmail_draft_id

            run.status = RunStatus.COMPLETED
            self.run_repo.update_run(run)
            StructuredLogger.info(
                "run_completed",
                run_id=run.id,
                review_count=run.review_count,
                document_id=run.document_id,
                gmail_draft_id=run.gmail_draft_id,
                status="completed",
            )
            return run, pulse

        except Exception as exc:
            run.status = RunStatus.FAILED
            run.error_summary = str(exc)[:200]
            self.run_repo.update_run(run)
            StructuredLogger.error("run_failed", run_id=run.id, error_summary=run.error_summary)
            raise
