# 3. One shared scratch space for agent working files

- **Date**: 2026-08-18
- **Status**: Accepted

## Context

The new `handoff` skill writes a handoff document that another agent — or the
user, by hand — picks up later. That file needs a home, and the candidates all
failed for a different reason:

- **OS temp dir** (what the upstream mattpocock skill does): cleared between
  sessions on some harnesses — Codex is the reported case — which is exactly
  when a handoff must survive.
- **Inside `.git/`** (the `agentkit-commit.json` convention): durable and
  invisible to `git status`, but IDEs hide `.git` from the project tree
  entirely, so a document the user wants to open, inspect, or hand over
  manually is effectively lost.
- **A visible directory + a `.gitignore` entry**: visible and durable, but
  editing `.gitignore` is itself a tree change that needs a commit — the setup
  step would dirty the very `git status` it is trying to protect, and it
  imposes personal tooling on a shared file.

The same question returns for every future skill that produces working files,
so answering it per-skill would scatter ad-hoc locations across the codebase.

## Decision

### One resolver in agentkit, one command as the contract

`agentkit scratch path <subdir>` prints an absolute, created directory. Skills
that need working-file storage call it and never hardcode a location.

- **Default root: `.agents/tmp/`** — in the working tree, so it shows in the
  IDE project tree; `.agents`-based, matching the existing `~/.agents`
  convention on this machine. Only `tmp` is ignored, leaving room to commit
  other `.agents/` content later.
- **Ignored via `.git/info/exclude`** — git's repo-local ignore file: the same
  effect as `.gitignore` with zero tree impact and no team-facing footprint.
  `agentkit scratch onboard --shared` opts into `.gitignore` instead, with a
  warning that the change needs a commit.
- **Self-onboarding**: the first `path` call adopts the default, registers the
  exclude entry, and records the choice in `<git-dir>/agentkit-scratch.json`
  (config follows the `agentkit-commit.json` pattern — machine state may live
  in `.git`; human-facing files may not). `onboard` exists only to override.
  Every resolve re-checks `git check-ignore` and heals a lost exclude entry.
- **Fallback outside git repositories**: `~/.agents/tmp/<path-slug>/`, so the
  command never fails for lack of a repo.

## Consequences

- The `handoff` skill's storage paragraph is one command; future skills reuse
  the same line. No per-skill location decisions remain.
- Scratch content stays out of `git status`, so it never pollutes the
  `handoff-commit` whitelist flow.
- `.git/info/exclude` is per-clone: a fresh clone re-onboards on first use
  (self-healing), and teammates never see the entry — by design.
- Scratch files accumulate; a `scratch clean --older-than` housekeeping command
  is the expected follow-up when that starts to hurt.
