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
- `fork_turns`: `none`
- `reasoning_effort`: `medium` for every mode

Accept the same low/default/high modes as `git-commit` (`medium` aliases default).
Pass the selected mode, repository path, applicable repository instructions,
user constraints, caller intent, and any current verification attestation.
Because the child starts without inherited conversation, include these explicitly.
Then pass this task:

> You are the commit subagent. Read the repository instructions and use the
> `git-commit` skill in the supplied mode. Do not spawn a message worker.
> Create a single comprehensive commit with
> `agentkit commit-safe commit`, never plain `git commit`. Do not split changes
> into multiple commits. Own the complete requested commit workflow in
> the shared checkout: check scope, skip agent-run verification unconditionally
> in low mode; otherwise reuse current verification or run it when required.
> Stage, read the staged context, and commit. For low, report verification as
> skipped (low mode), regardless of prior test attestations. Do not delegate,
> push unless requested or repository config enables it, amend/reset, or bypass a guard. Report the commit hash and subject,
> verification outcome, remaining uncommitted paths, and blockers.

While the child runs, do no diff, staging, verification, or commit work in this
checkout, and do not start another writer. Wait for the child and relay its
report. A blocker is for the user to decide; never retry automatically.
