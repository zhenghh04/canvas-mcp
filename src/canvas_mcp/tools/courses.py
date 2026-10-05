"""Courses, sections, and the syllabus."""

from __future__ import annotations

from typing import Any

from ..formatting import form, slim, slim_all, strip_html
from ..registry import Registrar

COURSE_KEYS = (
    "id",
    "name",
    "course_code",
    "workflow_state",
    "start_at",
    "end_at",
    "total_students",
    "term",
)


def register(reg: Registrar) -> None:
    client = reg.client
    config = reg.config

    @reg.tool(group="courses")
    def canvas_list_courses(enrollment_state: str = "active", enrollment_type: str = "") -> str:
        """List the courses the authenticated user can see.

        Start here when you do not know the course id. The id in the output is
        what every other tool's course_id parameter wants.

        Args:
            enrollment_state: active (default), completed, or invited_or_pending.
            enrollment_type: filter by your role — teacher, ta, student,
                observer, designer. Empty for all roles.
        """
        params: dict[str, Any] = {"enrollment_state": enrollment_state}
        if enrollment_type:
            params["enrollment_type"] = enrollment_type
        params["include[]"] = ["term"]
        courses = client.paged("courses", params)
        rows = []
        for course in courses:
            if not isinstance(course, dict):
                rows.append(course)
                continue
            row = slim(course, COURSE_KEYS)
            term = row.get("term")
            if isinstance(term, dict):
                row["term"] = term.get("name")
            rows.append(row)
        return client.fmt(rows)

    @reg.tool(group="courses")
    def canvas_get_course(course_id: str = "", max_chars: int = 0) -> str:
        """Get one course: teachers, student count, and the syllabus as plain text.

        Args:
            course_id: numeric id from the course URL; falls back to
                CANVAS_DEFAULT_COURSE_ID.
            max_chars: bound on the returned payload (0 = the server default).
        """
        cid = client.course(course_id)
        data = client.get_json(
            f"courses/{cid}",
            {"include[]": ["teachers", "total_students", "syllabus_body", "term"]},
        )
        if "syllabus_body" in data:
            data["syllabus_body"] = strip_html(data["syllabus_body"])
        data["html_url"] = f"{config.base_url}/courses/{cid}"
        return client.fmt(data, max_chars or None)

    @reg.tool(group="courses")
    def canvas_list_sections(course_id: str = "") -> str:
        """List a course's sections with their enrollment counts.

        Sections matter for anything scoped to part of a roster — section-level
        due dates, a lab subsection, or enrolling someone into one specific
        section rather than the course default.

        Args:
            course_id: numeric course id; defaults to CANVAS_DEFAULT_COURSE_ID.
        """
        cid = client.course(course_id)
        rows = client.paged(f"courses/{cid}/sections", {"include[]": ["total_students"]})
        keys = ("id", "name", "sis_section_id", "start_at", "end_at", "total_students")
        return client.fmt(slim_all(rows, keys))

    @reg.tool(group="courses", tier="write")
    def canvas_update_course(
        name: str = "",
        course_code: str = "",
        start_at: str = "",
        end_at: str = "",
        published: bool | None = None,
        default_view: str = "",
        course_id: str = "",
    ) -> str:
        """Edit course settings. MUTATES the live course.

        Only the fields you pass change. Publishing a course makes it visible to
        every enrolled student immediately, and Canvas will not let you
        unpublish once a student has submitted work — confirm before setting
        published=True.

        Args:
            name: new course name, or empty to leave unchanged.
            course_code: new short code, or empty to leave unchanged.
            start_at: ISO 8601 UTC start, e.g. 2026-08-26T05:00:00Z.
            end_at: ISO 8601 UTC end.
            published: True to publish, False to unpublish, omit to leave alone.
            default_view: landing page — feed, wiki, modules, syllabus, assignments.
            course_id: numeric course id; defaults to CANVAS_DEFAULT_COURSE_ID.
        """
        cid = client.course(course_id)
        payload = form(
            **{
                "course[name]": name,
                "course[course_code]": course_code,
                "course[start_at]": start_at,
                "course[end_at]": end_at,
                "course[default_view]": default_view,
            }
        )
        if published is not None:
            payload["course[event]"] = "offer" if published else "claim"
        if not payload:
            return "ERROR: no fields given to update — nothing to change."
        data = client.request("PUT", f"courses/{cid}", data=payload).json()
        out = slim(data, COURSE_KEYS)
        out["html_url"] = f"{config.base_url}/courses/{cid}"
        return client.fmt(out)

    @reg.tool(group="courses", tier="write")
    def canvas_update_syllabus(body: str, course_id: str = "") -> str:
        """Replace the course syllabus body. MUTATES the live course page.

        This OVERWRITES the existing syllabus wholesale — Canvas keeps no
        version history for it, so read canvas_get_course first if the current
        text matters, and show the instructor what is being replaced.

        Args:
            body: the new syllabus HTML. Plain text works, but newlines are not
                converted to <br>, so pass HTML if you want formatting.
            course_id: numeric course id; defaults to CANVAS_DEFAULT_COURSE_ID.
        """
        cid = client.course(course_id)
        data = client.request("PUT", f"courses/{cid}", data={"course[syllabus_body]": body}).json()
        out = slim(data, ("id", "name"))
        out["syllabus_chars"] = len(data.get("syllabus_body") or "")
        out["html_url"] = f"{config.base_url}/courses/{cid}/assignments/syllabus"
        return client.fmt(out)
