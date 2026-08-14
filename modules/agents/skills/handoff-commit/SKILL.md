---
name: handoff-commit
description: >-
  Delegates the whole commit workflow to the Antigravity CLI (agy). Invoke ONLY
  when the user explicitly runs /handoff-commit. Never trigger it on your own
  from a general request to commit — handing work to another agent is the user's
  call, not an inference.
allowed-tools: Bash(agentkit:*), Bash(git status:*), Bash(git log:*)
---

# Handoff Commit

Delegates committing to the Antigravity CLI (`agy`), which runs the `git-commit`
skill headlessly and creates the commits itself.

[handoff-commit-safe](../handoff-commit-safe/SKILL.md) is the same command with
`--safe`. Use this skill unless the user asked for the safe variant.

## Why this exists

The point of the handoff is to keep commit work off this session. This session
usually runs at high reasoning effort, which is wasted on commit messages and
slow. `agy` is cheaper and faster, and commit quality tolerates it.

**So do not do the commit work yourself.** Every bit of analysis performed here
cancels out the reason for delegating.

## Rules

- Do NOT read diffs, group changes, or draft commit messages. `agy` does all of it.
- Do NOT run `git add` or `git commit` yourself, before or after the handoff.
- Do NOT retry on failure. A failed handoff may have committed part of the work,
  and a blind retry risks duplicate or polluted commits. Report and stop.
- The handoff is synchronous and blocking. Make no other tool calls while it runs.

## Workflow

### Step 1: Run the handoff

One command, nothing before it:

```bash
agentkit handoff commit
```

It checks the working tree, calls `agy`, and verifies the result against git. It
takes roughly 20–60 seconds; allow longer for large diffs.

Options worth knowing, all with sane defaults:

- `--effort low|medium|high` — reasoning effort to ask `agy` for (default `low`)
- `--timeout 600s` — passed to `agy`'s own print timeout
- `--verbose` — also print `agy`'s narration

`agy`'s narration is suppressed on success by design: it restates the commit list
the command already derived from git, padded with absolute `file://` links, and
it is the unbounded part of the output. Failures and partial commits print it in
full. Do not pass `--verbose` unless you are debugging the handoff itself.

### Step 2: Report the result

Relay what the command printed. Do not re-verify with your own `git log`.

| Exit code | Meaning | What to report |
|---|---|---|
| 0 | Success, or nothing to commit | The commit hashes and subjects it listed |
| 1 | No commit was created | The cause line it printed, plus its suggested fix |
| 2 | Committed, but files remain uncommitted | The commits made *and* the leftover files |

Keep the report short: number of commits, each hash and subject, and any
remaining uncommitted files.

## Known constraints

- **Exit code 0 from `agy` means nothing.** Headless `agy` cannot prompt for tool
  permission, so it auto-denies, returns `"status":"SUCCESS"` with an empty
  response, and exits 0. The runner ignores that and checks whether HEAD moved
  instead. Never treat raw `agy` output as proof that a commit happened.
- **Permissions are required up front.** `agy` needs `command(git add)`,
  `command(git commit)` and `command(git ls-files)`. Grant them with
  `agentkit agy grant`; check with `agentkit agy check`. The runner refuses to
  start without them.
- **Quota.** Each handoff spends Antigravity quota on a five-hour rolling limit.
  Keep it user-triggered; do not put it in a loop or on a schedule.
- Verified against `agy` 1.1.12. Re-test after a CLI update.
