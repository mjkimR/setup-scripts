---
name: git-commit-safe
description: >-
  Use this skill when the user asks to perform safe git commits with email whitelist
  validation, custom commit timestamp control, or mentions git-commit-safe.
---

# Git Commit Safe Skill

This skill enforces strict safety pre-flight checks (email whitelist verification and custom commit timestamp control) before performing atomic, convention-compliant Git commits.

## Core Principles

0. **Handoff Mode (Check This First)**:
   - If `GIT_AUTHOR_DATE` and `GIT_COMMITTER_DATE` are **already set in your environment**, you were invoked through `/handoff-commit-safe`. The caller has already verified the email whitelist and resolved the timestamp.
   - In that case: **skip Principles 1–3 and Steps 1 and 4 entirely.** Do not run the pre-flight script, do not resolve or set any dates. Just `git add` and plain `git commit` — the dates are inherited.
   - Check with `printenv GIT_AUTHOR_DATE`. Everything else in this skill still applies.

1. **Pre-flight Configuration Verification**:
   - Check if `~/.config/git-commit-safe/config.yaml` exists.
   - If missing or invalid, **abort immediately** with a clear error and instruct the user to follow [references/onboard.md](./references/onboard.md).

2. **Email Whitelist Enforcement**:
   - Verify that the current `git config user.email` is explicitly listed in `allowed_emails`.
   - If not whitelisted, **abort the commit immediately** to prevent committing under an unwanted or incorrect identity.

3. **Commit Timestamp Control (Daily Range & Natural Elapsed Progression)**:
   - **Today's 1st Commit**: Automatically picks a random base timestamp within the configured range (e.g. `19:00 ~ 21:00`).
   - **Today's Subsequent Commits**: Naturally accumulates the elapsed real-time since the 1st commit.
   - **Strict Forward Progress**: Rapid consecutive commits always advance monotonically (+30s~90s min gap).
   - Injects both `GIT_AUTHOR_DATE` and `GIT_COMMITTER_DATE` consistently when creating commits.

4. **Direct Autonomous Execution & Atomic Commits**:
   - Inspect recent `git log` to match repository style.
   - Partition changes into atomic logical units (never blind `git add .`).
   - Format non-trivial commit bodies with an optional context summary sentence and bullet points (`- `).
   - Execute commits directly without asking for repetitive confirmation once checks pass.

---

## Step-by-Step Workflow

### Step 1: Pre-flight Verification

*Skip this step entirely in handoff mode (Core Principle 0).*

Run the pre-flight verification script to check config, email whitelist, and resolve timestamps. Use the skill's installed location — the path below is absolute because the working directory is the target repository, not this skill:
```bash
bash ~/.gemini/config/skills/git-commit-safe/scripts/verify-safe.sh
```

- **If exit code is 2 (Config Missing)**:
  Stop and guide the user:
  > `[ERROR] git-commit-safe configuration not found. Please refer to [references/onboard.md](./references/onboard.md) or run scripts/setup-config.sh.`
- **If exit code is 1 (Email Violation)**:
  Stop and alert the user with the non-whitelisted email details.

### Step 2: Check Commit History
Inspect recent commits to learn the repository's convention:
```bash
git log -n 5 --oneline
```

### Step 3: Inspect Working Tree & Partition Atomic Units
Analyze status and diffs:
```bash
git status -s
git diff --cached
git diff
```

Stage only files for the first atomic unit:
```bash
git add path/to/file1 path/to/file2
```

### Step 4: Execute Commit with Safe Timestamp & Identity

**In handoff mode** (Core Principle 0), the dates are already in your environment. Commit plainly:

```bash
git commit -m "<subject matching detected repo style>" \
  -m "[Optional 1-line overview explaining intent]" \
  -m "- <Key change 1>" \
  -m "- <Key change 2>"
```

**Otherwise**, load the verified environment variables first:

```bash
eval "$(bash ~/.gemini/config/skills/git-commit-safe/scripts/verify-safe.sh --env)" && \
git commit -m "<subject matching detected repo style>" \
  -m "[Optional 1-line overview explaining intent]" \
  -m "- <Key change 1>" \
  -m "- <Key change 2>"
```

Repeat Steps 3–4 for any remaining atomic change groups until the working tree is clean — **unless the prompt asked for exactly one atomic unit**, in which case stop after the first commit and leave the rest uncommitted.

### Step 5: Verify
Confirm the newly created commit and timestamps:
```bash
git log -n 1 --format=fuller
git status
```
