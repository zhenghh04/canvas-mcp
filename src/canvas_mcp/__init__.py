"""canvas-mcp — a Model Context Protocol server for the Canvas LMS REST API.

Instructure ships no official MCP server. This one exposes the teaching surface
of the Canvas REST API — roster, assignments, gradebook, pages, modules, files,
announcements — to any MCP client, with safety tiers in front of the calls that
change student records.

Typical use::

    from canvas_mcp import Config, build_server

    built = build_server(Config.from_env())
    built.mcp.run()
"""

from __future__ import annotations

__version__ = "0.2.0"

from .client import CanvasClient, CanvasError
from .config import GROUPS, TIERS, Config
from .server import BuiltServer, build_server

__all__ = [
    "__version__",
    "CanvasClient",
    "CanvasError",
    "Config",
    "GROUPS",
    "TIERS",
    "BuiltServer",
    "build_server",
]
