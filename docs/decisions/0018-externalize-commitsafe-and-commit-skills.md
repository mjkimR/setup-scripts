# 18. Externalize commitsafe and commit skills to devkit-gates

- **Status**: Accepted
- **Amends**: [0015](0015-deprecate-commit-subagents.md), [0016](0016-standalone-commit-onboarding-and-managed-git-hooks.md), [0017](0017-externalize-git-hooks-to-cgate.md)

## Decision

1. Remove `commitsafe` (`tools/agentkit/src/agentkit/commitsafe/`) and the `agentkit commit-safe` command group.
   Commit identity verification, secret scanning, branch guardrails, timestamp resolution, and auto-push
   are externalized to the standalone `devkit-gates` CLI and its managed Git hooks.

2. Remove commit-related agent skills (`git-commit` and `git-commit-onboard`) from `modules/agents/skills/`.
   Active sessions perform commits using Git directly, guarded by external hooks installed via `devkit-gates`.

3. Remove the commit handoff task (`COMMIT`, `COMMIT_SAFE`) and the `agentkit handoff commit` subcommand.
   `agentkit handoff` retains document-based session continuation (`work`, `prompt`) and Markdown copyediting (`polish`).

4. Retain `agentkit commit` (`conventions`, `context`, `verify`, `config`, `analyze`, `onboard`) for inspecting
   staged context and repository conventions without executing commits or managing Git hooks.

## Consequences

- The `agentkit` tool no longer wraps or executes `git commit`.
- AI agents no longer require `agentkit commit-safe commit` command permissions.
- Repository safety invariants (author identity, secret detection, branch protection) are enforced at the Git hook level by `devkit-gates`.
