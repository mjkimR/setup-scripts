# Agent notifications (macOS)

Run `modules/agents/hooks/notify/install.sh` from the repository root, or select
notification hooks in the setup wizard. It configures installed Claude Code and
Codex agents to use terminal-notifier; missing agents are skipped.

```text
<project_name> · done
Claude Code · 49s · 14:23
```

## Behavior

- Clicking returns to the originating terminal. iTerm2 uses `ITERM_SESSION_ID`
  to select the pane; VS Code derivatives and JetBrains open the containing project.
- For nested directories, the deepest open editor project wins. Discovery uses
  VS Code's `storage.json` (`windowsState.openedWindows`) or JetBrains'
  `recentProjects.xml` (`opened="true"`), falling back to the VCS root, then cwd.
  The banner shows `<subdir>(<project>)` when they differ.
- Each chat keeps one banner. Submitting a prompt retracts it. Codex uses its
  top-level `notify` command for completion and `UserPromptSubmit` for retraction.
- Claude forwards permission prompts and MCP elicitation, excluding `idle_prompt`.
  Codex forwards `PermissionRequest` asynchronously for shell, file, and MCP approvals.
- Claude suppresses completion banners for turns under 30 seconds; override with
  `AGENT_NOTIFY_MIN_SECONDS`. Codex reports completion regardless of duration.

## Installation and recovery

The installer stages and validates scripts/settings before replacing live files.
It updates `~/.claude/settings.json`, `~/.codex/config.toml`, and
`~/.codex/hooks.json`, rolling back earlier replacements if a later one fails.
Each target's `.bak` preserves its state before the first managed installation;
`.bak.latest` preserves its state before the current run. Reinstallation replaces
only this module's entries and preserves unrelated hooks.

Codex hooks live exclusively in `~/.codex/hooks.json`. Inline `[hooks]` tables in
the same `config.toml` stop installation before mutation; move or remove them to
avoid merged hook definitions and startup warnings.

After installation, open Codex's `/hooks` menu to review and trust the new
`UserPromptSubmit` and `PermissionRequest` hooks. Scripts from this directory are
installed into `~/.local/bin/`.

For stale banners, inspect `~/.local/state/agent-notify/notify.log`: removal records
include the notification group and exit code. Delivery uses terminal-notifier;
osascript lacks its own bundle identity and can silently drop notifications.
