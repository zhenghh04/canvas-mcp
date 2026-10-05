# Setup guide

A longer walkthrough than the README quick start, with the parts that commonly go
wrong called out.

- [Install](#install)
- [Canvas API token](#canvas-api-token)
- [Base URL](#base-url)
- [Course id](#course-id)
- [Where configuration comes from](#where-configuration-comes-from)
- [Verify with `doctor`](#verify-with-doctor)
- [Client configuration](#client-configuration)
- [HTTP transport](#http-transport)
- [Upgrading](#upgrading)
- [Uninstalling and revoking](#uninstalling-and-revoking)

---

## Install

Requires **Python 3.10+**. Check with `python3 --version`.

### Option A — `uv` (no virtualenv to manage)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh     # if you don't have uv
uvx --from git+https://github.com/zhenghh04/canvas-mcp canvas-mcp doctor
```

`uvx` downloads into a cache and runs. Nothing is installed into your Python.
This is the lowest-friction option, and the one to use if `pip install` into your
system Python makes you uneasy.

### Option B — `pip`

```bash
pip install git+https://github.com/zhenghh04/canvas-mcp
```

If `pip` refuses with *"externally-managed-environment"* (Debian/Ubuntu, Homebrew
Python), use a virtualenv:

```bash
python3 -m venv ~/.venvs/canvas-mcp
~/.venvs/canvas-mcp/bin/pip install git+https://github.com/zhenghh04/canvas-mcp
~/.venvs/canvas-mcp/bin/canvas-mcp doctor
```

Then point your MCP client at the absolute path
`~/.venvs/canvas-mcp/bin/canvas-mcp`.

### Option C — clone and edit

```bash
git clone https://github.com/zhenghh04/canvas-mcp
cd canvas-mcp
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

### Confirm

```bash
canvas-mcp --version
which canvas-mcp          # note this path — you may need it for your MCP client
```

---

## Canvas API token

### Creating one

1. Log in to Canvas.
2. **Account** → **Settings**.
3. Scroll down to **Approved Integrations**.
4. **+ New Access Token**.
5. *Purpose:* `canvas-mcp`. *Expires:* blank for never, or a date.
6. **Generate Token**.
7. Copy it immediately — Canvas displays it exactly once.

The token looks like `7~` followed by a long random string. Some Canvas versions
omit the prefix.

### If you don't see "+ New Access Token"

Your institution has disabled self-service tokens. There's no workaround on your
side; email your Canvas administrator and ask for a personal access token for an
API integration, or for the setting to be re-enabled for faculty.

### What the token can do

Everything you can do, everywhere you can do it. Not scoped to one course, not
scoped to teaching — it also covers courses where you're a student, and any admin
rights you happen to hold. There is no read-only variant in Canvas.

This is why `CANVAS_ENABLE_WRITES` and `CANVAS_ALLOW_DESTRUCTIVE` exist in this
server: Canvas gives you no way to issue a narrower credential, so the narrowing
happens here instead.

### Rotating

Account → Settings → Approved Integrations → the trash icon. The token stops
working immediately. Generate a new one and update your config file.

Do this if the token has ever appeared in a terminal transcript you shared, a
screenshot, a committed file, or a support ticket.

---

## Base URL

Your Canvas hostname, with scheme, without a path:

| Situation | Value |
|---|---|
| Most institutions | `https://yourschool.instructure.com` |
| Canvas Free for Teachers | `https://canvas.instructure.com` |
| Vanity domain | `https://canvas.yourschool.edu` |
| Self-hosted | whatever your Canvas is served at |
| Test/beta instance | `https://yourschool.test.instructure.com` |

Common mistakes:

- **Including `/api/v1`** — the server appends it. `…instructure.com/api/v1` becomes
  `…/api/v1/api/v1/courses` and 404s on everything.
- **Including a course path** — just the host.
- **`http://`** — Canvas redirects, and `requests` drops the `Authorization` header
  across a scheme change, so you get a confusing 401.

A trailing slash is fine; it gets stripped.

> **Tip:** if you want to experiment without risk, use your institution's **test**
> instance (`yourschool.test.instructure.com`). It's a nightly copy of production
> with email sending disabled. You'll need a separate token created there.

---

## Course id

In the URL when the course is open:

```
https://yourschool.instructure.com/courses/12345/assignments
                                           ^^^^^
```

Or ask the assistant — `canvas_list_courses` returns ids alongside names.

Setting `CANVAS_DEFAULT_COURSE_ID` is optional. With it set, every tool's
`course_id` parameter becomes optional and you can say "the roster" rather than
"the roster for 12345". Without it, the assistant will ask (or guess, which is
worse — so set it, or be explicit in your prompts).

If you teach several courses at once, leave it unset and name the course each time,
or run two server entries with different defaults:

```json
{
  "mcpServers": {
    "canvas-493": {
      "command": "canvas-mcp", "args": ["serve"],
      "env": { "CANVAS_DEFAULT_COURSE_ID": "12345" }
    },
    "canvas-101": {
      "command": "canvas-mcp", "args": ["serve"],
      "env": { "CANVAS_DEFAULT_COURSE_ID": "12346" }
    }
  }
}
```

(Both still need `CANVAS_BASE_URL`; put it in the shared env file.)

---

## Where configuration comes from

Resolution order. **Earlier wins** — nothing later overrides an already-set value.

1. **Real environment variables**, including your MCP client's `env` block.
2. **`$CANVAS_MCP_ENV_FILE`**, if set.
3. **`./.env`** in the process's working directory.
4. **`~/.config/canvas-mcp/.env`**.

The "earlier wins" rule is the useful bit: you can keep the token in a file and
still override the course id per client entry.

### Why `~/.config/canvas-mcp/.env` is the right default

MCP clients start the server in whatever directory they feel like — often `/`, your
home directory, or the app bundle. A `./.env` that works when you test by hand will
silently not be found when the client launches it. The `~/.config` location is
absolute, so it always resolves.

```bash
mkdir -p ~/.config/canvas-mcp
cp env.example ~/.config/canvas-mcp/.env
$EDITOR ~/.config/canvas-mcp/.env
chmod 600 ~/.config/canvas-mcp/.env
```

### File format

```
KEY=value
```

No quotes, no spaces around `=`, `#` starts a comment. `KEY = "value"` will store
the literal ` "value"` including quotes and space, and your token won't work.

### Keep the token out of client config files

`.mcp.json`, `claude_desktop_config.json`, and `.vscode/mcp.json` all get committed,
synced, and screenshotted. Put the non-secret settings there and leave
`CANVAS_API_TOKEN` in the `chmod 600` file.

---

## Verify with `doctor`

```bash
canvas-mcp doctor
```

It checks, in order, stopping at the first failure:

1. `CANVAS_BASE_URL` is set and well-formed.
2. `CANVAS_API_TOKEN` is set.
3. `GET /api/v1/users/self` succeeds — the token is valid for that host.
4. You have at least one teacher or TA enrollment.
5. `CANVAS_DEFAULT_COURSE_ID`, if set, resolves to a course you can see.

Then it prints how many tools the current configuration publishes and withholds.

Each failure prints what to change. This is the right first move for *any* problem —
it distinguishes "wrong host", "bad token", "no permission", and "wrong course id",
which otherwise all look like one opaque error inside a chat client.

Also useful:

```bash
canvas-mcp config    # resolved settings, token redacted to "set (N chars)"
canvas-mcp tools     # what's published, what's withheld, and why
```

---

## Client configuration

See the README's [step 6](../README.md#6-connect-your-ai-assistant) for per-client
blocks, and [`examples/`](../examples/) for files you can copy.

### The `command not found` problem

Desktop apps don't inherit your shell's `PATH`. If the server won't start:

```bash
which canvas-mcp
# /home/you/.local/bin/canvas-mcp
```

Use that absolute path as `"command"`. Or sidestep it entirely with `uvx`:

```json
{
  "command": "uvx",
  "args": ["--from", "git+https://github.com/zhenghh04/canvas-mcp", "canvas-mcp", "serve"]
}
```

### Checking that it started

- **Claude Desktop** — the tools icon in the input box should list Canvas tools.
  Logs: `~/Library/Logs/Claude/mcp*.log` (macOS),
  `%APPDATA%\Claude\logs\` (Windows).
- **Claude Code** — `claude mcp list` shows connected servers.
- **Cursor** — Settings → MCP shows a green dot per server.

Simplest check of all: ask the assistant *"what's my Canvas auth status?"* and see
whether it calls `canvas_auth_status`.

---

## HTTP transport

For a shared or remote setup:

```bash
canvas-mcp serve --transport http --host 127.0.0.1 --port 8900
```

`--transport sse` is also accepted for older clients.

> **This server has no authentication of its own.** Anyone who can open that port is
> operating as you, in your courses, with your token and your permissions. Bind to
> `127.0.0.1`. If you need it reachable from elsewhere, put it behind a reverse
> proxy that authenticates, or reach it through an SSH tunnel:
>
> ```bash
> ssh -N -L 8900:127.0.0.1:8900 you@the-host
> ```

---

## Upgrading

```bash
pip install --upgrade --force-reinstall git+https://github.com/zhenghh04/canvas-mcp
# or, from a clone:
git pull && pip install -e ".[dev]"
```

`uvx` callers get the latest on each run, subject to uv's cache; `uvx --refresh`
forces it.

Check [`CHANGELOG.md`](../CHANGELOG.md) before upgrading — safety defaults are the
kind of thing that can change between versions.

---

## Uninstalling and revoking

```bash
pip uninstall canvas-mcp
rm -rf ~/.config/canvas-mcp
```

Then remove the server entry from your client's config, and — the step people
forget — **revoke the token** in Canvas: Account → Settings → Approved Integrations
→ trash icon. Uninstalling the software does not invalidate the credential.

Also consider whether `CANVAS_DOWNLOAD_DIR` still holds student work.
