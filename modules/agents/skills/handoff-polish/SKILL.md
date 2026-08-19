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

**Which form to use when a 어체 is requested.** A register change is a
document-level job, but the sweep is a diff-level one:

- "이 문서 L2로 바꿔줘" — name the path:
  `agentkit handoff polish --level 2 docs/guide.md`. The sweep would
  re-register only the paragraphs that happen to sit in the diff and leave
  the rest of the document in its old 어체.
- No level named, or "고친 데만" — the sweep is right.
- A brand-new untracked file is the whole of its own change, so the sweep
  registers all of it either way; no path needed.

**Different 어체 for different files is a map, not two runs.** A request like
"ADR은 해라체, 나머지는 기본" is answered by the repository's level map, which
one run honors per file:

```json
{"levels": {"docs/decisions/**": 2, "*.md": 3}}
```

It lives at `agentkit-polish.json` under the git directory (`.git/` in a
normal checkout), patterns match gitignore-style with the first hit winning,
and `agentkit handoff polish --list-levels` prints the active map. Writing
that file is the user's call and outside this skill's tools — show them the
JSON and let them save it, or offer to have the session write it.

Two passes at different levels is the wrong answer, and worth saying out loud
if it comes up: the sweep targets everything changed against HEAD, so a file
the first pass polished is still changed and the second pass re-registers it.
`--level` also applies to every target in the run, overriding the map.

Options worth knowing, all with sane defaults:

- `--level 1..5` — the 어체 to polish into (default `3`). One discrete style
  pack per rung, never a point between two:

  | Level | 어체 | Fits |
  |---|---|---|
  | 1 | 개조식 (명사형 종결) | 릴리스 노트, 체크리스트, 표 |
  | 2 | 해라체 "~한다" | ADR, 기술 노트 |
  | 3 | 담백한 합니다체 | README, 가이드 (default) |
  | 4 | 합니다체 (완곡) | 온보딩, 대외 문서 |
  | 5 | 해요체 (정중·친절) | 공지, 사용자 안내 |

  `agentkit handoff polish --list-levels` prints the same ladder from the
  packs themselves. Pass a level when the user asks for one in any words
  ("좀 더 딱딱하게", "개조식으로", "친절하게") — map it to a rung rather than
  writing the request out as an instruction.
- `--language ko` — which language to polish (default `ko`, the only pack set
  installed). It doubles as a filter: prose in other languages is left alone,
  and changed files with none of the target language never reach `agy` at all,
  so an English-only doc in the sweep costs no quota. An explicitly named path
  is always sent — naming it states the intent the filter would only guess at.
- `--effort low|medium|high` — reasoning effort to ask `agy` for (default `medium`)
- `--timeout 600s` — passed to `agy`'s own print timeout
- `--verbose` — also print `agy`'s narration

One option carries what only this session knows:

- `--instruction "<one line>"` — repeatable. A directive that no level covers:
  a terminology preference, an audience note, a specific exception. It outranks
  the style pack where the two conflict. Pass the user's request close to their
  own words; do not invent instructions they did not give. A plain 어체 request
  is `--level`, not an instruction — the level carries its own rules and
  examples, which a one-line paraphrase does not.

Example — the user asked for warmer docs that keep one term untranslated:

```bash
agentkit handoff polish --level 4 --instruction "handoff는 번역하지 말고 그대로"
```

### Step 2: Follow the directive, then report

On success, relay what the runner printed: which files were polished (with
the diffstat and the 어체 they were polished into), which were already clean,
and how to review or undo — `git diff` shows exactly what the polisher
changed, `git restore <file>` undoes one file, and files outside the
repository have pre-polish copies in the printed backup directory. Do not open the diff to re-judge the style
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

- **A 어체 warning is not a failure.** The runner asks the polisher to echo
  the style pack it applied to each file and warns when that acknowledgement
  is missing or names another level. The edits still landed and the exit code still holds;
  relay the warning and point at `git diff`, since register is the one thing
  the hashes cannot verify.
- **A skipped file is not a failure.** "Skipped N file(s) with no Korean
  prose" is the language filter doing its job. Relay it; do not re-run those
  files as explicit paths to force them through unless the user asks.
- **A level on changed regions only re-registers what changed.** Prose the
  diff does not touch keeps its current 어체, so a document can come back
  mixed. Re-running with explicit paths (whole-file) is the fix, and it is the
  user's call — do not do it unasked.
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
