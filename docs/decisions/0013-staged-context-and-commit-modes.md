# 13. Generate single-commit messages from staged context

- **Date**: 2026-09-16
- **Status**: Accepted
- **Extends**: [0010](./0010-native-commit-subagent-profiles.md)

## Context

The commit skill already requires one comprehensive commit, but still reads both
unstaged and staged patches and lacks an explicit cost/depth choice. Mode words
inside a skill do not change the running agent's reasoning effort.

## Decision

Stage the authorized scope once after any required verification, then use
`agentkit commit context --mode low|default|high` to collect conventions and the
staged snapshot. Keep executable context collection in the CLI. Low returns all
paths plus a marked patch preview; default/high return the full patch. Missing
evidence requires targeted reads even in low mode. Low always skips agent-run
verification (tests, lint, builds, and `agentkit commit verify`) regardless of
configuration or prior attestations, and reports skipped (low mode). Default/high
retain their verification rules. Stored settings and Git hook policy are unchanged.

The direct Codex skill gives a single read-only `gpt-5.6-luna` child the prepared
context and asks only for a message. Every mode selects medium reasoning; low
reduces the context size and high allows additional inspection and refinement.
All modes create at most one commit. The parent owns staging, verification, and the checked commit wrapper.
This message worker is a bounded part of the skill, not a new commit-writer role.

The existing full-workflow handoff remains distinct and never delegates again.
Its Codex adapter also forwards modes and sets medium effort for every mode. Both spawn
contracts use `fork_turns: none`: full-history forks inherit the parent model and
effort, so they cannot implement this selection. Supply relevant instructions,
constraints, context, and verification attestations explicitly instead.
Other hosts without runtime effort controls follow workflow depth without
claiming to have changed effort. The Claude handoff profile remains medium.

## Consequences

- All modes produce at most one commit and retain commit guards. Low skips
  agent-run verification; default/high retain configured verification.
- Routine message generation avoids duplicated diff collection and full-session
  context; onboarding guidance loads only when needed.
- Truncated previews cannot be treated as complete code reviews.
- There is one writer throughout; the message child cannot mutate the checkout.
- No new provider API, credentials, headless session, or installer is required.
