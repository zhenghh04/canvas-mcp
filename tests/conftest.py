"""Shared fixtures.

Every test here runs offline. No test may reach a real Canvas tenant: the
`client` fixture installs a transport that raises on any unexpected call, so a
test that accidentally escapes fails loudly rather than mutating a live course.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from canvas_mcp.client import CanvasClient, CanvasError
from canvas_mcp.config import Config
from canvas_mcp.server import build_server


class FakeResponse:
    """Minimal stand-in for ``requests.Response``."""

    def __init__(
        self, payload: Any = None, status: int = 200, headers: dict | None = None, text: str = ""
    ):
        self._payload = payload
        self.status_code = status
        self.headers = headers or {}
        self.text = text or ("" if payload is None else "<json>")

    def json(self) -> Any:
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


class RecordingClient(CanvasClient):
    """A CanvasClient whose HTTP layer is a scripted stub.

    ``calls`` records every (method, path, kwargs) so a test can assert on the
    exact request a tool built. ``responses`` is either a single payload reused
    for every call or a list consumed in order.
    """

    def __init__(self, config: Config, responses: Any = None):
        super().__init__(config)
        self.calls: list[dict[str, Any]] = []
        self.responses = responses
        self.allow_network = False

    def request(self, method: str, path: str, **kwargs: Any):  # type: ignore[override]
        self.calls.append({"method": method, "path": path, **kwargs})
        if self.responses is None:
            raise AssertionError(f"unexpected request: {method} {path}")
        if isinstance(self.responses, list):
            payload = self.responses.pop(0) if self.responses else {}
        else:
            payload = self.responses
        resp = payload if isinstance(payload, FakeResponse) else FakeResponse(payload)
        if resp.status_code >= 400:
            # Mirror the real client: an HTTP error becomes a CanvasError here,
            # not a response object the tool would then try to parse.
            raise CanvasError(self.explain(resp.status_code, resp.text, path))
        return resp

    @property
    def last(self) -> dict[str, Any]:
        assert self.calls, "no request was made"
        return self.calls[-1]


def make_config(**overrides: Any) -> Config:
    """A fully-populated config: writes on, destructive on, so tests can reach
    every tool unless they are specifically testing a gate."""
    base = {
        "base_url": "https://example.instructure.com",
        "api_token": "fake-token",
        "default_course_id": "12345",
        "enable_writes": True,
        "allow_destructive": True,
        "max_retries": 1,
    }
    base.update(overrides)
    return Config(**base)


@pytest.fixture
def config() -> Config:
    return make_config()


@pytest.fixture
def client(config: Config) -> RecordingClient:
    return RecordingClient(config)


def build(client: CanvasClient):
    return build_server(client=client)


def tool_names(built) -> set[str]:
    return {t.name for t in asyncio.run(built.mcp.list_tools())}


def tool_schemas(built) -> dict[str, dict]:
    return {t.name: t.inputSchema for t in asyncio.run(built.mcp.list_tools())}


def call(client: CanvasClient, tool: str, /, **kwargs):
    """Invoke a registered tool by name through the MCP layer the model uses.

    Going through ``call_tool`` rather than the Python function is deliberate:
    it exercises the published schema, so a parameter that FastMCP failed to
    expose shows up here as a validation error instead of passing silently.

    The parameters are positional-only because several tools take their own
    ``name`` argument, which would otherwise collide with this signature.
    """
    built = build_server(client=client)
    result = asyncio.run(built.mcp.call_tool(tool, kwargs))
    content = result[0] if isinstance(result, tuple) else result
    return "".join(getattr(block, "text", "") for block in content)
