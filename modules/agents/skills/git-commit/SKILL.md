---
name: git-commit
description: >-
  Use this skill when the user asks to create git commits, write commit messages,
  inspect staged/unstaged changes, onboard commit conventions, or apply commit conventions.
---

# Git Commit Skill

This skill provides operational workflows for inspecting changes, adhering to repository-specific commit conventions and language preferences, splitting changes into atomic commits, and creating clean, consistent commits.

Configuration is maintained **per-repository** at `<git-dir>/agentkit-commit.json`.

---

## Core Principles

1. **Repository Onboarding & Self-Configuration**:
   - Each repository maintains its own settings:
     - **Whitelist Check**: (on/off) Verifies `git config user.email` against allowed list.
     - **Timeline Control**: (on/off) Enforces daily time windows (e.g. 19:00~21:00) and commit gaps.
     - **Conventions & Language**: (ko / en) Specific commit message template and tone.
   - On first use in a repository, the agent enters **Onboarding Mode** to analyze history and establish these settings.
   - Subsequent runs seamlessly use the saved settings. Re-onboarding can be triggered anytime with `/git-commit onboard`.

2. **Atomic Commits (Split Logical Concerns)**:
   - Group related changes together. Never combine unrelated features, bug fixes, refactoring, dependency updates, or documentation into a single mega-commit.
   - Explicitly stage files (`git add <file1> <file2>`) belonging to each specific logical unit. Never run `git add .` indiscriminately.
   - **A file is the smallest unit.** A file's entire change belongs to exactly one commit — never split one file's changes across commits via partial staging. When one file carries several concerns, commit it whole with its dominant concern (tie-break: the earliest commit that needs it) and note the piggybacked change in that commit's body.
   - **Intermediate commits may be red.** In a multi-commit split, intermediate commits need not keep tests or the build green — only the final commit must reproduce the working tree as it stood at the start. Spend no effort verifying or reordering for per-commit greenness; grouping by concern wins.
   - Never commit sensitive files (`.env`, credentials), temporary files, or build artifacts (`dist/`, `build/`, `node_modules/`).

3. **Direct Autonomous Execution**:
   - Once onboarded, do NOT ask for confirmation before committing.
   - Proactively partition changes, stage relevant files, craft messages according to the repository template, and execute commits directly.

4. **Honor Caller Constraints (Handoff Contract)**:
   - When invoked through `/handoff-commit` or headless runners:
     - If the prompt lists specific files, stage only those.
     - If the prompt asks for exactly one atomic unit, create a single commit and stop.
     - If commit dates are already exported in the environment, do not resolve or override them.
     - If the prompt carries caller hints (suggested commit units), use them to group and order the commits — but as advice, not instruction: the diff is the ground truth. Never create an empty or padded commit to match the hint count, never leave a change uncommitted because no hint covers it, and never reuse a hint verbatim as a subject — write subjects to the repository conventions. Report any hint/tree mismatch at the end.
     - If the prompt attests the test-suite state (`passed` / `failed` / `not-run`), trust it: do not run tests, builds, or linters yourself. `failed` is not a reason to hold back commits, and the attestation never goes into a commit message.
     - Never stop to prompt interactively during a headless run.

---

## Step-by-Step Workflow

### Step 0: Check Onboarding State (First Run / Re-onboard)

Check if the current repository has an active commit configuration:
```bash
agentkit commit config
```

- **If configuration is missing (`[INFO] No repository commit config found`)**:
  1. Analyze git history:
     ```bash
     agentkit commit analyze
     ```
  2. In an **interactive session**, present the detected defaults and ask the user to confirm:
     - **Whitelist**: Enable author email verification? (Default: ON, email: `user.email`)
     - **Timeline**: Enable time window spoofing? (Default: ON, 19:00~21:00 Asia/Seoul)
     - **Language**: Preferred commit language (`ko` / `en`)
     - **Style & Template**: Detected style (Conventional / Bracketed / Ticket) and template
  3. Save the configuration:
     ```bash
     agentkit commit onboard --language <ko|en> --style <style> [--whitelist/--no-whitelist] [--timeline/--no-timeline]
     ```
  *(In a headless handoff run, `agentkit commit onboard` will initialize auto-detected defaults automatically without prompting).*

- **If already onboarded**: Load and proceed with the stored configuration.

---

### Step 1: Inspect Working Tree & Differences

```bash
# Overview of branch and working tree
git status -s

# Inspect diffs
git diff --cached
git diff
```
*(Tip: `agentkit git summary` gives an aggregated overview in one call).*

---

### Step 2: Partition Changes into Atomic Units

Identify distinct logical changes:
- Feature additions vs. bug fixes
- Code refactoring vs. dependency updates
- Source code vs. tests / documentation

Stage only the files for the first logical unit:
```bash
git add path/to/file1 path/to/file2
```

---

### Step 3: Craft Commit Message & Commit

Follow the repository's onboarded language (`ko` vs `en`) and template.

Resolve the safe-mode environment, then commit. This applies with Timeline `[ON]`
**and** `[OFF]`: the `env` call is what enforces the identity whitelist. When
Timeline is `[OFF]` it simply exports no dates, so the commit uses the system
clock — but skipping it would skip the whitelist check too.

```bash
safe_env="$(agentkit commit-safe env)" && eval "$safe_env" && \
git commit -m "<subject matching repo template>" \
  -m "[Optional 1-line overview of intent or motivation]" \
  -m "- <Key change or reason 1>" \
  -m "- <Key change or reason 2>"
```

(The capture-then-eval form matters: a plain `eval "$(…)"` discards the CLI's
exit code, so a whitelist rejection would fall through to the commit anyway.)

If multiple atomic units exist, repeat Steps 2–3 for each remaining set of changes until the working tree is clean.

---

### Step 4: Verify

Confirm the committed changes:
```bash
git log -n 1 --format=fuller
git status
```
