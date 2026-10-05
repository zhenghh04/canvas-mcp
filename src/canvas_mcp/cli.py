"""Command line: run the server, or inspect a configuration before wiring it up.

    canvas-mcp                 # stdio server — what an MCP client launches
    canvas-mcp doctor          # is my token/base URL/course id actually working?
    canvas-mcp tools           # what would this config publish, and what not?
    canvas-mcp config          # show resolved settings (never the token)
    canvas-mcp serve --http    # streamable-HTTP, for a shared or remote server

``doctor`` exists because the alternative is debugging a stdio server through
an MCP client's error pane, which shows you a closed pipe and nothing else.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from . import __version__
from .client import CanvasClient, CanvasError
from .config import GROUPS, Config
from .server import build_server


def _redacted_config(config: Config) -> dict[str, Any]:
    return {
        "base_url": config.base_url or None,
        "api_token": f"set ({len(config.api_token)} chars)" if config.api_token else "NOT SET",
        "default_course_id": config.default_course_id or None,
        "env_file": config.env_file,
        "enable_writes": config.enable_writes,
        "allow_destructive": config.allow_destructive,
        "redact_pii": config.redact_pii,
        "tool_groups": sorted(config.tool_groups) or "all",
        "tools_allow": sorted(config.tools_allow) or None,
        "tools_deny": sorted(config.tools_deny) or None,
        "download_dir": str(config.downloads_path()),
        "timeout_s": config.timeout,
        "max_pages": config.max_pages,
        "max_chars": config.max_chars,
    }


def cmd_config(args: argparse.Namespace) -> int:
    config = Config.from_env()
    print(json.dumps(_redacted_config(config), indent=2))
    return 0


def cmd_tools(args: argparse.Namespace) -> int:
    built = build_server()
    rows = sorted(built.registrar.registered, key=lambda t: (GROUPS.index(t.group), t.name))
    if args.json:
        print(
            json.dumps(
                {
                    "published": [vars(t) for t in rows],
                    "withheld": [vars(t) for t in built.registrar.skipped],
                },
                indent=2,
            )
        )
        return 0
    group = None
    for tool in rows:
        if tool.group != group:
            group = tool.group
            print(f"\n{group.upper()}")
        marker = {"read": "  ", "write": "! ", "destructive": "!!"}[tool.tier]
        print(f"  {marker} {tool.name:<34} {tool.summary}")
    if built.registrar.skipped:
        print("\nWITHHELD by the current configuration:")
        for tool in built.registrar.skipped:
            why = (
                "needs CANVAS_ALLOW_DESTRUCTIVE=1"
                if tool.tier == "destructive" and not built.config.allow_destructive
                else "needs CANVAS_ENABLE_WRITES=1"
                if tool.tier == "write" and not built.config.enable_writes
                else "filtered out by CANVAS_TOOL_GROUPS/CANVAS_TOOLS/CANVAS_DISABLE_TOOLS"
            )
            print(f"     {tool.name:<34} {why}")
    print(f"\n{len(rows)} tools published, {len(built.registrar.skipped)} withheld.")
    print("Legend:  (blank) read-only   !  write   !! irreversible")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    """Walk the setup checklist in order and stop at the first real failure."""
    config = Config.from_env()
    client = CanvasClient(config)
    ok = True

    def check(label: str, passed: bool, detail: str = "") -> None:
        nonlocal ok
        mark = "OK  " if passed else "FAIL"
        print(f"[{mark}] {label}{(' — ' + detail) if detail else ''}")
        ok = ok and passed

    print(f"canvas-mcp {__version__}\n")
    check(
        "CANVAS_BASE_URL set",
        bool(config.base_url),
        config.base_url or "set it to https://<school>.instructure.com",
    )
    check(
        "CANVAS_API_TOKEN set",
        bool(config.api_token),
        "" if config.api_token else f"create one at {config.token_page_url}",
    )
    if config.env_file:
        print(f"       (loaded from {config.env_file})")
    if not ok:
        print("\nFix the above, then re-run `canvas-mcp doctor`.")
        return 1

    try:
        me = client.get_json("users/self")
        check("Token authenticates", True, f"{me.get('name')} (id {me.get('id')})")
    except CanvasError as exc:
        check("Token authenticates", False, str(exc))
        return 1

    try:
        courses = client.paged(
            "courses", {"enrollment_type": "teacher", "enrollment_state": "active"}, max_pages=1
        )
        teaching = [c for c in courses if isinstance(c, dict)]
        check("Teacher enrollments visible", True, f"{len(teaching)} active course(s)")
        for course in teaching[:10]:
            print(f"       {course.get('id'):>8}  {course.get('name')}")
    except CanvasError as exc:
        check("Teacher enrollments visible", False, str(exc))

    if config.default_course_id:
        try:
            course = client.get_json(f"courses/{config.default_course_id}")
            check("CANVAS_DEFAULT_COURSE_ID resolves", True, course.get("name", ""))
        except CanvasError as exc:
            check("CANVAS_DEFAULT_COURSE_ID resolves", False, str(exc))
    else:
        print("[note] CANVAS_DEFAULT_COURSE_ID unset — every tool call must pass course_id.")

    built = build_server(config)
    print(
        f"\n{len(built.registrar.registered)} tools would be published "
        f"(writes={'on' if config.enable_writes else 'off'}, "
        f"destructive={'on' if config.allow_destructive else 'off'}). "
        "Run `canvas-mcp tools` for the list."
    )
    return 0 if ok else 1


def cmd_serve(args: argparse.Namespace) -> int:
    built = build_server()
    config = built.config
    if not config.base_url or not config.api_token:
        # Do not exit: an MCP client that sees the server die just reports a
        # broken pipe. Start anyway so canvas_auth_status can explain itself.
        print(
            "canvas-mcp: CANVAS_BASE_URL and/or CANVAS_API_TOKEN are unset. Starting "
            "anyway — call canvas_auth_status for the remedy, or run `canvas-mcp doctor`.",
            file=sys.stderr,
        )
    if args.transport == "stdio":
        built.mcp.run()
        return 0
    built.mcp.settings.host = args.host
    built.mcp.settings.port = args.port
    built.mcp.run(transport="streamable-http" if args.transport == "http" else args.transport)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="canvas-mcp",
        description="MCP server for the Canvas LMS REST API.",
    )
    parser.add_argument("--version", action="version", version=f"canvas-mcp {__version__}")
    sub = parser.add_subparsers(dest="command")

    serve = sub.add_parser("serve", help="run the MCP server (default)")
    serve.add_argument(
        "--transport",
        choices=("stdio", "http", "sse"),
        default="stdio",
        help="stdio (default, for local MCP clients) or http for a shared server",
    )
    serve.add_argument("--host", default="127.0.0.1", help="bind host for --transport http")
    serve.add_argument("--port", type=int, default=8080, help="bind port for --transport http")
    serve.set_defaults(func=cmd_serve)

    doctor = sub.add_parser("doctor", help="check token, connectivity, and course access")
    doctor.set_defaults(func=cmd_doctor)

    tools = sub.add_parser("tools", help="list the tools this configuration publishes")
    tools.add_argument("--json", action="store_true", help="machine-readable output")
    tools.set_defaults(func=cmd_tools)

    cfg = sub.add_parser("config", help="show resolved settings (token never printed)")
    cfg.set_defaults(func=cmd_config)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        # Bare `canvas-mcp` is the stdio server: that is what an MCP client runs.
        args = parser.parse_args(["serve", *(argv or [])])
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
