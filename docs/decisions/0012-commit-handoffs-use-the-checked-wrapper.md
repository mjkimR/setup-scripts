# 12. Commit handoffs use the checked wrapper

- **Date**: 2026-09-15
- **Status**: Accepted
- **Supersedes in part**: [0009](./0009-commit-through-the-cli-not-an-eval.md)

## Context

The original headless Antigravity handoff granted `git commit` directly. Its
parent preflight checked the committing identity and, in safe mode, injected a
timestamp. The receiver could nevertheless bypass commit-time path and secret
guards because it ran plain `git commit`.

Native Codex commit subagents already use `agentkit commit-safe commit`. Keeping
a different execution path for headless handoffs made the security guarantee
depend on the delegation mechanism.

## Decision

Every delegated commit uses `agentkit commit-safe commit`; no handoff grants or
permits plain `git commit`.

Headless handoffs retain the narrowly scoped `git add` and read-only git grants,
and gain only `command(agentkit commit-safe commit)`. The wrapper builds its own
Git argv, so that permission does not provide arbitrary command execution. It
performs identity and guard checks immediately before committing.

`agentkit handoff commit --plain` calls the wrapper with `--plain`: identity and
guards still apply, but inherited dates are removed and the system clock is
used. Safe handoffs call the wrapper without that flag, allowing it to resolve
and persist the repository timeline itself.

## Consequences

- Handoff prompts explicitly prohibit plain `git commit`.
- The caller no longer pre-resolves safe-mode timestamps for a child process.
- Users granting headless commit handoffs must replace `command(git commit)`
  with `command(agentkit commit-safe commit)`.
