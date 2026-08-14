# 1. Delegate commit workflows to the Antigravity CLI

- **Date**: 2026-08-14
- **Status**: Accepted
- **Verified against**: `agy` 1.1.12

## Context

Commits in this environment are written by Antigravity (`agy`), not by the
session doing the actual work. Until now that meant opening a second terminal,
starting `agy`, and typing `/git-commit` by hand.

Claude Code and Codex sessions typically run at high reasoning effort. Commit
messages do not need that, and paying for it is both slow and wasteful. The goal
is a single explicit command in the working session that hands the whole commit
workflow to `agy` and reports back.

This is also a testbed. If handing work to another agent proves reliable here —
where the source of truth is git and the task is small — the same shape can carry
larger delegations later.

## Decision

Ship two skills, `handoff-commit` and `handoff-commit-safe`, each a thin wrapper
around a script that calls `agy -p` once and verifies the outcome against git.

### The requesting session performs no commit work

The skills forbid reading diffs, grouping changes, or drafting messages. Any
analysis done in the requesting session cancels out the reason for delegating.
Its only jobs are running one script and relaying the result.

### Narrow permission grants, never `--dangerously-skip-permissions`

Headless `agy` cannot prompt, so any command outside `permissions.allow` in
`~/.gemini/antigravity-cli/settings.json` is auto-denied. The handoff requires
exactly six read/write git rules:

```
command(git log)   command(git diff)     command(git status)
command(git add)   command(git commit)   command(git ls-files)
```

`git ls-files` is how the agent enumerates untracked files; without it any
repository containing an untracked path stalls. `scripts/setup-permissions.sh`
grants the write rules, and both runners refuse to start if they are missing —
failing before the call rather than after a wasted round trip.

`command(git reset)` is deliberately **not** granted. The agent reaches for
`git add -N <path> && git diff <path> && git reset <path>` to inspect untracked
files, but a prefix rule for `git reset` would also permit `git reset --hard`.
The runners instead instruct it to stage the file and use `git diff --cached`.

### Trust HEAD movement, never the exit code

See "Verified CLI behaviour" below: a fully denied run still exits 0 and reports
`"status":"SUCCESS"`. Every run snapshots HEAD first and compares afterwards.
Nothing else is treated as evidence that a commit happened.

### Failures are reported, never retried

A failed handoff may have committed part of the work. The runners stop, leave
what exists in place, and report. Deciding whether to retry belongs to the user.

### The safe variant calls `agy` once per atomic unit

`handoff-commit-safe` keeps the `git-commit-safe` guarantees on the calling side:
it checks the email whitelist and resolves the timestamp locally, then exports
`GIT_AUTHOR_DATE` / `GIT_COMMITTER_DATE` so `agy` only runs a plain `git commit`.

Environment variables are fixed once a process starts, so a single call covering
three commits would stamp all three identically and destroy the natural time
progression that skill exists to produce. One call per unit resolves a fresh
timestamp each time. The cost is real: two commits take ~24s batched versus
~104s split.

Doing the whitelist check locally also means a rejected identity aborts before
any quota is spent, and enforcement never depends on a model choosing to run it.

### Explicit invocation only

The skill descriptions instruct against autonomous triggering. Handing work to
another agent is the user's call, not an inference from "commit this".

### `agy`'s narration is dropped on success

It restates the commit list the runner already derived from git, padded with
absolute `file://` links, and it is the unbounded part of the output — 472 of 659
bytes for a single commit. The caller is an agent paying per token. Failures and
partial commits print it in full, where it is the only diagnostic available.
`HANDOFF_VERBOSE=1` restores it.

## Alternatives considered

**MCP wrapper exposing `agy` as a native tool.** Closest thing to registering
Gemini as a first-class subagent, and reusable for future handoffs. Rejected for
now: it is the same CLI behind the same auth, so it carries identical terms-of-
service exposure, while making it easy for the model to invoke `agy` repeatedly
on its own. A user-triggered skill keeps call volume visible and bounded.

**A real Claude Code subagent.** Not possible. Subagent `model:` accepts Claude
tiers or `inherit`; there is no hook for an external CLI runtime.

**Splitting the work — `agy` proposes, the caller commits.** Rejected. It
reintroduces the reasoning cost in the expensive session, which is the entire
thing being avoided.

**`--dangerously-skip-permissions`.** Rejected. Auto-approves every tool call
including arbitrary shell commands, which is far past what committing needs.

**A PATH wrapper (`git-safe-stamp`) resolving a timestamp per commit.** Would
have preserved timestamp progression in one `agy` call. Rejected as unnecessary
once `git-commit-safe` was taught to honour pre-set dates — modifying our own
skill beat installing a new binary.

## Consequences

- Committing now depends on a Google product, its auth cache, and its quota.
  Any of the three failing blocks the handoff; all three fail loudly.
- Antigravity's [additional terms](https://antigravity.google/terms) §6 bar
  "using the Service in connection with products not provided by us". The named
  example targets third-party clients using Antigravity OAuth directly, which is
  not this — we invoke Google's own binary in its documented `-p` mode — but the
  clause is broad enough to cover a Claude-to-`agy` pipeline if read strictly.
  The account here is `oauth-personal`, so exposure lands on that account, most
  plausibly as rate limiting. Mitigation is to keep the handoff user-triggered:
  no retry loops, no fan-out, no scheduling.
- Each handoff spends quota on a five-hour rolling limit; the safe variant spends
  per atomic unit.
- Grants are global. Any headless `agy` run can now stage and commit in any
  repository it is launched from, not just these skills.
- `git-commit` and `git-commit-safe` now carry handoff clauses, so they must stay
  in sync with the runners.

## Verified CLI behaviour

Findings that cost real time to discover. Re-check after an `agy` upgrade.

**A denied run looks like a successful one.** Headless mode soft-denies and
finishes cleanly:

```json
{"status":"SUCCESS","response":"","duration_seconds":4.83,"num_turns":1}
```

with exit code 0. Neither the exit code nor the JSON status carries signal.

**`--add-dir` is mandatory.** `run_command` does not inherit the directory `agy`
was launched from; it resolves a workspace from the CLI's own project list and
will operate in whatever repository it used last. During testing this surfaced
another project's `git status`. With commit rules granted, that means commits in
the wrong repository. Always pass
`--add-dir "$(git rev-parse --show-toplevel)"`.

**Permission rules are command prefixes, checked per `&&` segment.**
`command(git log)` matches `git log -n 5 --oneline`, and
`git log … && git status -s` passes when both halves are granted. One denied
segment kills the whole chain. An environment-variable prefix
(`GIT_AUTHOR_DATE="…" git commit …`) does not match `command(git commit)`.

**A denial makes the agent abandon the task**, not route around it. The runner
prompts state which commands exist and that a denial is not a reason to stop.

**`--log-file` is the only way to see what was denied.** stdout says only that
"a tool required the command permission"; the log names it:

```
permission check failed for command "git ls-files --others --exclude-standard"
```

Both runners pin the log to a temp file and print the extracted command, which
is what separates "nothing was ever granted" from "one rule is missing".

**Expired credentials block for a fixed 60 seconds**, independent of
`--print-timeout`, then fail with `authentication failed or timed out`. Closing
stdin does not help — it is a callback poll, not a stdin read.

**`--print-timeout` kills the agent.** No work continues in the background after
it fires, so there is no race where a commit lands after verification. Commits
made before the deadline survive and are reported.

**Non-TTY output is fine.** Pipes and subprocesses both work; the reported issue
about `-p` dropping stdout off a TTY does not reproduce on 1.1.12.

**Settings live in `~/.gemini/antigravity-cli/settings.json`** — not
`~/.gemini/settings.json`, and project-local `.gemini/settings.json` is ignored.
`agy -p "/permissions"` and `agy -p "/config"` print the merged view without
spending quota.