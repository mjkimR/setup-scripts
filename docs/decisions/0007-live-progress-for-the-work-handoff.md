# 7. A separate progress file for the work handoff

- **Date**: 2026-08-18
- **Status**: Accepted
- **Extends**: [0004](./0004-carry-caller-context-into-the-commit-handoff.md)

## Context

A headless work handoff (`agentkit handoff work`) is synchronous and can run
for half an hour. Until it returns, nobody — not the user, not the calling
agent — can see whether it is on step 1 or step 5. `agy`'s own narration is
captured, not streamed, and its `--log-file` is written into a
`TemporaryDirectory` that is deleted when the run ends. The only visible
artefact is the completion report, which by design does not exist until the
work is over.

The obvious fix — have the receiver write the completion report incrementally,
ticking items as it goes — breaks the completion contract. `_finish()` treats
the report's *existence* as the outcome signal, on the same principle as the
commit runner's HEAD check: trust the world, never the receiver's exit status
or its parting words. Marker-bearing failures (timeout, quota, permission wall)
are caught before that check, but the case `_finish` exists for — a receiver
that stops silently, which is exactly what headless `agy` does when it
soft-denies — would find the report already on disk and report `OK` for a
half-finished run.

Raw logs were considered and rejected as the primary answer: the requirement is
a per-task done/not-done view, not a transcript.

Invisibility is not the only cost. A headless run that dies at the timeout, on
quota, or at a permission wall leaves its edits in the working tree but takes
its bookkeeping with it — which steps it finished, where it was standing. The
caller is left diffing the tree to guess, and the cheapest way out looks like
starting over, which redoes work that is already on disk.

## Decision

Progress gets its own file, `<doc-stem>-progress.md`, beside the document:

- **The caller writes the skeleton**, at the same time as the handoff document
  — one `- [ ] <n> <step>` line per numbered next step. The checklist therefore
  exists from the first second, the plan is readable before the run starts, and
  a receiver that never touches it shows up as all-empty boxes rather than a
  missing file. The receiver only flips a character; it invents nothing.
- **The receiver ticks a box per finished step**, leaving blocked steps
  unchecked with a one-line reason appended. The pickup prompt states that
  updating the file is not a reply — the existing "reply exactly once"
  instruction ends the session, and the two must not be confused.
- **Granularity stops at the document's numbered next steps.** Per-file or
  per-edit updates cost tokens and turn the run into narration.
- **`-result.md` is untouched by all of this.** It is still written once, at
  the end, and its existence is still the only completion signal.
- **The file is a resume input, not only an output.** The pickup prompt has the
  receiver read it before starting and treat ticked steps as done — finished by
  an earlier run that did not survive to report — so handing the same document
  over again continues rather than restarts. Every advisory that reports partial
  work names the file and says resuming is possible — as information, not as a
  retry directive: those advisories are `Retry.UNSAFE`, so the caller still
  halts and reports, and the user decides whether to hand it over again.

The progress file is advisory. A `[x]` is what the receiver claimed, not
evidence; the verdict still comes from the document's verification commands,
run by the caller after the receiver returns.

## Consequences

Three files now share the document's stem — spec (immutable), progress (live),
result (terminal). The split is the point: each has exactly one writer and one
meaning, and no new failure mode is introduced, because ticking boxes needs the
same file-edit permission the receiver already needs for the work itself.

A part-way run is now recoverable at the cost of one re-run, which makes exit
code 2 a smaller event than it was. It does not make oversized handoffs free:
the resumed run pays for its own startup and re-reading, so sizing the work to
the timeout is still the goal.

Empty boxes are ambiguous — denied edit, batched updates, or an ignored
instruction — so they must never be read as a failure signal on their own. The
same ambiguity bounds resumption: an unticked step that was actually completed
gets done twice, which is why the prompt sends the receiver to inspect the
first unticked step's files rather than trusting the box.

The buried `agy` log remains buried. Persisting it would answer "why did it
stall", which this ADR does not address; it is a separate, still-open question.
