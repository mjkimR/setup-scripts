# 17. Externalize Git hooks to cgate

- **Status**: Accepted
- **Amends**: [0016](0016-standalone-commit-onboarding-and-managed-git-hooks.md)

## Decision

Remove agentkit's Git hook installation and execution commands. The standalone
`cgate` CLI owns repository commit gates and their hook installation.
`agentkit commit onboard` manages only its repository configuration and never
installs hooks. Hook installation state and output verbosity are removed from
agentkit configuration.

Keep commit-safe identity checks, guardrails, timestamp resolution, message
cleanup, and push behavior for existing agentkit workflows. Keep `hooks.policy`
as the handoff workflow's policy for running externally installed Git hooks.
Notification hooks for agent applications are unrelated and remain unchanged.

## Consequences

Git gates are installed explicitly with `cgate onboard`. A user enabling
both cgate and commit-safe timestamp or push features must configure which one
performs those actions to avoid duplicate amendments or pushes. Existing
agentkit hooks in other clones must be removed before uninstalling the old CLI;
this source change does not mutate those clones.
