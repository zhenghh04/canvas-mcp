"""Connectivity, configuration, and the raw-API escape hatches."""

from __future__ import annotations

import json
from typing import Any

from ..client import CanvasError
from ..formatting import slim
from ..registry import Registrar

_WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def register(reg: Registrar) -> None:
    client = reg.client
    config = reg.config

    @reg.tool(group="diagnostics")
    def canvas_auth_status() -> str:
        """Check Canvas connectivity, identity, and which tool tiers are enabled.

        Reveals no token material. Call this first whenever another Canvas tool
        fails, or when a tool you expected is missing — the ``tools`` section
        shows exactly what this server published and what a safety flag withheld.
        """
        status: dict[str, Any] = {
            "base_url": config.base_url or None,
            "token_configured": bool(config.api_token),
            "default_course_id": config.default_course_id or None,
            "env_file": config.env_file,
            "writes_enabled": config.enable_writes,
            "destructive_enabled": config.allow_destructive,
            "pii_redaction": config.redact_pii,
            "tools": {
                "published": len(reg.registered),
                "withheld": sorted({t.name for t in reg.skipped}),
            },
        }
        if not config.base_url:
            status["authenticated"] = False
            status["remedy"] = (
                "Set CANVAS_BASE_URL to your institution's Canvas host, e.g. "
                "https://myschool.instructure.com"
            )
            return client.fmt(status)
        if not config.api_token:
            status["authenticated"] = False
            status["remedy"] = (
                f"Create a token at {config.token_page_url} (Approved Integrations > "
                "+ New Access Token) and set CANVAS_API_TOKEN."
            )
            return client.fmt(status)
        try:
            me = client.get_json("users/self")
            status["authenticated"] = True
            status["user"] = slim(me, ("id", "name", "short_name", "login_id"))
        except CanvasError as exc:
            status["authenticated"] = False
            status["error"] = str(exc)
        return client.fmt(status)

    @reg.tool(group="diagnostics")
    def canvas_api_get(path: str, params_json: str = "", max_chars: int = 0) -> str:
        """Escape hatch: GET any Canvas REST endpoint without a dedicated tool.

        Canvas publishes well over a thousand operations; the tools here cover
        the common teaching ones. Use this for the rest. Read-only by
        construction — it cannot issue a write even if asked to.

        Args:
            path: path under /api/v1, e.g. "courses/12345/gradebook_history/days".
                A full URL is also accepted.
            params_json: optional JSON object of query parameters, e.g.
                '{"per_page": 20, "include[]": "submission"}'.
            max_chars: bound on the returned payload (0 = the server default).
        """
        try:
            params = json.loads(params_json) if params_json else {}
        except json.JSONDecodeError as exc:
            return f"ERROR: params_json is not valid JSON: {exc}"
        if not isinstance(params, dict):
            return "ERROR: params_json must be a JSON object, e.g. '{\"per_page\": 20}'"
        return client.fmt(client.get_json(path, params), max_chars or None)

    @reg.tool(group="diagnostics", tier="destructive")
    def canvas_api_write(
        method: str, path: str, form_json: str = "", params_json: str = "", max_chars: int = 0
    ) -> str:
        """Escape hatch: POST/PUT/PATCH/DELETE any Canvas endpoint. MUTATES RECORDS.

        This is the one tool with no idea what it is about to change — it will
        happily delete a course if that is the path you give it. It exists for
        the long tail of Canvas operations no dedicated tool covers, and it is
        gated behind CANVAS_ALLOW_DESTRUCTIVE for that reason. Show the
        instructor the exact method, path, and body and get an explicit
        go-ahead before every single call.

        Args:
            method: POST, PUT, PATCH, or DELETE.
            path: path under /api/v1, e.g. "courses/12345/assignment_groups/99".
            form_json: JSON object sent as the form body, e.g.
                '{"assignment_group[name]": "Labs"}'. Canvas expects its
                bracketed parameter names verbatim.
            params_json: JSON object of query parameters.
            max_chars: bound on the returned payload (0 = the server default).
        """
        verb = method.strip().upper()
        if verb not in _WRITE_METHODS:
            return (
                f"ERROR: method must be one of {sorted(_WRITE_METHODS)}, got {method!r}. "
                "Use canvas_api_get for reads."
            )
        try:
            body = json.loads(form_json) if form_json else {}
            params = json.loads(params_json) if params_json else {}
        except json.JSONDecodeError as exc:
            return f"ERROR: form_json/params_json is not valid JSON: {exc}"
        if not isinstance(body, dict) or not isinstance(params, dict):
            return "ERROR: form_json and params_json must each be a JSON object."
        resp = client.request(verb, path, data=body or None, params=params or None)
        try:
            payload = resp.json()
        except ValueError:
            payload = {"status_code": resp.status_code, "body": resp.text[:1000]}
        return client.fmt(payload, max_chars or None)
