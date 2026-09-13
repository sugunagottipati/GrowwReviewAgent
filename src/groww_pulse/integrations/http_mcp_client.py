"""Synchronous JSON-RPC MCP caller for the Railway API process."""

import json
import os
import uuid
from urllib.request import Request, urlopen

from groww_pulse.integrations.mcp_adapters import MCPToolError


def make_http_mcp_tool_caller(endpoint: str):
    """Return a tool caller for an HTTP MCP JSON-RPC endpoint."""

    def tool_caller(server_name: str, tool_name: str, arguments: dict) -> dict:
        payload = json.dumps(
            {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "server": server_name,
                    "tool": tool_name,
                    "arguments": arguments,
                },
                "id": uuid.uuid4().hex,
            }
        ).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        token = os.getenv("GROWW_PULSE_MCP_BEARER_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            response = urlopen(Request(endpoint, data=payload, headers=headers), timeout=60)
            data = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            raise MCPToolError(f"MCP HTTP request failed: {type(exc).__name__}") from exc
        if "error" in data:
            raise MCPToolError(str(data["error"].get("message", "MCP tool failed")))
        result = data.get("result")
        if not isinstance(result, dict):
            raise MCPToolError("MCP tool returned an invalid result")
        return result

    return tool_caller
