# 10. Use native subagent profiles for explicit commit delegation

- **Date**: 2026-09-13
- **Status**: Accepted
- **Extends**: [0001](./0001-delegate-commits-to-antigravity-cli.md) and
  [0002](./0002-consolidate-the-commit-skill-set.md)

## Context

The old `handoff-commit` delegated to the external Antigravity CLI. The new path
uses a native child agent that runs the existing `git-commit` workflow directly,
keeping commit-specific reasoning out of the parent session without a third CLI
or its global command grants.

The two supported hosts have different configuration models. Claude Code loads
custom subagents from Markdown files under `.claude/agents/` or
`~/.claude/agents/`; the definition chooses its model and preloaded skills.
Codex selects the child model at its native spawn call and has no matching
checked-in file registry. Treating either format as portable would make one
host silently ignore the important model choice.

## Decision

Create `modules/agents/subagents/<role>/` as the repository's role source of
truth. A role owns a portable contract and provider adapters. The first role is
`commit`:

```text
modules/agents/subagents/commit/
  README.md                         portable authority and completion contract
  codex/README.md                   Codex spawn contract (gpt-5.6-luna)
  codex/handoff-commit/SKILL.md     Codex-only sender skill
  claude/agentkit-commit.md         Claude Code adapter (Sonnet, medium effort)
  claude/handoff-commit/SKILL.md    Claude-only sender skill
```

The subagent runs in the parent's shared checkout. Commit delegation is one
writer at a time: the parent does no git work while the child is active. The
child invokes `git-commit` directly and reports hashes, verification state, and
remaining paths. It cannot delegate again, reset, amend unrelated work, change
policy, or bypass a guard.

`modules/agents/subagents/install.sh` installs the Claude profile as a symlink
under `~/.claude/agents/agentkit/`, the Claude sender under
`~/.claude/skills/`, and the Codex sender under `~/.codex/skills/`. Codex has
its own source adapter at `commit/codex/README.md` because model selection
happens through its native spawn call.

The user-facing `handoff-commit` name now belongs to the native route. The
established Antigravity command stays only as undocumented CLI compatibility
during rollout. The two mechanisms must never run against the same working tree
at the same time.

## Consequences

- The native path removes Antigravity quota, authentication, and global `agy`
  command-permission dependencies for commits.
- Commit quality and policy enforcement now depend on the child loading the
  same `git-commit` skill and repository instructions; both adapters preload or
  explicitly require it.
- Claude Code can discover the definition only after its agents directory
  exists. A session started before first installation needs one restart.
- Codex's child-model setting is intentionally visible in a skill, not hidden
  in a machine-local file. Updating it requires an ADR amendment and a review
  of cost/quality behavior.
