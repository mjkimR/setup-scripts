---
name: git-commit
description: >-
  Create a single git commit, generate a commit message, inspect pending changes,
  or configure repository commit conventions. Supports low, default, and high modes.
---

# Git Commit

Create one comprehensive commit for the requested scope. Commits run directly
in the active session using repository templates and `agentkit commit-safe`.

## Quick Router

Consult the relevant reference when encountering specific scenarios:
- **Missing or unconfigured repo**: See [onboarding](references/onboarding.md)
- **Session context vs cold start**: See [context handling](references/context-handling.md)
- **Verification, secret detection & guard failures**: See [guards & policies](references/guards.md)

## Modes

Recognize an optional leading mode argument (`low`, `default`/`medium`, `high`);
remaining text specifies user scope and constraints.

| Invocation | Verification | Context and workflow |
|---|---|---|
| `/git-commit low` | Skipped | Bounded preview; rapid single-pass message generation |
| `/git-commit` or `/git-commit default` | Configured / attested | Full staged diff; single-pass message generation |
| `/git-commit high` | Configured / attested | Full staged diff; targeted file/history reads permitted |

---

## Core Workflow

### 1. Prepare & Verify

Obtain configuration and inspect working tree:
```bash
agentkit commit config
git status --short --untracked-files=all
```
- If config is missing, route to [onboarding](references/onboarding.md).
- **Low**: Always skip verification.
- **Default / High**: Run `agentkit commit verify` unless tests already passed in the active session.

### 2. Stage Changes

Stage the intended scope into one comprehensive commit:
```bash
git add -A                    # Whole repository
git add -- <explicit paths>   # Restricted scope
```
Preserve unrelated changes. Do not stage credentials, local envs, or build artifacts.

### 3. Read Context & Generate Message

Collect conventions and staged patch:
```bash
agentkit commit context --mode <low|default|high>
```
Generate the commit message directly in the active session:
- **In-session work**: Reuse active task context directly; compose the message in one pass.
- **Cold start**: Follow [context handling](references/context-handling.md) to deduce intent from the diff.
- Adhere strictly to the template, style, and language returned by `agentkit commit context`.
- Do not spawn subagents.

### 4. Commit Safely

Execute the commit via the checked wrapper:
```bash
agentkit commit-safe commit -m '<subject>' -m '<optional body>'
```
This wrapper enforces the author whitelist, secret scanning, and timeline rules.
If blocked (e.g. `SECRET_DETECTED`), refer to [guards & policies](references/guards.md).

### 5. Report Outcome

Confirm and report hash, subject, verification outcome, and remaining files:
```bash
git log -1 --format=fuller
git status --short
```
