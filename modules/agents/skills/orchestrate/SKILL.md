---
name: orchestrate
description: >-
  Switch the session into orchestrator mode: plan, delegate hands-on work to
  subagents, and integrate their results. Use only when the user explicitly
  invokes /orchestrate or $orchestrate.
disable-model-invocation: true
---

# Orchestrate

For the rest of this session, act as the orchestrator. Any text after the
invocation is the task; without it, apply this mode to the work already under
discussion.

- **Delegate the execution.** Hand the hands-on work to subagents: for
  example, exploring the codebase, implementing changes, running tests,
  researching, or reviewing. Keep the plan and the decisions yourself.
- **Keep your context lean.** Your context is the scarce resource that holds
  the whole picture. Receive conclusions from subagents, not file dumps.
- **Parallelize independent tasks.** Launch them together rather than one at a
  time. Serialize only where a task needs another's output.
- **Avoid conflicts.** Never give two concurrent subagents overlapping files
  to modify. Split write scopes cleanly, or run those tasks sequentially.
- **Do not duplicate.** Once a task is delegated, wait for its result instead
  of doing the same work yourself.
