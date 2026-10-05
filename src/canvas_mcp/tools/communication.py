"""Announcements, discussions, calendar events, and messages to students.

Every write in this module is *outward-facing*: Canvas notifies people. An
announcement emails the roster; a conversation message lands in a student's
inbox. Deleting the object afterwards does not unsend the notification, so
these are not meaningfully reversible — get explicit approval on the exact
text before posting.
"""

from __future__ import annotations

import json
from typing import Any

from ..formatting import form, slim, slim_all, strip_html
from ..registry import Registrar

DISCUSSION_KEYS = (
    "id",
    "title",
    "posted_at",
    "delayed_post_at",
    "discussion_subentry_count",
    "published",
    "locked",
    "html_url",
)


def register(reg: Registrar) -> None:
    client = reg.client

    # -- announcements -----------------------------------------------------

    @reg.tool(group="communication")
    def canvas_list_announcements(course_id: str = "", max_chars: int = 0) -> str:
        """List a course's announcements, most recent first, with their text.

        Args:
            course_id: numeric course id; defaults to CANVAS_DEFAULT_COURSE_ID.
            max_chars: bound on the returned payload (0 = the server default).
        """
        cid = client.course(course_id)
        items = client.paged("announcements", {"context_codes[]": f"course_{cid}"})
        out = []
        for item in items:
            if not isinstance(item, dict):
                out.append(item)
                continue
            row = slim(item, ("id", "title", "posted_at", "delayed_post_at", "url"))
            row["message"] = strip_html(item.get("message", ""))[:2000]
            out.append(row)
        return client.fmt(out, max_chars or None)

    @reg.tool(group="communication", tier="write")
    def canvas_post_announcement(
        title: str, message: str, delayed_post_at: str = "", course_id: str = ""
    ) -> str:
        """Post an announcement. MUTATES the course — students are notified.

        Show the instructor the exact title and body and get explicit approval
        before calling. Canvas emails the whole roster on post, so deleting the
        announcement afterwards does not unsend it.

        Pass delayed_post_at to schedule instead: the announcement is created
        but stays unpublished until that moment, which leaves a window to
        review or cancel it.

        Args:
            title: announcement subject line.
            message: body (HTML allowed).
            delayed_post_at: ISO 8601 UTC; publish then instead of immediately.
            course_id: numeric course id; defaults to CANVAS_DEFAULT_COURSE_ID.
        """
        cid = client.course(course_id)
        payload = form(
            title=title,
            message=message,
            is_announcement=True,
            delayed_post_at=delayed_post_at,
        )
        data = client.request("POST", f"courses/{cid}/discussion_topics", data=payload).json()
        out = slim(data, ("id", "title", "posted_at", "delayed_post_at", "html_url"))
        out["notified_roster"] = not delayed_post_at
        return client.fmt(out)

    # -- discussions -------------------------------------------------------

    @reg.tool(group="communication")
    def canvas_list_discussions(course_id: str = "") -> str:
        """List discussion topics in a course.

        Args:
            course_id: numeric course id; defaults to CANVAS_DEFAULT_COURSE_ID.
        """
        cid = client.course(course_id)
        rows = client.paged(f"courses/{cid}/discussion_topics")
        return client.fmt(slim_all(rows, DISCUSSION_KEYS))

    @reg.tool(group="communication")
    def canvas_get_discussion(topic_id: str, course_id: str = "", max_chars: int = 0) -> str:
        """Get a discussion topic with its full reply thread as plain text.

        FERPA: student posts are student work, attributed by name. Use this to
        summarise a week's discussion, not to bulk-export it.

        Args:
            topic_id: numeric discussion topic id.
            course_id: numeric course id; defaults to CANVAS_DEFAULT_COURSE_ID.
            max_chars: bound on the returned payload (0 = the server default).
        """
        cid = client.course(course_id)
        topic = client.get_json(f"courses/{cid}/discussion_topics/{topic_id}")
        out = slim(topic, DISCUSSION_KEYS)
        out["message"] = strip_html(topic.get("message", ""))

        def flatten(entries: list, depth: int = 0) -> list[dict[str, Any]]:
            rows = []
            for entry in entries or []:
                if not isinstance(entry, dict):
                    continue
                rows.append(
                    {
                        "depth": depth,
                        "id": entry.get("id"),
                        "user_id": entry.get("user_id"),
                        "user_name": entry.get("user_name"),
                        "created_at": entry.get("created_at"),
                        "message": strip_html(entry.get("message", "")),
                    }
                )
                rows.extend(
                    flatten(entry.get("recent_replies") or entry.get("replies") or [], depth + 1)
                )
            return rows

        out["entries"] = flatten(
            client.paged(f"courses/{cid}/discussion_topics/{topic_id}/entries")
        )
        out["entry_count"] = len(out["entries"])
        return client.fmt(out, max_chars or None)

    @reg.tool(group="communication", tier="write")
    def canvas_create_discussion(
        title: str,
        message: str,
        published: bool = False,
        require_initial_post: bool = False,
        threaded: bool = True,
        pinned: bool = False,
        course_id: str = "",
    ) -> str:
        """Create a discussion topic. MUTATES the course.

        Defaults to UNPUBLISHED so you can review it before students see it.
        Publishing a discussion notifies students who have announcements and
        discussions turned on.

        Args:
            title: topic title.
            message: prompt body (HTML allowed).
            published: visible to students immediately (default False).
            require_initial_post: students must post before seeing replies.
            threaded: allow nested replies (default True).
            pinned: pin to the top of the discussions list.
            course_id: numeric course id; defaults to CANVAS_DEFAULT_COURSE_ID.
        """
        cid = client.course(course_id)
        payload = form(
            title=title,
            message=message,
            published=published,
            require_initial_post=require_initial_post or None,
            discussion_type="threaded" if threaded else "side_comment",
            pinned=pinned or None,
        )
        data = client.request("POST", f"courses/{cid}/discussion_topics", data=payload).json()
        return client.fmt(slim(data, DISCUSSION_KEYS))

    # -- calendar ----------------------------------------------------------

    @reg.tool(group="communication")
    def canvas_list_calendar_events(
        course_id: str = "",
        start_date: str = "",
        end_date: str = "",
        include_assignments: bool = True,
    ) -> str:
        """List calendar events (and optionally assignment due dates) for a course.

        Args:
            course_id: numeric course id; defaults to CANVAS_DEFAULT_COURSE_ID.
            start_date: YYYY-MM-DD lower bound; empty for Canvas's default window.
            end_date: YYYY-MM-DD upper bound.
            include_assignments: also return assignment due dates as events.
        """
        cid = client.course(course_id)
        base: dict[str, Any] = {"context_codes[]": f"course_{cid}"}
        if start_date:
            base["start_date"] = start_date
        if end_date:
            base["end_date"] = end_date
        keys = ("id", "title", "start_at", "end_at", "location_name", "type", "html_url")
        rows = slim_all(client.paged("calendar_events", dict(base)), keys)
        if include_assignments:
            rows += slim_all(client.paged("calendar_events", {**base, "type": "assignment"}), keys)
        return client.fmt(rows)

    @reg.tool(group="communication", tier="write")
    def canvas_create_calendar_event(
        title: str,
        start_at: str,
        end_at: str = "",
        description: str = "",
        location_name: str = "",
        course_id: str = "",
    ) -> str:
        """Create a calendar event on the course calendar. MUTATES the course.

        Appears on every enrolled student's calendar. Good for class meetings,
        office hours, and guest lectures — not for assignment due dates, which
        belong on the assignment itself so the gradebook knows about them.

        Args:
            title: event title.
            start_at: ISO 8601 UTC start, e.g. 2026-09-10T18:00:00Z.
            end_at: ISO 8601 UTC end; omit for a point-in-time event.
            description: event body (HTML allowed).
            location_name: room or place.
            course_id: numeric course id; defaults to CANVAS_DEFAULT_COURSE_ID.
        """
        cid = client.course(course_id)
        payload = form(
            **{
                "calendar_event[context_code]": f"course_{cid}",
                "calendar_event[title]": title,
                "calendar_event[start_at]": start_at,
                "calendar_event[end_at]": end_at,
                "calendar_event[description]": description,
                "calendar_event[location_name]": location_name,
            }
        )
        data = client.request("POST", "calendar_events", data=payload).json()
        keys = ("id", "title", "start_at", "end_at", "location_name", "html_url")
        return client.fmt(slim(data, keys))

    # -- direct messages ---------------------------------------------------

    @reg.tool(group="communication", tier="write")
    def canvas_message_students(
        recipient_ids: str,
        subject: str,
        body: str,
        group_conversation: bool = False,
        course_id: str = "",
    ) -> str:
        """Send a Canvas inbox message to one or more students. NOTIFIES PEOPLE.

        This reaches students directly and cannot be recalled. Show the
        instructor the recipient list and the exact text, and get explicit
        approval, every time.

        Defaults to individual conversations: each recipient gets their own
        thread and cannot see who else was written to. Only pass
        group_conversation=True when the students are meant to see each other —
        a group project thread, say — because otherwise it discloses the
        recipient list to everyone on it.

        Args:
            recipient_ids: comma-separated Canvas user ids, or a JSON array.
            subject: message subject.
            body: message text.
            group_conversation: put all recipients in one shared thread.
            course_id: numeric course id; scopes the message to the course so
                students can reply. Defaults to CANVAS_DEFAULT_COURSE_ID.
        """
        raw = recipient_ids.strip()
        if raw.startswith("["):
            try:
                ids = [str(r).strip() for r in json.loads(raw)]
            except json.JSONDecodeError as exc:
                return f"ERROR: recipient_ids looks like JSON but is not valid: {exc}"
        else:
            ids = [r.strip() for r in raw.split(",") if r.strip()]
        if not ids:
            return "ERROR: recipient_ids is empty — nobody to message."
        cid = client.course(course_id)
        payload: dict[str, Any] = {
            "recipients[]": ids,
            "subject": subject,
            "body": body,
            "context_code": f"course_{cid}",
            "group_conversation": "true" if group_conversation else "false",
            "mode": "async",
        }
        if not group_conversation:
            # Without this Canvas still creates one shared thread when it can.
            payload["bulk_message"] = "true"
        data = client.request("POST", "conversations", data=payload).json()
        return client.fmt(
            {
                "recipients": len(ids),
                "group_conversation": group_conversation,
                "subject": subject,
                "response": data if isinstance(data, dict) else data[:5],
            }
        )
