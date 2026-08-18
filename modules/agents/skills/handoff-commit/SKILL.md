---
name: handoff-commit
description: >-
  Delegates the commit workflow to the Antigravity CLI (agy). Use when requested
  via /handoff-commit or when committing changes with user confirmation.
allowed-tools: Bash(agentkit:*), Bash(git status:*), Bash(git log:*)
---

# Handoff Commit

Delegates committing to the Antigravity CLI (`agy`), which runs the `git-commit`
skill headlessly and creates the commits itself.

Repository settings (whitelist, timeline, template, language) configured in
`.git/agentkit-commit.json` are automatically respected.

## Why this exists

The point of the handoff is to keep commit work off this session. This session
usually runs at high reasoning effort, which is wasted on commit messages and
slow. `agy` is cheaper and faster, and commit quality tolerates it.

**So do not do the commit work yourself.** Every bit of analysis performed here
cancels out the reason for delegating.

## Rules

- Do NOT read diffs, group changes, or draft commit messages. `agy` does all of
  it. The one sanctioned exception is `--hint`, written purely from what this
  session already remembers of the work — never from new analysis.
- Do NOT run `git add` or `git commit` yourself, before or after the handoff.
- Do NOT decide for yourself whether to retry. A failed handoff may have
  committed part of the work, and a blind retry risks duplicate or polluted
  commits. The `[ACTION]` line states whether a retry is authorized; follow it.
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

- `--effort low|medium|high` — reasoning effort to ask `agy` for (default `medium`)
- `--timeout 600s` — passed to `agy`'s own print timeout
- `--verbose` — also print `agy`'s narration

Two more options carry what only this session knows. Both are optional — skip
them rather than doing any work to fill them in:

- `--hint "<one line>"` — repeatable, one per intended commit, in order. A
  subject-sized label for one unit of the work just done, written from memory.
  Do not read diffs or `git status` to compose hints, and do not polish them:
  `agy` treats them as advisory against the actual diff and writes the real
  subjects itself, following the repo conventions. No clear picture of the
  split? Pass no hints.
- `--tests passed|failed|not-run` — attest the test-suite state of exactly the
  tree being handed off, so `agy` neither runs nor speculates about tests.
  Claim `passed` only if the commands ran after the last edit to the tree; if
  anything changed since, or you are unsure, say `not-run`.

  The repo config may name what "verified" means here (`verify.test` /
  `verify.lint`, shown by `agentkit commit config`). Running those commands is
  part of finishing the work — if they have not run on this exact tree, run
  `agentkit commit verify` first (it echoes each command verbatim before
  running it, so the user sees exactly what executed) or attest `not-run`
  honestly; lint counts, not just tests. When the fields are empty, or the
  repo switched verification off (`verify.enabled=false` — e.g. tests
  known-broken and mid-repair), the topic is skipped entirely: attest nothing,
  run nothing. Omitting `--tests` while active verify commands exist prints a
  one-line reminder before the delegation; it never blocks.

Example — work that landed as an API change plus its docs, tests green:

```bash
agentkit handoff commit --tests passed \
  --hint "feat(api): add cursor pagination to /events" \
  --hint "docs: document the events cursor parameters"
```

`agy`'s narration is suppressed on success by design: it restates the commit list
the command already derived from git, padded with absolute `file://` links, and
it is the unbounded part of the output. Failures and partial commits print it in
full. Do not pass `--verbose` unless you are debugging the handoff itself.

### Step 2: Follow the directive, then report

On success, relay the commit hashes and subjects it listed. Do not re-verify
with your own `git log`.

On failure it prints a block that already states the directive in full. Do what
the `[ACTION]` line says and relay the `[REPORT]` line, which is written for the
user:

```
[handoff] [ERROR]  (QUOTA_EXHAUSTED) agy reported a usage limit.
[handoff] [ACTION] DEFER — Nothing is broken and nothing here is yours to fix.
                   Do not retry now. Report the cause and when it can be retried.
[handoff] [WHEN]   Not before: the Antigravity rolling quota window resets (up to 5h)
[handoff] [REPORT] Antigravity quota is exhausted; no commits were created. It will reset over time.
[handoff] [DETAIL] Nothing is misconfigured — the limit is time-based.
```

There is no table of modes here on purpose. The block is self-contained, so
treat it as the authority — if it ever contradicts this file, the block wins and
this file is stale.

One thing the block cannot know is what this skill is allowed to run: only
`agentkit …`, `git status` and `git log`. When a `[FIX]` command falls outside
that, hand it to the user instead of running it.

Exit codes carry the same news for anything reading only a number: `0` success
or nothing to commit, `1` nothing was committed, `2` committed with files left
over, `64` a malformed command line — which is a bug in this skill, so report it.

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
  Keep it user-triggered; do not put it in a loop or on a schedule. A spent
  quota comes back as `[ACTION] DEFER` — report it and leave the retry to the
  user, because retrying is exactly what runs the limit down further.
- Verified against `agy` 1.1.12. Re-test after a CLI update.
