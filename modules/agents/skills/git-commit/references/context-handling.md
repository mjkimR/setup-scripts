# Context Handling in Commit Workflows

This guide defines how agents handle commit message generation based on whether session context is available.

## 1. In-Session Work (Context-Aware)

Apply this flow when the active session performed, edited, or discussed the pending changes:

- **Primary Source of Truth**: The active conversation history, recent edits, and stated user objectives.
- **Workflow**:
  1. Check `git status --short` and read snapshot via `agentkit commit context --mode low`.
  2. The agent already understands *why* changes were made and *what* was accomplished.
  3. **Do NOT re-read full diffs or re-investigate intent.** Repeated diff exploration in this state wastes time and tokens.
  4. Compose the subject and body directly in a single pass using session memory and the repository template.
  5. If tests or linters already passed during the session, reuse that result without re-running verification commands.
  6. Execute `agentkit commit-safe commit -m '<subject>' -m '<optional body>'`.

## 2. Fresh Session / Cold Start (Context-Free)

Apply this flow when invoked in a new session or when committing external changes with no prior conversation context:

- **Primary Source of Truth**: Staged snapshot, git diffs, and repository history.
- **Workflow**:
  1. Inspect status with `git status --short --untracked-files=all`.
  2. Run `agentkit commit context --mode default` (or `high` if complex/unclear) to obtain conventions, changed paths, and the staged patch.
  3. Analyze the patch to deduce:
     - The overarching intent and motivation.
     - Key architectural or logical changes.
     - Affected components (for scope tagging).
  4. In `high` mode, targeted reads (`git log -n 5`, file inspections) are permitted to clarify surrounding context.
  5. Verify tests and linting via `agentkit commit verify` unless explicitly skipped or authorized by the user.
  6. Compose the message strictly adhering to repository conventions and template.
  7. Execute `agentkit commit-safe commit -m '<subject>' -m '<optional body>'`.

## Summary Comparison

| Aspect | In-Session Work (Context-Aware) | Fresh Session (Context-Free) |
|---|---|---|
| **Intent origin** | Session memory & immediate task context | Staged diff analysis & Git history |
| **Inspection depth** | Minimal (path list + bounded preview) | Full (complete staged patch + targeted reads if needed) |
| **Verification** | Reuses recent session test results | Runs `agentkit commit verify` |
| **Optimal mode** | `low` | `default` or `high` |
| **Execution goal** | Maximum speed: commit immediately in 1-pass | Maximum accuracy: deduce intent safely from diff data |
