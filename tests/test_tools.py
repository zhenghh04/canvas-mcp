"""Tool behaviour: the request each tool builds and the guards in front of it.

Every test calls through ``mcp.call_tool``, i.e. the same path the model takes,
so a parameter FastMCP failed to publish shows up as a validation error rather
than passing silently.
"""

from __future__ import annotations

import json

import pytest

from .conftest import FakeResponse, RecordingClient, call, make_config


@pytest.fixture
def client():
    return RecordingClient(make_config())


def respond(client: RecordingClient, payload):
    client.responses = payload
    return client


# -- read tools ------------------------------------------------------------


def test_list_courses_flattens_the_term_object(client):
    """Canvas nests term as an object; a bare id tells the instructor nothing
    and the whole object is noise."""
    respond(client, [{"id": 1, "name": "CSCI 493", "term": {"id": 9, "name": "Fall 2026"}}])
    out = json.loads(call(client, "canvas_list_courses"))
    assert out[0]["term"] == "Fall 2026"


def test_get_course_renders_the_syllabus_as_text_and_adds_a_link(client):
    respond(client, {"id": 12345, "name": "X", "syllabus_body": "<p>Week 1</p><p>Week 2</p>"})
    out = json.loads(call(client, "canvas_get_course"))
    assert out["syllabus_body"] == "Week 1\nWeek 2"
    assert out["html_url"] == "https://example.instructure.com/courses/12345"


def test_course_id_falls_back_to_the_default(client):
    respond(client, {"id": 12345})
    call(client, "canvas_get_course")
    assert client.last["path"] == "courses/12345"


def test_missing_course_id_errors_instead_of_guessing():
    c = RecordingClient(make_config(default_course_id=""))
    assert call(c, "canvas_get_course").startswith("ERROR:")
    assert c.calls == []


def test_list_students_asks_for_email_only_when_requested(client):
    """Requesting emails by default would pull identifiers into every roster
    read whether the task needed them or not."""
    respond(client, [{"id": 1, "name": "Ada", "email": "a@x.edu"}])
    call(client, "canvas_list_students")
    assert "include[]" not in client.last["params"]
    call(client, "canvas_list_students", include_email=True)
    assert client.last["params"]["include[]"] == ["email"]


def test_pii_redaction_applies_to_tool_output():
    c = RecordingClient(
        make_config(redact_pii=True), responses=[{"id": 1, "name": "Ada", "email": "a@x.edu"}]
    )
    out = call(c, "canvas_list_students", include_email=True)
    assert "a@x.edu" not in out and "anon-" in out
    assert "Ada" in out


def test_list_enrollments_surfaces_the_user_name_alongside_the_enrollment_id(client):
    """The enrollment id is what mutations need, but it is unrecognisable; the
    name is what the instructor will be asked to confirm."""
    respond(
        client, [{"id": 55, "user_id": 7, "type": "StudentEnrollment", "user": {"name": "Ada"}}]
    )
    out = json.loads(call(client, "canvas_list_enrollments"))
    assert out[0]["id"] == 55 and out[0]["user_name"] == "Ada"


def test_api_get_rejects_malformed_params_before_any_call(client):
    out = call(client, "canvas_api_get", path="x", params_json="{not json")
    assert out.startswith("ERROR:") and "JSON" in out
    assert client.calls == []


def test_api_get_rejects_a_json_array_for_params(client):
    out = call(client, "canvas_api_get", path="x", params_json="[1,2]")
    assert out.startswith("ERROR:") and "JSON object" in out


def test_get_gradebook_pivots_submissions_into_rows():
    c = RecordingClient(make_config())
    c.responses = [
        [{"id": 1, "name": "Paper 1", "points_possible": 20}],
        [{"id": 101, "name": "Ada"}, {"id": 102, "name": "Bob"}],
        [
            {"user_id": 101, "assignment_id": 1, "score": 18, "workflow_state": "graded"},
            {"user_id": 102, "assignment_id": 1, "score": None, "workflow_state": "unsubmitted"},
        ],
    ]
    out = json.loads(call(c, "canvas_get_gradebook"))
    rows = {r["name"]: r for r in out["students"]}
    assert rows["Ada"]["scores"]["Paper 1"]["score"] == 18
    assert rows["Bob"]["scores"]["Paper 1"]["score"] is None


# -- write guards ----------------------------------------------------------


@pytest.mark.parametrize(
    "name,kwargs",
    [
        ("canvas_update_assignment", {"assignment_id": "1"}),
        ("canvas_update_page", {"page_url": "x"}),
        ("canvas_update_module", {"module_id": "1"}),
        ("canvas_update_course", {}),
    ],
)
def test_update_with_no_fields_is_rejected_not_sent(client, name, kwargs):
    """An all-defaults update would PUT an empty body — harmless but confusing.
    Reject it so the caller learns they passed nothing."""
    assert call(client, name, **kwargs).startswith("ERROR:")
    assert client.calls == []


def test_grade_submission_refuses_an_empty_post(client):
    out = call(client, "canvas_grade_submission", assignment_id="1", user_id="2")
    assert out.startswith("ERROR:")
    assert client.calls == []


def test_grade_submission_sends_grade_and_comment_in_canvas_shape(client):
    respond(client, {"id": 1, "user_id": 2, "score": 18})
    call(
        client,
        "canvas_grade_submission",
        assignment_id="7",
        user_id="2",
        grade="18",
        comment="Nice",
    )
    assert client.last["path"] == "courses/12345/assignments/7/submissions/2"
    assert client.last["data"] == {
        "submission[posted_grade]": "18",
        "comment[text_comment]": "Nice",
    }


def test_excused_is_a_distinct_outcome_from_a_zero(client):
    respond(client, {"id": 1, "excused": True})
    call(client, "canvas_grade_submission", assignment_id="7", user_id="2", excused=True)
    assert client.last["data"] == {"submission[excuse]": "true"}


@pytest.mark.parametrize("bad", ["not json", "[]", "{}", '{"1": [2]}'])
def test_bulk_grade_rejects_unusable_input_before_sending(client, bad):
    assert call(client, "canvas_bulk_grade", assignment_id="1", grades_json=bad).startswith(
        "ERROR:"
    )
    assert client.calls == []


def test_bulk_grade_accepts_both_shorthand_and_full_entries(client):
    respond(client, {"id": 9, "workflow_state": "queued"})
    call(
        client,
        "canvas_bulk_grade",
        assignment_id="7",
        grades_json='{"101": "18", "102": {"grade": "15", "comment": "See notes"}}',
    )
    assert client.last["data"] == {
        "grade_data[101][posted_grade]": "18",
        "grade_data[102][posted_grade]": "15",
        "grade_data[102][text_comment]": "See notes",
    }


def test_bulk_grade_warns_that_canvas_applies_it_asynchronously(client):
    """Reading the gradebook back immediately shows the old scores; without this
    note a model concludes the write failed and does it again."""
    respond(client, {"id": 9, "workflow_state": "queued"})
    out = call(client, "canvas_bulk_grade", assignment_id="7", grades_json='{"1": "5"}')
    assert "asynchronously" in out


@pytest.mark.parametrize(
    "name,kwargs,published_key",
    [
        ("canvas_create_assignment", {"name": "a"}, "assignment[published]"),
        ("canvas_create_page", {"title": "p"}, "wiki_page[published]"),
        ("canvas_create_module", {"name": "m"}, "module[published]"),
        ("canvas_create_discussion", {"title": "d", "message": "m"}, "published"),
    ],
)
def test_authoring_tools_default_to_unpublished(client, name, kwargs, published_key):
    """Creating content must not expose it to students before review."""
    respond(client, {"id": 1})
    call(client, name, **kwargs)
    assert client.last["data"][published_key] == "false"


def test_create_assignment_rejects_an_unknown_submission_type(client):
    """Canvas accepts the request and silently files it under "none", so the
    assignment exists but no student can submit to it."""
    out = call(client, "canvas_create_assignment", name="a", submission_types="online_essay")
    assert out.startswith("ERROR:") and "online_text_entry" in out
    assert client.calls == []


def test_update_assignment_sends_only_the_fields_passed(client):
    """Omitted fields must not be blanked — a PUT with name="" renames the
    assignment to the empty string."""
    respond(client, {"id": 1})
    call(client, "canvas_update_assignment", assignment_id="1", due_at="2026-09-10T04:59:59Z")
    assert client.last["data"] == {"assignment[due_at]": "2026-09-10T04:59:59Z"}


def test_enroll_user_defaults_to_invited_and_silent(client):
    """Enrolling must not silently add somebody to a live roster or email them."""
    respond(client, {"id": 1, "user_id": 2})
    call(client, "canvas_enroll_user", user_id="2")
    assert client.last["data"]["enrollment[enrollment_state]"] == "invited"
    assert client.last["data"]["enrollment[notify]"] == "false"


def test_enroll_into_a_section_uses_the_section_endpoint(client):
    respond(client, {"id": 1})
    call(client, "canvas_enroll_user", user_id="2", section_id="77")
    assert client.last["path"] == "sections/77/enrollments"


def test_syllabus_update_sends_the_bracketed_course_param(client):
    """A bare syllabus_body is silently ignored by Canvas — the PUT succeeds and
    nothing changes."""
    respond(client, {"id": 12345, "syllabus_body": "<p>hi</p>"})
    call(client, "canvas_update_syllabus", body="<p>hi</p>")
    assert client.last["method"] == "PUT"
    assert client.last["path"] == "courses/12345"
    assert client.last["data"] == {"course[syllabus_body]": "<p>hi</p>"}


def test_publishing_a_course_uses_the_event_verb_not_a_boolean(client):
    """course[published]=true is not a thing; Canvas wants event=offer."""
    respond(client, {"id": 12345})
    call(client, "canvas_update_course", published=True)
    assert client.last["data"]["course[event]"] == "offer"


def test_announcement_reports_whether_the_roster_was_notified(client):
    respond(client, {"id": 1, "title": "t"})
    immediate = json.loads(call(client, "canvas_post_announcement", title="t", message="m"))
    assert immediate["notified_roster"] is True
    scheduled = json.loads(
        call(
            client,
            "canvas_post_announcement",
            title="t",
            message="m",
            delayed_post_at="2026-09-10T12:00:00Z",
        )
    )
    assert scheduled["notified_roster"] is False


def test_message_students_defaults_to_separate_threads(client):
    """A shared thread discloses the recipient list to every recipient."""
    respond(client, [{"id": 1}])
    call(client, "canvas_message_students", recipient_ids="1,2,3", subject="s", body="b")
    assert client.last["data"]["group_conversation"] == "false"
    assert client.last["data"]["bulk_message"] == "true"
    assert client.last["data"]["recipients[]"] == ["1", "2", "3"]


def test_message_students_accepts_a_json_array(client):
    respond(client, [{"id": 1}])
    call(client, "canvas_message_students", recipient_ids="[1, 2]", subject="s", body="b")
    assert client.last["data"]["recipients[]"] == ["1", "2"]


def test_message_students_rejects_an_empty_recipient_list(client):
    out = call(client, "canvas_message_students", recipient_ids=" , ", subject="s", body="b")
    assert out.startswith("ERROR:")
    assert client.calls == []


# -- module items ----------------------------------------------------------


@pytest.mark.parametrize("item_type", ["Assignment", "Quiz", "File", "Discussion"])
def test_module_item_requires_content_id(client, item_type):
    out = call(client, "canvas_create_module_item", module_id="1", title="t", item_type=item_type)
    assert out.startswith("ERROR:") and "content_id" in out
    assert client.calls == []


def test_module_item_page_requires_the_slug_not_content_id(client):
    """A Page item keyed by content_id is the easy mistake; Canvas 400s unhelpfully."""
    out = call(
        client,
        "canvas_create_module_item",
        module_id="1",
        title="t",
        item_type="Page",
        content_id="9",
    )
    assert out.startswith("ERROR:") and "page_url" in out


def test_module_item_external_url_is_required(client):
    out = call(
        client, "canvas_create_module_item", module_id="1", title="t", item_type="ExternalUrl"
    )
    assert out.startswith("ERROR:") and "external_url" in out


def test_module_item_rejects_an_unknown_type(client):
    out = call(client, "canvas_create_module_item", module_id="1", title="t", item_type="Lecture")
    assert out.startswith("ERROR:") and "SubHeader" in out


def test_subheader_needs_no_identifier(client):
    """SubHeader is the one type with no target — it must not hit the guards."""
    respond(client, {"id": 5, "title": "t", "type": "SubHeader"})
    out = call(client, "canvas_create_module_item", module_id="1", title="t", item_type="SubHeader")
    assert not out.startswith("ERROR:")
    assert client.last["method"] == "POST"


# -- destructive guards ----------------------------------------------------


def test_remove_enrollment_rejects_an_unknown_task(client):
    out = call(client, "canvas_remove_enrollment", enrollment_id="1", task="destroy")
    assert out.startswith("ERROR:") and "conclude" in out
    assert client.calls == []


def test_remove_enrollment_defaults_to_the_reversible_task(client):
    """The irreversible option must never be what you get by not choosing."""
    respond(client, {"id": 1, "user_id": 2})
    out = call(client, "canvas_remove_enrollment", enrollment_id="1")
    assert client.last["params"] == {"task": "conclude"}
    assert json.loads(out)["reversible"] is True


def test_remove_enrollment_flags_delete_as_irreversible(client):
    respond(client, {"id": 1})
    out = call(client, "canvas_remove_enrollment", enrollment_id="1", task="delete")
    assert json.loads(out)["reversible"] is False


def test_delete_assignment_returns_the_undelete_url(client):
    """Canvas soft-deletes, but only if you know where the recycle bin is."""
    respond(client, {"id": 1, "name": "a", "workflow_state": "deleted"})
    out = json.loads(call(client, "canvas_delete_assignment", assignment_id="1"))
    assert out["undelete_url"] == "https://example.instructure.com/courses/12345/undelete"


@pytest.mark.parametrize("method", ["GET", "HEAD", "get", "fetch"])
def test_api_write_refuses_non_write_methods(client, method):
    out = call(client, "canvas_api_write", method=method, path="x")
    assert out.startswith("ERROR:")
    assert client.calls == []


def test_api_write_accepts_a_lowercase_verb(client):
    respond(client, {"ok": True})
    call(client, "canvas_api_write", method="delete", path="courses/1/pages/x")
    assert client.last["method"] == "DELETE"


# -- uploads and downloads -------------------------------------------------


def test_upload_rejects_a_missing_file(client, tmp_path):
    out = call(client, "canvas_upload_file", local_path=str(tmp_path / "nope.pdf"))
    assert out.startswith("ERROR:") and "no such file" in out
    assert client.calls == []


def test_upload_rejects_an_unknown_on_duplicate(client, tmp_path):
    path = tmp_path / "a.txt"
    path.write_text("x")
    out = call(client, "canvas_upload_file", local_path=str(path), on_duplicate="clobber")
    assert out.startswith("ERROR:") and "on_duplicate" in out


def test_upload_enforces_the_size_cap(tmp_path):
    path = tmp_path / "big.bin"
    path.write_bytes(b"0" * 2048)
    c = RecordingClient(make_config(max_upload_mb=0.001))
    out = call(c, "canvas_upload_file", local_path=str(path))
    assert out.startswith("ERROR:") and "cap" in out
    assert c.calls == []


def test_download_submissions_sanitises_student_supplied_filenames(client, tmp_path, monkeypatch):
    """Attachment names come from students. "../../../etc/passwd" is a legal
    Canvas filename, and it must not become a path that escapes dest_dir."""
    client.responses = [
        [{"user_id": 7, "attachments": [{"url": "https://f/1", "display_name": "../../evil.txt"}]}]
    ]
    written: list = []
    monkeypatch.setattr(
        "canvas_mcp.client.CanvasClient.download",
        lambda self, url, dest: (written.append(dest), 3)[1],
    )
    out = json.loads(
        call(client, "canvas_download_submissions", assignment_id="1", dest_dir=str(tmp_path))
    )
    assert out["downloaded"] == 1
    assert written[0].parent == tmp_path / "1"
    assert ".." not in written[0].name


def test_download_submissions_honours_max_files(client, tmp_path, monkeypatch):
    client.responses = [
        [
            {"user_id": i, "attachments": [{"url": "https://f", "display_name": "a.txt"}]}
            for i in range(5)
        ]
    ]
    monkeypatch.setattr("canvas_mcp.client.CanvasClient.download", lambda self, url, dest: 1)
    out = json.loads(
        call(
            client,
            "canvas_download_submissions",
            assignment_id="1",
            dest_dir=str(tmp_path),
            max_files=2,
        )
    )
    assert out["downloaded"] == 2
    assert len(out["skipped"]) == 3


def test_download_file_without_a_url_explains_why(client):
    respond(client, {"id": 1, "display_name": "a.pdf"})
    out = call(client, "canvas_download_file", file_id="1")
    assert out.startswith("ERROR:") and "locked" in out


# -- auth status -----------------------------------------------------------


def test_auth_status_never_echoes_the_token():
    c = RecordingClient(
        make_config(api_token="super-secret-token"), responses={"id": 1, "name": "T"}
    )
    out = call(c, "canvas_auth_status")
    assert "super-secret-token" not in out
    assert json.loads(out)["token_configured"] is True


def test_auth_status_without_a_token_gives_a_remedy_and_makes_no_call():
    c = RecordingClient(make_config(api_token=""))
    out = json.loads(call(c, "canvas_auth_status"))
    assert out["authenticated"] is False
    assert "New Access Token" in out["remedy"]
    assert c.calls == []


def test_auth_status_lists_the_tools_a_flag_withheld():
    """Answering "why can't you grade?" without making the user read the source."""
    c = RecordingClient(make_config(enable_writes=False), responses={"id": 1})
    out = json.loads(call(c, "canvas_auth_status"))
    assert "canvas_grade_submission" in out["tools"]["withheld"]


def test_auth_status_reports_a_bad_token_without_raising():
    c = RecordingClient(make_config(), responses=FakeResponse(None, status=401, text="nope"))
    out = json.loads(call(c, "canvas_auth_status"))
    assert out["authenticated"] is False
    assert "401" in out["error"]
