---
name: research-req
description: >-
  Prepare focused, standalone prompt files for Gemini Deep Research. Use only
  when the user explicitly invokes /research-req or $research-req.
disable-model-invocation: true
---

# Research Request

Turn the user's research intent into independently usable prompt files for
Gemini Deep Research. Use the current conversation to supply relevant context.

## Select the research topics

- With a request after the invocation, prioritize that request. Carry forward
  relevant goals, constraints, and decisions; ask only for missing information
  that would materially change the research. Otherwise proceed to drafting.
- Without a request, inspect the available discussion for unresolved questions
  whose answers could change a decision. Present a short list with each topic's
  key question and the decision it informs, then wait for the user to select
  topics before writing prompts. If none merit external research, say so and
  stop. Do not invent research merely to produce an artifact.
- Prefer questions that benefit from comparing external sources. Local code
  inspection or a simple documentation lookup usually does not merit a deep
  research request. Do not conduct the research while preparing its prompts.

## Split by research objective

Give each independent topic its own prompt. Split topics that need substantially
different search scopes or support separate decisions. Keep tightly related
subquestions together when they support one objective; do not mechanically split
every question or force unrelated questions into one report.

Each prompt must work in a fresh Gemini chat. Repeat the necessary shared context
in each file. Never require Gemini to read another prompt, local repository path,
or this conversation. When one investigation depends on another's findings,
identify the sequence; do not invent those findings to make later prompts appear
ready. Draft the independent requests first and explain what remains dependent.

## Write copy-ready prompts

Write in the user's language unless they request another language. Include only
the material needed for that topic, adapting the structure to the investigation:

- The objective and decision the research should inform.
- Relevant background, constraints, known facts, and assumptions, distinguished
  from one another. Do not include secrets or unrelated private context.
- Focused questions, scope boundaries, and relevant dates, versions, or regions.
- Evidence expectations: prioritize primary sources; attach source URLs to major
  claims; distinguish documented facts, inference, and recommendations; identify
  conflicting evidence, missing evidence, and relevant applicability limits.
- Ask for counterevidence to the current hypothesis and alternatives when useful.
- Request a concise summary followed by question-specific findings, supporting
  sources, conditional recommendations, and unresolved questions. Scale detail
  to the topic rather than imposing a long report or a fixed source count.

The file itself is the complete text to paste into Gemini: no surrounding code
fence, setup instructions, unfilled placeholders, or references such as "as
discussed above." Put any user-facing usage notes outside the prompt file.

## Save and deliver

Run `agentkit scratch path research` to resolve the shared research directory.
Use the returned absolute path; do not hardcode `.agents/tmp` or create a competing
scratch location. If the command is unavailable or fails, report the prerequisite
or error instead of silently changing the storage contract.

Create a new `<YYYY-MM-DD-HHMMSS>-<slug>/` batch directory using the actual current
date and time. Add a suffix if it already exists; never overwrite another batch.
Create one numbered topic directory per independent request:

```text
<batch>/
  01-<topic>/prompt.md
  02-<topic>/prompt.md
```

Re-read each prompt for self-containment, topic focus, and copy readiness. Return
a short numbered list with the topic, purpose, and clickable absolute link to
each `prompt.md`. Explain any research ordering. Tell the user to paste each
file's entire content into a separate Deep Research request and later supply the
downloaded result file to `research-review`, ideally with its matching prompt.
Do not reproduce all prompt bodies in the chat, use the clipboard, or submit
requests to Gemini. Generating prompts does not initiate external research.
