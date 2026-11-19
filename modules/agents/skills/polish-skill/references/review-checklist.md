# Review Checklist

Each item names a defect and its fix. Apply the cut test to every line: would
the agent get this wrong without it? If no, cut it. If unsure, keep it and list it
in the report under items left as-is.

## Trigger

- The description says what the skill does and when to use it, in the words a
  user or agent would type, in the third person.
- Remove any summary of the procedure from the description. An agent that finds
  the steps there follows them and skips the body.
- Name the concrete contexts and phrasings that trigger the skill; drafted
  descriptions undertrigger. For an explicit-invocation-only skill, keep the
  restriction sentence instead.
- Delete a "When to use" section from the body. The body loads only after the
  skill triggers, so trigger information belongs in the description.
- `name` is 1-64 characters of lowercase letters, digits, and hyphens and
  matches the directory name. `description` is 1-1024 characters.

## Cut

- Explanation of what the model already knows: general programming, standard
  tools, common formats.
- Generic advice such as "handle errors appropriately" or "be thorough". Replace
  it with the specific condition and action, or delete it.
- Narrative from the authoring session: how the design was reached, earlier
  versions, "we decided".
- Options the design rejected.
- Edge cases the agent handles correctly unaided. Keep gotchas it would get
  wrong.
- A line written for one observed run. Rewrite it to address the general cause,
  or cut it.
- Duplication: each fact lives in `SKILL.md` or in one reference, never both.
- README, changelog, or creation-history files inside the skill directory.
- Overlapping examples. Keep one excellent example per pattern.
- Prose that re-implements a deterministic, repeated, or regex-checkable step.
  Propose a script or validator in the report. Where the skill ships a script,
  say whether the agent runs it or reads it.

## Wording

- Write one imperative directive per line or list item, condition first: "If
  `plan.md` is missing, create it."
- Pair each prohibition with its alternative when one exists.
- Replace hedges (`might`, `consider`, `probably`) with the condition under
  which the directive applies.
- Replace emphasis (`ALWAYS`, `NEVER`, `CRITICAL` in capitals, bold used for
  force) with ordinary case; emphasis makes models over-apply a directive. Keep
  the rule itself firm.
- Give a reason in one clause only when it changes how the agent applies the
  rule.
- Replace exemption clauses ("unless it matters", "where appropriate") with an
  explicit condition, or drop them; they do not scope anything.
- Use one term per concept. A synonym reads as a different concept.
- Replace time-relative words (`recently`, `currently`, "the new API") with a
  version or date, or drop them.
- Name exact identifiers: commands with flags, paths, tool names.
- Keep argument placeholders (`$ARGUMENTS`, `$0`, `$1`, ...) out of `SKILL.md`
  except where the skill means to receive arguments. Hosts substitute them at
  load time, so a shell or regex `$1` breaks whenever the skill is invoked with
  arguments. Rewrite the command without the token (`rg -o` instead of
  `rg -r '$1'`), or move it to a reference or script.

## Form

Match each instruction's form to the failure it prevents.

| Failure | Form |
| --- | --- |
| Discipline that breaks under pressure: skipped checks, scope creep | Firm rule or prohibition with its alternative |
| Wrong output shape | Positive recipe, template, or example; prohibitions backfire here |
| A missing element in the output | Required slot in the template |
| Fragile, order-sensitive, or destructive step | Exact command, no alternatives |
| Context-dependent judgment | Criteria and heuristics |

- Replace a menu of equal options with one default and the condition for its
  exception.

## Structure

- Procedure steps are numbered and end with completion criteria the agent can
  check: a command and its expected result, a file state, or an output line.
- References are one level deep; no reference sends the agent to another.
- Every pointer to a reference states when to read it.
- Gotchas stay in `SKILL.md`; the agent does not know to open a reference for
  them.
- A reference over 100 lines starts with a table of contents; a very large one
  also gives search patterns for its sections.
