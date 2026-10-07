---
name: git-commit
description: Create a git commit following repository conventions and templates.
---

# Git Commit

Stage intended changes and create a git commit.

- **Conventions (Template & Rules)**:
  ```bash
  agentkit commit conventions
  ```
- **Context (Staged Diff & Conventions for Cold Start)**:
  ```bash
  agentkit commit context
  ```
- **Commit**: Create the commit as usual
  - Verification automatically isolates and tests staged changes only (unstaged changes are safely stashed and restored).
  - To bypass only the test/lint verification while keeping guardrails (branch protection, secret scans) active:
    ```bash
    git -c agentkit.verify=false commit -m "..."
    ```
  - To bypass all hooks entirely:
    ```bash
    git commit --no-verify -m "..."
    ```
- **Auto-Push Policy**:
  - Check auto-push status via `agentkit commit conventions` (`Auto-push: [ON]` or `[OFF]`).
  - If `Auto-push: [ON]`, `post-commit` automatically pushes (`[hook:post-commit] [PUSH] Auto-pushed to ...`). **Do not run manual `git push`**.
  - If `Auto-push: [OFF]`, do **not** push unless explicitly instructed by the user.
  - To bypass auto-push for a specific commit:
    ```bash
    git -c agentkit.push=false commit -m "..."
    ```
