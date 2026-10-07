# 15. Deprecate commit subagents in favor of direct template-driven commits with commit-safe

- **Date**: 2026-10-07
- **Status**: Accepted
- **Supersedes**: [0010](./0010-native-commit-subagent-profiles.md)
- **Amends**: [0001](./0001-delegate-commits-to-antigravity-cli.md) and
  [0002](./0002-consolidate-the-commit-skill-set.md)

## Context

ADR 0010 introduced native commit subagents (Claude Code `agentkit-commit` profile,
Codex Luna subagent spawn) and message generation workers to avoid spending parent-session
reasoning on commit messages.

In practice, subagent delegation added considerable latency, invocation complexity,
and workflow fragility:
1. Creating a commit is not sufficiently token- or cost-intensive to justify spawning
   a separate subagent session.
2. Generating commit messages in the active working session is significantly faster
   because context and mental models of recent edits are immediately accessible.
3. Managing host-specific subagent profiles, spawn parameters, and inter-agent
   coordination introduced unnecessary maintenance overhead without quality benefits.

## Decision

1. **Deprecate and remove native commit subagents**:
   - Remove `modules/agents/subagents/` and its role definitions (`commit/`).
   - Remove subagent synchronization from `setup.sh` and repository test suites.
   - Remove subagent message worker delegation from `git-commit` (`SKILL.md`).

2. **Commit directly in the active session**:
   - The active session inspects staged context via `agentkit commit context --mode <low|default|high>`.
   - The active session composes the commit message directly, adhering to repository
     conventions and templates (`agentkit-commit.json`).
   - Commits are executed using `agentkit commit-safe commit`, preserving all safety
     guards (identity whitelist, secret detection, timeline enforcement, hook policy).

3. **Retain external handoff CLI**:
   - When offloading commits to an external agent is desired, `agentkit handoff commit`
     (delegating to Antigravity CLI) remains supported as a standalone CLI command.

## Consequences

- Direct session commits are faster and have lower cognitive and infrastructural overhead.
- No host-specific agent definitions need to be maintained or synchronized in
  `~/.claude/agents/` or `~/.codex/skills/`.
  - Repository setup is simplified: `setup.sh` no longer needs a subagent synchronization option.
  - Safety guarantees (secret checks, identity verification, hook enforcement) are
    strictly preserved via `agentkit commit-safe`.
