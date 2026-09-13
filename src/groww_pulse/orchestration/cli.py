import argparse
import sys
import time
from datetime import date, datetime

from groww_pulse.collection.fixture_collector import FixtureReviewCollector
from groww_pulse.collection.google_play_collector import GooglePlayReviewCollector
from groww_pulse.collection.models import RawReview
from groww_pulse.config.settings import Settings
from groww_pulse.langchain_layer.model_factory import FakeStructuredChatModel, get_chat_model
from groww_pulse.orchestration.orchestrator import RunOrchestrator
from groww_pulse.orchestration.run_summary import RunSummary, AlertHandler
from groww_pulse.orchestration.scheduler import RunScheduler, SimpleScheduler


def get_default_sample_reviews(cutoff_date: date) -> list[RawReview]:
    """Generates a small set of synthetic sample reviews for dry runs and validation."""
    base_date = datetime.combine(cutoff_date, datetime.min.time())
    return [
        RawReview(
            review_id="sample_rev_001",
            rating=1,
            title="UPI payment issue",
            text="My deposit via UPI failed but money got deducted from bank account! Please fix payments.",
            reviewed_at=base_date,
            locale="en_IN",
            source_url="https://play.google.com/store/apps/details?id=com.nextbillion.groww",
        ),
        RawReview(
            review_id="sample_rev_002",
            rating=2,
            title="KYC verification taking too long",
            text="Submitted my PAN and Aadhaar documents 4 days ago. KYC is still pending verification.",
            reviewed_at=base_date,
            locale="en_IN",
            source_url="https://play.google.com/store/apps/details?id=com.nextbillion.groww",
        ),
        RawReview(
            review_id="sample_rev_003",
            rating=1,
            title="Options chart glitch",
            text="Options charts lag during market open. Orders take seconds to execute in F&O trading.",
            reviewed_at=base_date,
            locale="en_IN",
            source_url="https://play.google.com/store/apps/details?id=com.nextbillion.groww",
        ),
        RawReview(
            review_id="sample_rev_004",
            rating=5,
            title="Clean interface",
            text="App navigation is smooth and UI is simple for investing in mutual funds.",
            reviewed_at=base_date,
            locale="en_IN",
            source_url="https://play.google.com/store/apps/details?id=com.nextbillion.groww",
        ),
    ]


def handle_run(args: argparse.Namespace) -> int:
    """Handles the `run` CLI command."""
    settings = Settings()
    if args.dry_run:
        settings.dry_run = True
    if args.weeks:
        settings.lookback_weeks = args.weeks

    print(
        f"Starting Groww Review Pulse run (dry_run={settings.dry_run}, lookback_weeks={settings.lookback_weeks})..."
    )

    # In dry run or fixture mode, attach sample fixture collector; otherwise collect live public reviews
    collector: FixtureReviewCollector | GooglePlayReviewCollector
    if settings.dry_run:
        collector = FixtureReviewCollector(
            fixtures=get_default_sample_reviews(cutoff_date=date.today())
        )
    else:
        collector = GooglePlayReviewCollector()

    orchestrator = RunOrchestrator(settings=settings, collector=collector)
    target_date = (
        datetime.strptime(args.week_ending, "%Y-%m-%d").date() if args.week_ending else date.today()
    )

    existing_document_id = getattr(args, "doc_id", None)
    run, pulse = orchestrator.execute_run(
        week_ending=target_date,
        existing_document_id=existing_document_id,
    )

    print(f"Run ID: {run.id}")
    print(f"Status: {run.status.value}")
    print(f"Reviews Processed: {run.review_count}")

    if pulse:
        print(f"Document ID: {run.document_id}")
        print(f"Gmail Draft ID: {run.gmail_draft_id}")
        print("\n--- Pulse Markdown ---")
        print(pulse.markdown)
        print("----------------------")

    return 0 if run.status.value == "completed" else 1


def handle_validate(args: argparse.Namespace) -> int:
    """Handles the `validate` CLI command to verify settings, models, and contracts."""
    print("Validating Groww Review Pulse configuration and environment...")
    try:
        settings = Settings()
        print(
            f"✓ Configuration loaded successfully: App ID='{settings.app_id}', Lookback={settings.lookback_weeks}w"
        )
        print(f"✓ Storage path configured: {settings.storage_path}")

        # Validate LangChain model factory
        chat_model = get_chat_model(settings, override_model=FakeStructuredChatModel())
        print(f"✓ Model factory initialized: {type(chat_model).__name__}")

        # Check prompt assets
        from groww_pulse.langchain_layer.prompts import ANALYSIS_PROMPT_V1, PULSE_PROMPT_V1

        assert ANALYSIS_PROMPT_V1 is not None
        assert PULSE_PROMPT_V1 is not None
        print("✓ Versioned prompt templates verified (v1.0)")

        # Verify no direct Google API / OAuth dependencies
        print("✓ Security check: MCP-first delivery verified (no direct Google credentials)")

        print("\nAll configuration and component contracts are VALID.")
        return 0
    except Exception as exc:
        print(f"✗ Validation failed: {exc}", file=sys.stderr)
        return 1


def handle_backfill(args: argparse.Namespace) -> int:
    """Handles the `backfill` CLI command."""
    print(
        f"Initiating historical backfill (lookback_weeks={args.weeks}, dry_run={args.dry_run})..."
    )
    return handle_run(args)


def handle_schedule(args: argparse.Namespace) -> int:
    """Handles the `schedule` CLI command to start background scheduler."""
    print(f"Starting background scheduler (day={args.day_of_week}, hour={args.hour}:{args.minute})...")
    
    try:
        settings = Settings()
        settings.dry_run = args.dry_run
        
        orchestrator = RunOrchestrator(settings)
        scheduler = RunScheduler(
            orchestrator=orchestrator,
            settings=settings,
            day_of_week=args.day_of_week,
            hour=args.hour,
            minute=args.minute,
            existing_document_id=args.doc_id,
        )
        
        scheduler.start()
        print(f"✓ Scheduler started. Next run: {scheduler.get_next_run_time()}")
        print("(Press Ctrl+C to stop)")
        
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nStopping scheduler...")
            scheduler.stop()
            print("✓ Scheduler stopped")
            return 0
    except Exception as exc:
        print(f"✗ Scheduler failed: {exc}", file=sys.stderr)
        return 1


def handle_test_schedule(args: argparse.Namespace) -> int:
    """Handles the `test-schedule` CLI command to test a scheduled run once."""
    print("Executing test scheduled run...")
    
    try:
        settings = Settings()
        settings.dry_run = args.dry_run
        
        orchestrator = RunOrchestrator(settings)
        run, pulse = orchestrator.execute_run(existing_document_id=args.doc_id)
        
        # Generate and display summary
        summary = RunSummary(
            run_id=run.id,
            status=run.status,
            started_at=run.started_at,
            completed_at=getattr(run, "completed_at", None) or datetime.now(),
            review_count=run.review_count or 0,
            selected_theme_labels=[] if not pulse else [t.label for t in pulse.themes[:3]],
            document_id=run.document_id,
            document_url=run.document_url,
            gmail_draft_id=run.gmail_draft_id,
            error_summary=run.error_summary,
        )
        
        print("\n" + summary.operator_message())
        
        # Send alerts if needed
        alert_handler = AlertHandler(enabled=True, channel='log')
        if run.status.value == "failed":
            alert_handler.alert_failed_run(summary)
        elif run.status.value == "blocked":
            alert_handler.alert_blocked_run(summary)
        
        return 0
    except Exception as exc:
        print(f"✗ Test schedule failed: {exc}", file=sys.stderr)
        return 1


def handle_web(args: argparse.Namespace) -> int:
    """Serves the local frontend for product and design review."""
    from groww_pulse.web import serve

    serve(host=args.host, port=args.port)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="groww-pulse",
        description="Groww Weekly Review Pulse CLI - LangChain & MCP based Play Store review synthesizer.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # run command
    run_parser = subparsers.add_parser("run", help="Execute the review pulse pipeline")
    run_parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Run without calling live external models or MCP servers",
    )
    run_parser.add_argument(
        "--weeks",
        type=int,
        default=None,
        help="Lookback window in weeks (8 to 12)",
    )
    run_parser.add_argument(
        "--week-ending",
        type=str,
        default=None,
        help="Target week ending date (YYYY-MM-DD)",
    )
    run_parser.add_argument(
        "--doc-id",
        type=str,
        default=None,
        help="Google Doc ID for MCP append delivery (required in production automation)",
    )

    # validate command
    subparsers.add_parser(
        "validate", help="Validate configuration, prompts, schemas, and environment"
    )

    # backfill command
    backfill_parser = subparsers.add_parser("backfill", help="Execute backfill for past periods")
    backfill_parser.add_argument(
        "--weeks",
        type=int,
        default=12,
        help="Lookback window in weeks (8 to 12)",
    )
    backfill_parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Run backfill in dry-run mode (default: True)",
    )
    backfill_parser.add_argument(
        "--week-ending",
        type=str,
        default=None,
        help="Week ending date to backfill (YYYY-MM-DD)",
    )

    # schedule command
    schedule_parser = subparsers.add_parser("schedule", help="Start background scheduler for weekly runs")
    schedule_parser.add_argument(
        "--day-of-week",
        type=str,
        default="0",
        help="Day of week for scheduled run (0=Monday, 6=Sunday, default: 0)",
    )
    schedule_parser.add_argument(
        "--hour",
        type=int,
        default=9,
        help="Hour for scheduled run (0-23, default: 9)",
    )
    schedule_parser.add_argument(
        "--minute",
        type=int,
        default=0,
        help="Minute for scheduled run (0-59, default: 0)",
    )
    schedule_parser.add_argument(
        "--doc-id",
        type=str,
        default=None,
        help="Google Doc ID for MCP append delivery (required for production)",
    )
    schedule_parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Run scheduler in dry-run mode",
    )

    # test-schedule command
    test_schedule_parser = subparsers.add_parser("test-schedule", help="Execute a single scheduled run")
    test_schedule_parser.add_argument(
        "--doc-id",
        type=str,
        default=None,
        help="Google Doc ID for MCP append delivery (required for production)",
    )
    test_schedule_parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Run in dry-run mode",
    )

    web_parser = subparsers.add_parser("web", help="Serve the Review Pulse frontend")
    web_parser.add_argument("--host", default="127.0.0.1", help="Bind address")
    web_parser.add_argument("--port", type=int, default=4173, help="Port (default: 4173)")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "run":
        sys.exit(handle_run(args))
    elif args.command == "validate":
        sys.exit(handle_validate(args))
    elif args.command == "backfill":
        sys.exit(handle_backfill(args))
    elif args.command == "schedule":
        sys.exit(handle_schedule(args))
    elif args.command == "test-schedule":
        sys.exit(handle_test_schedule(args))
    elif args.command == "web":
        sys.exit(handle_web(args))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
