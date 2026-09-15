---
name: git-commit
description: >-
  Use this skill when the user asks to create git commits, write commit messages,
  inspect staged/unstaged changes, onboard commit conventions, or apply commit conventions.
---

# Git Commit Skill

This skill provides operational workflows for inspecting changes, adhering to repository-specific commit conventions and language preferences, creating a single comprehensive commit, and maintaining clean, consistent commit history.

Configuration is maintained **per-repository** at `<git-dir>/agentkit-commit.json` —
the shared git dir, so every worktree of a repository commits under the same settings.

---

## Core Principles

1. **Repository Onboarding & Self-Configuration**:
   - Each repository maintains its own settings:
     - **Whitelist Check**: (on/off) Verifies `git config user.email` against allowed list.
     - **Timeline Control**: (on/off) Enforces daily time windows (e.g. 09:00~18:00) and commit gaps.
     - **Auto-Push**: (on/off, `push.enabled`) Automatically push commits to remote after successful commit. Default is OFF.
     - **Conventions & Language**: (ko / en) Specific commit message template and tone.
     - **Hooks Policy**: how commits treat git hooks.
     - **Guards**: (`guards.protected_branches` / `deny_paths` / `allow_paths`, plus `guards.scan_secrets`) pre-commit guardrails the *command* enforces, not you. `agentkit commit-safe commit` refuses to commit onto a protected branch, refuses a staged path on the deny list, and refuses staged content matching a known credential format. All three lists are empty by default; the secret scan is on. A refusal exits non-zero as `BLOCKED` — report it and stop, never route around it.
     - **Verify Commands**: (`verify.test` / `verify.lint`, plus `verify.enabled` on/off) shell commands that verify the tree (e.g. `uv run pytest -q`, `ruff check`). An empty field skips that kind of verification; `verify.enabled=false` switches all of it off while keeping the commands on record — for repos whose tests are known-broken and mid-repair. Transparency is non-negotiable: whoever runs these must show the exact command line (`agentkit commit verify` echoes each one before running it).
   - On first use in a repository, the agent enters **Onboarding Mode** to analyze history and establish these settings.
   - Subsequent runs seamlessly use the saved settings. Re-onboarding can be triggered anytime with `/git-commit onboard`.

2. **Single-Turn Comprehensive Commit (No Split)**:
   - Commit all pending changes together in a single commit. Do not split changes across multiple atomic commits.
   - Splitting commits introduces extra token overhead, repeated permission requests, git state toggle delays, and fragmented histories.
   - Stage all intended changes together (`git add <files>` or `git add -A`).
   - Never commit sensitive files (`.env`, credentials), temporary files, or build artifacts (`dist/`, `build/`, `node_modules/`). Staging judgement is still yours: the secret scan is a backstop for the obvious accident (an issued API key, a private key block), not a substitute for looking at what you stage. A filename alone decides nothing — `.env.example` is a normal file to commit.

3. **Direct Autonomous Execution**:
   - Once onboarded, do NOT ask for confirmation before committing.
   - Proactively stage all relevant files, craft messages according to the repository template, and execute commits directly in a single turn.

4. **Honor Caller Constraints (Handoff Contract)**:
   - When invoked through `/handoff-commit` or headless runners:
     - If the prompt lists specific files, stage only those.
     - Always create a single comprehensive commit covering all specified or pending changes. Do not split changes across multiple commits.
     - If commit dates are already exported in the environment, do not resolve or override them:
       pass them through to `agentkit commit-safe commit`, which inherits them without re-resolving.
     - If the prompt carries caller hints (context on changes made), use them to understand intent and craft the commit message — but the diff is the ground truth. Combine all covered changes into the single commit, and never leave an intended change uncommitted.
     - If the prompt attests the test-suite state (`passed` / `failed` / `not-run`), trust it: do not run tests, builds, or linters yourself. `failed` is not a reason to hold back commits, and the attestation never goes into a commit message.
     - Follow the repository's hook policy. Do not add `--no-verify` on your own judgment unless explicitly configured or requested.
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
     - **Timeline**: Enable time window spoofing? (Default: OFF, 09:00~18:00 Asia/Seoul)
     - **Guards**: Any branches to protect from direct commits? (Default: none — ask, do not assume `main`). Secret scanning is on by default and needs no question.
     - **Language**: Preferred commit language (`ko` / `en`)
     - **Style & Template**: Detected style (Conventional / Bracketed / Ticket) and template
     - **Verify commands**: how to run this repo's tests and linter. If the repo has a ready-made entry point (Makefile target, package script), store that. If not, ask the user to choose: generate a small script and store its path, or store the raw shell command inline. Leaving a field empty deliberately skips that verification everywhere. Also confirm `verify.enabled`: a repo with known-broken tests can record the commands now but start switched off (`--no-verify`), flipping it back on with `agentkit commit config --set verify.enabled=true` once fixed.
     - **Auto-Push**: Enable automatic git push after commit? (Default: OFF)
     - **Hooks policy**: default `bypass-intermediate`; offer `run-all` only as a visibly closed option (it errors as not implemented).
  3. Save the configuration:
     ```bash
     agentkit commit onboard --language <ko|en> --style <style> [--whitelist/--no-whitelist] [--timeline/--no-timeline] \
       [--test-cmd "<command>"] [--lint-cmd "<command>"] [--verify/--no-verify] [--hooks <policy>] [--push/--no-push]
     ```
  *(In a headless handoff run, `agentkit commit onboard` will initialize auto-detected defaults automatically without prompting).*

- **If already onboarded**: Load and proceed with the stored configuration.

Any stored setting can be changed later with `agentkit commit config --set KEY=VALUE`.
`--set` is repeatable and applies as a unit — every pair lands, or none does:

```bash
agentkit commit config --set timeline.enabled=true --set guards.protected_branches=main,release/*
```

---

### Step 1: Verify, then Inspect Working Tree & Differences

**Verification first — interactive (non-handoff) runs only.** When the caller
did not attest the test state, run the repo's configured verification before
any staging:

```bash
agentkit commit verify
```

It echoes every command verbatim (`[verify] $ …`) before running it, so the
user always sees exactly what executed. It exits 0 with a printed `[SKIP]`
when `verify.enabled=false` — a repo mid-repair opts out this way; respect it
and do not run the commands anyway — and a printed `[INFO]` when nothing is
configured. Running the commands yourself instead is fine (`agentkit commit
config` shows them), as long as the command line stays equally visible to the
user; never run verification in a way that hides what was executed.

A failure is worth surfacing before anything is committed; committing anyway is
the user's call, not a default. In a **handoff run**, skip verification
entirely — the caller's attestation (or its absence) governs, only git commands
are permitted, and running or speculating about tests is explicitly out of
scope there.

Then inspect:

```bash
# Overview of branch and working tree
git status -s

# Inspect diffs
git diff --cached
git diff
```
*(Tip: `agentkit git summary` gives an aggregated overview in one call).*

---

### Step 2: Stage All Pending Changes

Stage all intended files together for a single comprehensive commit:
```bash
git add -A
```
*(Ensure untracked files you stage do not include secrets or unwanted artifacts; omit sensitive files).*

---

### Step 3: Craft Commit Message & Commit

Follow the repository's onboarded language (`ko` vs `en`) and template.

Commit through `agentkit`, never `git commit` directly. This applies with
Timeline `[ON]` **and** `[OFF]`: the command is what enforces the identity
whitelist. When Timeline is `[OFF]` it sets no dates and the commit uses the
system clock — but reaching for plain `git commit` would skip the whitelist
check too.

```bash
agentkit commit-safe commit -m "<subject matching repo template>" \
  -m "[Optional 1-line overview of intent or motivation]" \
  -m "- <Key change or reason 1>" \
  -m "- <Key change or reason 2>"
```

`-m` behaves exactly as git's own, and `--amend` / `--no-verify` / `--push` pass through.
If `push.enabled` is active in repository config or `--push` is passed, `agentkit commit-safe commit`
automatically pushes the commit to the remote.

If the commit is refused as `SECRET_DETECTED`, stop and report it. Only when the
user confirms the match is a placeholder or a test fixture, re-run naming that
one path:

```bash
agentkit commit-safe commit --allow-secret path/to/fixture.py -m "<subject>"
```

`--allow-secret` takes a path per flag and is echoed in the output. There is no
blanket override, and inventing one is not yours to do — a file that needs a
standing exemption belongs in `guards.allow_paths`, which the user decides.

**In a handoff run, still use `agentkit commit-safe commit`, never plain `git
commit`.** The runner grants that exact command; it checks the identity and
guards, and inherits pre-set dates without re-resolving them.

---

### Step 4: Verify

Confirm the committed changes:
```bash
git log -n 1 --format=fuller
git status
```
