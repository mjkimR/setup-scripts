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
agentkit commit-safe commit -m … [--amend]    the checked, stamped `git commit` skills call
agentkit commit-safe init|verify|stamp|env    identity whitelist + commit timestamps
agentkit handoff commit [--safe/--plain]      delegate a commit via the checked AgentKit wrapper
                        [--hint L]... [--tests S]   advisory commit-unit labels + test attestation
agentkit handoff work --to agy|codex --doc F  have another agent CLI continue a handoff document
agentkit handoff prompt --doc F               print the pickup prompt for an interactive session
agentkit handoff tasks                        what can be handed off
agentkit agy check|grant                      the allow-list headless agy needs
agentkit git summary                          working tree overview
agentkit scratch path|onboard|clean           per-repo scratch space for agent working files
```

## Single-commit modes

`/git-commit low` uses a bounded staged patch preview; `/git-commit` uses the full
staged patch; `/git-commit high` permits additional targeted inspection. Every
mode uses medium message reasoning and creates at most one commit. In Codex the
direct skill sets medium effort on a Luna message worker; other hosts retain their runtime effort if no override is
available. `/handoff-commit` delegates the whole workflow instead.

Low uses only the supplied inventory and bounded preview for message generation.
Even when omitted changes are unclear, it forbids further diff, file, or history
reads and uses broader supported wording instead. It never upgrades modes automatically.

Low always skips agent-run tests, lint, builds, and `agentkit commit verify`,
regardless of configuration or prior attestations, and reports verification as
skipped (low mode). Default/high retain the configured verification workflow.
Commit guards and configured Git hooks still apply in every mode.

After staging the intended scope, `agentkit commit context` prints the repository
conventions, all staged paths, summary, and patch. Low limits only the patch to
200 lines / 16,000 characters and explicitly marks omitted content. Default/high
print the full patch. The command requires onboarding and a nonempty index, runs
from the repository root even when invoked in a subdirectory, and never stages,
verifies, commits, or launches an LLM. The skill owns those steps.

## Commit message cleanup

`agentkit commit-safe commit` removes `Co-Authored-By:` lines from supplied
`-m` messages by default, including repeated paragraphs and `--amend` messages.
Matching ignores case and leading spaces; other text and trailers are preserved.
Repositories with no config, or older configs without this setting, also default
to removal.

```bash
# Keep co-author lines for this repository (after onboarding).
agentkit commit config --set conventions.strip_co_authored_by=false

# Override the repository setting for one commit.
agentkit commit-safe commit --no-strip-co-authored-by -m '…'
agentkit commit-safe commit --strip-co-authored-by -m '…'
```

Onboarding also accepts `--strip-co-authored-by` (default) or
`--no-strip-co-authored-by`. Cleanup applies to the supplied messages before Git
runs; it does not rewrite existing history or text added later by Git hooks.

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
  commitsafe/     config, identity whitelist, timestamp timeline, pre-commit guards
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

### Commit workflow modes

`agentkit handoff commit --mode default` (the CLI default) runs enabled repository
verification before staging/delegation. Failure stops before agy is started. An explicit
`--tests` attestation skips duplicate verification. Disabled/unconfigured checks are
reported as skipped, not passed. The headless receiver never runs verification itself.

`--mode low` always skips runner verification and reports `skipped (low mode)`;
it overrides supplied attestations with `not-run`. Both modes invoke `/git-commit MODE`
and request `agentkit commit context --mode MODE` after staging. Low bounds the patch
while retaining every path; default uses the full staged patch. `--effort` remains a
separate model setting (medium by default). One commit is expected per handoff;
unexpected commit counts are reported as incomplete, without pushing or retrying.

Run `agentkit agy grant` to add the read-only context command permission when upgrading.
The Python runner's omitted mode retains the legacy caller-managed attestation behavior;
the CLI always passes an explicit workflow mode. Use `--no-push` to override repo push policy.

Headless `unsandboxed` denials are separate from `command(...)` permissions.
The default `agentkit agy grant` does not grant sandbox bypass. Such failures,
and denials with no identified command, require evidence review instead of an
automatic grant/retry. Conversation tool arguments are reported as unconfirmed
request candidates, never as proof of which command was denied.
