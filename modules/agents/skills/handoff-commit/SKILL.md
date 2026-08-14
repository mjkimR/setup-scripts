---
name: handoff-commit
description: >-
  Delegates the whole commit workflow to the Antigravity CLI (agy). Invoke ONLY
  when the user explicitly runs /handoff-commit. Never trigger it on your own
  from a general request to commit — handing work to another agent is the user's
  call, not an inference.
allowed-tools: Bash(bash:*), Bash(git status:*), Bash(git log:*)
---

# Handoff Commit

Delegates committing to the Antigravity CLI (`agy`), which runs the `git-commit`
skill headlessly and creates the commits itself.

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
bash ~/.claude/skills/handoff-commit/scripts/handoff-agy.sh
```

On Codex the skill installs elsewhere:

```bash
bash ~/.codex/skills/handoff-commit/scripts/handoff-agy.sh
```

The script checks the working tree, calls `agy`, and verifies the result. It
takes roughly 20–60 seconds; allow longer for large diffs.

Environment variables that tune it:

- `HANDOFF_AGY_EFFORT` — `low` (default), `medium`, or `high`
- `HANDOFF_AGY_TIMEOUT` — Go duration, default `600s`
- `HANDOFF_VERBOSE` — set to any value to also print `agy`'s own narration

`agy`'s narration is suppressed on success by design: it restates the commit
list the script already derived from git, padded with absolute `file://` links,
and it is the unbounded part of the output. Failures and partial commits print
it in full. Do not set `HANDOFF_VERBOSE` unless you are debugging the handoff
itself.

### Step 2: Report the result

Relay what the script printed. Do not re-verify with your own `git log`.

| Exit code | Meaning | What to report |
|---|---|---|
| 0 | Success, or nothing to commit | The commit hashes and subjects the script listed |
| 1 | No commit was created | The cause line the script printed, plus its suggested fix |
| 2 | Committed, but files remain uncommitted | The commits made *and* the leftover files |

Keep the report short: number of commits, each hash and subject, and any
remaining uncommitted files.

## Known constraints

- **Exit code 0 from `agy` means nothing.** Headless `agy` cannot prompt for tool
  permission, so it auto-denies, returns `"status":"SUCCESS"` with an empty
  response, and exits 0. The script ignores that and checks whether HEAD moved
  instead. Never treat raw `agy` output as proof that a commit happened.
- **Permissions are required up front.** `agy` needs `command(git add)` and
  `command(git commit)` in `~/.gemini/antigravity-cli/settings.json`. Grant them
  with `bash ~/.claude/skills/handoff-commit/scripts/setup-permissions.sh`.
- **Quota.** Each handoff spends Antigravity quota on a five-hour rolling limit.
  Keep it user-triggered; do not put it in a loop or on a schedule.
- Verified against `agy` 1.1.12. Re-test after a CLI update.
