---
name: polish-doc
description: >-
  Use this skill to copyedit Markdown documents into natural Korean. Invoked
  headlessly through `agentkit handoff polish`, which supplies the target
  files, their scope, the 어체 style pack, and any caller instructions.
---

# Polish Doc

Copyedit Markdown prose into natural, idiomatic Korean. The usual input is
text drafted by an English-aligned coding agent: grammatically fine, but
translationese — English sentence structure wearing Korean words. The job is
to make it read as if it had been written in Korean from the start.

## Scope discipline

The caller's prompt lists every target with a scope. Honor it exactly:

- **changed-regions** — the file has a pending change; the prompt names the
  `git diff --cached` command that shows it. Polish only the sentences and
  paragraphs that change touches. Rewrite a touched sentence or paragraph as
  a whole when that is what natural phrasing needs, but text the diff does
  not touch stays byte-identical.
- **whole-file** — polish the entire document.

Edit files in place with the file-editing tools — edits are pre-approved.
Never print a rewrite instead of applying it. The only shell command
permitted is read-only `git diff`; everything else — `git status`, `git log`,
`git add`, `git commit`, `git restore` — is denied. The caller staged the
pre-polish state on purpose; touching the index destroys the user's rollback.

## Protected content

Never alter, in any scope:

- Code blocks and inline code (anything inside backticks)
- Frontmatter, URLs, link targets, image paths, file paths
- Identifiers, command names, flag names, config keys
- Markdown structure: heading levels, list nesting, table layout

Prose only. A "more natural" rewrite of a command name is a defect.

## Korean style rules

- 번역투를 걷어낸다. 영어 문장 구조를 그대로 옮긴 흔적이 교정 대상이다.
- 주어를 반복하지 않는다. "저는", "제가", "당신의", "귀하의"는 대부분 지운다.
- 피동을 능동으로. "~에 의해 처리됩니다" → "~가 처리합니다".
- 명사화를 동사로. "수정을 진행했습니다" → "수정했습니다". "확인이 필요합니다" → "확인해야 합니다".
- "~에 대한 / ~에 대해"를 남발하지 않는다. "이 함수에 대한 테스트" → "이 함수 테스트".
- "~할 수 있습니다", "~하는 것입니다", "~인 것 같습니다"를 반복하지 않는다.
- 접속부사를 직역하지 않는다. Additionally → "추가적으로" 말고 그냥 문장을 잇는다.
  However → "그러나"보다 "다만/근데". Therefore → "따라서"보다 "그래서".
- 한 문장에 관형절을 두 개 이상 쌓지 않는다. 끊어 쓴다.
- 기술 용어는 억지로 번역하지 않는다. 커밋, 브랜치, 마이그레이션, 캐시, 타임아웃, 롤백은 그대로 쓴다.

These rules hold at every 어체. The endings below are shown in the default
register (L3); the style pack decides how a sentence actually ends.

교정 예시:

- ❌ 이 변경사항은 인증 로직의 개선을 가능하게 합니다.
  ✅ 이 변경으로 인증 로직이 개선됩니다.
- ❌ 해당 파일에 대한 확인이 필요할 것으로 보입니다.
  ✅ 그 파일을 확인해야 할 것 같습니다.
- ❌ 테스트가 실패하고 있는 것으로 확인되었습니다.
  ✅ 테스트가 실패합니다.
- ❌ 추가적으로, 캐시 무효화 처리가 누락되어 있습니다.
  ✅ 캐시 무효화도 빠져 있습니다.
- ❌ 이 함수는 사용자에 의해 전달된 값을 검증하는 역할을 수행합니다.
  ✅ 이 함수는 사용자가 넘긴 값을 검증합니다.

Correct what reads unnaturally; keep what already reads well. A document that
needs nothing is a legitimate outcome — mark it CLEAN rather than inventing
changes to justify the run.

## 어체 — the style pack

Register is not a rule in this file; it arrives with the job. The prompt
lists every target under the pack it gets — `[L2 해라체 (평서형)]` — and then
carries those packs in full, each naming the 종결어미 to use, the phrasings to
avoid, how much 부연 is allowed, and the ❌/✅ pairs for that level. Follow the
pack for each file exactly.

One run can carry several packs, because a repository can map different paths
to different levels — an ADR at L2 while a README stays at L3. Read the group
headings before editing; do not assume one register for the whole run.

The ladder runs from L1 개조식 to L5 해요체, and the packs live in
`references/style/<language>/` in this skill directory. **A prompt with no
pack means Korean L3: read `references/style/ko/L3.md` and work from it.**
Never mix two levels in one document, and never invent a level between two
rungs.

Precedence, highest first:

1. Protected content — never overridden except by an instruction that names
   the exception explicitly.
2. Caller instructions, when the prompt carries them.
3. The style pack.
4. The default rules in this file.

## Caller instructions

The prompt may carry caller instructions (a terminology preference, an
audience note, a specific exception). They outrank the style pack and these
default rules where they conflict, and they can widen the job beyond
copyediting.

## The language filter

The style pack names the language it polishes, and the prompt states it as a
rule. That language is the whole job: prose in any other language stays
byte-identical, and a target with none of the target language in it is CLEAN,
not a translation request. A Korean run leaves an English paragraph exactly
where it is, and vice versa.

Mixed documents are the normal case, not an exception — polish the parts in
the target language and leave the rest alone. A caller instruction can widen
this, but nothing else can.

## Completion contract

This runs headlessly: never stop to ask a question. When done, end the reply
with exactly one line per target file, using the path exactly as the target
list spells it:

```
POLISHED: <file>   (the file was changed)
CLEAN: <file>      (nothing needed changing)
```

Then one more line per target file, naming the 어체 you applied to it:

```
STYLE: <file> L3
```

The caller verifies outcomes by hashing the files, so an unmarked or
mislabeled file is treated as a failed run — the marks must match what was
actually done. Hashes cannot see register, which is what the STYLE lines are
for: report the pack you actually worked from for each file, never the one
you assume was wanted.
