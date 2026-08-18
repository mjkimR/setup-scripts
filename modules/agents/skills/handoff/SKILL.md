---
name: handoff
description: >-
  Compact the current session into a handoff document a fresh agent (agy,
  codex, or claude) can pick up, then optionally run the receiver. Use only
  when requested via /handoff.
argument-hint: "What will the next session do, and where (agy/codex/claude)? Append 'auto' to skip confirmation."
disable-model-invocation: true
allowed-tools: Bash(agentkit:*), Bash(date:*), Bash(git status:*), Bash(git log:*), Bash(git rev-parse:*), Bash(git diff:*)
---

# Handoff

Write a handoff document summarising the current session so a fresh agent can
continue the work without re-explaining anything — then, on confirmation, hand
it to that agent.

## Workflow

1. **Parse the argument** for three things: what the next session will do,
   the target (`agy`, `codex`, or `claude`), and the keyword `auto`.
   Recommended defaults for anything unstated: target `agy`, effort `high`.
2. **Without `auto`**: ask the user before writing (the document is tailored
   to its reader) — one question covering:
   - **How to run it** — *run here now* (headless `handoff work`; recommend
     for a small, single-topic handoff that fits the ~30m timeout) vs *hand
     me the prompt* (the user pastes it into their own interactive
     agy/codex/claude session; recommend for long or heavy work — no timeout,
     and they can watch it) vs *document only*.
   - **Target**, when unstated: agy (recommended), codex, or claude.
   - **Effort**, for headless runs: high recommended; low, medium, or the
     receiver's default. Mention a model override only if the user brings it up.
3. **Write the document** (structure below) and, beside it, the progress file
   `<doc-stem>-progress.md`: one `- [ ] <n> <step>` line per numbered next
   step, nothing else. Writing it yourself — rather than leaving it to the
   receiver — means the checklist exists from the first second, so the user
   can watch it, and a receiver that never touches it shows up as all-empty
   boxes instead of a missing file. Show the user both absolute paths plus a
   3–5 line summary of what the document captures.
4. **Execute** per the chosen mode (`auto` → headless immediately with the
   stated or recommended values):

   ```bash
   agentkit handoff work --doc <path> [--to agy|codex] [--effort high] [--model <m>]
   ```

   Headless is synchronous; make no other tool calls while it runs. Tell the
   user they can follow along with `tail -f <doc-stem>-progress.md` in their
   own terminal — the receiver ticks a box per finished step. The
   timeout (default 30m) is a hard lifetime cap — the receiver is cut off
   mid-work when it expires — so pass `--timeout 1h` for a large handoff
   rather than hoping. Exit codes: 0 receiver finished, 1 it failed outright,
   2 it stopped part-way. A part-way run is resumable rather than lost: its
   edits are still in the working tree and the progress file says which steps
   completed, so handing the same document over again picks up from the first
   unticked step. Read the progress file and inspect that step's files before
   re-running — it is the one the receiver died inside, so it may be
   half-applied. A re-run is a new run: it needs the user's go-ahead like any
   other.

   For *hand me the prompt*, `claude` targets, and *document only*: print the
   output of `agentkit handoff prompt --doc <path>` for the user to paste,
   and ask them to report back when the run finishes.
5. **Close the loop.** The prompt tells the receiver to write a completion
   report to `<doc-stem>-result.md` next to the document; the handoff
   document itself stays untouched, and the progress file is a status view
   only — a `[x]` is what the receiver claimed, never proof, so never report
   an outcome on its strength alone. Headless: relay the receiver's closing
   summary and follow any `[ACTION]` directive. Prompt mode: when the user
   reports the run finished, read the completion report. Either way, finish
   by running the document's own verification commands and reporting the
   outcome — and if no report file exists, say so and verify from the
   working tree alone.

## Where to save

Run `agentkit scratch path handoff` — it prints an absolute directory, creating
and git-ignoring it on first use (default `.agents/tmp/handoff/`, visible in
the project tree, and it works outside git repositories too). Save the document
there as `<YYYY-MM-DD>-<slug>.md`, taking the date from `date +%Y-%m-%d`. Two
siblings join it, both derived from that name: `-progress.md` (live checklist,
written by you, ticked by the receiver) and `-result.md` (the completion
report, written once by the receiver at the end — its existence is what marks
the run finished, which is why progress never goes in it).

## Document structure

Target 50–100 lines. Sections, in order:

1. **Header** — date, repo, branch + HEAD SHA, uncommitted changes (yes/no + summary).
2. **Goal of the next session** — one paragraph. Readable alone, with an explicit success criterion.
3. **State of play** — done / in progress / broken. Name what works and what does not.
4. **Decisions** — settled ones with rationale; open ones with the user's current lean.
5. **Failed approaches** — what was tried and why it failed. Mandatory: write `None.` explicitly if empty. This is the most expensive context to lose.
6. **Files that matter** — path + one line on why each matters.
7. **Next steps** — ordered. The first action must be concrete enough to execute immediately. Include verification commands with their expected outcome.
8. **References** — specs, plans, ADRs, issues, PRs, commits, by path or URL.
9. **Suggested skills** — only when the receiving harness is claude: name skills the next agent should invoke. Omit for codex/agy.

## Rules

- Do not duplicate content already captured elsewhere — specs, plans, ADRs,
  issues, commits, diffs, `AGENTS.md`/`CLAUDE.md`. Reference by path or URL.
  The receiving harness reads `AGENTS.md` on its own; carry only session-delta.
- No vague claims. Not "improved" but "improved from X to Y"; not "mostly
  works" but which cases pass and which fail. Do not state beliefs as facts —
  mark anything the session did not actually verify as unverified.
- Redact secrets: API keys, tokens, passwords, PII.
- Re-read the document before finishing: a fresh agent must be able to act on
  it without asking the user to re-explain the setup.
- When the receiver is agy, every shell command the document asks it to run —
  verification steps included — must be covered by an existing grant: headless
  agy dies with an empty response (and no completion report) at its first
  denial, mid-run edits included. Check with `agentkit agy check`, add narrow
  rules with `agentkit agy grant --rule 'command(<prefix>)'` (with the user's
  consent), or keep those steps out of the document and run them yourself in
  step 5.
- Keep the progress checklist at the granularity of the document's numbered
  next steps — 4–6 lines. Finer than that and the receiver spends its run
  narrating instead of working.
- A handoff sized to the timeout is still the goal — resuming costs a whole
  second run. Split the work rather than relying on it.
- Ticking boxes needs the same file-edit permission the receiver already needs
  for the work and its completion report, so the progress file adds no failure
  mode of its own. It adds no signal of its own either: empty boxes may mean a
  denied edit, a receiver that batched its updates, or one that ignored the
  instruction. Judge the run by the completion report and the document's
  verification commands — never by the checkboxes.
- Never run `agentkit handoff work` without either the `auto` keyword or the
  user's explicit go-ahead from step 4.
