---
name: git-commit-onboard
description: >-
  Onboard a repository for commit conventions, verification commands, and install
  managed git hooks. Use when setting up a new repository or reconfiguring commit settings.
---

# Git Commit Onboarding

Initialize or reconfigure repository commit conventions, verification commands,
guardrails, and install git hooks (`pre-commit`, `commit-msg`).

## When to Use

- When running `/git-commit` on an unconfigured repository.
- When explicitly requested by the user: `/git-commit-onboard` or `@git-commit-onboard`.
- When updating commit conventions or verification commands across the repository.

---

## Onboarding Workflow

### 1. Check Existing Configuration

Check whether the current repository already has an active commit configuration:
```bash
agentkit commit config
```

- If already configured and the user requested an update, use `agentkit commit onboard --update`
  to preserve existing custom settings while syncing missing configurations and hooks, or
  `agentkit commit config --set KEY=VALUE` for targeted adjustments.
  Use `--force` only if the user requests a complete reset.
- If unconfigured, proceed with initial setup below.

### 2. Analyze Repository History

Analyze git history to detect authors, styles, and patterns:
```bash
agentkit commit analyze
```

### 3. Confirm with User (Interactive Session)

Present detected defaults and ask the user to confirm:

1. **Identity & Whitelist**: Allowed author emails (Default: detected primary email).
2. **Timeline**: Working hours window spoofing (Default: OFF, 09:00~18:00 Asia/Seoul).
3. **Guards & Branch Protection**: Any branches to protect against direct commits (Default: none — ask, do not assume `main`). Secret scanning is always ON.
4. **Language**: Commit message language (`ko` or `en`).
5. **Style**: Detected style (`conventional`, `bracketed`, `ticket`, `freeform`).
6. **Verification Commands**:
   - `test-cmd`: Test runner command (e.g. `uv run pytest -q`, `npm test`).
   - `lint-cmd`: Linter command (e.g. `ruff check`, `npm run lint`).
   - `verify.enabled`: Set to `false` if existing tests are currently broken and being fixed.
7. **Git Hooks Installation & Verbosity**:
   - Install managed thin-wrapper hooks (`pre-commit`, `commit-msg`, `post-commit`) into `.git/hooks/`. (Default: YES).
   - Hook output verbosity: `quiet` (Default, silent on success, trimmed tail on failure), `compact` (1-line tags), or `verbose`.
8. **Auto-Push**: Automatic `git push` upon successful commit (Default: OFF).

### 4. Execute Onboarding & Hook Setup

Run `agentkit commit onboard` with the agreed options:
```bash
agentkit commit onboard \
  --language <ko|en> \
  --style <style> \
  [--whitelist/--no-whitelist] \
  [--timeline/--no-timeline] \
  [--test-cmd "<command>"] \
  [--lint-cmd "<command>"] \
  [--verify/--no-verify] \
  [--install-hooks/--no-install-hooks] \
  [--hooks-verbosity <quiet|compact|verbose>] \
  [--push/--no-push]
```

### 5. Verify Installation

Confirm that hooks and configurations are properly established:
```bash
agentkit hook status
agentkit commit config
```

Once onboarded, future commits can proceed via `/git-commit` without configuration prompts.
