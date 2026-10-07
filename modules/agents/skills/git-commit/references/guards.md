# Verification and Guard Policies

This reference documents verification rules, commit guards, and error handling for `git-commit`.

## 1. Verification Rules

- **Low mode**:
  - Always skips agent-run verification (`agentkit commit verify`, tests, linters, builds).
  - Report `verification: skipped (low mode)`.
  - Prior test attestations or test failures do not block low mode.
- **Default / High modes**:
  - Run `agentkit commit verify` unless a valid test attestation already exists from the active session.
  - Respect disabled/empty verification settings and report them as skipped, not passed.
  - Stop on verification failure unless explicitly authorized by the user to commit known failures.
- **Test attestations**:
  - Never put test run results or attestations inside the commit message itself.

## 2. Commit Guards and Safe Commit

`agentkit commit-safe commit` strictly enforces:
- **Identity whitelist**: Ensures author matches approved repository contributor emails.
- **Secret detection**: Blocks staged credentials, tokens, or private keys.
- **Timeline spoofing / timestamps**: Enforces configured repository timestamp behavior.
- **Protected branches**: Refuses direct commits to protected branches if configured.

## 3. Guard Failure and Error Handling

- **Never bypass refusals**:
  - Do not fall back to plain `git commit`.
  - Do not add `--no-verify` on your own (only follows configured hook policy).
  - Do not split commits or rewrite history to circumvent a block.
- **`SECRET_DETECTED`**:
  - Stop and report the exact blocked file.
  - Only when the user explicitly confirms the file is a test fixture or placeholder, retry with `--allow-secret <that-path>`.
  - Never invent blanket overrides.
- **Scope conflict**:
  - If unrelated files are already staged or present in the index, stop and report rather than silently committing or unstaging them.

## 4. Headless and Restricted Callers

Headless runners (e.g., `agentkit handoff commit` via Antigravity):
- Run strictly with pre-granted tool permissions.
- If `agentkit commit context` is unavailable in low mode, stop and report the blocker.
- In default/high, fallback to `git diff --cached` directly if tool transport truncates output.
- Caller file lists, dates, push constraints, and test attestations take precedence over defaults.
