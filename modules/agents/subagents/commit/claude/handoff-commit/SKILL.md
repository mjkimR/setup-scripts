---
name: handoff-commit
description: >-
  Delegate an explicitly requested git commit workflow to the native Claude
  Code commit subagent. Use only when the user asks to commit.
disable-model-invocation: true
---

# Commit Handoff

Delegate to the installed `agentkit-commit` subagent and pass the user's
explicit commit constraints and low/default/high mode unchanged. Default is
`default`; `medium` aliases default. The installed profile stays at medium
effort for every mode; modes control context size and workflow depth. It owns the complete
`git-commit` workflow in the shared checkout.

While the child runs, do no diff, staging, verification, or commit work in this
checkout, and do not start another writer. Wait for the child and relay its
report. A blocker is for the user to decide; never retry automatically.

If `~/.claude/agents/` did not exist when the active Claude Code session
started, restart Claude Code once after installation so it discovers the
`agentkit-commit` profile.
