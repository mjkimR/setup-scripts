---
name: handoff-commit
description: >-
  Delegate an explicitly requested git commit workflow to the native Luna commit
  subagent. Use only when the user asks to commit.
disable-model-invocation: true
---

# Commit Handoff

For an explicit user request to create commits, spawn exactly one child through
the collaboration tool:

- `task_name`: `commit`
- `model`: `gpt-5.6-luna`
- `fork_turns`: `all`

Pass this task, followed by the user's explicit commit constraints:

> You are the commit subagent. Read the repository instructions and use the
> `git-commit` skill. Create a single comprehensive commit with
> `agentkit commit-safe commit`, never plain `git commit`. Do not split changes
> into multiple commits. Own the complete requested commit workflow in
> the shared checkout: inspect changes, run required verification, stage, and
> commit. Do not delegate, push unless requested or repository config enables
> it, amend/reset, or bypass a guard. Report the commit hash and subject,
> verification outcome, remaining uncommitted paths, and blockers.

While the child runs, do no diff, staging, verification, or commit work in this
checkout, and do not start another writer. Wait for the child and relay its
report. A blocker is for the user to decide; never retry automatically.
