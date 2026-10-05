# Tool reference

All 47 tools, with their real parameters.

`*` marks a required parameter. Everything else has a default, shown after `=`.
Tier: **read** (always available) · **write** (`CANVAS_ENABLE_WRITES`, on by
default) · **destructive** (`CANVAS_ALLOW_DESTRUCTIVE`, **off** by default).

`course_id` defaults to `CANVAS_DEFAULT_COURSE_ID` everywhere it appears. If
neither is set, the tool returns an error telling you to supply one.

`max_chars` defaults to `0`, meaning *use the server-wide `CANVAS_MAX_CHARS`*
(20000). Pass a positive number to override for one call; truncation is always
announced in the output, never silent.

Dates are ISO 8601, e.g. `2026-10-31T23:59:00Z` or `2026-10-31`.

To see what *your* configuration actually publishes: `canvas-mcp tools`.

---

## Contents

- [Diagnostics](#diagnostics)
- [Courses](#courses)
- [People](#people)
- [Assignments](#assignments)
- [Grading](#grading)
- [Content](#content)
- [Communication](#communication)
- [Conventions](#conventions)

---

## Diagnostics

### `canvas_auth_status()` — read

Connectivity, identity, and which tiers are enabled. Returns your Canvas user id
and name, the base URL in use, and the write/destructive/redaction flags.

Worth calling at the start of a session: it confirms *which* Canvas and *which*
account the assistant is about to act as, and it costs one cheap request.

### `canvas_api_get(path*, params_json='', max_chars=0)` — read

Escape hatch for any `GET` endpoint without a dedicated tool.

- `path` — relative to `/api/v1`, with or without a leading slash.
  `courses/12345/rubrics` and `/courses/12345/rubrics` both work.
- `params_json` — a JSON object of query parameters, e.g. `{"per_page": 50}`.

Paginated like everything else, capped by `CANVAS_MAX_PAGES`.

### `canvas_api_write(method*, path*, form_json='', params_json='', max_chars=0)` — **destructive**

Escape hatch for `POST` / `PUT` / `DELETE`. No guardrails whatsoever — this can do
anything your token can do, including things no other tool here exposes.

- `method` — `POST`, `PUT`, or `DELETE`.
- `form_json` — JSON object sent as form fields. Canvas's bracket syntax works:
  `{"assignment[name]": "Essay 3"}`.

Gated behind `CANVAS_ALLOW_DESTRUCTIVE=1` because its blast radius is "the entire
Canvas API".

---

## Courses

### `canvas_list_courses(enrollment_state='active', enrollment_type='')` — read

Courses visible to you, with ids.

- `enrollment_state` — `active`, `invited_or_pending`, `completed`.
  Use `completed` to reach last term's courses.
- `enrollment_type` — `teacher`, `ta`, `student`, `observer`, `designer`.
  `teacher` is the usual filter when you teach and also take courses.

### `canvas_get_course(course_id='', max_chars=0)` — read

One course: name, code, term dates, workflow state, teacher list, student count,
and the **syllabus rendered to plain text** with paragraph breaks preserved.

### `canvas_list_sections(course_id='')` — read

Sections with their enrollment counts. You need `section_id` from here to enrol
someone into a specific section.

### `canvas_update_course(name='', course_code='', start_at='', end_at='', published=None, default_view='', course_id='')` — write

Edit course settings. Only the fields you pass are changed; omitted fields are left
alone (this is why they default to `''`/`None` rather than being blanked).

- `published` — `true` publishes the course to students. **This is the switch that
  makes a course visible to the whole roster.** `false` unpublishes, which Canvas
  only allows while there are no graded submissions.
- `default_view` — the course landing page: `feed`, `wiki`, `modules`,
  `assignments`, `syllabus`.

### `canvas_update_syllabus(body*, course_id='')` — write

Replace the syllabus body. `body` is HTML — Canvas renders it as a page. Plain text
works but won't have paragraph breaks; use `<p>…</p>` or `<br>`.

This **replaces**, it does not append. Read the current syllabus with
`canvas_get_course` first if you mean to edit rather than overwrite.

---

## People

### `canvas_list_students(course_id='', include_email=False, search_term='')` — read

The roster: Canvas user ids, names, sortable names.

- `include_email` — off by default. Turn it on only when you actually need to
  contact someone outside Canvas; see [SAFETY.md](SAFETY.md).
- `search_term` — partial name match, at least 2 characters.

### `canvas_list_enrollments(course_id='', role='', state='active')` — read

Enrollments rather than users — the difference matters because `enrollment_id` is
what `canvas_remove_enrollment` takes, and a user can hold several.

- `role` — `StudentEnrollment`, `TeacherEnrollment`, `TaEnrollment`,
  `ObserverEnrollment`, `DesignerEnrollment`.
- `state` — `active`, `invited`, `completed`, `inactive`.

### `canvas_enroll_user(user_id*, enrollment_type='StudentEnrollment', enrollment_state='invited', notify=False, section_id='', course_id='')` — write

Add someone to the course.

- `user_id` — a numeric Canvas user id, or `sis_user_id:S12345` to enrol by SIS id.
- `enrollment_state` — `invited` (default; they get an invitation they must accept)
  or `active` (enrolled immediately, no acceptance step).
- `notify` — **off by default**, so a batch of enrollments doesn't fire a batch of
  emails. Set `true` deliberately.

### `canvas_remove_enrollment(enrollment_id*, task='conclude', course_id='')` — **destructive**

Remove someone from the course. The `task` argument decides how reversible that is:

| `task` | Effect | Reversible? |
|---|---|---|
| `conclude` (default) | Marks the enrollment completed. Read-only access, grades retained. | Yes |
| `inactivate` | Hides them from the gradebook, retains everything. | Yes |
| `deactivate` | Alias Canvas accepts for `inactivate`. | Yes |
| `delete` | **Removes the enrollment and its submissions.** | **No** |

The default is the safe one on purpose. `delete` destroys student work.

---

## Assignments

### `canvas_list_assignments(course_id='', bucket='', search_term='')` — read

Assignments with due dates, points, published state, and needs-grading counts.

- `bucket` — `past`, `overdue`, `undated`, `ungraded`, `unsubmitted`, `upcoming`,
  `future`. `ungraded` is the one you want for "what do I owe students".

### `canvas_get_assignment(assignment_id*, course_id='', max_chars=0)` — read

One assignment with its description rendered to plain text, plus submission types,
rubric presence, and the lock/unlock window.

### `canvas_list_assignment_groups(course_id='')` — read

Gradebook categories with their `group_weight` percentages. Useful for checking the
weights sum to 100.

### `canvas_create_assignment_group(name*, group_weight=None, position=None, course_id='')` — write

Create a gradebook category.

- `group_weight` — a percentage. Only has an effect if the course is set to weight
  final grades by group; otherwise it's stored and ignored.

### `canvas_create_assignment(name*, description='', points_possible=None, due_at='', unlock_at='', lock_at='', submission_types='online_text_entry', grading_type='', published=False, assignment_group_id='', omit_from_final_grade=None, course_id='')` — write

Create an assignment. **`published=False` by default — students see nothing until
you publish it.**

- `submission_types` — comma-separated:
  `online_text_entry`, `online_upload`, `online_url`, `online_quiz`,
  `discussion_topic`, `media_recording`, `on_paper`, `none`, `external_tool`.
- `grading_type` — `points` (default), `percent`, `letter_grade`, `gpa_scale`,
  `pass_fail`, `not_graded`.
- `description` — HTML.
- `unlock_at` / `lock_at` — availability window, distinct from the due date.
  Students can still submit late between `due_at` and `lock_at`.

### `canvas_update_assignment(assignment_id*, name='', description='', points_possible=None, due_at='', unlock_at='', lock_at='', published=None, assignment_group_id='', course_id='')` — write

Edit an existing assignment. Only the fields you pass change. Pass `published=true`
to release it to students.

### `canvas_delete_assignment(assignment_id*, course_id='')` — **destructive**

Delete an assignment. Canvas soft-deletes, so it can be restored for a while from
`/courses/<id>/undelete` in a browser — but submissions and grades go with it, and
the undelete page is easy to miss. Treat it as permanent.

---

## Grading

### `canvas_list_submissions(assignment_id*, course_id='', include_ungraded=True, only_submitted=False)` — read

Per-student: workflow state, score, `submitted_at`, `graded_at`, late/missing flags,
attempt count.

- `only_submitted=true` — skip students who haven't turned anything in.
- `include_ungraded=false` — only rows that already have a score.

This is the workhorse for "who's missing" and "what's left to grade".

### `canvas_get_submission(assignment_id*, user_id*, course_id='', max_chars=0)` — read

One submission in full: body text (HTML flattened), attachment names and ids,
submission url, existing grade, and the comment thread.

`user_id` is the numeric Canvas id from `canvas_list_students`.

### `canvas_get_gradebook(course_id='', assignment_ids='', include_names=True, max_chars=0)` — read

The whole gradebook pivoted into one student × assignment table, rather than one
request per assignment. This is the tool to use for "who's falling behind" and
"what's still ungraded across the course".

- `assignment_ids` — comma-separated, to narrow a large course.
- `include_names=false` — ids only, if you're working with redaction on.

Large courses will hit `max_chars`; narrow with `assignment_ids` rather than
raising the cap.

### `canvas_download_submissions(assignment_id*, dest_dir='', course_id='', max_files=100)` — read

Download every file attachment for an assignment to local disk.

- `dest_dir` — defaults to `CANVAS_DOWNLOAD_DIR` (`./canvas-downloads`).
- `max_files` — a deliberate stop so one call can't pull 400 files.

Files are named `<user_id>_<original-name>`, with the original name **sanitised** —
student-supplied filenames are untrusted input, and `../../.ssh/authorized_keys` is
a legal Canvas filename.

Everything this writes is student work. See [SAFETY.md](SAFETY.md).

### `canvas_grade_submission(assignment_id*, user_id*, grade='', comment='', excused=None, course_id='')` — write

Post a grade and/or a comment. **Mutates a student record.**

- `grade` — a string, matched to the assignment's grading type:
  `"18"`, `"85%"`, `"B+"`, `"pass"`, `"complete"`.
- `comment` — posted as a submission comment; the student is notified per their
  notification settings.
- `excused=true` — marks excused, which removes the assignment from that student's
  final grade entirely. Mutually exclusive with `grade`.

Grade changes are recorded in Canvas's grade-change log and are revertible there.

### `canvas_bulk_grade(assignment_id*, grades_json*, course_id='')` — write

Post many grades at once. **Mutates student records.**

`grades_json` is a JSON object keyed by user id:

```json
{
  "4211": {"posted_grade": "10", "text_comment": "Nice work"},
  "4212": {"posted_grade": "8"},
  "4213": {"excuse": true}
}
```

Canvas processes this asynchronously and returns a Progress object; the tool
returns its url so the assistant can report where it stands.

One request instead of N — but also one blast radius instead of N. Have the
assistant show you the mapping before it posts.

---

## Content

### `canvas_list_pages(course_id='', search_term='')` — read

Page titles and `url` slugs. Not bodies — fetch those individually.

The `url` slug (e.g. `week-9-reading`) is the identifier every other page tool
takes, not the numeric id.

### `canvas_get_page(page_url*, course_id='', max_chars=0)` — read

One page's body as plain text, with paragraph breaks preserved.

### `canvas_create_page(title*, body='', published=False, front_page=False, course_id='')` — write

Create a wiki page. **Unpublished by default.**

- `body` — HTML.
- `front_page=true` — makes it the course home page. Only one page can hold this.

### `canvas_update_page(page_url*, title='', body='', published=None, course_id='')` — write

Edit a page. `body` **replaces** the existing body; read it first if you're editing.

Changing `title` also changes the url slug, which breaks module items and links
that point at the old one. Canvas keeps a redirect, but not reliably.

### `canvas_delete_page(page_url*, course_id='')` — **destructive**

Delete a page. Soft-deleted; restorable from `/courses/<id>/undelete` for a while.

### `canvas_list_modules(course_id='', with_items=True, max_chars=0)` — read

The course outline. With `with_items=true` (the default) it returns each module's
items — the best single view of how a course is structured.

### `canvas_create_module(name*, position=None, published=False, course_id='')` — write

Create a module. **Unpublished by default.**

### `canvas_update_module(module_id*, name='', position=None, published=None, course_id='')` — write

Rename, reorder, or publish a module.

**Publishing a module publishes its items.** This is the usual "release Week 9"
action — and the usual way an unfinished draft goes live. Check the contents first.

### `canvas_create_module_item(module_id*, title*, item_type*, content_id='', page_url='', external_url='', position=None, indent=None, course_id='')` — write

Add an item to a module. Which of the three content arguments you need depends on
`item_type`:

| `item_type` | Identify it with |
|---|---|
| `Page` | `page_url` (the slug) |
| `Assignment`, `Quiz`, `Discussion`, `File` | `content_id` |
| `ExternalUrl`, `ExternalTool` | `external_url` |
| `SubHeader` | neither — just `title` |

`indent` nests the item visually (0–5).

### `canvas_delete_module(module_id*, course_id='')` — **destructive**

Delete a module. The items themselves survive — pages and assignments still exist;
they're just no longer in a module.

### `canvas_list_quizzes(course_id='')` — read

Classic Quizzes. **New Quizzes is a separate API and does not appear here.**

### `canvas_list_files(course_id='', search_term='')` — read

Files in the course Files area, with ids, sizes, and content types.

### `canvas_download_file(file_id*, dest_dir='', name='')` — read

Download one course file. `name` overrides the local filename.

### `canvas_upload_file(local_path*, parent_folder_path='course files', name='', on_duplicate='rename', course_id='')` — write

Upload a local file into the course's Files area.

- `parent_folder_path` — e.g. `course files/readings`. Created if absent.
- `on_duplicate` — `rename` (default, safe) or `overwrite`.

Refuses files above `CANVAS_MAX_UPLOAD_MB` (default 100). Canvas uploads are a
three-step handshake through a separate storage host; **your Canvas token is never
sent to that host** — the pre-signed upload parameters are the only credential it
sees.

---

## Communication

### `canvas_list_announcements(course_id='', max_chars=0)` — read

Announcements newest first, with their text flattened.

### `canvas_post_announcement(title*, message*, delayed_post_at='', course_id='')` — write

Post an announcement. **Students are notified** according to their notification
settings — for most of them, immediately, by email.

- `delayed_post_at` — schedule it. Nothing is sent until then, and the tool's
  response says so (`notified_roster: false`).

There is no unsend. Deleting an announcement does not recall the emails already
delivered. Have the assistant show you the text first.

### `canvas_list_discussions(course_id='')` — read

Discussion topics with reply counts and unread counts.

### `canvas_get_discussion(topic_id*, course_id='', max_chars=0)` — read

A topic with its full nested reply thread, flattened to readable text with authors.
Good for "summarise where this discussion got to".

### `canvas_create_discussion(title*, message*, published=False, require_initial_post=False, threaded=True, pinned=False, course_id='')` — write

Create a discussion topic. **Unpublished by default.**

- `require_initial_post=true` — students must post before they can read others'
  replies.
- `threaded=true` (default) — allows nested replies.

### `canvas_list_calendar_events(course_id='', start_date='', end_date='', include_assignments=True)` — read

Calendar events in a window. With `include_assignments=true` (the default),
assignment due dates appear alongside events — which is usually what you want when
asking "what's happening in week 9".

### `canvas_create_calendar_event(title*, start_at*, end_at='', description='', location_name='', course_id='')` — write

Add an event to the course calendar. Omit `end_at` for a point-in-time event.

### `canvas_message_students(recipient_ids*, subject*, body*, group_conversation=False, course_id='')` — write

Send a Canvas inbox message. **Notifies people.**

- `recipient_ids` — comma-separated Canvas user ids.
- `group_conversation` — **`False` by default, deliberately.** That sends each
  student a separate message. Setting it `true` creates one shared thread in which
  **every recipient can see who else received it** and can reply to all — which for
  a message about grades or missing work is a privacy problem.

---

## Conventions

**Omitted means unchanged.** Every update tool distinguishes "unset" (`''` /
`None`, field untouched) from a real value. This is why `published` is `None` and
not `False` on the update tools: `False` is a meaningful instruction to unpublish,
so it can't double as "not specified". `points_possible=0` likewise sets zero
points rather than being dropped.

**Pagination.** List tools follow Canvas's `Link` headers up to
`CANVAS_MAX_PAGES` × `CANVAS_PER_PAGE` rows. If that cap is hit, the result carries
`"_truncated": true` with a note. A truncated list is never silently presented as
complete.

**Output size.** Payloads are slimmed to the fields that matter and then bounded by
`max_chars`. Truncation appends an explicit notice naming the limit, so the model
knows it's looking at a fragment.

**HTML.** Canvas stores descriptions, pages, and syllabi as HTML. Read tools flatten
it to text, converting `<br>` and block-element closes to newlines first — without
that, a syllabus collapses into one unreadable line. Write tools take HTML.

**Errors.** Canvas failures come back as `ERROR: <explanation>` with a suggested
remedy, so the model can adapt rather than retrying blindly. Bugs in this server
raise normally instead of being disguised as Canvas errors.

**Rate limits.** Canvas signals throttling with `403` and the body text "Rate Limit
Exceeded", not `429`. The client distinguishes that from a genuine permission `403`
and retries only the former, honouring `Retry-After` when present, up to
`CANVAS_MAX_RETRIES`.

**SIS ids.** `canvas_enroll_user` accepts `sis_user_id:ABC123` in place of a numeric
Canvas id. Canvas supports that prefix on many other user-id paths too, but only
this tool documents and relies on it; elsewhere, prefer the numeric id from
`canvas_list_students`.
