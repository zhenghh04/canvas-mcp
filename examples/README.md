# Example configurations

Copy the one that matches your client, edit `CANVAS_BASE_URL` and
`CANVAS_DEFAULT_COURSE_ID`, and restart the client.

| File | Client | Where it goes |
|---|---|---|
| [`claude-desktop.json`](claude-desktop.json) | Claude Desktop | macOS `~/Library/Application Support/Claude/claude_desktop_config.json` · Windows `%APPDATA%\Claude\claude_desktop_config.json` · Linux `~/.config/Claude/claude_desktop_config.json` |
| [`claude-code.json`](claude-code.json) | Claude Code | `.mcp.json` in your project, or `~/.claude.json` for all projects |
| [`cursor.json`](cursor.json) | Cursor | `~/.cursor/mcp.json`, or `.cursor/mcp.json` per project |
| [`vscode.json`](vscode.json) | VS Code (Copilot agent mode) | `.vscode/mcp.json` |
| [`uvx.json`](uvx.json) | any | no install needed — runs straight from GitHub |
| [`read-only.json`](read-only.json) | any | the strictly-read-only posture |
| [`multi-course.json`](multi-course.json) | any | two courses as two server entries |

## The token is not in any of these

On purpose. These files get committed, synced, and screenshotted. Put
`CANVAS_API_TOKEN` in `~/.config/canvas-mcp/.env` with `chmod 600`, and keep only
the non-secret settings here:

```bash
mkdir -p ~/.config/canvas-mcp
cp env.example ~/.config/canvas-mcp/.env
$EDITOR ~/.config/canvas-mcp/.env
chmod 600 ~/.config/canvas-mcp/.env
```

A real environment variable always beats a file, so anything you *do* put in the
`env` block below still wins — which is what makes the split work.

## If the server won't start

The most common cause is that desktop apps don't inherit your shell's `PATH`, so
`canvas-mcp` isn't found. Two fixes:

```bash
which canvas-mcp        # use this absolute path as "command"
```

or switch to [`uvx.json`](uvx.json), which needs nothing on `PATH` but `uvx`
itself.

Verify your configuration independently of any client first:

```bash
canvas-mcp doctor
```
