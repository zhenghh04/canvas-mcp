"""Payload shaping: slimming, bounding, HTML flattening, PII redaction."""

from __future__ import annotations

import json

from canvas_mcp.formatting import (
    PII_KEYS,
    form,
    format_payload,
    pseudonym,
    redact,
    slim,
    slim_all,
    strip_html,
)


def test_slim_keeps_only_present_requested_keys():
    assert slim({"id": 1, "name": "x", "noise": 2}, ("id", "name", "absent")) == {
        "id": 1,
        "name": "x",
    }


def test_slim_all_passes_non_dicts_through():
    """The pagination truncation marker is a dict, but a malformed Canvas
    response might not be — dropping it would hide that the list is partial."""
    rows = slim_all([{"id": 1, "x": 9}, "junk"], ("id",))
    assert rows == [{"id": 1}, "junk"]


def test_format_payload_truncates_and_says_so():
    text = format_payload({"body": "x" * 500}, 100)
    assert len(text) < 300
    assert "truncated" in text and "max_chars" in text


def test_format_payload_unbounded_when_max_chars_zero():
    text = format_payload({"body": "x" * 500}, 0)
    assert "truncated" not in text


def test_redaction_is_stable_and_non_reversible():
    a = pseudonym("student@example.edu")
    assert a == pseudonym("student@example.edu")
    assert "student" not in a and "example" not in a


def test_redaction_reaches_nested_structures():
    data = {"users": [{"name": "Ada", "email": "ada@x.edu", "sis_user_id": "S1"}]}
    out = redact(data)
    user = out["users"][0]
    assert user["name"] == "Ada", "names are not direct identifiers; the model needs them"
    assert user["email"].startswith("anon-")
    assert user["sis_user_id"].startswith("anon-")


def test_redaction_leaves_empty_identifiers_alone():
    """Hashing "" would invent an identifier for a student who has none, and the
    same hash for every such student."""
    assert redact({"email": None})["email"] is None
    assert redact({"email": ""})["email"] == ""


def test_format_payload_applies_redaction_when_asked():
    text = format_payload({"email": "a@b.edu"}, 0, redact_pii=True)
    assert "a@b.edu" not in text and "anon-" in text


def test_every_pii_key_is_actually_redacted():
    data = {key: "value" for key in PII_KEYS}
    out = redact(data)
    assert all(v.startswith("anon-") for v in out.values())


# -- HTML ------------------------------------------------------------------


def test_strip_html_keeps_paragraph_breaks():
    """Canvas page bodies are HTML. Dropping tags without replacing block ends
    collapses a syllabus into one unreadable run-on line."""
    out = strip_html("<p>Week 1</p><p>Week 2</p>")
    assert out.splitlines() == ["Week 1", "Week 2"]


def test_strip_html_handles_br_and_lists():
    out = strip_html("<ul><li>A</li><li>B</li></ul>")
    assert "A" in out and "B" in out and out.index("A") < out.index("B")
    assert strip_html("one<br/>two").splitlines() == ["one", "two"]


def test_strip_html_unescapes_entities():
    assert strip_html("<p>Bonhoeffer &amp; Barth</p>") == "Bonhoeffer & Barth"


def test_strip_html_on_empty_input():
    assert strip_html(None) == "" and strip_html("") == ""


# -- form ------------------------------------------------------------------


def test_form_drops_unset_but_keeps_meaningful_falsy():
    """False and 0 are real values a caller may intend; None and "" are "unset".

    Getting this wrong either blanks fields the caller never mentioned or
    silently refuses to set points_possible=0 / published=False."""
    assert form(a=None, b="", c=False, d=0, e="x") == {"c": "false", "d": 0, "e": "x"}


def test_form_renders_booleans_as_canvas_strings():
    assert form(flag=True) == {"flag": "true"}


def test_format_payload_is_valid_json_when_untruncated():
    assert json.loads(format_payload({"a": [1, 2]}, 0)) == {"a": [1, 2]}
