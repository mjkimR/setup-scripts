# 16. Standalone commit onboarding and managed git hooks

- **Date**: 2026-10-07
- **Status**: Accepted
- **Amends**: [0005](./0005-hook-policy-and-repo-verify-commands.md) and
  [0015](./0015-deprecate-commit-subagents.md)

## Context

Following ADR 0015's consolidation of direct commits within active sessions, the `git-commit` skill
still carried complex onboarding routing, conditional checklists, and manual safety instructions.
Enforcing guardrails (branch protection, secret detection, path deny-lists) and verification solely
through prompt instructions wastes context tokens on every commit and leaves room for human/agent oversight.

Furthermore, Git hooks natively execute during `git commit`, providing an immutable local barrier.
However, manually configuring `.git/hooks/` per repository or writing bespoke scripts lacks consistency.

## Decision

1. **Independent, hidden onboarding skill (`git-commit-onboard`)**:
   - Extract onboarding workflows into a standalone skill: `modules/agents/skills/git-commit-onboard/`.
   - Mark the skill with `default: false` and `hidden: true` in `meta.yaml` so it is excluded from
     routine interactive skill selection menus and default syncs. It is only installed when explicitly
     named (`install.sh git-commit-onboard`).
   - The primary `git-commit` skill is relieved of onboarding logic, merely referencing `/git-commit-onboard`
     if repository configuration is absent.

2. **Managed Git hooks in `agentkit`**:
   - Add `agentkit hook install`, `uninstall`, `status`, `run-pre-commit`, and `run-commit-msg`.
   - Install thin-wrapper scripts into `.git/hooks/` that delegate execution to `agentkit hook run-*`.
   - Track hook installation state in `agentkit-commit.json` (`hooks.installed = true`).
   - `run-pre-commit` enforces repository guardrails (secret scanning, branch protections, deny-lists)
     and configured verification commands according to hook policy.
   - `run-commit-msg` validates non-empty messages and verifies conventional commit formatting.

3. **Onboarding integration**:
   - `agentkit commit onboard` supports `--install-hooks/--no-install-hooks` to automatically install
     managed hooks during repository onboarding.

4. **Eliminate modes and streamline workflow**:
   - Remove `low`, `medium`, and `high` modes from `git-commit`. A single unified workflow handles
     both in-session and cold-start commits.
   - Verification commands are run directly via `agentkit commit verify` and pre-commit hooks when
     configured. Complex bypass rules or mode flags are eliminated from the skill prompt.

## Consequences

- Daily commit workflows (`git-commit`) remain compact and fast without cognitive or token overhead.
- All references within the skill are consolidated into a single self-contained `SKILL.md`.
- Guardrails are reliably and mechanically enforced at the Git repository hook level.
- Thin wrappers ensure hook logic can be upgraded or maintained through `agentkit` without re-writing hook files.
