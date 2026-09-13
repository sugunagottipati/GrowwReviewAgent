"""Local static server for the Review Pulse frontend."""

from __future__ import annotations

import argparse
import functools
import json
import os
from datetime import date
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from groww_pulse.collection.fixture_collector import FixtureReviewCollector
from groww_pulse.collection.google_play_collector import GooglePlayReviewCollector
from groww_pulse.config.settings import Settings
from groww_pulse.integrations.http_mcp_client import make_http_mcp_tool_caller
from groww_pulse.integrations.mcp_adapters import MCPDocsAdapter, MCPGmailAdapter
from groww_pulse.orchestration.orchestrator import RunOrchestrator
from groww_pulse.storage.sqlite_repository import SQLiteRepository

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"


def _build_orchestrator(settings: Settings) -> RunOrchestrator:
    if settings.dry_run:
        from groww_pulse.orchestration.cli import get_default_sample_reviews

        collector = FixtureReviewCollector(fixtures=get_default_sample_reviews(date.today()))
    else:
        collector = GooglePlayReviewCollector()
    endpoint = os.getenv("GROWW_PULSE_MCP_HTTP_URL")
    if settings.dry_run or not endpoint:
        return RunOrchestrator(settings=settings, collector=collector)
    caller = make_http_mcp_tool_caller(endpoint)
    return RunOrchestrator(
        settings=settings,
        collector=collector,
        docs_port=MCPDocsAdapter(
            caller,
            server_name=settings.mcp_docs_server_name,
            append_tool_name=os.getenv("GROWW_PULSE_MCP_DOCS_TOOL_APPEND", "google_docs_append_content"),
        ),
        gmail_port=MCPGmailAdapter(
            caller,
            server_name=settings.mcp_gmail_server_name,
            create_draft_tool_name=os.getenv("GROWW_PULSE_MCP_GMAIL_TOOL_CREATE_DRAFT", "gmail_create_draft"),
        ),
    )


def _json_response(handler: SimpleHTTPRequestHandler, payload: object, status: int = 200) -> None:
    body = json.dumps(payload, default=str).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Access-Control-Allow-Origin", os.getenv("GROWW_PULSE_ALLOWED_ORIGIN", "*"))
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


class PulseRequestHandler(SimpleHTTPRequestHandler):
    """Static frontend handler plus the live pulse API."""

    def _repository(self) -> SQLiteRepository:
        return SQLiteRepository(Settings().storage_path)

    def do_OPTIONS(self) -> None:
        _json_response(self, {}, status=204)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        repository = self._repository()
        if path == "/api/health":
            _json_response(self, {"status": "ok"})
        elif path == "/api/pulse":
            latest = repository.get_latest_pulse()
            if latest is None:
                _json_response(self, {"pulse": None, "run": None})
                return
            run_id, pulse = latest
            run = repository.get_run(run_id)
            _json_response(
                self,
                {
                    "pulse": pulse.model_dump(mode="json"),
                    "run": run.model_dump(mode="json") if run else None,
                },
            )
        elif path == "/api/reviews":
            reviews = repository.get_reviews(limit=1000)
            _json_response(self, {"reviews": [review.model_dump(mode="json") for review in reviews]})
        elif path == "/api/runs":
            runs = repository.list_runs(limit=50)
            _json_response(self, {"runs": [run.model_dump(mode="json") for run in runs]})
        else:
            super().do_GET()

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/pulse/deliver":
            if not os.getenv("GROWW_PULSE_MCP_HTTP_URL"):
                _json_response(
                    self,
                    {
                        "error": "MCP delivery is not configured on Railway. Configure GROWW_PULSE_MCP_HTTP_URL and a tool caller before delivering.",
                        "status": "not_configured",
                    },
                    status=503,
                )
                return
            latest = self._repository().get_latest_pulse()
            if latest is None:
                _json_response(self, {"error": "No completed pulse is available to deliver."}, status=422)
                return
            run_id, pulse = latest
            settings = Settings()
            run = self._repository().get_run(run_id)
            caller = make_http_mcp_tool_caller(os.environ["GROWW_PULSE_MCP_HTTP_URL"])
            docs = MCPDocsAdapter(caller, server_name=settings.mcp_docs_server_name, append_tool_name=os.getenv("GROWW_PULSE_MCP_DOCS_TOOL_APPEND", "google_docs_append_content"))
            gmail = MCPGmailAdapter(caller, server_name=settings.mcp_gmail_server_name, create_draft_tool_name=os.getenv("GROWW_PULSE_MCP_GMAIL_TOOL_CREATE_DRAFT", "gmail_create_draft"))
            document_id, document_url = docs.create_or_update_document(
                title=f"Groww Weekly Review Pulse - Week Ending {pulse.week_ending}",
                content=pulse.markdown,
                existing_document_id=run.document_id if run else os.getenv("EXISTING_GOOGLE_DOC_ID"),
            )
            draft_id = gmail.create_draft(
                to_address=settings.recipient_alias,
                subject=f"Groww Weekly Review Pulse - Week Ending {pulse.week_ending}",
                body=pulse.markdown,
            )
            if run:
                run.document_id = document_id
                run.document_url = document_url
                run.gmail_draft_id = draft_id
                self._repository().update_run(run)
            _json_response(self, {"status": "delivered", "document_url": document_url, "gmail_draft_id": draft_id}, status=201)
            return
        if path != "/api/pulse/run":
            _json_response(self, {"error": "Not found"}, status=404)
            return
        try:
            settings = Settings()
            if not settings.dry_run and not os.getenv("GROWW_PULSE_MCP_HTTP_URL"):
                _json_response(
                    self,
                    {
                        "error": "MCP delivery is not configured on Railway. Pulse generation is disabled until a real MCP caller is connected.",
                        "status": "not_configured",
                    },
                    status=503,
                )
                return
            run, pulse = _build_orchestrator(settings).execute_run(
                existing_document_id=os.getenv("EXISTING_GOOGLE_DOC_ID")
            )
            _json_response(
                self,
                {
                    "run": run.model_dump(mode="json"),
                    "pulse": pulse.model_dump(mode="json") if pulse else None,
                },
                status=201 if pulse else 422,
            )
        except Exception as exc:
            _json_response(self, {"error": str(exc)[:200]}, status=500)


def serve(host: str = "127.0.0.1", port: int = 4173) -> None:
    """Serve the local frontend assets for design review and demos."""
    if not FRONTEND_DIR.is_dir():
        raise FileNotFoundError(f"Frontend assets not found at {FRONTEND_DIR}")
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(FRONTEND_DIR))
    server = ThreadingHTTPServer((host, port), handler)
    print(f"Review Pulse frontend: http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping frontend server...")
    finally:
        server.server_close()


def serve_api(host: str = "0.0.0.0", port: int = 8000) -> None:
    """Serve the API and keep the weekly scheduler running in the same process."""
    settings = Settings()
    scheduler_orchestrator = _build_orchestrator(settings)
    from groww_pulse.orchestration.scheduler import RunScheduler

    scheduler = RunScheduler(
        orchestrator=scheduler_orchestrator,
        settings=settings,
        day_of_week=os.getenv("GROWW_PULSE_SCHEDULE_DAY", "0"),
        hour=int(os.getenv("GROWW_PULSE_SCHEDULE_HOUR", "9")),
        minute=int(os.getenv("GROWW_PULSE_SCHEDULE_MINUTE", "0")),
        existing_document_id=os.getenv("EXISTING_GOOGLE_DOC_ID"),
    )
    scheduler.start()
    server = ThreadingHTTPServer(
        (host, port), functools.partial(PulseRequestHandler, directory=str(FRONTEND_DIR))
    )
    print(f"Review Pulse API: http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Review Pulse API...")
    finally:
        scheduler.stop()
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the Groww Review Pulse frontend")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4173)
    args = parser.parse_args()
    serve(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
