# AGENTS.md

Guidance for coding agents working in this repository.

## Overview

`setup-scripts` configures development environments on macOS and Ubuntu. Its
installers may use the network, package managers, `sudo`, or files under
`$HOME`, so understand their side effects before running them.

## Root layout

- `setup.sh`: interactive entry point and module registration
- `lib/`: shared Bash helpers
- `modules/`: independently runnable setup modules
- `config/`: configuration presets consumed by modules
- `tools/`: installable CLI packages
- `tests/`: shell and Python test suites
- `docs/decisions/`: architecture decision records
- `check.sh`: repository-wide format, lint, and test command

Do not document volatile subtree details here. If a directory needs detailed
architecture or maintenance guidance, keep it in that directory's `README.md`
and consult it before making changes there.

## Development guidelines

- Put shared Bash primitives in `lib/`, tool-specific setup in `modules/`, and
  reusable executable CLI behavior in `tools/`.
- Agent skill files are workflow documentation; executable behavior belongs in
  a CLI rather than `SKILL.md`.
- Keep installers safe to re-run. Detect existing state, preserve unrelated
  user configuration, and back up files before destructive replacement.
- Derive paths from `BASH_SOURCE[0]`, quote paths and expansions, and handle
  macOS and Ubuntu differences explicitly.
- The `options`, `defaults`, and `scripts` arrays in `setup.sh` are positional.
  Update all three together when changing module registration.
- Respect existing ADRs and add one for significant, durable architecture
  decisions.

Do not run `setup.sh` or real installers as routine tests. Installer tests must
isolate external effects with a temporary `HOME`, controlled `PATH`, fixtures,
and stubbed commands.

## Verification

Run focused tests while iterating, then run the full check before finishing:

```bash
./check.sh
```

Use `./check.sh --check` when verification must not modify files. If `uv` is
unavailable, Python checks are skipped; report that instead of claiming they
passed.

## Repository hygiene

- Preserve unrelated working-tree changes.
- Do not commit credentials, environments, caches, or generated artifacts.
- Do not commit or push unless explicitly asked.
