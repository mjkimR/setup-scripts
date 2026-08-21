# 9. Commit through the CLI, not an eval

- **Date**: 2026-08-21
- **Status**: Accepted
- **Extends**: [0002](./0002-consolidate-the-commit-skill-set.md)

## Context

`/git-commit` told the agent to commit like this:

```bash
safe_env="$(agentkit commit-safe env)" && eval "$safe_env" && git commit -m …
```

The `env` call is what enforces the identity whitelist, so it could not simply
be dropped — but the shape of the line cost something on every commit.

An agent CLI's allow-list matches a **command prefix**. That line starts with a
shell assignment, so it matches nothing: not `command(git commit)`, not
`command(agentkit)`, both of which a user running these skills already grants.
Antigravity prompted for permission on every single commit, and it was right to
— `eval` of a command substitution is exactly the case a prefix rule cannot
reason about.

The line also carried a trap the skill had to document in prose: a plain
`eval "$(…)"` discards the CLI's exit code, so a whitelist rejection would fall
straight through to the commit. Hence the capture-then-eval spelling, and a
paragraph of the skill spent explaining why.

Both problems come from the same place. The whitelist check, the timestamp, and
the commit are one operation, and we had split it across a shell idiom.

## Decision

### One command owns the whole operation

```bash
agentkit commit-safe commit -m "<subject>" -m "<body>" [--amend] [--no-verify]
```

It checks the identity, resolves the timestamp, and runs `git commit` in one
process. No `eval`, no command substitution — so the exit code propagates by
itself and the prose warning disappears. The command line starts with
`agentkit`, which an allow-list can match, and the permission prompt is gone.

This follows the rule AGENTS.md already states: skill files are workflow
documentation, executable behavior belongs in a CLI. The eval line was the last
piece of real logic left in a `SKILL.md`.

### It builds the git argv itself, and never runs what a caller names

The obvious generalization — `agentkit commit-safe exec -- git commit …` — is
refused. `command(agentkit)` is a *prefix* grant, so a passthrough subcommand
would silently convert it into permission to run arbitrary shell, which is
strictly worse than the prompt it removes. The wrapper accepts `-m`, `--amend`
and `--no-verify`, and assembles `git commit` from them.

For the same reason `-m` is required: without it git opens an editor and hangs
a headless run.

### Pre-set dates are inherited, never re-resolved

`resolve()` advances a persistent virtual timeline. The commit-safe handoff
stamps one unit in the parent process and exports it to the child, so a wrapper
that resolved again would consume two stamps per unit and pull the sequence off
the timeline. If `GIT_AUTHOR_DATE` or `GIT_COMMITTER_DATE` is already set, the
wrapper passes it through untouched. The handoff contract in `/git-commit`
("do not resolve or override them") is now also enforced by the code.

### The handoff path stays on plain `git commit`

Headless runs are granted `command(git add|commit|ls-files)` and not
`command(agentkit)`; the grant set is deliberately narrow, which is why
`command(git reset)` is absent too. Widening it so the receiver could call
`agentkit` would trade a real security boundary for a convenience the handoff
does not need — the parent has already checked the identity and exported the
dates. `/git-commit` therefore carries an explicit carve-out: in a handoff run,
commit with plain `git commit`.

## Consequences

- `/git-commit` and `/git-commit-revise` no longer contain a shell idiom. The
  revise skill also loses its Timeline `[ON]`/`[OFF]` branch — one command
  covers both, because `[OFF]` simply resolves to no dates.
- `agentkit commit-safe env` survives for debugging and for anyone with an
  existing shell habit. It is no longer what the skills call.
- A user upgrading gets the prompt back exactly once — for whatever their
  allow-list does not yet cover — and `command(agentkit)` is a rule they can
  grant knowing it cannot reach past agentkit's own subcommands.
- Two grant sets now exist by design: interactive runs want `command(agentkit)`,
  headless handoffs want `command(git …)`. `agentkit agy grant` keeps issuing
  the handoff set; the interactive one is the user's own allow-list.
