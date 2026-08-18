---
name: polish-doc
description: >-
  Use this skill to copyedit Markdown documents into natural Korean. Invoked
  headlessly through `agentkit handoff polish`, which supplies the target
  files, their scope, and any caller instructions.
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
- 담백한 합니다체. "~하시기 바랍니다", "~해 주시길 부탁드립니다"는 쓰지 않는다.
- 기술 용어는 억지로 번역하지 않는다. 커밋, 브랜치, 마이그레이션, 캐시, 타임아웃, 롤백은 그대로 쓴다.

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

## Caller instructions

The prompt may carry caller instructions (a tone change, a different 어체, a
terminology preference). They override these style rules where the two
conflict, and they can widen the job beyond default copyediting. The
protected-content rules above still hold unless an instruction names the
exception explicitly.

## Non-Korean prose

The default job is Korean. Leave non-Korean prose untouched — a fully
English document is CLEAN, not a translation request — unless a caller
instruction says otherwise.

## Completion contract

This runs headlessly: never stop to ask a question. When done, end the reply
with exactly one line per target file, using the path exactly as the target
list spells it:

```
POLISHED: <file>   (the file was changed)
CLEAN: <file>      (nothing needed changing)
```

The caller verifies outcomes by hashing the files, so an unmarked or
mislabeled file is treated as a failed run — the marks must match what was
actually done.
