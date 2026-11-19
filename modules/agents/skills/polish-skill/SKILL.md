---
name: polish-skill
description: >-
  Reviews a drafted agent skill and polishes its trigger description, wording,
  and router structure without changing its behavior. Use only when the user
  explicitly invokes /polish-skill or $polish-skill.
disable-model-invocation: true
---

# Polish Skill

A first-draft skill is written in one pass by the session that designed it,
before anyone has watched an agent run it. It carries that session's residue:
background the agent already knows, design history, emphasis, and content every
run loads but few runs need. Remove the residue and keep the behavior.

## Input

Take one or more skill directory paths. Without a path, polish the skill created
or edited in this conversation. If more than one skill qualifies, or none does,
ask. With several paths, run steps 1-8 separately for each skill and report
each separately.

## Constraints

- Preserve behavior: every directive, safety or scope boundary, completion
  criterion, output contract, and example the procedure depends on survives,
  rewritten or moved but not lost.
- Treat a behavior change as a redesign: report it as a proposal and leave it
  unapplied.
- Modify files only inside the skill directory; scratch copies (snapshot,
  inventory) go in a scratch location.
- When the frontmatter `description` changes, keep any description in
  `meta.yaml` or `agents/openai.yaml` consistent with it.
- If the skill needs no change, report it as clean instead of inventing edits.
- If the repository holding the skill has its own authoring guide or checks,
  follow them where they differ from this skill.

## Procedure

Paths below are resolved from the directory of this `SKILL.md`, not the working
directory. "Markdown files" means every `.md` file in the target skill.
`<scratch>` is the absolute directory printed by
`agentkit scratch path polish-skill`; if that command is unavailable or fails,
use a temporary directory outside the repository from `mktemp -d`.

1. Baseline.
   - Copy the skill directory to `<scratch>/<skill-name>/snapshot/`.
   - Record sizes with
     `find <skill-dir> -type f -name '*.md' -exec wc -c -l -w {} +`.
   - Write `<scratch>/<skill-name>/inventory.md`: one line per directive,
     boundary, completion criterion, output contract, and needed example, with
     its file and section.
   - If the skill's job does not fit in one sentence, stop and report
     `Outcome: needs redesign`, the sizes, and the competing jobs.
2. Critique in fresh context. If the host can spawn a subagent, delegate the
   critique to a fresh one every run. Pass the absolute paths of the target
   skill, [roles/critic.md](roles/critic.md), and
   [review-checklist.md](references/review-checklist.md), and tell it to follow
   `roles/critic.md` as its contract. Give it the files, not your own
   conclusions. Without subagents, critique the skill yourself as
   the agent that will run it, using the checklist and the findings format in
   `roles/critic.md`. Triage each finding: apply it in steps 3-5, reject it with
   a one-line reason, or report it as a proposed behavior change.
3. Trigger pass. Check the frontmatter against the Trigger section of
   [review-checklist.md](references/review-checklist.md) and fix each item it
   fails. Done when every Trigger item holds.
4. Bloat and wording pass. Apply the rest of the checklist to every Markdown
   file. Done when each line meets the checklist or is listed for the report
   with its reason.
5. Structure pass. When any Markdown file exceeds the size budget (the
   repository's, otherwise about 500 lines or 12 KiB), or `SKILL.md` mixes
   content every run needs with content only some runs need, read
   [router-split.md](references/router-split.md) and restructure by it. Done
   when every file is within budget or its overrun has a reason for the report.
6. Verify, in this order.
   - If the first critique had `must` findings, run one re-critique on the
     edited skill and triage it the same way. Do not run a third round.
   - Map every line of `<scratch>/<skill-name>/inventory.md` to its new
     location; restore any item that has none.
   - List relative links with
     `rg -on --no-heading '\]\(([^)#:]+\.md)' -r '$1' <skill-dir>` and confirm
     each target exists relative to the linking file. Every reference is linked
     from `SKILL.md` with a read condition.
   - The frontmatter limits in the Trigger section hold.
   - If the repository has checks for skills or Markdown, run them and fix what
     they report until they pass.
7. Behavior check. When the description or procedure changed materially, the
   skill is high-stakes (destructive, publishing, or credential-handling), a
   line was kept as unsure under the cut test, or the user asks, read
   [behavior-check.md](references/behavior-check.md) and run it against
   `<scratch>/<skill-name>/snapshot/` and the inventory.
8. Report:
   - `Outcome: polished / clean / needs redesign`
   - Sizes before and after, from the step 1 command.
   - Changes grouped by pass.
   - `Critique: independent | not independent; applied N, rejected M,
     proposed K` (totals across both rounds; independent means it ran in a
     fresh subagent), followed by each rejection's reason.
   - Proposed behavior changes, not applied.
   - Items left as-is, each with its reason, including lines kept as unsure.
   - Checks and behavior check run, with results, or why they were skipped.
