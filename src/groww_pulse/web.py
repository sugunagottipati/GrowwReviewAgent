"""Local static server for the Review Pulse frontend."""

from __future__ import annotations

import argparse
import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"


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


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the Groww Review Pulse frontend")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4173)
    args = parser.parse_args()
    serve(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
