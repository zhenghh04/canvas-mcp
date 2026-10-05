# canvas-mcp

**Run your Canvas course from an AI assistant.**

`canvas-mcp` is an [MCP](https://modelcontextprotocol.io) server that gives Claude,
Cursor, VS Code, or any other MCP-capable assistant **47 tools** for Canvas LMS —
reading your roster, drafting assignments, building modules, grading submissions,
posting announcements, and pulling the whole gradebook into one table.

It is written for **instructors**, not Canvas administrators. Everything it does,
it does as *you*, with *your* token, inside the courses you already teach.

```
You:  "Which students haven't submitted Essay 2 yet, and when is it due?"
      "Draft a Week 9 module on Bonhoeffer with a reading page and a discussion,
       but leave it unpublished so I can look first."
      "Give everyone who submitted Lab 3 full marks with the comment 'Nice work'."
```

---

## Table of contents

- [What you get](#what-you-get)
- [Quick start (5 minutes)](#quick-start-5-minutes)
  - [1. Install](#1-install)
  - [2. Get a Canvas API token](#2-get-a-canvas-api-token)
  - [3. Find your course id](#3-find-your-course-id)
  - [4. Tell the server about them](#4-tell-the-server-about-them)
  - [5. Check it works](#5-check-it-works)
  - [6. Connect your AI assistant](#6-connect-your-ai-assistant)
- [Safety model](#safety-model)
- [The 47 tools](#the-47-tools)
- [Configuration reference](#configuration-reference)
- [Command-line interface](#command-line-interface)
- [Recipes](#recipes)
- [Student privacy and FERPA](#student-privacy-and-ferpa)
- [Troubleshooting](#troubleshooting)
- [FAQ](#faq)
- [Contributing](#contributing)
- [License](#license)

---

## What you get

| | |
|---|---|
| **47 tools** | across diagnostics, courses, people, assignments, grading, content, and communication |
| **Three safety tiers** | read-only always on; writes on by default; deletes **off** by default |
| **Tools you disable are never published** | a withheld tool isn't in the model's tool list at all — it can't be called and it costs no context |
| **Bounded output** | big payloads are slimmed to the fields that matter and truncated with an explicit notice, so one `list_submissions` doesn't eat your context window |
| **Readable text, not raw HTML** | syllabi, pages, and discussion threads come back as plain text with paragraph breaks intact |
| **Optional PII redaction** | `CANVAS_REDACT_PII=1` replaces emails and SIS ids with stable `anon-…` hashes |
| **Retries that understand Canvas** | Canvas signals rate limiting with a `403`, not a `429`; this server tells the two apart and only retries the right one |
| **A `doctor` command** | tells you exactly which of base-url / token / permissions / course-id is wrong, instead of a generic 401 |
| **No vendor lock-in** | pure `requests` against the public Canvas REST API; no Canvas app registration, no OAuth dance, no admin approval |

---

## Quick start (5 minutes)

### 1. Install

Pick whichever matches how you already run Python.

**With `uv` (recommended — no virtualenv to manage):**

```bash
uvx --from git+https://github.com/zhenghh04/canvas-mcp canvas-mcp doctor
```

**With `pip`:**

```bash
pip install git+https://github.com/zhenghh04/canvas-mcp
```

**From a clone (if you want to modify it):**

```bash
git clone https://github.com/zhenghh04/canvas-mcp
cd canvas-mcp
pip install -e ".[dev]"
pytest          # 163 tests, all offline — none of them touch a real course
```

Requires Python 3.10 or newer.

### 2. Get a Canvas API token

You do **not** need an administrator, and you do **not** need to register an app.

1. Log in to Canvas in a browser.
2. Click **Account** (left sidebar) → **Settings**.
3. Scroll to **Approved Integrations**.
4. Click **+ New Access Token**.
5. Purpose: `canvas-mcp`. Expiry: leave blank for no expiry, or set a date — if you
   set one, note it, because an expired token looks exactly like a wrong token.
6. Click **Generate Token**.
7. **Copy the token now.** Canvas shows it exactly once. If you lose it, delete the
   entry and make a new one.

The token carries *all* your Canvas permissions — in every course you teach, and
every course you take. Treat it like your password. See
[Student privacy and FERPA](#student-privacy-and-ferpa).

> **Locked down?** Some institutions disable self-service tokens. If you don't see
> **+ New Access Token**, ask your Canvas admin for a token or for the setting to be
> enabled for faculty.

### 3. Find your course id

Open the course in Canvas and look at the URL:

```
https://yourschool.instructure.com/courses/12345
                                           ^^^^^
                                           this is the course id
```

Setting a default course id is optional but makes every conversation shorter — you
can say "the roster" instead of "the roster for course 12345". You can always
override it per call, and `canvas_list_courses` will show you all of them.

### 4. Tell the server about them

Two settings are required: **where your Canvas lives** and **your token**.

You can supply them three ways. Later entries do *not* override earlier ones —
**an already-set environment variable always wins**, so your MCP client's `env`
block beats any `.env` file.

| Priority | Source |
|---|---|
| 1 | Real environment variables (including your MCP client's `env` block) |
| 2 | `$CANVAS_MCP_ENV_FILE` — point this at any file you like |
| 3 | `./.env` in the current directory |
| 4 | `~/.config/canvas-mcp/.env` |

The last one is usually what you want, because it works no matter which directory
your assistant starts in:

```bash
mkdir -p ~/.config/canvas-mcp
cat > ~/.config/canvas-mcp/.env <<'EOF'
CANVAS_BASE_URL=https://yourschool.instructure.com
CANVAS_API_TOKEN=paste-your-token-here
CANVAS_DEFAULT_COURSE_ID=12345
EOF
chmod 600 ~/.config/canvas-mcp/.env
```

That `chmod` matters — the file now contains a credential.

See [`env.example`](env.example) for every available setting, annotated.

### 5. Check it works

```bash
canvas-mcp doctor
```

A healthy run looks like:

```
canvas-mcp 0.2.0

[OK  ] CANVAS_BASE_URL set — https://yourschool.instructure.com
[OK  ] CANVAS_API_TOKEN set
[OK  ] Token authenticates — Ada Lovelace (id 10665)
[OK  ] Teacher enrollments visible — 1 active course(s)
          12345  Introduction to Analytical Engines (CS-101)
[OK  ] CANVAS_DEFAULT_COURSE_ID resolves — Introduction to Analytical Engines (CS-101)

42 tools would be published (writes=on, destructive=off). Run `canvas-mcp tools` for the list.
```

If any line is wrong, `doctor` says what to fix. See
[Troubleshooting](#troubleshooting).

### 6. Connect your AI assistant

<details open>
<summary><strong>Claude Code</strong> (CLI)</summary>

One command:

```bash
claude mcp add canvas -- canvas-mcp serve
```

Or add to `.mcp.json` in your project (or `~/.claude.json` for every project):

```json
{
  "mcpServers": {
    "canvas": {
      "command": "canvas-mcp",
      "args": ["serve"],
      "env": {
        "CANVAS_BASE_URL": "https://yourschool.instructure.com",
        "CANVAS_DEFAULT_COURSE_ID": "12345"
      }
    }
  }
}
```

Note that the **token is deliberately not in this file** — `.mcp.json` is the kind
of file that gets committed to git by accident. Leave `CANVAS_API_TOKEN` in
`~/.config/canvas-mcp/.env`.
</details>

<details>
<summary><strong>Claude Desktop</strong></summary>

Edit `claude_desktop_config.json`:

- **macOS** — `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows** — `%APPDATA%\Claude\claude_desktop_config.json`
- **Linux** — `~/.config/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "canvas": {
      "command": "canvas-mcp",
      "args": ["serve"],
      "env": {
        "CANVAS_BASE_URL": "https://yourschool.instructure.com",
        "CANVAS_DEFAULT_COURSE_ID": "12345"
      }
    }
  }
}
```

Then **fully quit and reopen** Claude Desktop — reloading the window is not enough.

If `canvas-mcp` isn't found, Claude Desktop doesn't inherit your shell `PATH`. Use
an absolute path (`which canvas-mcp` will tell you), or use `uvx`:

```json
{
  "mcpServers": {
    "canvas": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/zhenghh04/canvas-mcp", "canvas-mcp", "serve"]
    }
  }
}
```
</details>

<details>
<summary><strong>Cursor</strong></summary>

**Settings → MCP → Add new MCP server**, or edit `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "canvas": {
      "command": "canvas-mcp",
      "args": ["serve"],
      "env": { "CANVAS_BASE_URL": "https://yourschool.instructure.com" }
    }
  }
}
```
</details>

<details>
<summary><strong>VS Code (GitHub Copilot agent mode)</strong></summary>

Create `.vscode/mcp.json`:

```json
{
  "servers": {
    "canvas": {
      "type": "stdio",
      "command": "canvas-mcp",
      "args": ["serve"],
      "env": { "CANVAS_BASE_URL": "https://yourschool.instructure.com" }
    }
  }
}
```
</details>

<details>
<summary><strong>Anything else (generic stdio, or HTTP)</strong></summary>

Standard stdio MCP server:

```bash
canvas-mcp serve                      # stdio, the default
```

Or serve over HTTP for a remote or multi-client setup:

```bash
canvas-mcp serve --transport http --host 127.0.0.1 --port 8900
```

**Bind to `127.0.0.1` unless you have put real authentication in front of it.**
This server has no auth of its own: anyone who can reach the port is acting as you,
in your courses, with your token.
</details>

Ready-made config snippets live in [`examples/`](examples/).

---

## Safety model

Three tiers. A tool you don't enable is **never registered** — the model cannot see
it, cannot call it, and it costs nothing in context.

| Tier | Default | Controlled by | What's in it |
|---|---|---|---|
| **read** | always on | — | 24 tools. Rosters, assignments, submissions, pages, the gradebook. Never changes anything. |
| **write** | **on** | `CANVAS_ENABLE_WRITES=0` to disable | 18 tools. Create and edit assignments, pages, modules; post grades; send announcements and messages. |
| **destructive** | **off** | `CANVAS_ALLOW_DESTRUCTIVE=1` to enable | 5 tools. Delete assignments, pages, modules; remove enrollments; arbitrary `POST`/`PUT`/`DELETE`. |

The destructive flag cannot bypass the write gate: with `CANVAS_ENABLE_WRITES=0`,
setting `CANVAS_ALLOW_DESTRUCTIVE=1` publishes nothing.

**Three postures worth knowing:**

```bash
# Read-only. Nothing can change. Good for a first week, or for a shared setup.
CANVAS_ENABLE_WRITES=0

# Default. Author and grade freely; nothing can be deleted.
# (this is what you get with no settings at all)

# Full. Only turn this on for a specific cleanup task, then turn it back off.
CANVAS_ALLOW_DESTRUCTIVE=1
```

Beyond the tiers, every mutating tool says so **in its own description** —
`MUTATES the course`, `MUTATES STUDENT RECORDS`, `NOTIFIES PEOPLE`, `IRREVERSIBLE` —
because that text is what the model actually reads when deciding whether to ask you
first. The server's instructions tell the assistant to get explicit go-ahead before
any of them.

Some further guarantees, each with a test behind it:

- **Authoring is unpublished by default.** `canvas_create_assignment`,
  `canvas_create_page`, and `canvas_create_module` all create *drafts*. Students see
  nothing until you publish.
- **Your token never reaches the file-storage host.** Canvas uploads go to an S3 /
  InstFS URL with its own pre-signed credentials; the bearer token is stripped.
- **Student filenames are sanitised.** `canvas_download_submissions` writes
  attachments to disk, and `../../.ssh/authorized_keys` is a perfectly legal Canvas
  filename.
- **Messages don't leak the recipient list.** `canvas_message_students` sends
  individually by default, not as a group conversation.
- **Errors are errors.** A bug in this server raises; only genuine Canvas failures
  are converted into a readable `ERROR: …` string for the model.

---

## The 47 tools

Legend: (blank) read-only · `!` write · `!!` destructive.

Run `canvas-mcp tools` to see exactly what *your* configuration publishes.

### Diagnostics

| | Tool | What it does |
|---|---|---|
| | `canvas_auth_status` | Check connectivity, identity, and which tiers are enabled. Call this first. |
| | `canvas_api_get` | Escape hatch: `GET` any Canvas REST endpoint that has no dedicated tool. |
| `!!` | `canvas_api_write` | Escape hatch: `POST`/`PUT`/`DELETE` any endpoint. Unrestricted. |

### Courses

| | Tool | What it does |
|---|---|---|
| | `canvas_list_courses` | List the courses you can see. |
| | `canvas_get_course` | One course: teachers, student count, syllabus as plain text. |
| | `canvas_list_sections` | Sections with enrollment counts. |
| `!` | `canvas_update_course` | Edit course settings (name, dates, publish state). |
| `!` | `canvas_update_syllabus` | Replace the syllabus body. |

### People

| | Tool | What it does |
|---|---|---|
| | `canvas_list_students` | The roster. |
| | `canvas_list_enrollments` | Enrollments including the `enrollment_id` you need to change one. |
| `!` | `canvas_enroll_user` | Add a user to the course. |
| `!!` | `canvas_remove_enrollment` | Remove someone from the course. |

### Assignments

| | Tool | What it does |
|---|---|---|
| | `canvas_list_assignments` | Assignments with due dates and needs-grading counts. |
| | `canvas_get_assignment` | One assignment, description rendered to plain text. |
| | `canvas_list_assignment_groups` | Gradebook categories and their weights. |
| `!` | `canvas_create_assignment_group` | Create a gradebook category. |
| `!` | `canvas_create_assignment` | Create an assignment (unpublished by default). |
| `!` | `canvas_update_assignment` | Edit an existing assignment. |
| `!!` | `canvas_delete_assignment` | Delete an assignment. |

### Grading

| | Tool | What it does |
|---|---|---|
| | `canvas_list_submissions` | Status, score, timestamps, lateness for an assignment. |
| | `canvas_get_submission` | One student's submission: body text, attachments, comments. |
| | `canvas_get_gradebook` | The whole gradebook as one student × assignment table. |
| | `canvas_download_submissions` | Download every file attachment for an assignment. |
| `!` | `canvas_grade_submission` | Post a grade and/or a comment. |
| `!` | `canvas_bulk_grade` | Post many grades to one assignment at once. |

### Content

| | Tool | What it does |
|---|---|---|
| | `canvas_list_pages` | Wiki page titles and url slugs. |
| | `canvas_get_page` | One page's body as plain text. |
| | `canvas_list_modules` | The course outline, optionally with items. |
| | `canvas_list_quizzes` | Quizzes in a course. |
| | `canvas_list_files` | Files uploaded to a course. |
| | `canvas_download_file` | Download one course file. |
| `!` | `canvas_create_page` | Create a wiki page (unpublished by default). |
| `!` | `canvas_update_page` | Edit a wiki page. |
| `!` | `canvas_create_module` | Create a module (unpublished by default). |
| `!` | `canvas_update_module` | Edit or publish a module. |
| `!` | `canvas_create_module_item` | Add a page / assignment / quiz / link to a module. |
| `!` | `canvas_upload_file` | Upload a local file into Files. |
| `!!` | `canvas_delete_page` | Delete a wiki page. |
| `!!` | `canvas_delete_module` | Delete a module. |

### Communication

| | Tool | What it does |
|---|---|---|
| | `canvas_list_announcements` | Announcements, newest first, with their text. |
| | `canvas_list_discussions` | Discussion topics. |
| | `canvas_get_discussion` | A topic with its full reply thread as plain text. |
| | `canvas_list_calendar_events` | Calendar events, optionally with assignment due dates. |
| `!` | `canvas_post_announcement` | Post an announcement — **students are notified**. |
| `!` | `canvas_create_discussion` | Create a discussion topic. |
| `!` | `canvas_create_calendar_event` | Add an event to the course calendar. |
| `!` | `canvas_message_students` | Send a Canvas inbox message. |

Full parameter-by-parameter reference: [`docs/TOOLS.md`](docs/TOOLS.md).

---

## Configuration reference

Every setting is an environment variable. All are optional except the first two.

### Required

| Variable | Example | Notes |
|---|---|---|
| `CANVAS_BASE_URL` | `https://yourschool.instructure.com` | No trailing slash needed; one is stripped. Do **not** include `/api/v1`. |
| `CANVAS_API_TOKEN` | `7~abc123…` | From Account → Settings → New Access Token. |

### Convenience

| Variable | Default | Notes |
|---|---|---|
| `CANVAS_DEFAULT_COURSE_ID` | — | Used whenever a tool's `course_id` is omitted. |
| `CANVAS_MCP_ENV_FILE` | — | Path to a `.env` file to load first. |
| `CANVAS_DOWNLOAD_DIR` | `./canvas-downloads` | Where downloaded files and submissions land. |

### Safety

| Variable | Default | Notes |
|---|---|---|
| `CANVAS_ENABLE_WRITES` | `1` | `0` for a strictly read-only server. |
| `CANVAS_ALLOW_DESTRUCTIVE` | `0` | `1` publishes the five delete/raw-write tools. |
| `CANVAS_REDACT_PII` | `0` | `1` pseudonymises emails, login ids, SIS ids. |

### Trimming the tool surface

Fewer tools means less context spent and fewer ways to go wrong.

| Variable | Example | Notes |
|---|---|---|
| `CANVAS_TOOL_GROUPS` | `courses,assignments,grading` | Comma-separated. Groups: `diagnostics`, `courses`, `people`, `assignments`, `grading`, `content`, `communication`. |
| `CANVAS_TOOLS` | `canvas_auth_status,canvas_get_gradebook` | Strict allowlist. Only these, and only if their tier is enabled. |
| `CANVAS_DISABLE_TOOLS` | `canvas_message_students` | Denylist, applied after everything else. |

An allowlist can never bypass a tier gate. Listing `canvas_delete_page` in
`CANVAS_TOOLS` does nothing unless `CANVAS_ALLOW_DESTRUCTIVE=1`.

### Limits and performance

| Variable | Default | Notes |
|---|---|---|
| `CANVAS_TIMEOUT` | `30` | Seconds per API request. |
| `CANVAS_UPLOAD_TIMEOUT` | `300` | Seconds for file uploads. |
| `CANVAS_MAX_UPLOAD_MB` | `100` | Refuse larger local files. |
| `CANVAS_PER_PAGE` | `100` | Canvas page size. |
| `CANVAS_MAX_PAGES` | `10` | Pagination cap. Results past it are marked `_truncated`. |
| `CANVAS_MAX_CHARS` | `20000` | Response size cap, with an explicit truncation notice. |
| `CANVAS_MAX_RETRIES` | `3` | Attempts on rate limits and 5xx. |

---

## Command-line interface

```bash
canvas-mcp                  # same as `serve` — stdio MCP server
canvas-mcp serve            # stdio (what MCP clients launch)
canvas-mcp serve --transport http --host 127.0.0.1 --port 8900
canvas-mcp doctor           # diagnose configuration and permissions
canvas-mcp tools            # list what this configuration publishes, and what it withholds
canvas-mcp config           # show resolved settings (token redacted)
```

`canvas-mcp config` prints `"api_token": "set (70 chars)"` — never the token itself.

`serve` deliberately **starts even when misconfigured**, printing a warning to
stderr. An MCP client that sees its server exit immediately reports only "broken
pipe", which tells you nothing; a running server can answer `canvas_auth_status`
with an actual explanation.

---

## Recipes

Things that work well. More in [`docs/RECIPES.md`](docs/RECIPES.md).

**Triage before office hours**
> "Who hasn't submitted Essay 2? For each, tell me whether they've submitted the
> previous two assignments."

**Build a week**
> "Create an unpublished module called 'Week 9 — Bonhoeffer', add a page with the
> reading questions below, and a discussion topic due Friday 11:59pm. Don't publish
> anything."

**Grade a batch**
> "List submissions for Lab 3. For everyone who submitted on time with a file
> attached, give 10/10 and the comment 'Received, nice work.' Show me the list
> before you post anything."

**Catch grading drift**
> "Pull the gradebook. Which assignments still have ungraded submissions, and which
> students are more than one standard deviation below the mean overall?"

**Sync a syllabus**
> "Here's my updated syllabus as markdown. Replace the Canvas syllabus with it,
> preserving the existing course-policies section at the bottom."

**Read the room**
> "Summarise the Week 4 discussion thread. What are the three most common
> misunderstandings, and which students should I follow up with?"

A habit worth forming: **ask for the plan before the action.** "Show me what you'd
post, then wait" costs one extra turn and catches the wrong-assignment-id mistake
before it reaches 30 students.

---

## Student privacy and FERPA

This server reads real student data. A few things are worth being deliberate about.

**Your token is your whole Canvas account.** Not just one course — every course you
teach and every course you take. Keep it in a `chmod 600` file, never in a
git-tracked config, and revoke it from Account → Settings if it leaks.

**Student data flows to your AI provider.** When the assistant reads a roster or a
submission, that text goes to whoever runs the model. Check whether your institution
has a data-processing agreement covering that provider before putting student work
through it. This is the single most important thing on this page.

**`CANVAS_REDACT_PII=1` helps, partially.** It replaces emails, login ids, and SIS
ids with stable `anon-<hash>` values — stable so the model can still correlate rows,
non-reversible so the identifier itself doesn't travel. **Names are deliberately not
redacted**, because an assistant that can't say *"follow up with Dana"* isn't much
use. If names are the concern, redaction is not the answer — don't route the roster
through a model at all.

**Downloads land on your disk.** `canvas_download_submissions` writes student work
to `CANVAS_DOWNLOAD_DIR`. That's a FERPA-relevant directory; treat it like one, and
clean it up.

**Keep the destructive tier off.** Grades and enrollments are student records. The
default posture lets the assistant *write* grades (recoverable, visible in the
gradebook history) but not *remove* enrollments (not recoverable in the same way).

More detail: [`docs/SAFETY.md`](docs/SAFETY.md).

---

## Troubleshooting

Run `canvas-mcp doctor` first — most of these it will name directly.

<details>
<summary><strong>"CANVAS_API_TOKEN is not set"</strong></summary>

The server couldn't find your token. Check, in order:

1. `canvas-mcp config` — which env file did it load? If `env file: (none)`, it found
   no file at any of the four locations.
2. Your MCP client may start the server in a different working directory, so a
   `./.env` won't be found. Use `~/.config/canvas-mcp/.env`.
3. Make sure the file has no quotes and no spaces around `=`:
   `CANVAS_API_TOKEN=7~abc` — not `CANVAS_API_TOKEN = "7~abc"`.
</details>

<details>
<summary><strong>401 Unauthorized</strong></summary>

The token is wrong, revoked, or expired. Canvas tokens can have an expiry date set
at creation, and an expired token returns exactly the same 401 as a typo'd one.

Generate a fresh one at Account → Settings → + New Access Token.

Also confirm `CANVAS_BASE_URL` points at the tenant the token came from — a valid
token for `school-a.instructure.com` is a 401 at `school-b.instructure.com`.
</details>

<details>
<summary><strong>403 Forbidden</strong></summary>

Two different things wear this status code in Canvas.

- **Rate limiting.** The body says "Rate Limit Exceeded". The server detects this
  and retries with backoff; if you still see it, you're hammering the API — raise
  `CANVAS_TIMEOUT` and make fewer, larger requests.
- **Real permission denied.** You're not a teacher in that course, or your role
  lacks the specific permission (some institutions restrict `message_students` or
  enrollment changes even for teachers). Nothing this server can do; ask your Canvas
  admin.
</details>

<details>
<summary><strong>404 Not Found</strong></summary>

Usually a wrong id, but Canvas also returns 404 instead of 403 for things you're not
allowed to see, which is a deliberate anti-enumeration measure. So: check the id is
right *and* that you're enrolled in that course as a teacher.
</details>

<details>
<summary><strong>422 Unprocessable Entity</strong></summary>

Canvas rejected the content. Common causes: a due date outside the course term, a
page title that collides with an existing one, `points_possible` on an assignment
whose grading type doesn't take points. The error message passes Canvas's own
explanation through.
</details>

<details>
<summary><strong>The assistant can't see any Canvas tools</strong></summary>

1. Restart the client fully (Claude Desktop needs a real quit, not a window reload).
2. Run the exact command from your config by hand in a terminal. If
   `canvas-mcp: command not found`, your client doesn't share your shell `PATH` —
   use an absolute path from `which canvas-mcp`, or switch to the `uvx` form.
3. Check the client's MCP logs. Claude Desktop: `~/Library/Logs/Claude/` on macOS.
</details>

<details>
<summary><strong>The assistant can see some tools but not the one I want</strong></summary>

Run `canvas-mcp tools`. The **WITHHELD** section at the bottom lists every suppressed
tool and the exact reason — a tier gate, a group filter, an allowlist, or a
denylist.
</details>

<details>
<summary><strong>Results are cut off / say `_truncated`</strong></summary>

Two separate caps. `_truncated` in a list means pagination stopped at
`CANVAS_MAX_PAGES`. A trailing truncation notice means the text hit
`CANVAS_MAX_CHARS`. Raise whichever one you hit — but they exist to protect your
context window, so prefer narrowing the request (one assignment, one section) over
raising the cap.
</details>

<details>
<summary><strong>Uploads fail</strong></summary>

Check the file is under `CANVAS_MAX_UPLOAD_MB` (default 100) and that
`CANVAS_UPLOAD_TIMEOUT` is generous enough for your connection. Canvas uploads are a
three-step handshake through a separate storage host; a timeout in the middle leaves
nothing behind, so it's safe to retry.
</details>

---

## FAQ

**Do I need to be a Canvas administrator?**
No. A plain teacher account and a self-service access token. If your institution has
disabled self-service tokens, you'll need an admin to issue one — that's the only
admin involvement.

**Will this work with my school's Canvas?**
If it's Canvas and you can reach it over HTTPS, yes. It uses only the public REST
API v1. Self-hosted Canvas works too; just point `CANVAS_BASE_URL` at it.

**Can it see other instructors' courses?**
Only what your own Canvas account can see. It has exactly your permissions — no more.

**Can students use it?**
It'll run, but most tools need teacher permissions. It isn't designed for that.

**Does it store anything?**
No database, no cache, no telemetry. The only things written to disk are files you
explicitly download, into `CANVAS_DOWNLOAD_DIR`.

**What if the AI grades something wrong?**
Canvas keeps grade history — you can see and revert every change in the gradebook's
grade-change log. That's precisely why grading is in the `write` tier and not gated
behind `destructive`: it's recoverable. Still: review before posting.

**Can I use it with a local model (Ollama, LM Studio)?**
Yes, if your client speaks MCP. Note that the 47 tool descriptions are a meaningful
chunk of context for a small model — use `CANVAS_TOOL_GROUPS` to publish only what
you need.

**Why doesn't it support Canvas's New Quizzes?**
New Quizzes lives behind a separate API with different auth. `canvas_list_quizzes`
sees Classic Quizzes. PRs welcome.

**Does it work with Canvas Free for Teachers?**
Yes — `https://canvas.instructure.com` as your base URL.

---

## Contributing

Issues and PRs welcome, particularly from instructors who hit something this doesn't
cover. See [`CONTRIBUTING.md`](CONTRIBUTING.md).

```bash
git clone https://github.com/zhenghh04/canvas-mcp
cd canvas-mcp
pip install -e ".[dev]"
pytest        # 163 tests, fully offline
ruff check .
```

The test suite never contacts a real Canvas tenant — the fixture transport raises on
any unexpected call, so a test that escapes fails loudly instead of mutating
somebody's live course.

---

## License

MIT. See [`LICENSE`](LICENSE).

Not affiliated with or endorsed by Instructure. "Canvas" is their trademark.
