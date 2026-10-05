"""Tool modules, registered in order by :func:`canvas_mcp.server.build_server`.

Each module exposes a single ``register(reg: Registrar) -> None`` that defines
its tools as closures over ``reg.client``. Adding a module here is the whole of
"add a tool group" — see CONTRIBUTING.md.
"""

from __future__ import annotations

from . import assignments, communication, content, courses, diagnostics, grading, people

#: Registration order. Also the order tools appear in ``canvas-mcp tools``.
MODULES = (diagnostics, courses, people, assignments, grading, content, communication)

__all__ = [
    "MODULES",
    "assignments",
    "communication",
    "content",
    "courses",
    "diagnostics",
    "grading",
    "people",
]
