"""Roster: students, enrollments, and roster changes.

Everything in this module returns or alters data about identifiable students.
See docs/SAFETY.md — ``CANVAS_REDACT_PII=1`` hashes direct identifiers if you
want to reason over a roster without shipping the identifiers anywhere.
"""

from __future__ import annotations

from typing import Any

from ..formatting import form, slim, slim_all
from ..registry import Registrar

ENROLLMENT_TASKS = ("conclude", "inactivate", "deactivate", "delete")


def register(reg: Registrar) -> None:
    client = reg.client

    @reg.tool(group="people")
    def canvas_list_students(
        course_id: str = "", include_email: bool = False, search_term: str = ""
    ) -> str:
        """List the students enrolled in a course.

        FERPA: returns student names, and email addresses when
        include_email=True. With CANVAS_REDACT_PII=1 identifiers come back as
        stable hashes instead.

        Args:
            course_id: numeric course id; defaults to CANVAS_DEFAULT_COURSE_ID.
            include_email: also request email addresses (default False).
            search_term: optional name/login substring filter (3+ characters).
        """
        cid = client.course(course_id)
        params: dict[str, Any] = {"enrollment_type[]": "student"}
        if include_email:
            params["include[]"] = ["email"]
        if search_term:
            params["search_term"] = search_term
        users = client.paged(f"courses/{cid}/users", params)
        keys = ("id", "name", "sortable_name", "email", "login_id", "sis_user_id")
        return client.fmt(slim_all(users, keys))

    @reg.tool(group="people")
    def canvas_list_enrollments(course_id: str = "", role: str = "", state: str = "active") -> str:
        """List enrollments, including the enrollment_id needed to change one.

        canvas_list_students returns *users*; removing or modifying somebody
        needs the *enrollment* id, which is a different number. Fetch it here
        first — passing a user id to canvas_remove_enrollment silently targets
        the wrong record or 404s.

        Args:
            course_id: numeric course id; defaults to CANVAS_DEFAULT_COURSE_ID.
            role: StudentEnrollment, TeacherEnrollment, TaEnrollment,
                ObserverEnrollment, DesignerEnrollment. Empty for all.
            state: active, invited, concluded, completed, inactive. Empty for all.
        """
        cid = client.course(course_id)
        params: dict[str, Any] = {}
        if role:
            params["type[]"] = role
        if state:
            params["state[]"] = state
        rows = client.paged(f"courses/{cid}/enrollments", params)
        keys = ("id", "user_id", "type", "role", "enrollment_state", "course_section_id")
        out = []
        for row in rows:
            if not isinstance(row, dict):
                out.append(row)
                continue
            rec = slim(row, keys)
            rec["user_name"] = (row.get("user") or {}).get("name")
            out.append(rec)
        return client.fmt(out)

    @reg.tool(group="people", tier="write")
    def canvas_enroll_user(
        user_id: str,
        enrollment_type: str = "StudentEnrollment",
        enrollment_state: str = "invited",
        notify: bool = False,
        section_id: str = "",
        course_id: str = "",
    ) -> str:
        """Enrol a user in the course. MUTATES the roster.

        Defaults to state=invited and notify=False: the person gets an
        invitation they must accept, and no email goes out until you ask for
        one. Pass enrollment_state="active" to place them straight onto the
        roster.

        Args:
            user_id: numeric Canvas user id. "sis_user_id:ABC123" enrols by SIS
                id instead, which is usually what a registrar export gives you.
            enrollment_type: StudentEnrollment, TeacherEnrollment, TaEnrollment,
                ObserverEnrollment, or DesignerEnrollment.
            enrollment_state: invited (default) or active.
            notify: send Canvas's notification email (default False).
            section_id: enrol into a specific section instead of the default one.
            course_id: numeric course id; defaults to CANVAS_DEFAULT_COURSE_ID.
        """
        cid = client.course(course_id)
        payload = form(
            **{
                "enrollment[user_id]": user_id,
                "enrollment[type]": enrollment_type,
                "enrollment[enrollment_state]": enrollment_state,
                "enrollment[notify]": notify,
            }
        )
        path = f"sections/{section_id}/enrollments" if section_id else f"courses/{cid}/enrollments"
        data = client.request("POST", path, data=payload).json()
        return client.fmt(slim(data, ("id", "user_id", "type", "enrollment_state", "course_id")))

    @reg.tool(group="people", tier="destructive")
    def canvas_remove_enrollment(
        enrollment_id: str, task: str = "conclude", course_id: str = ""
    ) -> str:
        """Remove a user from the course. MUTATES the roster.

        Defaults to the REVERSIBLE option. The four tasks differ sharply:
          conclude   (default) - ends the enrollment, keeps grades, re-enrollable
          inactivate           - hides them from the course, keeps everything
          deactivate           - alias of inactivate
          delete               - IRREVERSIBLE: removes the enrollment along with
                                 its grades and submissions from the gradebook

        Only pass task="delete" when the instructor has explicitly asked for a
        permanent removal and understands that the grades go with it.

        Args:
            enrollment_id: from canvas_list_enrollments — NOT the user id.
            task: conclude (default), inactivate, deactivate, or delete.
            course_id: numeric course id; defaults to CANVAS_DEFAULT_COURSE_ID.
        """
        if task not in ENROLLMENT_TASKS:
            return f"ERROR: task must be one of {sorted(ENROLLMENT_TASKS)}, got {task!r}."
        cid = client.course(course_id)
        data = client.request(
            "DELETE", f"courses/{cid}/enrollments/{enrollment_id}", params={"task": task}
        ).json()
        out = slim(data, ("id", "user_id", "type", "enrollment_state"))
        out["task_performed"] = task
        out["reversible"] = task != "delete"
        return client.fmt(out)
