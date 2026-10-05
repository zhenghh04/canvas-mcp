# Changelog

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning is [semver](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] — 2026-10-05

First public release. The code began as a single-file MCP server used to run one
course; this release makes it a standalone package any instructor can install.

### Added

- **Three-tier safety model.** `read` / `write` / `destructive`, with destructive
  **off by default**. A withheld tool is never registered — the model can't see it,
  can't call it, and it costs no context.
- **Tool-surface trimming.** `CANVAS_TOOL_GROUPS`, `CANVAS_TOOLS` (allowlist), and
  `CANVAS_DISABLE_TOOLS` (denylist). An allowlist cannot bypass a tier gate.
- **`canvas-mcp` CLI** with `serve`, `doctor`, `tools`, and `config`.
  - `doctor` walks base-url → token → identity → teacher enrollments → default
    course and names the first thing that's wrong, instead of surfacing one opaque
    401 inside a chat client.
  - `tools` lists what the current configuration publishes *and* what it withholds,
    with the reason.
  - `config` shows resolved settings with the token redacted to `set (N chars)`.
- **New tools:** `canvas_get_gradebook` (whole gradebook as one student ×
  assignment table), `canvas_download_submissions`, `canvas_download_file`,
  `canvas_list_sections`, `canvas_list_calendar_events`,
  `canvas_create_calendar_event`, `canvas_create_assignment_group`,
  `canvas_message_students`. 47 tools total.
- **Retry with backoff** on 429 and 5xx, honouring `Retry-After`. Canvas signals
  rate limiting with a **403** and the body text "Rate Limit Exceeded", not a 429;
  the client distinguishes that from a genuine permission 403 and retries only the
  former.
- **Error explanations** for 401 / 403-ratelimit / 403-permission / 404 / 422, each
  with a suggested remedy, so the model can adapt rather than retry blindly.
- **HTTP and SSE transports** alongside stdio (`serve --transport http`).
- **`CANVAS_REDACT_PII`** — stable, non-reversible `anon-<hash>` pseudonyms for
  emails, login ids, and SIS ids. Names are deliberately not redacted.
- **Config file discovery:** `$CANVAS_MCP_ENV_FILE` → `./.env` →
  `~/.config/canvas-mcp/.env`. A real environment variable always wins, so an MCP
  client's `env` block beats any file.
- **163 offline tests.** The fixture transport raises on any unexpected request, so
  a test that escapes fails loudly rather than mutating a live course.
- Documentation: README, [SETUP](docs/SETUP.md), [TOOLS](docs/TOOLS.md),
  [SAFETY](docs/SAFETY.md), [RECIPES](docs/RECIPES.md), and client config
  [examples](examples/).

### Changed

- **Destructive tools are now withheld by default.** `canvas_delete_assignment`,
  `canvas_delete_page`, `canvas_delete_module`, `canvas_remove_enrollment`, and
  `canvas_api_write` require `CANVAS_ALLOW_DESTRUCTIVE=1`. If you used the
  single-file predecessor, these were available with writes alone; set the flag to
  restore that behaviour.
- **No institution-specific defaults.** `CANVAS_BASE_URL` has no default and must
  be set.
- **HTML is flattened block-aware.** `<br>` and block-element closes become
  newlines *before* tags are stripped. Previously a syllabus collapsed into one
  unreadable line.
- `canvas_message_students` defaults to individual messages
  (`group_conversation=False`) so a note about missing work doesn't disclose the
  recipient list.
- Pagination caps are reported. A truncated list carries `_truncated` with a note
  naming `CANVAS_MAX_PAGES`, rather than being silently presented as complete.
- Restructured into a `src/` layout package. `build_server(config)` is a pure
  function of configuration, so the published tool surface can be tested
  per-configuration without re-importing modules under a mutated environment.

### Fixed

- **`functools.wraps` on the error guard.** Without it, FastMCP introspected the
  wrapper's `(*args, **kwargs)` and published two bogus string parameters, making
  every guarded tool uncallable while the tool list still looked correct.
  `test_no_tool_publishes_args_or_kwargs` now guards against the regression.
- **Path traversal in submission downloads.** Attachment names come from students,
  and `../../.ssh/authorized_keys` is a legal Canvas filename. Names are now
  sanitised before touching the filesystem.
- **Token no longer sent to the file-storage host.** Canvas uploads redirect to
  S3/InstFS, where the pre-signed `upload_params` are the entire authorisation;
  the bearer token is stripped. Multipart field ordering is also fixed — S3 ignores
  fields that follow the `file` part.
- **`form()` no longer drops meaningful falsy values.** `points_possible=0` and
  `published=False` are real instructions; only `None` and `""` mean "unset".
- Redaction leaves empty identifiers alone. Hashing `""` invented an identifier for
  every student who had none — and gave them all the same one.
- The error guard no longer swallows non-Canvas exceptions. A `KeyError` is a bug
  in this server, not a Canvas failure, and must not be disguised as one.

[Unreleased]: https://github.com/zhenghh04/canvas-mcp/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/zhenghh04/canvas-mcp/releases/tag/v0.2.0
