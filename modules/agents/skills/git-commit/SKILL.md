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
