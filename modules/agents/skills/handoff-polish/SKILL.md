---
name: handoff-polish
description: >-
  Use only when the user explicitly invokes /handoff-polish. Ignore otherwise.
allowed-tools: Bash(agentkit:*), Bash(git status:*)
---

# Handoff Polish

Delegates copyediting Markdown documents to the Antigravity CLI (`agy`),
which runs the `polish-doc` skill headlessly and edits the files in place.
Nothing is committed: the polish lands in the working tree for the user to
review.

## Why this exists

Korean prose drafted by this session tends toward translationese — English
sentence structure wearing Korean words — and self-review does not catch it,
because the same alignment that produced it judges it. The receiver edits
from a different footing, which is the entire value. **So never polish the
text yourself, and never re-review agy's edits for style afterwards** —
either one silently reintroduces the accent the handoff exists to remove.

## Rules

- Do NOT read the target documents, draft improvements, or "pre-clean" them
  before the handoff. `agy` does all of it.
- Do NOT run `git add`, `git restore`, or edit the target files yourself,
  before or after the handoff. The runner stages the pre-polish state so the
  user can undo with `git restore <file>`; touching the index or the files
  destroys that.
- Do NOT decide for yourself whether to retry. The `[ACTION]` line in a
  failure block states whether a retry is authorized; follow it.
- The handoff is synchronous and blocking. Make no other tool calls while it
  runs.

## Workflow

### Step 1: Run the handoff

```bash
agentkit handoff polish
```

With no arguments it targets every Markdown file changed against HEAD —
staged, unstaged, and untracked — and polishes only the changed regions.
Variants:

- `agentkit handoff polish --base <ref>` — widen the change window (e.g.
  docs already committed on this branch).
- `agentkit handoff polish <path> [<path>…]` — explicit files, polished
  whole. Paths outside the repository work too; the runner backs them up to
  the scratch space first, since git cannot restore them.

Options worth knowing, all with sane defaults:

- `--effort low|medium|high` — reasoning effort to ask `agy` for (default `medium`)
- `--timeout 600s` — passed to `agy`'s own print timeout
- `--verbose` — also print `agy`'s narration

One option carries what only this session knows:

- `--instruction "<one line>"` — repeatable. A directive for the polisher
  beyond default copyediting: a tone change ("합쇼체를 해요체로"), a
  terminology preference, an audience note. Pass the user's request close to
  their own words; do not invent instructions they did not give. No special
  request? Pass none — the default Korean-naturalness rubric applies.

Example — the user asked for a softer tone in the changed docs:

```bash
agentkit handoff polish --instruction "합니다체 유지하되 딱딱한 명령조는 풀어서"
```

### Step 2: Follow the directive, then report

On success, relay what the runner printed: which files were polished (with
the diffstat), which were already clean, and how to review or undo —
`git diff` shows exactly what the polisher changed, `git restore <file>`
undoes one file, and files outside the repository have pre-polish copies in
the printed backup directory. Do not open the diff to re-judge the style
yourself; the user is the reviewer.

On failure it prints a self-contained block. Do what the `[ACTION]` line
says and relay the `[REPORT]` line. If the block ever contradicts this file,
the block wins and this file is stale.

One thing the block cannot know is what this skill is allowed to run: only
`agentkit …` and `git status`. When a `[FIX]` command falls outside that,
hand it to the user instead of running it.

Exit codes: `0` polished or every file already clean, `1` nothing was
polished — refused preflights (bad --base, non-Markdown path) included, `2`
some files polished with the rest unaccounted — treat that as HALT and let
the user decide, since re-running would re-polish finished files. `64` is a
malformed command line — a bug in this skill, so report it.

## Known constraints

- **Exit code 0 from `agy` means nothing.** The runner hashes every target
  before and after and believes only that. Never treat `agy` narration as
  proof of an edit.
- **Edits are auto-approved via `--mode accept-edits`;** the one command
  grant the receiver needs is `command(git diff)`. Grant with
  `agentkit agy grant`; check with `agentkit agy check`.
- **Quota.** Each handoff spends Antigravity quota on a five-hour rolling
  limit. Keep it user-triggered; never loop or schedule it. A spent quota
  comes back as `[ACTION] DEFER` — report it and leave the retry to the
  user.
- Verified against `agy` 1.1.12. Re-test after a CLI update.
