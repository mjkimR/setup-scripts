# Development environment setup

Bash setup wizard for macOS and Ubuntu: terminal tools, Git/IDE configuration,
agent skills, native subagents, and notification hooks. The checkbox menu uses
arrow keys to navigate, Space to select, and Enter to confirm.

## Usage

```bash
./setup.sh             # interactive category menu
./setup.sh --terminal  # all required terminal tools; no configuration prompts
./setup.sh --env       # environment configuration and optional addons
./setup.sh --agents    # skills, subagents, and notification hooks
./setup.sh --all       # environment and agents
```

Terminal setup installs Git, NVM/Node 24, UV, just, ripgrep, APM, gh, gcloud, and
Docker/Compose. It preserves installed tools and Git identity, and stops on failure.
workbench initialization uses this mode. Zsh/Oh My Zsh, IDE settings, and agents
are separate wizard options. See [terminal tools](modules/terminal/README.md) for
platform requirements and post-install steps.

Customize `config/vscode/settings.json`, `config/vscode/keybindings.json`, and
`config/extensions.txt` before IDE sync. Extensions are one per line; blank lines
and `#` comments are ignored. Existing editor configuration is backed up.

## Agent setup

The **Sync AI Agent skills** option installs skills and their required CLI tools.
Each skill's `meta.yaml` declares supported agents and default selection;
`git-commit` and `handoff` are selected by default.

```bash
modules/agents/skills/install.sh            # interactive menu, or defaults without a TTY
modules/agents/skills/install.sh --all      # all skills in this installer
modules/agents/skills/install.sh git-commit # one skill
```

| Skill | Agents | Purpose |
| --- | --- | --- |
| `git-commit` | Antigravity, Claude Code, Codex | One commit with low/default/high modes and repository guards. |
| `git-commit-revise` | Antigravity | Review/revise commit messages. |
| `handoff` | Claude Code | Write a portable session handoff document. |
| `polish-doc` | Antigravity | Korean Markdown copyediting. |
| `handoff-polish` | Claude Code, Codex | Delegate copyediting to agy. |
| `research-req` | Claude Code, Codex | Prepare separate, copy-ready Deep Research prompts by topic. |
| `research-review` | Claude Code, Codex | Review result files and derive conclusions for the current task. |

The research skills are opt-in at installation:

```bash
modules/agents/skills/install.sh research-req research-review
```

Invoke them explicitly with `/research-req` or `/research-review` in Claude Code,
and `$research-req` or `$research-review` in Codex. Request text after
`research-req` scopes the prompts; without it, the skill proposes topics from the
discussion for selection. Paste each generated prompt file into its own Gemini
Deep Research request, then pass downloaded result files to `research-review`.
Both skills use `agentkit scratch path research` for prompts, preserved reports,
and reviews. No clipboard or Google account connection is required.

The installer links entire skill directories, including Claude's invocation
setting in `SKILL.md` and Codex's policy in `agents/openai.yaml`. These research
skills disable implicit invocation in both hosts; `meta.yaml`'s `default` only
controls installation selection, not invocation.

Use the separate **Sync AI Agent subagents** option for `handoff-commit` and its
native commit worker. This route delegates to Codex's native child or Claude Code's
installed profile. See [subagents](modules/agents/subagents/README.md) for installation
and provider contracts; [ADR 0010](docs/decisions/0010-native-commit-subagent-profiles.md)
records the design. The older `agentkit handoff commit` CLI remains available for
compatibility with existing callers.

[AgentKit](tools/agentkit/README.md) owns executable behavior: commit onboarding,
verification, guards, handoff, and polish configuration. Skills describe workflows.
[Notification setup](modules/agents/hooks/notify/README.md) covers macOS banners,
click-to-focus, hook trust, backups, and troubleshooting.

## Personal developer CLI

`devkit` prepares diff attachments and prompts for manual AI chats. It is installed
separately from AgentKit:

```sh
uv tool install --editable tools/devkit
devkit copy-diff
devkit prompt review --last -l Korean
```

See [devkit](tools/devkit/README.md) for options and clipboard support.

## Development

[AGENTS.md](AGENTS.md) defines repository layout, installer safety, and change rules.

```bash
./check.sh --check       # read-only format/lint checks and all tests
./check.sh               # apply formatting/lint fixes, then test
tests/run-all.sh agentkit # focused suites by name
tests/run-all.sh '' unit # isolated logic across tools
tests/run-all.sh '' integration # installer, Git, and CLI contracts
```

Shell tests use fixtures and stub external commands; Python CLI tests run through
UV against repository sources. Do not run real installers as routine tests.

See [the test guide](tests/README.md) for tier boundaries and source-mirroring paths.
