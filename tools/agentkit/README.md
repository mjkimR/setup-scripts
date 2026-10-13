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
agentkit commit context [--mode low|default|high]  conventions + staged diff; no mutations
agentkit commit verify [--only test|lint]     run the repo's verify commands, echoing each first
agentkit handoff work --to agy|codex --doc F  have another agent CLI continue a handoff document
agentkit handoff prompt --doc F               print the pickup prompt for an interactive session
agentkit handoff polish [paths…]              delegate Markdown copyediting to agy
agentkit handoff tasks                        what can be handed off
agentkit agy check|grant                      the allow-list headless agy needs
agentkit git summary                          working tree overview
agentkit scratch path|onboard|clean           per-repo scratch space for agent working files
agentkit devkit copy-diff                     export staged diff to temp file & copy to clipboard
agentkit devkit prompt commit|review          generate commit message or code review prompt
devkit copy-diff|prompt                       standalone CLI alias (installed alongside agentkit)
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
| 1 | Nothing happened: no work was performed or task failed |
| 2 | Unfinished: tasks made partial progress, a loop guard tripped, or the config is unusable |
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
  devkit/         personal developer utilities (diff export, review/commit prompts, clipboard)
  handoff/        work: continue a handoff document (spec/progress/result); polish: copyediting delegation
  commands/       click bindings (domain modules stay click-free)
```

Adding a handoff task means adding one entry to `handoff/tasks.py`: the skill to
invoke, the prompt, the grants it needs, and whether the runner should drive it
one unit at a time.

## Developer utilities (devkit)

Personal developer utilities for sharing Git changes with an AI chat.
Available via `agentkit devkit` or directly as `devkit`:

```bash
devkit copy-diff                         # staged diff file, copied as a macOS attachment
devkit copy-diff feature --head          # tracked staged + unstaged changes, feature.txt
devkit copy-diff --last --no-copy         # latest commit to a file; print its path
devkit prompt commit -l Korean           # copy a commit-message prompt
devkit prompt review -l Korean           # copy a staged review prompt
devkit prompt review --last --stdout     # print a prompt without clipboard access
devkit prompt review --head --exclude uv.lock --stdout
```

All commands read from the repository root. Untracked files are omitted; stage intended
files to include them.

## Tests

```bash
cd tools/agentkit && uv run pytest     # package tests
tests/run-all.sh                       # repository-wide suites
```

## Markdown polish

`agentkit handoff polish [paths…]` runs the copyediting skill through agy and
verifies file outcomes. The staged pre-polish state supports undo with Git restore;
see the [copyediting skill](../../modules/agents/skills/polish-doc/SKILL.md) for scope.

`--level` chooses L1 개조식, L2 해라체, L3 담백한 합니다체 (default), L4 합니다체(완곡),
or L5 해요체. `--language` selects style packs and filters targets to that language.
Run `agentkit handoff polish --list-levels` for the available levels. Packs live under
`modules/agents/skills/polish-doc/references/style/<language>/`.

Without `--level`, repository configuration in `<common-git-dir>/agentkit-polish.json`
can choose per-file levels:

```json
{"levels": {"docs/decisions/**": 2, "*.md": 3}}
```

Patterns use gitignore-style matching; the first match wins, so put specific rules
first. A bare pattern matches basenames and `**` crosses directories.
`agentkit agy grant` installs required command grants: diff-scoped polish needs
`command(git diff)`; explicit whole-file runs do not.
The runner checks Git/file state rather than relying on agy's exit status alone.

Git commit gates and hooks are handled by the separate `devkit-gates` CLI.
`agentkit commit onboard` configures agentkit conventions and verification workflows
without managing Git hooks.
