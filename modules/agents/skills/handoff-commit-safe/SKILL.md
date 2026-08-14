---
name: handoff-commit-safe
description: >-
  Delegates the commit workflow to the Antigravity CLI (agy) while enforcing the
  email whitelist and commit timestamp rules locally. Invoke ONLY when the user
  explicitly runs /handoff-commit-safe. Never trigger it on your own from a
  general request to commit — handing work to another agent is the user's call,
  not an inference.
allowed-tools: Bash(agentkit:*), Bash(git status:*), Bash(git log:*)
---

# Handoff Commit (Safe)

`--safe` mode of [handoff-commit](../handoff-commit/SKILL.md). **Everything in
that skill applies** — why the work is delegated, the rules against doing any of
it yourself, how to report the result. Read it if you have not.

Only the command and three details differ.

## Step 1: Run the handoff

One command, nothing before it:

```bash
agentkit handoff commit --safe
```

## What `--safe` changes

1. **The whitelist and the timestamp are resolved locally, before `agy` is
   called.** The current `git config user.email` must be authorised, and the
   resolved timestamp is exported so `agy` only ever runs a plain `git commit`.
   A rejected identity aborts before any quota is spent. **Do not work around a
   rejection** — report it and let the user decide.
2. **One `agy` call per atomic unit**, because environment variables are fixed
   once a process starts: a single call covering three commits would stamp all
   three identically and destroy the progression this variant exists to produce.
   So a three-way split costs three round trips of ~20–60s each, not one.
   `--max-units` (default `10`) guards the loop.
3. **Report each commit's timestamp**, not just hash and subject.

Exit codes carry the same meanings as the base skill. A rejected identity is
exit 1 — report the offending email verbatim. Exit 2 also covers the
`--max-units` guard tripping with changes still pending.

## Extra requirement

`~/.config/git-commit-safe/config.yaml` must exist and list the current git
email. `agentkit commit-safe init` creates it; see
[the onboarding guide](../git-commit-safe/references/onboard.md).
