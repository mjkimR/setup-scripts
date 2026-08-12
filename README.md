# Development Environment Setup Scripts

An interactive, terminal-based (TUI) setup tool for automating the configuration of fresh development environments on macOS and Ubuntu.

## Features

- **No Dependency TUI Menu**: Uses pure Bash (ANSI escape codes) to draw an interactive checkbox list. Navigate with arrow keys, select/deselect with Space, and confirm with Enter.
- **Cohesive Modular Design**: Every tool is packaged in its own directory under `modules/` (e.g. `git/`, `nvm/`), grouping Linux/macOS installers (`install.sh`) and future Windows installers (`install.ps1`) together.
- **Git Installer & Configurer**: Installs Git and configures global credentials dynamically.
- **NVM & Node 24**: Sets up Node Version Manager and configures Node.js v24 LTS as the default.
- **Astral UV**: Installs the high-performance Python package manager.
- **Zsh & Oh My Zsh**: Performs unattended setup of Zsh, Oh My Zsh, and installs helper plugins (`zsh-autosuggestions`, `zsh-syntax-highlighting`).
- **IDE Sync (VS Code, Cursor, VSCodium)**: Auto-detects installed editors, backs up existing configurations, copies preset settings/keybindings, and auto-installs plugins listed in `extensions.txt`.
- **Agent Notification Hooks (macOS)**: One macOS notification format shared by Claude Code and Codex CLI, with click-to-focus that returns to the exact terminal the turn came from.

---

## Directory Structure

```text
setup-scripts/
├── setup.sh          # Main entry point script (for macOS/Ubuntu)
├── setup.ps1         # [Future] Entry point script (for Windows)
├── README.md         # Documentation
├── lib/              # Shared helper libraries (UI & Utilities)
├── config/           # VS Code settings and extension lists
└── modules/          # Installation scripts grouped by tool categories
```

---

## Usage

Simply make the entry point script executable and run it:

```bash
# Make sure files are executable
chmod +x setup.sh lib/*.sh modules/terminal/*/install.sh modules/ide/*/install.sh

# Run the setup wizard
./setup.sh
```

### Customizing Configuration Files

Before running the script, you can adjust the configs inside the `config/` directory to suit your preferences:

1. **`config/vscode/settings.json`**: Place your customized IDE settings here (e.g., font size, tab sizing, format-on-save preference).
2. **`config/vscode/keybindings.json`**: Add your custom editor shortcut mappings.
3. **`config/extensions.txt`**: List the extensions you want to install, one per line. Blank lines and lines starting with `#` are ignored.

---

## Agent Notification Hooks (macOS)

`modules/agents/notify/install.sh` gives Claude Code and Codex CLI a single
notification format, delivered through `terminal-notifier`:

```text
<project_name> · done          <- project first; several sessions run at once
Claude Code · 49s · 14:23      <- which agent, how long it took, when it landed
```

- **Click returns to the right terminal.** iTerm2 is resolved down to the exact
  split pane via `ITERM_SESSION_ID`; VS Code, Antigravity and JetBrains editors
  get the project folder opened, which raises the window already holding it.
- **Sessions started in a subdirectory still land on the project.** Handing an
  editor a subdirectory makes it open that as a *new* project instead of raising
  the window the terminal lives in. Both editor families publish which projects
  are currently open — JetBrains in `recentProjects.xml` (`opened="true"`),
  VS Code derivatives in `storage.json` (`windowsState.openedWindows`) — and the
  deepest open project containing the session wins, so a subproject nested inside
  another open project still resolves to itself. Anything else falls back to the
  VCS root, then to the directory itself. The banner names both as
  `<subdir>(<project>)` so it never silently disagrees with where the click goes.
- **Banners replace rather than stack.** Claude Code and Codex both keep one
  live notification per chat session.
- **Submitting a prompt retracts that chat's notification**, so a banner never
  outlives the reason you needed it. Codex completion delivery stays on its
  top-level `notify` command, while a `UserPromptSubmit` lifecycle hook handles
  retraction.
- **Input-needed alerts mean actual intervention.** Claude Code forwards
  permission prompts and MCP elicitation dialogs, but filters `idle_prompt` so
  a completed turn does not produce a second notification one minute later.
  Codex forwards `PermissionRequest` events, including shell, file-edit, and
  MCP approval prompts, through an asynchronous lifecycle hook so it does not
  delay the approval UI.
- Claude Code stays quiet for turns under 30 seconds. Override with
  `AGENT_NOTIFY_MIN_SECONDS`. Codex completion notifications remain unfiltered
  by duration and fire on every completed turn.

The installer stages and validates every script and settings change before it
touches a live target. It then updates `~/.claude/settings.json`,
`~/.codex/config.toml`, and `~/.codex/hooks.json` as one commit, rolling back
files already replaced if a later replacement fails. For every existing target,
`.bak` permanently preserves the version from before this installer first
managed it, while `.bak.latest` is refreshed with the version immediately before
the current run. Re-running replaces only this module's entries instead of
stacking duplicates and preserves unrelated Codex lifecycle hooks.

Codex hooks are managed exclusively in `~/.codex/hooks.json`. If the same
`~/.codex/config.toml` contains inline `[hooks]` tables, installation stops
before copying scripts or changing settings and asks you to move or remove the
inline hooks. This avoids Codex merging two hook representations in one config
layer and emitting a startup warning.

The installer skips either agent that is not installed.

Open Codex's `/hooks` menu once after installation to review and trust the new
`UserPromptSubmit` and `PermissionRequest` hooks. The hook scripts ship
alongside the installer in `modules/agents/notify/` and are copied to
`~/.local/bin/`. The debug log at
`~/.local/state/agent-notify/notify.log` includes each removal's group and exit
code, making stale-banner failures distinguishable from missing hooks.

Delivery deliberately goes through `terminal-notifier` rather than `osascript`:
`osascript` has no bundle id, so macOS attributes its notifications elsewhere
and drops them silently while still exiting 0 — a broken setup that looks like
a working one.
