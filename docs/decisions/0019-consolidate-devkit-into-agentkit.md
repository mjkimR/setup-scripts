# 19. Consolidate devkit into agentkit

- **Status**: Accepted
- **Amends**: [0014](0014-personal-developer-cli.md)

## Context

ADR 0014 introduced `tools/devkit` as an independent CLI package to keep personal clipboard/diff utilities
separate from agent workflows. Maintaining two standalone Python packages in `tools/` with separate `pyproject.toml`,
`uv.lock`, test runners, and editable installation workflows added overhead without architectural benefit.

## Decision

1. Consolidate `tools/devkit` into `tools/agentkit` under the `agentkit.devkit` subpackage (`src/agentkit/devkit/`).
2. Register `devkit = "agentkit.devkit.cli:main"` in `tools/agentkit/pyproject.toml` so the standalone `devkit` executable
   is installed automatically when installing AgentKit.
3. Register the devkit command group in `agentkit` CLI (`agentkit devkit ...`), allowing invocation through either binary.
4. Remove the `tools/devkit` package directory.

## Consequences

- Only one tool package (`tools/agentkit`) exists to format, lint, test, and install.
- `uv tool install --editable tools/agentkit` provides both `agentkit` and `devkit` commands.
- Standalone CLI commands (`devkit copy-diff`, `devkit prompt`) remain 100% backward-compatible.
