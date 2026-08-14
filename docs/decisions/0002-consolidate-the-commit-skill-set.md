# 2. Move skill logic into one CLI, leave skills as documentation

- **Date**: 2026-08-14
- **Status**: Accepted
- **Amends**: [0001 — Delegate commit workflows to the Antigravity CLI](./0001-delegate-commits-to-antigravity-cli.md)

## Context

0001 shipped four skills — `git-commit`, `git-commit-safe`, `handoff-commit`,
`handoff-commit-safe` — as four independent directories, each carrying its own
scripts. Each `-safe` variant was written as a full copy of its base with the
safety parts added, which put the same content in two places three times over:

- The two `handoff-agy.sh` runners were 159 and 185 lines, of which roughly 120
  were identical: pre-flight, the permission-grant check, denied-command
  extraction, HEAD-movement verification, and failure diagnosis.
- The two handoff `SKILL.md` files repeated "why this exists", the rules against
  doing commit work locally, and the reporting table.
- `git-commit-safe/SKILL.md` restated the whole commit convention doctrine that
  `git-commit/SKILL.md` already carried.

0001 itself named the cost: *"`git-commit` and `git-commit-safe` now carry
handoff clauses, so they must stay in sync with the runners."*

Underneath the duplication was a worse problem: **a script inside a skill can
only be named by a path, and that path differs per agent.** `git-commit-safe`
hardcoded `~/.gemini/config/skills/...`; the handoff skills documented both
`~/.claude/...` and `~/.codex/...`; the safe runner reached sideways for
`$SCRIPT_DIR/../../git-commit-safe/scripts/resolve-time.py` with a fallback for
when that relative walk missed. Every one of those is the same bug waiting to
happen.

## Decision

### Skills are documentation. Logic lives in one CLI.

`tools/agentkit/`, installed with `uv tool install --editable`, holds everything
the skills need to *do*. The four skill directories now contain `SKILL.md`,
`meta.yaml` and references — no scripts at all.

```text
agentkit commit-safe init|verify|stamp|env    identity whitelist + timestamps
agentkit handoff commit [--safe]              delegate committing to agy
agentkit handoff tasks                        what can be handed off
agentkit agy check|grant                      the allow-list headless agy needs
agentkit git summary                          working tree overview
```

A `PATH` command has one name from everywhere, so the per-agent paths and the
cross-skill filesystem coupling are simply gone. Secondary gains:
`command(agentkit)` is a narrower Antigravity grant than the `command(bash)` a
script path required, and the commands are usable by hand without knowing any
skill exists.

One CLI rather than one per domain: the shared parts — the agy adapter, the git
helpers, the exit-code contract — are the bulk of the code, and a second entry
point would have meant either duplicating them or publishing a library nobody
imports. Adding a domain is adding a group under `commands/`.

`click` is a dependency, accepted deliberately: nested command groups in argparse
cost more lines than the domain logic they wrap.

### The handoff runner is generic; commits are a task

`handoff/runner.py` knows how to delegate and verify, and nothing about git
commits. A `HandoffTask` says what to ask for, which grants the ask needs, and
whether the runner should drive it one unit at a time; `handoff/tasks.py` holds
the two commit profiles. Adding a delegable job is one entry in that registry.

Everything 0001 decided about *how* the handoff behaves is unchanged, and now
lives in one place instead of two: `--add-dir` is mandatory, HEAD movement is the
only trusted signal, failures are reported rather than retried, and `agy`'s
narration is dropped on success.

### The safe handoff delegates `/git-commit`, not `/git-commit-safe`

`git-commit-safe` used to open with a "Handoff Mode" principle telling the model
to skip principles 1–3 and steps 1 and 4 when the dates were already in the
environment. What remained after those skips was `git-commit`, exactly.

So the safe task sends `/git-commit` with the dates exported, and the
handoff-mode branch is deleted rather than documented. `git-commit` already
carries the caller-constraint clause covering pre-set dates and single-unit runs.

`git-commit-safe` survives for interactive use under `agy`, reduced to the
pre-flight, the commit invocation, and a pointer to `git-commit` for everything
about splitting and wording commits.

### Flat skill directories, not plugin namespacing

Claude Code can namespace skills as `plugin:skill`: a directory in
`~/.claude/skills/<name>/` containing `.claude-plugin/plugin.json` auto-loads as
`<name>@skills-dir`, and nested `skills/<sub>/SKILL.md` files surface as
`<name>:<sub>`. This was verified directly, including through a symlink, which is
how this repository installs skills — so `/handoff-commit:safe` was available for
the taking.

Rejected anyway. Codex namespaces components too, but only through
`.codex-plugin/plugin.json` plus a marketplace entry, and Antigravity has no
plugin concept at all. Worse, the runner hands `agy` a literal `/git-commit`
string, so the Antigravity-side skills cannot be renamed without editing prompts.
Adopting namespacing would have meant one skill name on Claude Code and a
different one on the other two agents, to buy a colon.

### Tests live in the repository's root tree

`tests/tools/agentkit/` holds the pytest suite; `tests/agents/notify/` keeps the
existing shell suites; `tests/run-all.sh` runs everything and is the only entry
point anyone needs to remember. Test config sits with the tests
(`tests/tools/agentkit/pytest.ini`), not in the package manifest.

The handoff is covered end to end against a stub `agy` that records what it was
asked and commits according to a mode — cooperative, partial, permission-denied,
unauthenticated. That is the only way to test the property the runner exists for:
that a delegated run reporting success while doing nothing is caught.

## Consequences

- Committing now depends on `uv` and on `~/.local/bin` being on `PATH`. The
  skills module warns about both rather than failing the sync.
- `--editable` means the tool tracks the repository in place: moving or deleting
  the clone breaks the installed command.
- The skills are useless without the CLI. That is the trade for having them work
  identically across three agents, and every entry point says so.
- Environment overrides were renamed: `HANDOFF_AGY_EFFORT` → `--effort` or
  `AGENTKIT_AGY_EFFORT`, `HANDOFF_MAX_UNITS` → `--max-units`, `HANDOFF_VERBOSE` →
  `--verbose`, `SAFE_COMMIT_CONFIG` → `AGENTKIT_COMMIT_SAFE_CONFIG`.
- `agy`'s settings are now parsed as JSON rather than grepped, so a grant is
  recognised wherever it appears in either settings file.

## Fixed in passing

Three defects the consolidation surfaced, all present in the original
implementation:

- **The minimum commit gap never applied.** The check was `if target <= last`,
  but `target` is `last` plus the real time elapsed between the two calls, so any
  non-zero delay cleared it. Two commits a second apart formatted to the same
  timestamp — the exact collision `min_gap_seconds` exists to prevent. It is now
  `if target < last + min_gap_seconds`.
- **The first commit in an empty repository was reported as zero commits.**
  `git rev-parse HEAD` echoes the literal string `HEAD` to stdout on an unborn
  branch before failing, so the "no HEAD yet" branch never ran and the range
  became `HEAD..<sha>`, which is empty once HEAD has moved. Now
  `git rev-parse --verify --quiet HEAD`.
- **`verify` consumed a timestamp.** Checking advanced the day's sequence, so a
  pre-flight followed by a commit skipped a slot. The preview no longer persists.
