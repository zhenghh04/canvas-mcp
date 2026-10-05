"""Tool registration with safety tiers, group filtering, and error guarding.

Every tool goes through :meth:`Registrar.tool`, which decides — from the
:class:`~canvas_mcp.config.Config` alone — whether the tool is published at all.
A tool that is gated off is never registered, so the model cannot see it, cannot
call it, and does not spend context on its description.
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from dataclasses import dataclass

from mcp.server.fastmcp import FastMCP

from .client import CanvasClient, CanvasError
from .config import Config


@dataclass(frozen=True)
class ToolInfo:
    """What was registered, for ``canvas_auth_status`` and ``canvas-mcp tools``."""

    name: str
    group: str
    tier: str
    summary: str


def guard(fn: Callable) -> Callable:
    """Turn a :class:`CanvasError` into a returned message, not a transport error.

    ``functools.wraps`` is load-bearing, not cosmetic: it sets ``__wrapped__``,
    which ``inspect.signature`` follows. Without it FastMCP introspects the
    wrapper's own ``(*args, **kwargs)`` and publishes a schema with two bogus
    string parameters instead of the real ones — every guarded tool becomes
    uncallable while still *looking* fine in the tool list.
    """

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except CanvasError as exc:
            return f"ERROR: {exc}"

    return wrapper


class Registrar:
    """Registers tools on a FastMCP instance subject to a Config."""

    def __init__(self, mcp: FastMCP, client: CanvasClient) -> None:
        self.mcp = mcp
        self.client = client
        self.config: Config = client.config
        self.registered: list[ToolInfo] = []
        self.skipped: list[ToolInfo] = []

    def tool(self, *, group: str, tier: str = "read") -> Callable:
        """Decorator: publish ``fn`` as an MCP tool if the config allows it."""

        def decorator(fn: Callable) -> Callable:
            summary = (fn.__doc__ or "").strip().splitlines()[0] if fn.__doc__ else ""
            info = ToolInfo(name=fn.__name__, group=group, tier=tier, summary=summary)
            if not self.config.tool_enabled(fn.__name__, group=group, tier=tier):
                self.skipped.append(info)
                return fn
            self.mcp.tool()(guard(fn))
            self.registered.append(info)
            return fn

        return decorator
