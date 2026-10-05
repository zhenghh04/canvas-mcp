"""The published tool surface: schemas, safety tiers, and filtering."""

from __future__ import annotations

import asyncio

import pytest

from canvas_mcp.config import GROUPS
from canvas_mcp.registry import guard
from canvas_mcp.server import build_server

from .conftest import RecordingClient, make_config, tool_names, tool_schemas

WRITE_TOOLS = {
    "canvas_update_course",
    "canvas_update_syllabus",
    "canvas_enroll_user",
    "canvas_create_assignment",
    "canvas_create_assignment_group",
    "canvas_update_assignment",
    "canvas_grade_submission",
    "canvas_bulk_grade",
    "canvas_create_page",
    "canvas_update_page",
    "canvas_create_module",
    "canvas_update_module",
    "canvas_create_module_item",
    "canvas_upload_file",
    "canvas_post_announcement",
    "canvas_create_discussion",
    "canvas_create_calendar_event",
    "canvas_message_students",
}

DESTRUCTIVE_TOOLS = {
    "canvas_api_write",
    "canvas_remove_enrollment",
    "canvas_delete_assignment",
    "canvas_delete_page",
    "canvas_delete_module",
}


def built(**overrides):
    return build_server(client=RecordingClient(make_config(**overrides)))


def test_no_tool_publishes_args_or_kwargs():
    """Regression: the error guard once wrapped tools without functools.wraps,
    so FastMCP introspected the wrapper's (*args, **kwargs) and published two
    bogus string params. Every guarded tool became uncallable while still
    looking fine in the tool list."""
    offenders = {
        name: sorted(schema.get("properties", {}))
        for name, schema in tool_schemas(built()).items()
        if {"args", "kwargs"} & set(schema.get("properties", {}))
    }
    assert offenders == {}


def test_every_tool_has_a_docstring_summary():
    """The description is the model's only guide to when a tool applies."""
    reg = built().registrar
    assert [t.name for t in reg.registered if not t.summary] == []


def test_every_mutating_tool_announces_itself_in_its_description():
    """A model deciding whether to ask the instructor first reads the
    description, not the tier metadata — the warning has to be in the text."""
    tools = asyncio.run(built().mcp.list_tools())
    tiers = {t.name: t.tier for t in built().registrar.registered}
    missing = [
        t.name
        for t in tools
        if tiers.get(t.name) in ("write", "destructive")
        and not any(
            word in (t.description or "")
            for word in ("MUTATES", "NOTIFIES", "IRREVERSIBLE", "notified")
        )
    ]
    assert missing == []


def test_every_registered_group_is_a_known_group():
    assert {t.group for t in built().registrar.registered} <= set(GROUPS)


@pytest.mark.parametrize(
    "tool_name,expected",
    [
        ("canvas_auth_status", set()),
        ("canvas_get_course", {"course_id", "max_chars"}),
        ("canvas_list_assignments", {"course_id", "bucket", "search_term"}),
        ("canvas_list_students", {"course_id", "include_email", "search_term"}),
        ("canvas_get_submission", {"assignment_id", "user_id", "course_id", "max_chars"}),
        ("canvas_api_get", {"path", "params_json", "max_chars"}),
        (
            "canvas_grade_submission",
            {"assignment_id", "user_id", "grade", "comment", "excused", "course_id"},
        ),
        ("canvas_post_announcement", {"title", "message", "delayed_post_at", "course_id"}),
    ],
)
def test_tool_parameters_survive_the_guard(tool_name, expected):
    assert set(tool_schemas(built())[tool_name].get("properties", {})) == expected


def test_required_parameters_are_marked_required():
    """A model must not be able to call canvas_grade_submission with no target."""
    schema = tool_schemas(built())["canvas_grade_submission"]
    assert set(schema.get("required", [])) == {"assignment_id", "user_id"}


# -- safety tiers ----------------------------------------------------------


def test_default_posture_publishes_writes_but_withholds_deletes():
    """Shipped default: author and grade freely, never delete by accident."""
    names = tool_names(build_server(client=RecordingClient(make_config(allow_destructive=False))))
    assert WRITE_TOOLS <= names
    assert not (DESTRUCTIVE_TOOLS & names)


def test_read_only_mode_withholds_every_mutation():
    names = tool_names(built(enable_writes=False, allow_destructive=False))
    assert not ((WRITE_TOOLS | DESTRUCTIVE_TOOLS) & names)
    assert "canvas_list_students" in names and "canvas_api_get" in names


def test_destructive_opt_in_publishes_the_delete_tools():
    assert DESTRUCTIVE_TOOLS <= tool_names(built(allow_destructive=True))


def test_destructive_flag_alone_cannot_bypass_the_write_gate():
    names = tool_names(built(enable_writes=False, allow_destructive=True))
    assert not (DESTRUCTIVE_TOOLS & names)


def test_withheld_tools_are_reported_not_merely_absent():
    """ "Why can't you grade?" needs an answer; a silently missing tool has none."""
    reg = built(enable_writes=False).registrar
    assert {t.name for t in reg.skipped} >= WRITE_TOOLS


# -- filtering -------------------------------------------------------------


def test_group_filter_trims_the_surface():
    names = tool_names(built(tool_groups=frozenset({"grading"})))
    assert "canvas_get_gradebook" in names
    assert "canvas_list_pages" not in names


def test_explicit_allowlist_publishes_exactly_those_tools():
    names = tool_names(built(tools_allow=frozenset({"canvas_auth_status", "canvas_list_students"})))
    assert names == {"canvas_auth_status", "canvas_list_students"}


def test_denylist_removes_one_tool_without_touching_the_rest():
    names = tool_names(built(tools_deny=frozenset({"canvas_bulk_grade"})))
    assert "canvas_bulk_grade" not in names
    assert "canvas_grade_submission" in names


# -- the guard itself ------------------------------------------------------


def test_guard_converts_canvas_errors_into_messages():
    from canvas_mcp.client import CanvasError

    @guard
    def boom(course_id: str = "") -> str:
        raise CanvasError("nope")

    assert boom() == "ERROR: nope"


def test_guard_preserves_the_signature():
    import inspect

    @guard
    def tool(assignment_id: str, course_id: str = "") -> str:
        return "ok"

    assert list(inspect.signature(tool).parameters) == ["assignment_id", "course_id"]


def test_guard_does_not_swallow_programming_errors():
    """A KeyError is a bug in this server, not a Canvas problem. Turning it into
    a polite ERROR: string would hide it from tests and from the user."""

    @guard
    def tool() -> str:
        raise KeyError("oops")

    with pytest.raises(KeyError):
        tool()
