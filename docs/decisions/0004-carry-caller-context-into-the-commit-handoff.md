# 4. Carry caller context into the commit handoff

- **Date**: 2026-08-18
- **Status**: Accepted
- **Amends**: [0001](./0001-delegate-commits-to-antigravity-cli.md) — the
  "requesting session performs no commit work" rule gains one narrow,
  memory-only exception.

## Context

The commit handoff ([0001](./0001-delegate-commits-to-antigravity-cli.md))
deliberately tells the receiver nothing: `agy` sees only the diff. Two costs
showed up in practice:

- **Grouping quality.** The caller knows the intent behind the changes — it
  did the work minutes earlier — but none of that crosses the handoff. In
  `--safe` mode the problem is structural: each unit is a *fresh* `agy` call
  with no memory of how the previous call partitioned the tree, so the split
  can drift between units.
- **Duplicate test effort.** Work is normally handed off with the suite
  already green, yet the receiver has no way to know that. It cannot actually
  run tests (only six git commands are permitted), but it wastes turns trying,
  being denied, and hedging about it — and the interactive `/git-commit` path
  has no such guard at all.

Separately, splitting a large change into several commits kept raising two
questions the spec never answered: must intermediate commits stay green, and
may one file's changes be divided across commits?

## Decision

### Two optional flags on `agentkit handoff commit`

- `--hint "<one line>"`, repeatable: one subject-sized label per intended
  commit, in order. Validation checks shape only — non-empty, single line
  (one flag per unit) — and a failure is a usage error (exit 64), refused
  before any quota is spent. Length and count are deliberately **not**
  enforced: "subject-sized" is advice about the caller's own effort, and the
  receiver's quota is the cheap side of the handoff, so a long hint should
  pass through rather than fail the command.
- `--tests passed|failed|not-run`: an attestation about exactly the tree
  being handed off.

Both feed a "Caller context" block in the prompt that
`HandoffTask.prompt()` builds; omitted flags leave the prompt unchanged.

### Hints are advisory; the diff is ground truth

The caller writes hints **from memory of the work only** — reading diffs or
`git status` to compose them would spend the effort the handoff exists to
save, so the handoff-commit skill forbids it. Memory can lag the tree, so the
receiver resolves conflicts in the diff's favor: no empty or padded commits
to match the hint count, no change left uncommitted because no hint covers
it, and mismatches are reported rather than forced. Hints are grouping
labels, not subjects — the receiver writes every subject itself, to the
repository conventions (a hint may even be in the wrong language for the
repo). In `--safe` mode the prompt routes each fresh unit to "the first hint
whose work is still uncommitted", using `git log` as the shared state between
calls.

### The attestation is trusted, and bounded

`--tests passed` may be claimed only if the suite ran after the last edit to
the tree; anything changed since is `not-run`. The receiver trusts the claim
and never runs tests, builds, or linters itself; `failed` authorizes the
commit anyway (fixing tests is not the receiver's job), and the attestation
never appears in a commit message. The caller must not launch a test run
merely to fill the flag in.

### Two standing grouping rules, hints or not

Added to the `git-commit` skill and to every commit-handoff prompt:

- **A file is the smallest unit.** A file's entire change lands in exactly
  one commit of a split — no partial staging. This is also a tooling fact:
  `git add -p` is interactive and `git apply --cached` is not granted, so
  hunk-level staging cannot work headlessly anyway. A file carrying several
  concerns goes whole into the commit of its dominant concern (tie-break: the
  earliest commit that needs it), with the piggybacked change noted in that
  commit's body.
- **Intermediate commits may be red.** Only the final commit of a split must
  reproduce the tree as handed over; nothing is spent verifying or reordering
  for per-commit greenness. What matters is start → final state, and the
  receiver could not verify greenness with git-only permissions anyway.

The two rules reinforce each other: tolerating red intermediate commits is
what makes "never split a file" cheap, because a contested file's placement
no longer has to keep every intermediate state consistent.

## Consequences

- Bisectability inside a handoff's commit sequence is explicitly given up.
  Acceptable here; revisit before reusing this spec on a repo where
  `git bisect` matters.
- The trust boundary moves: a wrong `--tests passed` propagates unchecked,
  by design. The receiver's report cannot catch it; only the caller's
  discipline (attest only what ran on this exact tree) holds the line.
- 0001's "no commit work in the requesting session" survives in amended
  form: hints must come from memory, never from new analysis. If hint-writing
  is ever observed triggering diff reads, the flag should be removed rather
  than the rule relaxed.
- Hint syntax stays one line with no file annotations. If dominant-concern
  placement of contested files proves too coarse, per-hint file pinning is
  the designed extension point — not smarter prose in the prompt.
