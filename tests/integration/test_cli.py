from types import SimpleNamespace
from unittest.mock import patch

from groww_pulse.orchestration.cli import build_parser, handle_run, handle_validate


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
    mock_orchestrator.execute_run.assert_called_once_with(
        week_ending=None,
        existing_document_id="abc123",
    )
