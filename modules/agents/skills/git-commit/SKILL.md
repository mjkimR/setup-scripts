---
name: git-commit
description: >-
  Use this skill when the user asks to create git commits, write commit messages,
  inspect staged/unstaged changes, or apply commit conventions.
---

# Git Commit Skill

This skill provides operational workflows for inspecting changes, referencing recent repository history, splitting changes into atomic commits, and creating clean, consistent commit messages.

## Core Principles

1. **Check History First (`git log`)**:
   - Always inspect recent commits (`git log -n 5 --oneline` or `git log -n 10`) before writing a commit message.
   - Match the repository's established conventions, language (e.g., English vs. Korean), capitalization, prefix style, and ticket/scope formats.

2. **Atomic Commits (Split Logical Concerns)**:
   - Group related changes together. Never combine unrelated features, bug fixes, refactoring, dependency updates, or documentation changes into a single mega-commit.
   - Do NOT run `git add .` or `git add -A` indiscriminately. Explicitly stage files (`git add <file1> <file2>`) belonging to each specific logical unit.
   - Never commit sensitive files (`.env`, credentials, private keys), temporary test files, or generated build artifacts (`dist/`, `build/`, `node_modules/`).

3. **Direct Autonomous Execution**:
   - Do NOT ask the user for confirmation before committing.
   - Proactively analyze, partition changes into atomic groups, stage relevant files, craft the messages, and execute `git commit` directly.

4. **Honor Caller Constraints (Handoff Contract)**:
   - This skill is also invoked non-interactively through `/handoff-commit` and `/handoff-commit-safe`, where the caller may narrow the job. Those constraints override the default behavior.
   - **If the prompt lists specific files**, stage only those. Never `git add` a file outside the list, even when it looks related.
   - **If the prompt asks for exactly one atomic unit**, create a single commit and stop, leaving every other change uncommitted.
   - **If the prompt says the commit dates are already set**, do not resolve or override them.
   - There is nobody to ask in a headless run, so settle any remaining choice yourself rather than stopping to ask.

5. **Format Precedence & Conventions**:
   - **Repository Style First (Highest Priority)**:
     Always adhere to the pattern observed in `git log`. Different projects use different styles, for example:
     - Conventional: `type(scope): subject` or `type: subject`
     - Bracketed Scope/Module: `[scope] type: subject` or `[scope] subject`
     - Issue/Ticket Prefix: `[PROJ-123] feat: subject` or `PROJ-123: subject`
     - Subsystem Prefix: `subsystem: subject`
   - **Default Fallback (Conventional Commits)**:
     If the repository has no established convention or history, default to Conventional Commits:
     - `feat`, `fix`, `refactor`, `docs`, `style`, `test`, `chore`
   - **Body Formatting**:
     Whenever a multi-line explanation is warranted:
     - **High-Level Context/Summary (Optional, Recommended for complex/multi-bullet commits)**: Include a brief 1–2 sentence overview stating the overarching intent or motivation that cannot fit into the subject line alone.
     - **Key Changes Breakdown (`- `)**: Use concise bullet points outlining *what* was changed and *why*.
     ```text
     <subject line matching repository style>

     [Optional 1-line overview explaining overarching intent or context]

     - <Key change or reason 1>
     - <Key change or reason 2>
     - <Key change or reason 3>
     ```

---

## Step-by-Step Workflow

### Step 1: Check Commit History
Inspect recent commits to identify repository-specific conventions:
```bash
git log -n 5 --oneline
```
- Observe the prefix/casing format (e.g., `feat(scope):`, `[module] fix:`, `[JIRA-123]`, `docs:`, etc.).
- Observe the language (English/Korean), tense (imperative vs. past), and punctuation.

### Step 2: Inspect Working Tree & Differences
Check the current working tree state:
```bash
# Check working tree overview
git status -s

# Inspect diffs
git diff --cached
git diff
```
*Tip: `agentkit git summary` gives an aggregated overview in one call. Skip it in a headless run — it needs a `command(agentkit)` grant that the handoff deliberately does not ask for.*

### Step 3: Partition Changes into Atomic Units
Identify distinct logical changes:
- Feature code vs. test additions
- Bug fixes vs. unrelated formatting or refactoring
- Configuration/dependency updates vs. source code changes

Stage only the files for the first logical unit:
```bash
git add path/to/file1 path/to/file2
```

### Step 4: Craft Commit Message & Commit
Formulate a subject line matching the detected repository style, and outline details with a summary and bullet points if non-trivial:

**Simple atomic commit**:
```bash
git commit -m "<subject matching detected repo style>"
```

**Non-trivial commit with optional context summary & bullet points**:
```bash
git commit -m "<subject matching detected repo style>" \
  -m "Refactor auth middleware to decouple session validation and support multi-tenant tokens." \
  -m "- Add TokenValidator interface and JWT implementation" \
  -m "- Move session verification into separate pipeline handler" \
  -m "- Update route guards across all protected endpoints"
```

If multiple atomic units exist, repeat Steps 2–4 for each remaining set of changes until the working tree is clean.

### Step 5: Verify
Confirm the committed changes and verify the working tree status:
```bash
git log -n 1
git status
```
