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
agentkit commit verify [--only test|lint]     run the repo's verify commands, echoing each first
agentkit commit-safe init|verify|stamp|env    identity whitelist + commit timestamps
agentkit handoff commit [--safe/--plain]      delegate committing to the Antigravity CLI
                        [--hint L]... [--tests S]   advisory commit-unit labels + test attestation
agentkit handoff work --to agy|codex --doc F  have another agent CLI continue a handoff document
agentkit handoff prompt --doc F               print the pickup prompt for an interactive session
agentkit handoff tasks                        what can be handed off
agentkit agy check|grant                      the allow-list headless agy needs
agentkit git summary                          working tree overview
agentkit scratch path|onboard|clean           per-repo scratch space for agent working files
```

## Scratch space

Skills that need somewhere to put working files (handoff documents, reports,
intermediate state) must not invent their own locations. The contract is one
command:

```bash
agentkit scratch path <skill-name>   # prints an absolute directory, created
```

First use in a repository adopts `.agents/tmp/` and registers it in
`.git/info/exclude` — visible in the IDE project tree, invisible to
`git status`, and no tree change to commit. `agentkit scratch onboard` changes
the root or, with `--shared`, moves the ignore entry into the committed
`.gitignore`. Outside a git repository the path falls back under
`~/.agents/tmp/`. Rationale in `docs/decisions/0003`.

## Work handoff files

`agentkit handoff work` expects three files sharing one stem in the scratch
directory, each with a single writer and a single meaning:

| File | Written by | Meaning |
|---|---|---|
| `<stem>.md` | the sending agent | the spec — read-only for the receiver |
| `<stem>-progress.md` | sender writes the empty checklist, receiver ticks it | live status; `tail -f` it during a run, and it is what a resumed run reads to skip finished steps |
| `<stem>-result.md` | the receiver, once, at the end | the completion report — its **existence** is the only signal that the run finished |

Progress therefore never goes in the result file: that would make a half-done
run indistinguishable from a finished one. Checkboxes are advisory — the verdict
comes from the document's own verification commands. Rationale in
`docs/decisions/0007`.

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
  scratch.py      per-repository scratch space for agent working files
  ui.py           tagged console output
  agy/            Antigravity CLI adapter: invocation, log parsing, permissions
  codex/          Codex CLI adapter: headless `codex exec` invocation
  handoff/        commit: delegate-and-verify runner + task registry; work: continue a handoff document (spec/progress/result)
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
