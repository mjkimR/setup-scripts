---
name: git-commit-revise
description: >-
  Use this skill when the user asks to review, critique, refine, or amend git commit
  messages and commit structures.
---

# Git Commit Revise Skill

This skill provides expert review, critique, and revision workflows for git commits. It evaluates commit message clarity, structure, and adherence to repository conventions, offering concrete improvements and automated amend execution.

---

## When to Use

Invoke this skill when:
- The user asks for feedback or opinions on recent commit messages (`/git-commit-revise`, "커밋 메시지 검토해줘", "방금 한 커밋 피드백 줘").
- The user wants to polish or reword the latest commit message.
- Checking whether changes in a commit should be split into smaller atomic units.

---

## Core Review Criteria

1. **Repository Convention Alignment**:
   - Check `agentkit commit config` to ensure the commit matches the repository's preferred language (`ko` / `en`), style (`conventional`, `bracketed`, `ticket`), and template format.
2. **Subject Line Quality**:
   - Concise, imperative, and specific (avoid generic phrases like `update code`, `fix bug`, `수정`).
   - Prefix/Scope accuracy (e.g., `feat(auth):`, `[core] fix:`).
3. **Body & Explanation Depth**:
   - High-level intent / motivation summary for non-trivial changes.
   - Clear, scannable bullet points explaining *what* was changed and *why*.
4. **Atomic Scope**:
   - Verify if unrelated concerns (e.g. refactoring + feature + documentation) are conflated into a single commit.

---

## Step-by-Step Workflow

### Step 1: Inspect Target Commit & Diff

Inspect the latest commit (or specified commit/range):
```bash
# Check commit message, author, and changed files
git log -n 1 --format=fuller --stat

# Inspect exact diff of the commit
git show --stat HEAD
```

Check repository configuration:
```bash
agentkit commit config
```

---

### Step 2: Formulate Review & Proposed Revision

Analyze the commit against the criteria and present a structured review:

```markdown
### 📋 Commit Review & Feedback

- **Target Commit**: `<commit-hash>`
- **Current Subject**: `<original subject>`

#### 🔍 Assessment
- **Language & Style**: (e.g. Matches Korean Conventional Commit format)
- **Clarity & Scope**: (e.g. Subject is clear, but body lacks reason for change)
- **Atomic Grouping**: (e.g. Single logical unit / Should be split into 2 commits)

#### ✍️ Proposed Revision
```text
<revised subject line>

[Optional 1-2 sentence overview explaining overarching intent]

- <Key change or reason 1>
- <Key change or reason 2>
```
```

---

### Step 3: Apply Revision (Amend)

If the user approves the revision or asks to apply it:

- **If Timeline is Enabled (`[ON]` in `agentkit commit config`)**:
  ```bash
  eval "$(agentkit commit-safe env)" && \
  git commit --amend -m "<revised subject>" \
    -m "<summary>" \
    -m "- <Key change 1>" \
    -m "- <Key change 2>"
  ```

- **If Timeline is Disabled (`[OFF]`)**:
  ```bash
  git commit --amend -m "<revised subject>" \
    -m "<summary>" \
    -m "- <Key change 1>" \
    -m "- <Key change 2>"
  ```

---

### Step 4: Verify

Confirm the amended commit:
```bash
git log -n 1 --format=fuller
git status
```
