# 14. Keep personal developer utilities separate from agentkit

- **Date**: 2026-09-16
- **Status**: Accepted

## Context

The removed app-common app-helper provided diff attachments and prompts for a
person to paste into an AI chat. Agentkit serves executable agent workflows;
clipboard-oriented interaction has different output and installation needs.

## Decision

Keep these utilities in an independent `tools/devkit` Python CLI in this
repository. Install it explicitly with `uv tool install --editable tools/devkit`.
The agent skill installer installs only agentkit, not every package in tools.
Devkit has no dependency on agentkit or app-common and no associated agent skill.

Restore copy-diff and commit/review prompts without automatic staging. Use
repository-wide read-only diffs, optional exclusions, private temporary exports,
and a usable stdout/file fallback when the clipboard is unavailable.

## Consequences

Personal commands do not expand agentkit's command surface or require its
onboarding. Small Git and clipboard helpers remain local to devkit; a shared
package is unnecessary. The existing tool discovery in quality checks and tests
continues to cover both packages.
