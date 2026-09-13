"""Synchronous JSON-RPC MCP caller for the Railway API process."""

import json
import os
import uuid
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from groww_pulse.integrations.mcp_adapters import MCPToolError


def _parse_mcp_http_response(raw_body: bytes) -> dict:
    """Parse either a JSON response or a Streamable HTTP SSE response."""
    text = raw_body.decode("utf-8", errors="replace").strip()
    if not text:
        raise MCPToolError("MCP server returned an empty response")

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    messages = []
    for block in text.split("\n\n"):
        if not block.strip():
            continue
        data_lines = []
        for line in block.splitlines():
            if line.startswith("data:"):
                data_lines.append(line[5:].lstrip())
        if not data_lines:
            continue
        payload = "\n".join(data_lines)
        try:
            messages.append(json.loads(payload))
        except json.JSONDecodeError:
            continue

    if not messages:
        raise MCPToolError("MCP HTTP response was not valid JSON or SSE")

    for message in messages:
        if isinstance(message, dict) and "error" in message:
            raise MCPToolError(str(message["error"].get("message", "MCP tool failed")))
        if isinstance(message, dict) and "result" in message:
            return message

    if isinstance(messages[-1], dict):
        return messages[-1]
    raise MCPToolError("MCP HTTP response did not contain a result")


def make_http_mcp_tool_caller(endpoint: str):
    """Return a tool caller for an HTTP MCP JSON-RPC endpoint."""

    def tool_caller(server_name: str, tool_name: str, arguments: dict) -> dict:
        del server_name  # The real HTTP MCP server contract uses tool name + arguments, not "server".
        payload = json.dumps(
            {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": arguments,
                },
                "id": uuid.uuid4().hex,
            }
        ).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": "2025-06-18",
        }
        token = os.getenv("GROWW_PULSE_MCP_BEARER_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            response = urlopen(Request(endpoint, data=payload, headers=headers), timeout=60)
            data = _parse_mcp_http_response(response.read())
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:200]
            raise MCPToolError(f"MCP HTTP {exc.code}: {detail}") from exc
        except Exception as exc:
            raise MCPToolError(f"MCP HTTP request failed: {type(exc).__name__}") from exc
        if "error" in data:
            raise MCPToolError(str(data["error"].get("message", "MCP tool failed")))
        result = data.get("result")
        if not isinstance(result, dict):
            raise MCPToolError("MCP tool returned an invalid result")
        return result

    return tool_caller
