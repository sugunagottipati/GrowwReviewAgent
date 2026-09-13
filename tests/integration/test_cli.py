from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock, patch

from groww_pulse.orchestration.cli import build_parser, handle_run, handle_schedule, handle_validate
from groww_pulse.orchestration.scheduler import RunScheduler


def test_cli_validate_command() -> None:
    parser = build_parser()
    args = parser.parse_args(["validate"])
    exit_code = handle_validate(args)
    assert exit_code == 0


def test_cli_run_dry_run_command() -> None:
    parser = build_parser()
    args = parser.parse_args(["run", "--dry-run", "--weeks", "12"])
    exit_code = handle_run(args)
    assert exit_code == 0


def test_cli_run_accepts_doc_id_for_automation() -> None:
    parser = build_parser()
    args = parser.parse_args(["run", "--doc-id", "abc123", "--weeks", "12"])
    assert args.doc_id == "abc123"

    fake_run = SimpleNamespace(
        id="run_123",
        status=SimpleNamespace(value="completed"),
        review_count=12,
        document_id="doc_123",
        gmail_draft_id="draft_123",
    )

    with patch("groww_pulse.orchestration.cli.RunOrchestrator") as mock_orchestrator_cls:
        mock_orchestrator = mock_orchestrator_cls.return_value
        mock_orchestrator.execute_run.return_value = (fake_run, None)

        exit_code = handle_run(args)

    assert exit_code == 0
    _, kwargs = mock_orchestrator.execute_run.call_args
    assert kwargs["existing_document_id"] == "abc123"
    assert kwargs["week_ending"] == date.today()


def test_scheduler_passes_doc_id_to_orchestrator() -> None:
    orchestrator = Mock()
    fake_run = SimpleNamespace(id="run_123", status=SimpleNamespace(value="completed"))
    orchestrator.execute_run.return_value = (fake_run, None)

    scheduler = RunScheduler(
        orchestrator=orchestrator,
        day_of_week="0",
        hour=9,
        minute=0,
        existing_document_id="doc_123",
    )

    scheduler._run_pulse()

    orchestrator.execute_run.assert_called_once_with(existing_document_id="doc_123")


def test_schedule_command_forwards_doc_id_to_scheduler() -> None:
    parser = build_parser()
    args = parser.parse_args(["schedule", "--day-of-week", "1", "--doc-id", "abc123", "--dry-run"])

    with patch("groww_pulse.orchestration.cli.RunOrchestrator") as mock_orchestrator_cls:
        with patch("groww_pulse.orchestration.cli.RunScheduler") as mock_scheduler_cls:
            mock_scheduler = mock_scheduler_cls.return_value
            mock_scheduler.get_next_run_time.return_value = None

            with patch("time.sleep", side_effect=KeyboardInterrupt):
                exit_code = handle_schedule(args)

    assert exit_code == 0
    call_kwargs = mock_scheduler_cls.call_args.kwargs
    assert call_kwargs["orchestrator"] == mock_orchestrator_cls.return_value
    assert call_kwargs["day_of_week"] == "1"
    assert call_kwargs["existing_document_id"] == "abc123"
