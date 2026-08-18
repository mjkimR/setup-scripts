# handoff

Compacts the current session into a portable handoff document that a fresh
agent (claude, codex, or antigravity) can pick up. Document generation only —
invoking the receiving harness is out of scope (planned as
`agentkit handoff work`).

## Attribution

Derived from the `handoff` skill in
[mattpocock/skills](https://github.com/mattpocock/skills)
(`skills/productivity/handoff`, MIT license).

Kept from the original:

- No duplication of existing artifacts — reference specs/plans/ADRs/commits by
  path or URL
- Secret/PII redaction
- "Suggested skills" section for the next agent
- Argument-driven tailoring ("what will the next session be used for?")
- User-invoked only (`disable-model-invocation: true`)

Adapted for the agentkit workflow:

- Storage: OS temp dir → the shared scratch space via
  `agentkit scratch path handoff` (default `.agents/tmp/handoff/`). Durable
  across harness switches, visible in the IDE project tree (unlike anything
  under `.git/`, which IDEs hide), and kept out of `git status` via
  `.git/info/exclude` so it never pollutes the `handoff-commit` whitelist.
  See ADR 0003 for the scratch-space design.
- Argument also names the receiving harness; Claude-only sections are dropped
  for codex/antigravity
- Fixed 9-section structure with a 50–100 line budget (formalization inspired
  by [alirezarezvani/claude-skills](https://github.com/alirezarezvani/claude-skills));
  mandatory "Failed approaches" section and expected-outcome verification steps
  (inspired by [willseltzer/claude-handoff](https://github.com/willseltzer/claude-handoff))
