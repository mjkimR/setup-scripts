# Codex adapter

Codex selects a native child model when it spawns the child. It does not load a
named, on-disk subagent profile for this flow, so this adapter deliberately
contains the exact spawn contract rather than a TOML file that no caller reads.

The `handoff-commit` skill is the sender. For an explicit commit request, it
creates exactly one child with:

```text
task_name:   commit
model:       gpt-5.6-luna
fork_turns:  none
reasoning_effort: medium
```

The sender passes the selected mode, repository path, applicable instructions,
user constraints, caller context, and current verification attestation explicitly;
`fork_turns: none` permits model/effort overrides without inheriting a large
conversation. The task tells that child to read the checked-in instructions, use the
`git-commit` skill, and own inspection, verification, staging, and commit
creation in the shared checkout. The parent does no git work while it runs.

The model identifier belongs here and in the sender skill together. Do not use
`codex exec --profile` for this role: that configures a separate CLI session,
not a native child created through the collaboration tool.

The direct `git-commit` route instead prepares the staged context in the parent
and uses a read-only Luna message worker at medium effort for every mode. A full
commit handoff never spawns that nested worker.
