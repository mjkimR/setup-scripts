# 8. A level ladder for 어체, carried as style packs

- **Date**: 2026-08-19
- **Status**: Accepted
- **Extends**: [0006](./0006-delegate-korean-copyediting-to-antigravity.md)

## Context

The polish handoff (0006) shipped with exactly one register: a single line in
`polish-doc/SKILL.md` reading "담백한 합니다체". Anything else — an ADR that
wants 해라체, release notes that want 개조식, a notice that wants 해요체 — had
to go through `--instruction "합쇼체를 해요체로"`, a free-form line the caller
rewrites every time.

That is weak in three ways. The wording drifts between runs, so the output
does too. A one-line directive carries no examples, and a rule sentence
without ❌/✅ pairs gets read as a suggestion — the receiver hears "해요체" and
produces something adjacent to it. And nothing about a free-form string can be
regression-tested, which is the same reason the rubric was moved out of the
global prompt in the first place.

The natural fix is a named preset per register. The open question was how the
preset reaches a headless receiver, and whether presets should be named or
numbered.

## Decision

### Five levels, each a discrete pack

`--level 1..5`, from 1 개조식 to 5 해요체, with 3 담백한 합니다체 as the default
— the register the skill already used, so the flag changes nothing until it is
passed. Numbers, not names, because the axis is ordinal: "한 칸 낮춰" is a
thing users say, and a per-path default map (`docs/adr/** → 2`) stays short.

A level is an ordinal label for a fully specified pack, never a point on a
continuum. There is no 2.5 and nothing interpolates: each rung is a file
naming its 종결어미, its banned phrasings, its 부연 policy, its exclusions
(제목, 표 셀, 코드 캡션) and at least five ❌/✅ pairs.

A level collapses two axes that usually move together but need not — 종결형
(nominal → haera → hapnida → haeyo) and 친절도 (minimal → lean → expanded).
Both are declared in every pack's frontmatter, so the day a request needs them
apart ("짧게, 그런데 정중하게") one axis can be overridden without redesigning
the ladder.

Only the level-varying rules moved into the packs. 번역투 제거, 피동, 명사화,
접속부사, 관형절, and the protected-content list hold at every rung and stay in
the skill.

### The sender inlines the pack; the receiver acknowledges it

Packs ship inside the `polish-doc` skill directory, because an interactive
`/polish-doc` run reads them itself. The headless path does not rely on that:
`agentkit` reads the selected pack and inlines it into the prompt.

Leaving the read to the receiver looked cleaner and is the failure this
repository keeps designing against. The skill directory sits outside `agy`'s
`--add-dir` scope; a denied read in headless mode cannot prompt, so the run
would polish at whatever register it assumed and exit 0 — indistinguishable
from success. Inlining also makes the pack a string in the prompt, which is
testable.

Precedence is stated in the prompt: protected content, then caller
instructions, then the pack, then the skill's defaults. `--instruction`
survives for what no level covers — terminology, audience, one-off exceptions.

The completion contract gained a `STYLE: L<n>` line. File hashes prove edits
happened; they cannot see register, which is exactly the failure a wrong or
missing pack produces. A mark that is absent or names another level warns and
points at `git diff`; it does not change the exit code, because the edits did
land and re-running would re-polish finished files.

### Per-path levels, so one run can mix registers

`--level` sets one 어체 for a whole run. That is wrong for the common request
— "ADR은 해라체, 나머지는 기본" — and the obvious workaround is worse than it
looks: two runs at two levels cannot work, because the sweep targets every
Markdown file changed against HEAD, and a file the first run polished is still
changed. The second run picks it up again and re-registers it at its own
level.

So the mapping lives in the repository: `<git-dir>/agentkit-polish.json`,
`{"levels": {"<glob>": <level>}}`, consulted per target when `--level` is
absent. One run, one prompt, each file under the pack its path earned.

It is a second config file rather than a section in `agentkit-commit.json`,
because that file is created by commit onboarding and carries a schema
version, while polishing works in any repository. A level map that demanded
onboarding first would be a surprising coupling between two independent
handoffs.

Patterns match gitignore-style — `**` crosses separators, `*` does not, a
pattern without a separator matches the basename — and the first hit wins, so
narrow rules go on top. Last-match-wins was the alternative; first-match reads
the way people actually write these lists. A map that names a level with no
pack, or a value that is not a level, refuses the run instead of falling back
to the default: silently polishing at the wrong register is precisely the
outcome nobody would notice.

The `STYLE` acknowledgement became per file (`STYLE: <file> L2`) for the same
reason. With several packs in one prompt, "did the receiver use the right
one" is a per-file question, and a single run-wide mark could not answer it.

### The pack's language is also the run's filter

Packs are filed under `references/style/<language>/`, and each declares its
language in frontmatter; a pack whose frontmatter disagrees with its directory
is refused rather than guessed at. `--language` selects the pack set.

It doubles as a target filter. A changed-file sweep collects whatever is in
the tree, and handing an English-only document to a Korean polisher spends
five-hour-window quota to be told CLEAN. Files with no prose in the target
language are dropped before the call; if nothing survives, no call is made.

Detection is deliberately blunt — after stripping code fences, inline code,
URLs and frontmatter, does any of the language's script appear — and
deliberately one-sided: a language with no detector is never filtered. The
filter gates whether a file is handed over at all, so a false positive costs
one CLEAN mark while a false negative silently drops work the user asked for.
An explicitly named path is never filtered; naming a file states the intent
the filter would only be guessing at.

## Consequences

The 어체 is now a testable input. The runner's prompt tests assert which pack
was inlined, and the packs have their own shape tests — every rung present,
both axes declared, the required sections, the ❌/✅ pairs, and the
"지어내지 않는다" clause that keeps L4/L5's 부연 from turning a copyedit into
authorship.

Register consistency across a document is still not guaranteed in
changed-regions scope: prose the diff does not touch keeps its old 어체, so a
level applied there can leave a document mixed. The whole-file re-run that
fixes it re-polishes finished text, so it stays the user's call, and both
skills say so.

Adding a language is now a directory of packs plus one detector entry, and no
change to the runner. That is the extension this shape was chosen for; it is
untested until a second language actually exists.

The level map is unpopulated by design — no repository ships one, and the
patterns worth writing are the ones a few real runs reveal. Nothing writes the
file automatically either: `handoff-polish` can run `agentkit` and `git status`
and nothing else, so the map is the user's to save, which is the right owner
for a policy that decides how their documents read.
