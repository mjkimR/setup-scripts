# agentkit

Everything this repository's agent skills need to *do*, behind one command.

Skills are documentation. When one needs to run something, it calls `agentkit`
rather than a script inside its own directory — a `PATH` command is the only
reference that resolves identically from Claude Code, Codex and Antigravity,
which install skills to three different places.

```bash
uv tool install --editable tools/agentkit
```

## Commands

```text
agentkit commit onboard|analyze|config        per-repo config, onboarding, history analysis
agentkit commit-safe init|verify|stamp|env    identity whitelist + commit timestamps
agentkit handoff commit [--safe/--plain]      delegate committing to the Antigravity CLI
agentkit handoff tasks                        what can be handed off
agentkit agy check|grant                      the allow-list headless agy needs
agentkit git summary                          working tree overview
```

## Exit codes

They are a contract — skills tell the calling agent what each one means.

| Code | Meaning |
|---|---|
| 0 | What was asked for happened |
| 1 | Nothing happened: no commit was created, or the identity was rejected |
| 2 | Unfinished: commits made with files left over, a loop guard tripped, or the config is unusable |
| 64 | The command line itself was wrong |

## Layout

```text
src/agentkit/
  cli.py          root command, error → exit code mapping
  errors.py       the exit-code contract
  gitutil.py      git helpers
  repoconfig.py   per-repository configuration and history analysis
  ui.py           tagged console output
  agy/            Antigravity CLI adapter: invocation, log parsing, permissions
  handoff/        generic delegate-and-verify runner + the task registry
  commitsafe/     config, identity whitelist, timestamp timeline
  commands/       click bindings (domain modules stay click-free)
```

Adding a handoff task means adding one entry to `handoff/tasks.py`: the skill to
invoke, the prompt, the grants it needs, and whether the runner should drive it
one unit at a time. The runner itself knows nothing about commits.

## Tests

```bash
cd tools/agentkit && uv run pytest     # package tests
tests/run-all.sh                       # repository-wide suites
```
