# Contributing

Contributions welcome — especially from instructors who hit something this doesn't
cover. A bug report that says *"I tried to do X for my course and the tool did Y"*
is genuinely useful even without a patch.

## Setup

```bash
git clone https://github.com/zhenghh04/canvas-mcp
cd canvas-mcp
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
ruff check .
```

163 tests, a few seconds, no network.

## The one hard rule about tests

**No test may contact a real Canvas tenant.** The `client` fixture installs a
transport that raises on any unexpected request, so a test that escapes fails
loudly instead of quietly mutating somebody's live course. Don't add a test that
needs a token, and don't add a `skipif` that re-enables one.

If you need to verify against real Canvas, do it by hand against your institution's
**test** instance (`yourschool.test.instructure.com` — a nightly copy of production
with email disabled), and say so in the PR.

## Adding a tool

1. Pick the right module in `src/canvas_mcp/tools/`. Each has a
   `register(reg: Registrar) -> None` that defines tools as closures over
   `reg.client`.
2. Decorate it:

   ```python
   @reg.tool(group="assignments", tier="write")
   def canvas_do_the_thing(thing_id: str, course_id: str = "") -> str:
       """One-line summary — this is what the model reads. MUTATES the course.

       Args:
           thing_id: ...
           course_id: defaults to CANVAS_DEFAULT_COURSE_ID.
       """
   ```

3. Add a test in `tests/test_tools.py` asserting the **request it builds** — method,
   path, and form fields — not just that it returns a string.

### Conventions a new tool has to follow

**Pick the tier honestly.** `read` never changes anything. `write` is recoverable
or at least visible. `destructive` is for anything that destroys data or can't be
undone. When unsure, go one tier stricter.

**Say what it does in the first docstring line.** That line is the model's only
guide to when the tool applies, and for mutating tools it must contain one of
`MUTATES`, `NOTIFIES`, `IRREVERSIBLE`, or `notified` — there's a test enforcing
this, because the tier metadata isn't what the model reads when deciding whether to
ask the instructor first.

**Default to not-live.** Anything that creates student-visible content takes
`published: bool = False`.

**Distinguish unset from false.** Use `""` / `None` for "caller didn't mention it"
and let `form()` drop them. A parameter whose `False` is meaningful (`published`,
`excused`) must default to `None`, not `False` — otherwise you can't tell "leave it
alone" from "unpublish it". `form()` keeps `False` and `0`, drops `None` and `""`.

**Bound the output.** Run list results through `slim_all()` with an explicit key
tuple and finish with `client.fmt(...)`. A tool that can return 400 full Canvas
objects will eat a context window.

**Let bugs raise.** The `guard` decorator converts `CanvasError` into an
`ERROR: …` string for the model. It deliberately does not catch anything else — a
`KeyError` is a bug here, not a Canvas problem, and dressing it up as one hides it.

**`functools.wraps` on `guard` is load-bearing.** Without it, FastMCP introspects
the wrapper's `(*args, **kwargs)` and publishes two bogus string parameters,
making every guarded tool uncallable while the tool list still looks fine. This has
shipped as a bug before. `test_no_tool_publishes_args_or_kwargs` exists to stop it
coming back — don't touch `guard` without running it.

## Style

Ruff with the config in `pyproject.toml` (line length 100, `E,F,I,UP,B,W`,
`E501` ignored). `ruff check . && ruff format --check .` before you push.

Type-annotate public functions. Comments should explain *why*, not restate the
code — the existing comments are a reasonable guide to the density expected.

## Pull requests

- One topic per PR.
- Tests for new behaviour; a failing test first for a bug fix.
- Update `docs/TOOLS.md` if you changed a tool's surface, and `CHANGELOG.md` under
  `Unreleased`.
- Say how you verified it. "Ran against my test instance, created and deleted a
  module" is worth a lot more than "should work".

CI runs ruff and pytest on Python 3.10–3.13. All four must pass.

## Changing a safety default

Changing what's published by default — a new tier assignment, a tool moving from
`destructive` to `write`, a flag flipping — is a bigger deal than a feature, because
people's existing configs silently inherit it. Open an issue first, and if it lands,
it goes in `CHANGELOG.md` under a **Changed** heading with the word *default* in it.

## Reporting bugs

Include: what you asked the assistant to do, which tool it called, what Canvas
returned, your `canvas-mcp config` output, and your Canvas flavour (hosted,
self-hosted, Free for Teachers).

**Never paste a token or real student data.** `canvas-mcp config` already redacts
the token; redact names and emails yourself.

## Security

For anything involving credential exposure or student-data leakage, email the
maintainer rather than opening a public issue. Vulnerabilities in Canvas itself go
to Instructure.
