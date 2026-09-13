---
name: handoff-commit
description: >-
  Delegate an explicitly requested git commit workflow to the native commit
  subagent. Use only when the user asks to commit.
disable-model-invocation: true
---

# Commit Handoff

Delegate the complete commit workflow to one native commit subagent. The child
runs `git-commit` directly in the shared checkout; the parent does no diff,
staging, verification, or commit work while it runs.

Provider-specific configuration is deliberately separate:

- Codex: `modules/agents/subagents/commit/codex/README.md`
- Claude Code: `modules/agents/subagents/commit/claude/agentkit-commit.md`

## Codex

For an explicit user request to create commits, spawn exactly one child through
the collaboration tool:

- `task_name`: `commit`
- `model`: `gpt-5.6-luna`
- `fork_turns`: `all`

Pass this task, followed by the user's explicit commit constraints:

> You are the commit subagent. Read the repository instructions and invoke the
> `git-commit` skill directly. Own the complete requested commit workflow in
> the shared checkout: inspect changes, run required verification, stage, and
> commit. Do not delegate, push unless requested or repository config enables
> it, amend/reset, or bypass a guard. Report commit hashes and subjects,
> verification outcome, remaining uncommitted paths, and blockers.

Wait for the child and relay its report. A blocker is for the user to decide;
never retry automatically.

## Claude Code

Delegate to the installed `agentkit-commit` subagent and pass the user's
explicit constraints unchanged. Its file is installed at
`~/.claude/agents/agentkit/agentkit-commit.md`; it preloads `git-commit` and
pins the Claude-specific model and effort settings.

If `~/.claude/agents/` did not exist when the active Claude Code session
started, restart Claude Code once after installation so it discovers the new
directory.

## Shared rules

- Do not run the legacy `agentkit handoff commit`/Antigravity path for the same
  worktree.
- Do not start another writer in this checkout until the child returns.
- Do not make a competing commit after a child failure; report its exact
  blocker and leave retry or recovery to the user.
