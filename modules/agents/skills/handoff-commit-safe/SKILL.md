---
name: handoff-commit-safe
description: >-
  Delegates the commit workflow to the Antigravity CLI (agy) while enforcing the
  email whitelist and commit timestamp rules locally. Invoke ONLY when the user
  explicitly runs /handoff-commit-safe. Never trigger it on your own from a
  general request to commit — handing work to another agent is the user's call,
  not an inference.
allowed-tools: Bash(bash:*), Bash(git status:*), Bash(git log:*)
---

# Handoff Commit (Safe)

Same handoff as [handoff-commit](../handoff-commit/SKILL.md), with the
`git-commit-safe` guarantees kept on this side: the email whitelist is checked
and the commit timestamps are resolved locally, before `agy` is ever called.

## Why this exists

Commit work is delegated to `agy` because it is cheaper and faster than running
it at this session's reasoning effort, and commit quality tolerates it.

**So do not do the commit work yourself.** Every bit of analysis performed here
cancels out the reason for delegating.

The safety checks are the one exception, and they are already handled by the
script — you do not run them either.

## Rules

- Do NOT read diffs, group changes, or draft commit messages. `agy` does all of it.
- Do NOT run `git add` or `git commit` yourself, before or after the handoff.
- Do NOT retry on failure. Earlier units may already be committed, so a blind
  retry risks duplicate commits. Report and stop.
- Do NOT work around a whitelist rejection. An aborted run means the current
  `git config user.email` is not authorised — report it and let the user decide.
- The handoff is synchronous and blocking. Make no other tool calls while it runs.

## Workflow

### Step 1: Run the handoff

One command, nothing before it:

```bash
bash ~/.claude/skills/handoff-commit-safe/scripts/handoff-agy.sh
```

On Codex the skill installs elsewhere:

```bash
bash ~/.codex/skills/handoff-commit-safe/scripts/handoff-agy.sh
```

The script calls `agy` once per atomic unit, so a split into three commits takes
three round trips — roughly 20–60 seconds each.

Environment variables that tune it:

- `HANDOFF_AGY_EFFORT` — `low` (default), `medium`, or `high`
- `HANDOFF_AGY_TIMEOUT` — Go duration, default `600s`
- `HANDOFF_MAX_UNITS` — loop guard, default `10`

`agy`'s own narration is printed only when a unit fails. On success the script
reports the commit list it derived from git instead, which is authoritative and
far shorter.

### Step 2: Report the result

Relay what the script printed, including the timestamp of each commit. Do not
re-verify with your own `git log`.

| Exit code | Meaning | What to report |
|---|---|---|
| 0 | Success, or nothing to commit | Each commit's hash, timestamp, and subject |
| 1 | A unit produced no commit | The cause line and its suggested fix, plus any commits already made |
| 2 | Hit the `HANDOFF_MAX_UNITS` guard | The commits made and the files still pending |

A non-zero exit from the whitelist check also surfaces here — report the
rejected email verbatim.

## Why one `agy` call per unit

Environment variables are fixed once a process starts. A single `agy` call
covering three commits would stamp all three with the identical timestamp,
which defeats the natural progression `git-commit-safe` exists to produce. One
call per unit gets a freshly resolved timestamp each time.

## Known constraints

- **Exit code 0 from `agy` means nothing.** Headless `agy` cannot prompt for tool
  permission, so it auto-denies, returns `"status":"SUCCESS"` with an empty
  response, and exits 0. The script ignores that and checks whether HEAD moved.
- **Permissions are required up front.** `agy` needs `command(git add)` and
  `command(git commit)` in `~/.gemini/antigravity-cli/settings.json`. Grant them
  with `bash ~/.claude/skills/handoff-commit/scripts/setup-permissions.sh`.
- **Config is required.** `~/.config/git-commit-safe/config.yaml` must exist and
  list the current git email. See
  [the onboarding guide](../git-commit-safe/references/onboard.md).
- **Quota.** One handoff spends Antigravity quota per atomic unit, on a five-hour
  rolling limit. Keep it user-triggered; do not put it in a loop or on a schedule.
- Verified against `agy` 1.1.12. Re-test after a CLI update.
