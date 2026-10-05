"""Assignments and assignment groups."""

from __future__ import annotations

from ..formatting import form, slim, slim_all, strip_html
from ..registry import Registrar

ASSIGNMENT_KEYS = (
    "id",
    "name",
    "due_at",
    "unlock_at",
    "lock_at",
    "points_possible",
    "grading_type",
    "submission_types",
    "published",
    "needs_grading_count",
    "assignment_group_id",
    "html_url",
)

SUBMISSION_TYPES = (
    "online_text_entry",
    "online_upload",
    "online_url",
    "online_quiz",
    "discussion_topic",
    "media_recording",
    "student_annotation",
    "on_paper",
    "external_tool",
    "none",
)


def register(reg: Registrar) -> None:
    client = reg.client
    config = reg.config

    @reg.tool(group="assignments")
    def canvas_list_assignments(
        course_id: str = "", bucket: str = "", search_term: str = ""
    ) -> str:
        """List assignments in a course, with due dates and needs-grading counts.

        Args:
            course_id: numeric course id; defaults to CANVAS_DEFAULT_COURSE_ID.
            bucket: optional filter — past, overdue, undated, ungraded,
                unsubmitted, upcoming, future.
            search_term: optional title substring filter.
        """
        cid = client.course(course_id)
        params = {}
        if bucket:
            params["bucket"] = bucket
        if search_term:
            params["search_term"] = search_term
        items = client.paged(f"courses/{cid}/assignments", params)
        return client.fmt(slim_all(items, ASSIGNMENT_KEYS))

    @reg.tool(group="assignments")
    def canvas_get_assignment(assignment_id: str, course_id: str = "", max_chars: int = 0) -> str:
        """Get one assignment, with its description rendered to plain text.

        Args:
            assignment_id: numeric assignment id.
            course_id: numeric course id; defaults to CANVAS_DEFAULT_COURSE_ID.
            max_chars: bound on the returned payload (0 = the server default).
        """
        cid = client.course(course_id)
        data = client.get_json(f"courses/{cid}/assignments/{assignment_id}")
        if "description" in data:
            data["description"] = strip_html(data["description"])
        return client.fmt(data, max_chars or None)

    @reg.tool(group="assignments")
    def canvas_list_assignment_groups(course_id: str = "") -> str:
        """List assignment groups and their gradebook weights.

        A course that grades by weighted categories ("Participation 20%, Papers
        50%...") carries those weights here, not on the assignments. Read this
        before reasoning about what a score is worth.

        Args:
            course_id: numeric course id; defaults to CANVAS_DEFAULT_COURSE_ID.
        """
        cid = client.course(course_id)
        rows = client.paged(f"courses/{cid}/assignment_groups")
        keys = ("id", "name", "position", "group_weight")
        return client.fmt(slim_all(rows, keys))

    @reg.tool(group="assignments", tier="write")
    def canvas_create_assignment_group(
        name: str,
        group_weight: float | None = None,
        position: int | None = None,
        course_id: str = "",
    ) -> str:
        """Create an assignment group (a gradebook category). MUTATES the course.

        Args:
            name: group name, e.g. "Response Papers".
            group_weight: percentage of the final grade, if the course uses
                weighted groups. Omit for unweighted.
            position: 1-based slot in the group list; omit to append.
            course_id: numeric course id; defaults to CANVAS_DEFAULT_COURSE_ID.
        """
        cid = client.course(course_id)
        payload = form(name=name, group_weight=group_weight, position=position)
        data = client.request("POST", f"courses/{cid}/assignment_groups", data=payload).json()
        return client.fmt(slim(data, ("id", "name", "position", "group_weight")))

    @reg.tool(group="assignments", tier="write")
    def canvas_create_assignment(
        name: str,
        description: str = "",
        points_possible: float | None = None,
        due_at: str = "",
        unlock_at: str = "",
        lock_at: str = "",
        submission_types: str = "online_text_entry",
        grading_type: str = "",
        published: bool = False,
        assignment_group_id: str = "",
        omit_from_final_grade: bool | None = None,
        course_id: str = "",
    ) -> str:
        """Create an assignment. MUTATES the course.

        Defaults to UNPUBLISHED so students do not see it until you publish —
        pass published=True only when the instructor says it is ready.

        Args:
            name: assignment title.
            description: body HTML shown to students.
            points_possible: max score; omit for an ungraded assignment.
            due_at: ISO 8601 UTC, e.g. 2026-09-10T04:59:59Z. Canvas stores UTC,
                so an 11:59pm local deadline is not 23:59Z — convert first.
            unlock_at: ISO 8601 UTC; students cannot see it before this.
            lock_at: ISO 8601 UTC; submissions close after this.
            submission_types: comma-separated, from online_text_entry,
                online_upload, online_url, online_quiz, discussion_topic,
                media_recording, student_annotation, on_paper, external_tool, none.
            grading_type: points (default), percent, letter_grade, gpa_scale,
                pass_fail, not_graded.
            published: visible to students immediately (default False).
            assignment_group_id: group to file it under; see
                canvas_list_assignment_groups.
            omit_from_final_grade: True to score it without affecting the total.
            course_id: numeric course id; defaults to CANVAS_DEFAULT_COURSE_ID.
        """
        types = [t.strip() for t in submission_types.split(",") if t.strip()]
        unknown = [t for t in types if t not in SUBMISSION_TYPES]
        if unknown:
            return (
                f"ERROR: unknown submission_types {unknown}. Valid values: "
                f"{', '.join(SUBMISSION_TYPES)}."
            )
        cid = client.course(course_id)
        payload = form(
            **{
                "assignment[name]": name,
                "assignment[description]": description,
                "assignment[points_possible]": points_possible,
                "assignment[due_at]": due_at,
                "assignment[unlock_at]": unlock_at,
                "assignment[lock_at]": lock_at,
                "assignment[grading_type]": grading_type,
                "assignment[published]": published,
                "assignment[assignment_group_id]": assignment_group_id,
                "assignment[omit_from_final_grade]": omit_from_final_grade,
            }
        )
        payload["assignment[submission_types][]"] = types
        data = client.request("POST", f"courses/{cid}/assignments", data=payload).json()
        return client.fmt(slim(data, ASSIGNMENT_KEYS))

    @reg.tool(group="assignments", tier="write")
    def canvas_update_assignment(
        assignment_id: str,
        name: str = "",
        description: str = "",
        points_possible: float | None = None,
        due_at: str = "",
        unlock_at: str = "",
        lock_at: str = "",
        published: bool | None = None,
        assignment_group_id: str = "",
        course_id: str = "",
    ) -> str:
        """Edit an existing assignment. MUTATES the course.

        Only the fields you pass are changed; omitted ones are left alone. Two
        edits have downstream gradebook effects worth flagging to the
        instructor: publishing an assignment students have not seen, and
        changing points_possible on one that is already graded (every existing
        score is silently re-scaled in the totals).

        Args:
            assignment_id: numeric assignment id.
            name: new title, or empty to leave unchanged.
            description: new body HTML, or empty to leave unchanged.
            points_possible: new max score, or omit to leave unchanged.
            due_at: new ISO 8601 UTC due date, or empty to leave unchanged.
            unlock_at: new ISO 8601 UTC availability date.
            lock_at: new ISO 8601 UTC close date.
            published: True/False to change visibility, or omit to leave alone.
            assignment_group_id: move it to another gradebook category.
            course_id: numeric course id; defaults to CANVAS_DEFAULT_COURSE_ID.
        """
        cid = client.course(course_id)
        payload = form(
            **{
                "assignment[name]": name,
                "assignment[description]": description,
                "assignment[points_possible]": points_possible,
                "assignment[due_at]": due_at,
                "assignment[unlock_at]": unlock_at,
                "assignment[lock_at]": lock_at,
                "assignment[published]": published,
                "assignment[assignment_group_id]": assignment_group_id,
            }
        )
        if not payload:
            return "ERROR: no fields given to update — nothing to change."
        data = client.request(
            "PUT", f"courses/{cid}/assignments/{assignment_id}", data=payload
        ).json()
        return client.fmt(slim(data, ASSIGNMENT_KEYS))

    @reg.tool(group="assignments", tier="destructive")
    def canvas_delete_assignment(assignment_id: str, course_id: str = "") -> str:
        """Delete an assignment. MUTATES the course and hides any grades on it.

        Canvas soft-deletes, so this is recoverable from the course's /undelete
        page — but any submissions and scores attached to it disappear from the
        gradebook meanwhile, and students lose access to their own work.
        Confirm with the instructor first.

        Args:
            assignment_id: numeric assignment id.
            course_id: numeric course id; defaults to CANVAS_DEFAULT_COURSE_ID.
        """
        cid = client.course(course_id)
        data = client.request("DELETE", f"courses/{cid}/assignments/{assignment_id}").json()
        out = slim(data, ("id", "name", "workflow_state"))
        out["undelete_url"] = f"{config.base_url}/courses/{cid}/undelete"
        return client.fmt(out)
