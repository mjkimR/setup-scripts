# 6. Delegate Korean copyediting to the Antigravity CLI

- **Date**: 2026-08-18
- **Status**: Accepted
- **Extends**: [0001](./0001-delegate-commits-to-antigravity-cli.md)

## Context

Korean documents drafted by Claude Code read as translationese: English
sentence structure wearing Korean words. A global-prompt rubric
(`~/.claude/CLAUDE.md`) did not fix it — the alignment that produces the
accent also judges it, so self-review passes it — and its effect on
generation was negligible. The correction has to come from outside the
session that wrote the text.

The commit handoff (0001) already established the machinery: a Claude-side
skill that refuses to do the work, an `agentkit` runner that invokes headless
`agy` and verifies the outcome from the world rather than from agy's exit
status, and an agy-side skill holding the actual workflow.

## Decision

### A polish handoff, shaped like the commit handoff

`agentkit handoff polish` targets the Markdown files changed against HEAD
(or `--base <ref>`), scoped to their changed regions; explicit paths — inside
the repository or not — are polished whole. The skill pair mirrors the commit
pair: `handoff-polish` (Claude/Codex, sender) delegates and relays;
`polish-doc` (Antigravity, receiver) holds the copyediting rubric — moved
there from the global prompt, where it was inert, to the one place a
dedicated pass actually applies it. The global prompt was then removed
entirely: a residual style instruction invites confusion about what governs,
so the sender runs unprompted and polishing happens only on explicit
request.

### Edits, not commits — and the receiver cannot touch the index

The outcome is working-tree edits. Committing stays with the existing commit
handoff, which keeps grants disjoint: the polish receiver gets file edits via
`agy --mode accept-edits` (verified against agy 1.1.12) plus read-only
`command(git diff)`, and nothing that writes to git.

### Rollback is arranged before the run, in the index

Uncommitted changes are the common polish input, so pre-polish state has no
commit to fall back to. The runner stages the targets first: afterwards
`git diff` shows exactly the polisher's delta (the review view), and
`git restore <file>` undoes exactly the polish while keeping the user's own
edits. Files git cannot restore — outside the repository, or ignored — are
copied into the scratch space (0003) instead. Denying the receiver `git add`
is what makes the staged state trustworthy.

### Verification: hashes first, then the receiver's marks

The runner hashes every target before and after and believes only that. But
"unchanged" is ambiguous — already-natural text is a legitimate no-op — so
the receiver must end its reply with one `POLISHED:`/`CLEAN:` line per
target. Unchanged and CLEAN is success; unchanged and unmarked (or marked
POLISHED) is a failure; changed files are polished regardless of what the
marks claim, with a warning on disagreement.

### No hooks, by decision

An automatic trigger (Claude Code hook or git pre-commit hook) was
considered and rejected: it would spend the five-hour rolling quota on every
edit of a document still being drafted, polish intermediate states whose
work the next edit discards, and — as a tree-mutating pre-commit hook —
collide with the commit handoff's leftover-files check (0005). The right
moment ("the document is done, before commit") is one only the user
recognizes, so the handoff stays user-triggered.

## Consequences

- The polish → review (`git diff`) → `/handoff-commit` sequence composes
  from existing pieces; nothing new is committed on the polish side.
- Staging collapses a target's staged/unstaged split if the user had one;
  the runner warns when it does. Markdown documents are rarely
  partial-staged, so this was accepted over a more elaborate snapshot
  scheme.
- The rubric now lives in a repo-tracked skill: it is versioned and
  editable, and tuning it no longer means editing a global prompt that
  applies to every conversation.
- `agentkit agy grant`'s default set gains `command(git diff)` — read-only,
  and already commonly granted.
- A second quota consumer exists. Both handoffs stay user-triggered; the
  constraint is documented in both sender skills.
