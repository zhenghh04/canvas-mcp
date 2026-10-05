"""Configuration: environment resolution, `.env` loading, and safety tiers.

Everything the server needs is read once into a frozen :class:`Config`. Tests
build one directly instead of mutating the process environment, so the tool
surface for a given configuration can be asserted without re-importing modules.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

#: Environment variable pointing at an explicit `.env` file.
ENV_FILE_VAR = "CANVAS_MCP_ENV_FILE"

#: Tool groups, in the order they are registered. Used by ``CANVAS_TOOL_GROUPS``.
GROUPS = (
    "diagnostics",
    "courses",
    "people",
    "assignments",
    "grading",
    "content",
    "communication",
)

#: Safety tiers. ``read`` is always on; ``write`` and ``destructive`` are gated.
TIERS = ("read", "write", "destructive")

_TRUE = {"1", "true", "yes", "on", "y", "t"}
_FALSE = {"0", "false", "no", "off", "n", "f", ""}


def _as_bool(value: str | None, default: bool) -> bool:
    """Parse a flag, falling back to ``default`` for anything unrecognised.

    A typo must not silently flip a safety tier in either direction: ``"flase"``
    leaves the default in place rather than reading as False.
    """
    if value is None:
        return default
    v = value.strip().lower()
    if v in _TRUE:
        return True
    if v in _FALSE:
        return False
    return default


def _as_int(value: str | None, default: int) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _as_float(value: str | None, default: float) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default


def _as_set(value: str | None) -> frozenset[str]:
    if not value:
        return frozenset()
    return frozenset(part.strip() for part in value.split(",") if part.strip())


def candidate_env_files() -> list[Path]:
    """`.env` locations searched, highest precedence first.

    1. ``$CANVAS_MCP_ENV_FILE`` — an explicit path, for multi-tenant hosts.
    2. ``./.env`` — the working directory, for ``git clone && run``.
    3. ``~/.config/canvas-mcp/.env`` — the per-user default most instructors want,
       because an MCP client launches the server with an unpredictable cwd.
    """
    paths: list[Path] = []
    explicit = os.environ.get(ENV_FILE_VAR, "").strip()
    if explicit:
        paths.append(Path(explicit).expanduser())
    paths.append(Path.cwd() / ".env")
    paths.append(Path.home() / ".config" / "canvas-mcp" / ".env")
    return paths


def load_env_file(path: Path | None = None) -> Path | None:
    """Populate ``os.environ`` from the first `.env` that exists.

    Existing environment variables always win — an MCP client's ``env`` block is
    the more specific signal, and silently overriding it is how a user ends up
    editing a config that has no effect. Returns the file used, or ``None``.
    """
    paths = [path] if path is not None else candidate_env_files()
    for candidate in paths:
        if candidate is None or not candidate.is_file():
            continue
        for line in candidate.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export ") :]
            key, sep, value = line.partition("=")
            if not sep:
                continue
            key, value = key.strip(), value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
                value = value[1:-1]
            if key and key not in os.environ:
                os.environ[key] = value
        return candidate
    return None


@dataclass(frozen=True)
class Config:
    """Resolved server configuration.

    Attributes mirror the ``CANVAS_*`` environment variables one-for-one; see
    ``.env.example`` and the README for the user-facing documentation.
    """

    base_url: str = ""
    api_token: str = ""
    default_course_id: str = ""
    enable_writes: bool = True
    allow_destructive: bool = False
    redact_pii: bool = False
    tool_groups: frozenset[str] = frozenset()
    tools_allow: frozenset[str] = frozenset()
    tools_deny: frozenset[str] = frozenset()
    timeout: float = 30.0
    upload_timeout: float = 300.0
    max_upload_mb: float = 100.0
    per_page: int = 100
    max_pages: int = 10
    max_chars: int = 20000
    max_retries: int = 3
    download_dir: str = ""
    env_file: str | None = field(default=None, compare=False)

    # -- derived ----------------------------------------------------------

    @property
    def api_url(self) -> str:
        return f"{self.base_url}/api/v1"

    @property
    def token_page_url(self) -> str:
        return f"{self.base_url}/profile/settings"

    def downloads_path(self) -> Path:
        return (
            Path(self.download_dir).expanduser()
            if self.download_dir
            else Path.cwd() / "canvas-downloads"
        )

    def tier_enabled(self, tier: str) -> bool:
        if tier == "read":
            return True
        if tier == "write":
            return self.enable_writes
        if tier == "destructive":
            return self.enable_writes and self.allow_destructive
        raise ValueError(f"unknown tier {tier!r}; expected one of {TIERS}")

    def group_enabled(self, group: str) -> bool:
        return not self.tool_groups or group in self.tool_groups

    def tool_enabled(self, name: str, *, group: str, tier: str) -> bool:
        """Whether a tool should be registered under this configuration.

        ``CANVAS_TOOLS`` (allowlist) is an explicit override of the group filter
        — naming a tool is a stronger signal than naming its group — but it does
        **not** override a safety tier. Opting a delete tool in by name still
        requires ``CANVAS_ALLOW_DESTRUCTIVE=1``, so no single setting can hand a
        model an irreversible tool by accident.
        """
        if not self.tier_enabled(tier):
            return False
        if name in self.tools_deny:
            return False
        if self.tools_allow:
            return name in self.tools_allow
        return self.group_enabled(group)

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None, *, load_dotenv: bool = True) -> Config:
        """Build a Config from the environment, loading a `.env` first."""
        used: Path | None = None
        if env is None:
            if load_dotenv:
                used = load_env_file()
            env = dict(os.environ)
        return cls(
            base_url=env.get("CANVAS_BASE_URL", "").strip().rstrip("/"),
            api_token=env.get("CANVAS_API_TOKEN", "").strip(),
            default_course_id=env.get("CANVAS_DEFAULT_COURSE_ID", "").strip(),
            enable_writes=_as_bool(env.get("CANVAS_ENABLE_WRITES"), True),
            allow_destructive=_as_bool(env.get("CANVAS_ALLOW_DESTRUCTIVE"), False),
            redact_pii=_as_bool(env.get("CANVAS_REDACT_PII"), False),
            tool_groups=_as_set(env.get("CANVAS_TOOL_GROUPS")),
            tools_allow=_as_set(env.get("CANVAS_TOOLS")),
            tools_deny=_as_set(env.get("CANVAS_DISABLE_TOOLS")),
            timeout=_as_float(env.get("CANVAS_TIMEOUT"), 30.0),
            upload_timeout=_as_float(env.get("CANVAS_UPLOAD_TIMEOUT"), 300.0),
            max_upload_mb=_as_float(env.get("CANVAS_MAX_UPLOAD_MB"), 100.0),
            per_page=_as_int(env.get("CANVAS_PER_PAGE"), 100),
            max_pages=_as_int(env.get("CANVAS_MAX_PAGES"), 10),
            max_chars=_as_int(env.get("CANVAS_MAX_CHARS"), 20000),
            max_retries=_as_int(env.get("CANVAS_MAX_RETRIES"), 3),
            download_dir=env.get("CANVAS_DOWNLOAD_DIR", "").strip(),
            env_file=str(used) if used else None,
        )
