"""Configuration parsing, `.env` resolution, and the tier/group gates."""

from __future__ import annotations

import pytest

from canvas_mcp.config import Config, _as_bool, load_env_file


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on", "y"])
def test_truthy_values_parse_true(value):
    assert _as_bool(value, False) is True


@pytest.mark.parametrize("value", ["0", "false", "FALSE", "no", "off", ""])
def test_falsy_values_parse_false(value):
    assert _as_bool(value, True) is False


@pytest.mark.parametrize("default", [True, False])
def test_typos_fall_back_to_the_default_in_both_directions(default):
    """A typo must not silently flip a safety tier. "flase" is not False — it is
    "I cannot tell what you meant", which has to mean "leave the default alone"
    or a misspelled CANVAS_ALLOW_DESTRUCTIVE would read as consent."""
    assert _as_bool("flase", default) is default


def test_unset_falls_back_to_the_default():
    assert _as_bool(None, True) is True


def test_base_url_loses_its_trailing_slash():
    """A trailing slash would produce //api/v1, which some Canvas hosts 404."""
    cfg = Config.from_env({"CANVAS_BASE_URL": "https://x.instructure.com/"})
    assert cfg.base_url == "https://x.instructure.com"
    assert cfg.api_url == "https://x.instructure.com/api/v1"


def test_defaults_are_write_on_destructive_off():
    """The shipped posture: author and grade freely, but never hand a model an
    irreversible delete without an explicit opt-in."""
    cfg = Config.from_env({})
    assert cfg.enable_writes is True
    assert cfg.allow_destructive is False


def test_destructive_requires_writes_too():
    """CANVAS_ALLOW_DESTRUCTIVE alone must not re-enable anything: a read-only
    deployment that also sets it is still read-only."""
    cfg = Config.from_env({"CANVAS_ENABLE_WRITES": "0", "CANVAS_ALLOW_DESTRUCTIVE": "1"})
    assert cfg.tier_enabled("write") is False
    assert cfg.tier_enabled("destructive") is False


def test_tier_read_is_always_enabled():
    cfg = Config.from_env({"CANVAS_ENABLE_WRITES": "0"})
    assert cfg.tier_enabled("read") is True


def test_unknown_tier_is_a_programming_error():
    with pytest.raises(ValueError):
        Config().tier_enabled("sorta-write")


def test_group_filter_restricts_the_surface():
    cfg = Config.from_env({"CANVAS_TOOL_GROUPS": "grading, courses"})
    assert cfg.group_enabled("grading") and cfg.group_enabled("courses")
    assert not cfg.group_enabled("content")


def test_allowlist_overrides_the_group_filter():
    """Naming a tool is a more specific signal than naming its group."""
    cfg = Config.from_env({"CANVAS_TOOL_GROUPS": "grading", "CANVAS_TOOLS": "canvas_list_pages"})
    assert cfg.tool_enabled("canvas_list_pages", group="content", tier="read")
    assert not cfg.tool_enabled("canvas_get_gradebook", group="grading", tier="read")


def test_allowlist_cannot_override_a_safety_tier():
    """Opting a delete tool in by name is still subject to the destructive gate —
    otherwise one setting would be enough to hand a model an irreversible tool."""
    cfg = Config.from_env({"CANVAS_TOOLS": "canvas_delete_page"})
    assert not cfg.tool_enabled("canvas_delete_page", group="content", tier="destructive")


def test_denylist_wins_over_the_allowlist():
    cfg = Config.from_env(
        {"CANVAS_TOOLS": "canvas_list_pages", "CANVAS_DISABLE_TOOLS": "canvas_list_pages"}
    )
    assert not cfg.tool_enabled("canvas_list_pages", group="content", tier="read")


# -- .env loading ----------------------------------------------------------


def test_env_file_is_loaded_and_quotes_stripped(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text('export CANVAS_API_TOKEN="abc123"\n# comment\nCANVAS_BASE_URL=https://x.edu\n')
    monkeypatch.delenv("CANVAS_API_TOKEN", raising=False)
    monkeypatch.delenv("CANVAS_BASE_URL", raising=False)
    assert load_env_file(env) == env
    import os

    assert os.environ["CANVAS_API_TOKEN"] == "abc123"
    assert os.environ["CANVAS_BASE_URL"] == "https://x.edu"


def test_existing_environment_wins_over_the_env_file(tmp_path, monkeypatch):
    """An MCP client's env block is the more specific signal. Silently
    overriding it is how somebody ends up editing a file that has no effect."""
    env = tmp_path / ".env"
    env.write_text("CANVAS_API_TOKEN=from-file\n")
    monkeypatch.setenv("CANVAS_API_TOKEN", "from-client")
    load_env_file(env)
    import os

    assert os.environ["CANVAS_API_TOKEN"] == "from-client"


def test_missing_env_file_is_not_an_error(tmp_path):
    assert load_env_file(tmp_path / "nope.env") is None


def test_malformed_lines_are_skipped_not_fatal(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("this line has no equals sign\nCANVAS_BASE_URL=https://ok.edu\n")
    monkeypatch.delenv("CANVAS_BASE_URL", raising=False)
    load_env_file(env)
    import os

    assert os.environ["CANVAS_BASE_URL"] == "https://ok.edu"
