"""Assembly: turn a :class:`~canvas_mcp.config.Config` into a FastMCP server.

``build_server`` is a pure function of its config. Tests call it directly with
hand-built configs to assert the published tool surface, instead of reimporting
a module under a mutated process environment.
"""

from __future__ import annotations

from dataclasses import dataclass

from mcp.server.fastmcp import FastMCP

from .client import CanvasClient
from .config import Config
from .registry import Registrar
from .tools import MODULES

SERVER_NAME = "canvas"

INSTRUCTIONS = """\
Canvas LMS tools for a course you teach.

Orientation: call canvas_auth_status first if anything is unclear — it reports
who the token belongs to, which course is the default, and which tool tiers
this server published. Use canvas_list_courses to find a course id.

Writes: any tool whose description says MUTATES changes the live course that
real students see. Show the instructor exactly what you intend to change and
get an explicit go-ahead before each such call. Grades and announcements are
not undoable from here — a posted grade is in the gradebook, and deleting an
announcement does not unsend the email it already triggered.

Privacy: rosters, submissions, and discussions carry student PII. Keep it in
the conversation that needs it; do not write it into files, summaries, or
external services unless the instructor asks.
"""


@dataclass
class BuiltServer:
    """A configured FastMCP instance plus the registrar that populated it."""

    mcp: FastMCP
    client: CanvasClient
    registrar: Registrar

    @property
    def config(self) -> Config:
        return self.client.config


def build_server(
    config: Config | None = None, *, client: CanvasClient | None = None
) -> BuiltServer:
    """Create a FastMCP server exposing the tools this config allows."""
    if client is None:
        client = CanvasClient(config or Config.from_env())
    mcp = FastMCP(SERVER_NAME, instructions=INSTRUCTIONS)
    registrar = Registrar(mcp, client)
    for module in MODULES:
        module.register(registrar)
    return BuiltServer(mcp=mcp, client=client, registrar=registrar)
