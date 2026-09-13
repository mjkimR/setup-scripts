# 11. Categorized setup workflow and interactive agent skill selection

- **Date**: 2026-09-13
- **Status**: Accepted
- **Extends**: [0002](./0002-consolidate-the-commit-skill-set.md) and
  [0010](./0010-native-commit-subagent-profiles.md)

## Context

As tooling expanded, `setup.sh` presented an undivided flat list of 8 options
spanning system packages, shells, editor settings, and AI agent skills/hooks/subagents.
Environment bootstrapping and AI agent configuration serve different workflows:
developers setting up a machine often want core runtimes first, while agents and
skills evolve frequently and are installed or updated independently.

Furthermore, `modules/agents/skills/install.sh` previously installed every
available skill unconditionally. As the catalog grew (`git-commit`,
`git-commit-revise`, `handoff`, `handoff-polish`, `polish-doc`), users needed
the ability to select which skills to link into their agents (Antigravity, Claude Code,
Codex), with sensible defaults configured via each skill's `meta.yaml`.

## Decision

1. **Categorized entry point in `setup.sh`**:
   - Provide a top-level single-select menu (`single_select_menu`) dividing
     setup into:
     - **🛠️ Development Environment**: Git, NVM & Node 24, Astral UV, Oh My Zsh, VS Code/IDE
     - **🤖 AI Agent Ecosystem**: AI Agent Skills, AI Agent Subagents, Notification Hooks (macOS)
     - **🚀 Full Setup**: Runs both categories sequentially
     - **❌ Exit**
   - Provide direct CLI flags: `./setup.sh --env`, `./setup.sh --agents`, `./setup.sh --all`.

2. **Metadata-driven defaults and interactive skill selection**:
   - Add `default: true` / `default: false` to each skill's `meta.yaml`.
   - By default, core skills (`git-commit`, `handoff`) and subagent roles
     (`subagents/commit`) are enabled (`default: true`), while specialized
     tools (`git-commit-revise`, `handoff-polish`, `polish-doc`) default to
     `false`.
   - `modules/agents/skills/install.sh` provides an interactive TUI multi-select
     menu when attached to a TTY (`[ -t 0 ] && [ -t 1 ]`), pre-checking items
     where `default: true`.
   - In non-interactive contexts or CI, it automatically defaults to `default: true`
     skills, while accepting `--all` or specific skill names as arguments.

3. **Reusable TUI single-select menu**:
   - Add `single_select_menu` to `lib/ui.sh` matching the ANSI navigation
     standards of `multi_select_menu`. Guard TTY operations against invalid ioctls
     when redirected.

## Consequences

- The setup wizard has a clear two-tier structure: developers can configure core
  environment runtimes or manage their AI agent toolchain independently.
- Users have full visibility and granular control over which agent skills are
  linked into Antigravity, Claude Code, and Codex.
- Tests and automated installations remain fully non-interactive and deterministic.
