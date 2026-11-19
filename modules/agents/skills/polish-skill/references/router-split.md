# Router Split

`SKILL.md` holds what every run needs; references hold what only some runs need.
Aim for about 75-80% of the size budget named in step 5 of `SKILL.md`. Never
split an inseparable procedure to reach it.

## What stays in SKILL.md

- Purpose and input.
- Constraints that apply on every run, including safety and scope boundaries.
- Gotchas.
- The procedure and its branches.
- Completion criteria and the output contract.

## What moves to a reference

- Recovery procedures for failures.
- Host- or tool-specific steps.
- One stage's detailed schema or format.
- Rare or long examples.

## Method

1. Move conditional content first, one file per situation, named for it:
   `references/recovery.md`.
2. Leave `SKILL.md` as a router: purpose, shared constraints, procedure with
   branches, and reference links.
3. Remove repeated explanation, long background, and overlapping examples found
   while moving.
4. Apply the same steps to an oversized reference.

## Rules

- Do not tell the agent to read every reference up front.
- Fold a reference of only a few lines back into `SKILL.md`.
- After moving content, delete it from its source.
- Do not shrink a file by joining lines, dropping completion criteria, or
  deleting examples the procedure depends on.
- If a file must stay over budget (one procedure always read whole, a quoted
  external protocol), leave it and give the reason in the report.
