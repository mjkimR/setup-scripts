# AGENTS.md

Instructions and operating guidelines for AI coding agents (Antigravity, Claude Code, Codex) working in this repository.

---

## Repository Overview

This repository (`setup-scripts`) provides automated development environment setup, modular configuration, and AI agent extensions:
- **`lib/`**: Reusable Bash utility libraries (`utils.sh`, `ui.sh`).
- **`modules/`**: Setup modules for tools, shell, and AI agent skills/hooks (`modules/agents/`).
- **`tools/agentkit/`**: Python CLI package managing commit timestamps, whitelists, handoff delegation, and repository configuration.
- **`tests/`**: Automated test suites for shell scripts and Python packages.

---

## Core Guidelines & Workflow

### 1. Verification & Quality Assurance

Always run quality checks before finishing any task:
```bash
# Automatically format code, auto-fix lint issues, and run all test suites
./check.sh

# Verify-only mode (fails if unformatted/lint issues exist without modifying files)
./check.sh --check
```

- Python code formatting and linting are enforced via **Ruff** inside `tools/agentkit`.
- Test suites must always pass (`tests/run-all.sh`).

### 2. Architecture: Skills vs CLI Logic

- **Skills are documentation**: Files in `modules/agents/skills/` (`SKILL.md`, `meta.yaml`) provide workflow guidance for AI agents.
- **Executable logic belongs to CLIs**: All functional logic lives in `tools/agentkit/` and is installed via `uv tool install --editable`.
- A `PATH` command (e.g. `agentkit`) resolves identically across different agent environments.
- After adding or modifying skills, sync them using:
  ```bash
  bash modules/agents/skills/install.sh
  ```

### 3. Git & Working Tree Hygiene

- Never commit temporary files, credential files (`.env`), test artifacts, or virtual environments (`.venv/`, `.ruff_cache/`, `.pytest_cache/`).
- Respect existing directory layouts and ADR records under `docs/decisions/`.
- Ensure changes are verified with `./check.sh` before finishing.
