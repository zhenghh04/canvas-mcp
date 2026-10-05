"""Submissions, the gradebook, and grade entry.

Everything here either reads or writes a real student's academic record. The
grading tools are the sharpest edge in this server: a grade posted through the
API lands in the live gradebook with no confirmation step and no undo. Treat
instructor approval as mandatory per call, not per session.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..formatting import slim, slim_all, strip_html
from ..registry import Registrar

SUBMISSION_KEYS = (
    "id",
    "user_id",
    "workflow_state",
    "submitted_at",
    "graded_at",
    "score",
    "grade",
    "late",
    "missing",
    "excused",
    "attempt",
)

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_name(value: str) -> str:
    """Flatten an arbitrary Canvas filename into one safe path component.

    Attachment names come from students, so they are untrusted input on the way
    to a filesystem path: ``../../.ssh/authorized_keys`` is a legal Canvas
    filename. Collapsing everything outside a conservative alphabet removes the
    separators and the dot-dot along with them.
    """
    cleaned = _UNSAFE.sub("_", value).strip("._") or "file"
    return cleaned[:120]


def register(reg: Registrar) -> None:
    client = reg.client

    @reg.tool(group="grading")
    def canvas_list_submissions(
        assignment_id: str,
        course_id: str = "",
        include_ungraded: bool = True,
        only_submitted: bool = False,
    ) -> str:
        """List submissions for an assignment: status, score, timestamps, lateness.

        Metadata only — call canvas_get_submission for a student's actual work.

        Args:
            assignment_id: numeric assignment id.
            course_id: numeric course id; defaults to CANVAS_DEFAULT_COURSE_ID.
            include_ungraded: keep submissions with no score yet (default True).
            only_submitted: drop students who have not turned anything in.
        """
        cid = client.course(course_id)
        subs = client.paged(f"courses/{cid}/assignments/{assignment_id}/submissions")
        rows = slim_all(subs, SUBMISSION_KEYS)
        if not include_ungraded:
            rows = [r for r in rows if not isinstance(r, dict) or r.get("score") is not None]
        if only_submitted:
            rows = [r for r in rows if not isinstance(r, dict) or r.get("submitted_at")]
        return client.fmt(rows)

    @reg.tool(group="grading")
    def canvas_get_submission(
        assignment_id: str, user_id: str, course_id: str = "", max_chars: int = 0
    ) -> str:
        """Get one student's submission: body text, attachments, and comments.

        FERPA: this returns a named student's submitted work. Treat accordingly
        — and note that attachment contents are not inlined, only listed; use
        canvas_download_submissions to fetch the files themselves.

        Args:
            assignment_id: numeric assignment id.
            user_id: numeric Canvas user id, or "self".
            course_id: numeric course id; defaults to CANVAS_DEFAULT_COURSE_ID.
            max_chars: bound on the returned payload (0 = the server default).
        """
        cid = client.course(course_id)
        data = client.get_json(
            f"courses/{cid}/assignments/{assignment_id}/submissions/{user_id}",
            {"include[]": ["submission_comments", "rubric_assessment", "user"]},
        )
        if data.get("body"):
            data["body"] = strip_html(data["body"])
        data["attachments"] = [
            slim(a, ("id", "display_name", "content-type", "size", "url"))
            for a in data.get("attachments") or []
        ]
        return client.fmt(data, max_chars or None)

    @reg.tool(group="grading")
    def canvas_get_gradebook(
        course_id: str = "",
        assignment_ids: str = "",
        include_names: bool = True,
        max_chars: int = 0,
    ) -> str:
        """Get the whole gradebook as one student-by-assignment table.

        One call instead of N calls to canvas_list_submissions. Use it to find
        missing work, spot an assignment nobody passed, or summarise standing
        before office hours. FERPA: this is the full class record.

        Args:
            course_id: numeric course id; defaults to CANVAS_DEFAULT_COURSE_ID.
            assignment_ids: comma-separated ids to restrict to; empty for all.
            include_names: label rows with student names as well as ids.
            max_chars: bound on the returned payload (0 = the server default).
        """
        cid = client.course(course_id)
        wanted = {a.strip() for a in assignment_ids.split(",") if a.strip()}
        assignments = {
            str(a["id"]): a
            for a in client.paged(f"courses/{cid}/assignments")
            if isinstance(a, dict) and (not wanted or str(a["id"]) in wanted)
        }
        names: dict[str, str] = {}
        if include_names:
            for user in client.paged(f"courses/{cid}/users", {"enrollment_type[]": "student"}):
                if isinstance(user, dict):
                    names[str(user.get("id"))] = user.get("name") or ""

        params: dict[str, Any] = {"student_ids[]": "all", "per_page": client.config.per_page}
        if wanted:
            params["assignment_ids[]"] = sorted(wanted)
        rows: dict[str, dict[str, Any]] = {}
        truncated = False
        for sub in client.paged(f"courses/{cid}/students/submissions", params):
            if not isinstance(sub, dict):
                truncated = True
                continue
            uid = str(sub.get("user_id"))
            aid = str(sub.get("assignment_id"))
            if aid not in assignments:
                continue
            row = rows.setdefault(uid, {"user_id": uid, "name": names.get(uid), "scores": {}})
            row["scores"][assignments[aid].get("name") or aid] = {
                "score": sub.get("score"),
                "state": sub.get("workflow_state"),
                "late": sub.get("late"),
                "missing": sub.get("missing"),
            }
        out: dict[str, Any] = {
            "course_id": cid,
            "assignments": [
                slim(a, ("id", "name", "points_possible", "due_at")) for a in assignments.values()
            ],
            "students": sorted(rows.values(), key=lambda r: (r.get("name") or "", r["user_id"])),
        }
        if truncated:
            out["_truncated"] = True
            out["_note"] = "Submission paging hit CANVAS_MAX_PAGES; this gradebook is incomplete."
        return client.fmt(out, max_chars or None)

    @reg.tool(group="grading")
    def canvas_download_submissions(
        assignment_id: str, dest_dir: str = "", course_id: str = "", max_files: int = 100
    ) -> str:
        """Download every file attachment for an assignment to a local folder.

        Writes files to disk on the machine running this server. Each lands as
        ``<dest_dir>/<assignment_id>/<user_id>__<filename>`` so the owner stays
        attached to the file without putting a student name in a path.

        FERPA: this copies student work out of Canvas onto local storage. Make
        sure the instructor knows where it is going and cleans it up afterwards.

        Args:
            assignment_id: numeric assignment id.
            dest_dir: destination folder; defaults to CANVAS_DOWNLOAD_DIR, or
                ./canvas-downloads.
            course_id: numeric course id; defaults to CANVAS_DEFAULT_COURSE_ID.
            max_files: safety cap on how many files to pull (default 100).
        """
        cid = client.course(course_id)
        root = Path(dest_dir).expanduser() if dest_dir else client.config.downloads_path()
        target = root / str(assignment_id)
        subs = client.paged(f"courses/{cid}/assignments/{assignment_id}/submissions")
        saved: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        for sub in subs:
            if not isinstance(sub, dict):
                continue
            for att in sub.get("attachments") or []:
                if len(saved) >= max_files:
                    skipped.append({"user_id": sub.get("user_id"), "reason": "max_files reached"})
                    continue
                url = att.get("url")
                if not url:
                    skipped.append(
                        {"user_id": sub.get("user_id"), "reason": "attachment has no url"}
                    )
                    continue
                name = f"{sub.get('user_id')}__{_safe_name(att.get('display_name') or 'file')}"
                size = client.download(url, target / name)
                saved.append({"user_id": sub.get("user_id"), "file": name, "bytes": size})
        return client.fmt(
            {
                "assignment_id": assignment_id,
                "dest_dir": str(target),
                "downloaded": len(saved),
                "files": saved,
                "skipped": skipped,
            }
        )

    @reg.tool(group="grading", tier="write")
    def canvas_grade_submission(
        assignment_id: str,
        user_id: str,
        grade: str = "",
        comment: str = "",
        excused: bool | None = None,
        course_id: str = "",
    ) -> str:
        """Post a grade and/or a comment to a submission. MUTATES STUDENT RECORDS.

        Writes to the live gradebook immediately and cannot be undone from here.
        ALWAYS show the instructor the exact student, assignment, grade, and
        comment text and get an explicit go-ahead before calling. Never call
        this to "try" something or as part of exploratory reasoning.

        Args:
            assignment_id: numeric assignment id.
            user_id: numeric Canvas user id of the student.
            grade: points ("18"), percentage ("88%"), or a letter grade. Omit to
                post a comment only.
            comment: comment posted alongside the grade; the student sees it.
            excused: True to excuse the student from the assignment entirely.
            course_id: numeric course id; defaults to CANVAS_DEFAULT_COURSE_ID.
        """
        if not grade and not comment and excused is None:
            return "ERROR: supply grade, comment, or excused — nothing to post."
        cid = client.course(course_id)
        payload: dict[str, Any] = {}
        if grade:
            payload["submission[posted_grade]"] = grade
        if comment:
            payload["comment[text_comment]"] = comment
        if excused is not None:
            payload["submission[excuse]"] = "true" if excused else "false"
        data = client.request(
            "PUT",
            f"courses/{cid}/assignments/{assignment_id}/submissions/{user_id}",
            data=payload,
        ).json()
        return client.fmt(slim(data, ("id", "user_id", "score", "grade", "excused", "graded_at")))

    @reg.tool(group="grading", tier="write")
    def canvas_bulk_grade(assignment_id: str, grades_json: str, course_id: str = "") -> str:
        """Post many grades to one assignment at once. MUTATES STUDENT RECORDS.

        Canvas processes this asynchronously and returns a Progress object, so
        the grades appear a few seconds later. There is no partial-failure
        report — read back with canvas_list_submissions to confirm.

        A bulk write is the highest-consequence call in this server. Show the
        instructor the complete table of student ids, grades, and comments and
        get an explicit go-ahead; never assemble one from inference.

        Args:
            assignment_id: numeric assignment id.
            grades_json: JSON object keyed by user id, e.g.
                '{"101": {"grade": "18", "comment": "Clear thesis."},
                  "102": {"grade": "15"}}'.
                A bare string value is accepted as the grade:  '{"101": "18"}'.
            course_id: numeric course id; defaults to CANVAS_DEFAULT_COURSE_ID.
        """
        try:
            grades = json.loads(grades_json)
        except json.JSONDecodeError as exc:
            return f"ERROR: grades_json is not valid JSON: {exc}"
        if not isinstance(grades, dict) or not grades:
            return (
                "ERROR: grades_json must be a non-empty JSON object keyed by user id, "
                'e.g. \'{"101": {"grade": "18"}}\'.'
            )
        cid = client.course(course_id)
        payload: dict[str, Any] = {}
        for user_id, value in grades.items():
            if isinstance(value, dict):
                entry = value
            elif isinstance(value, (str, int, float)):
                entry = {"grade": value}
            else:
                return f"ERROR: entry for user {user_id!r} must be a string or an object."
            if "grade" in entry and entry["grade"] not in (None, ""):
                payload[f"grade_data[{user_id}][posted_grade]"] = entry["grade"]
            if entry.get("comment"):
                payload[f"grade_data[{user_id}][text_comment]"] = entry["comment"]
            if entry.get("excused") is not None and "excused" in entry:
                payload[f"grade_data[{user_id}][excuse]"] = "true" if entry["excused"] else "false"
        if not payload:
            return "ERROR: no grades, comments, or excusals found in grades_json."
        data = client.request(
            "POST",
            f"courses/{cid}/assignments/{assignment_id}/submissions/update_grades",
            data=payload,
        ).json()
        out = slim(data, ("id", "workflow_state", "url"))
        out["students_affected"] = len(grades)
        out["note"] = (
            "Canvas applies bulk grades asynchronously. Re-run canvas_list_submissions "
            "in a few seconds to confirm every row landed."
        )
        return client.fmt(out)
