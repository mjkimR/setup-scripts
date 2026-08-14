---
name: git-commit-safe
description: >-
  Use this skill when the user asks to perform safe git commits with email whitelist
  validation, custom commit timestamp control, or mentions git-commit-safe.
---

# Git Commit Safe Skill

[git-commit](../git-commit/SKILL.md) plus two guarantees: the commit is refused
unless the current git identity is whitelisted, and the commit timestamp is
resolved rather than taken from the clock.

**Everything about inspecting changes, splitting them into atomic units and
wording the message lives in `git-commit`. Follow it.** This file only adds the
pre-flight and changes how the commit itself is executed.

Both additions belong to the `agentkit` CLI, which owns the config, the whitelist
and the timestamp state. If it is not on `PATH`, stop and point the user at
[references/onboard.md](./references/onboard.md).

## Step 1: Pre-flight

```bash
agentkit commit-safe verify
```

- **Exit 2 — config missing or unusable.** Stop. Tell the user to run
  `agentkit commit-safe init`, or point at [references/onboard.md](./references/onboard.md).
- **Exit 1 — identity rejected.** Stop and report the offending email verbatim.
  Never work around it; choosing a different identity is the user's call.

`verify` only previews the timestamp — it never consumes one, so running it costs
nothing.

## Step 2: Analyse and stage

Exactly as in `git-commit`: read `git log` for the repository's conventions,
inspect `git status -s` and the diffs, then stage one atomic unit.

```bash
git add path/to/file1 path/to/file2
```

## Step 3: Commit with the resolved timestamp

`agentkit commit-safe env` re-checks the whitelist, advances the timestamp state
and prints the exports. Load them in the same command as the commit — a separate
shell would lose them:

```bash
eval "$(agentkit commit-safe env)" && \
git commit -m "<subject matching detected repo style>" \
  -m "[Optional 1-line overview explaining intent]" \
  -m "- <Key change 1>" \
  -m "- <Key change 2>"
```

Repeat Steps 2–3 for each remaining atomic unit until the working tree is clean
— **unless the caller asked for exactly one unit**, in which case stop after the
first commit. Each unit gets its own freshly resolved timestamp, which is the
point: they advance by the real time that passed between them.

## Step 4: Verify

```bash
git log -n 1 --format=fuller
git status
```

## Note for headless runs

Under the Antigravity CLI this skill needs `command(agentkit)` and
`command(eval)` granted; `/handoff-commit-safe` deliberately grants neither.
That handoff resolves the timestamp on the calling side and delegates plain
`/git-commit` instead, so nothing here runs inside `agy` during a handoff.
