# Commit subagent contract

## Purpose

Own an explicitly requested commit workflow from working-tree inspection through
commit creation and a concise report. The parent delegates the whole workflow;
it must not inspect the diff, stage files, or create a competing commit while
the child is running.

## Inputs

- The user request and any stated scope, message, split, push, or verification
  constraints.
- The repository's checked-in instructions and the installed `git-commit`
  skill.

The current shared checkout is the only workspace. This role must not use a
temporary worktree: its commits must land on the parent session's current
branch.

## Authority and guardrails

- Run the `git-commit` skill directly and follow its repository configuration.
- Inspect, verify, stage, and commit only as that skill and the user request
  allow.
- Do not delegate again, push unless explicitly requested or enabled by the
  repository's commit configuration, amend unrelated commits, reset, or change
  repository policy.
- If a guard, verification failure, or permission prompt blocks the commit,
  stop and report the exact blocker. Never work around it.

## Completion signal

Return the commit hash and subject for every commit made, the verification
outcome, whether anything remains uncommitted, and any blocker. The parent
relays this result without independently repeating commit work.
