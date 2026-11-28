---
name: decision-brief
description: >-
  Lays out the decisions pending in the current work with a recommendation for
  each, comparing options only where the choice is a real trade-off. Use only
  when the user explicitly invokes /decision-brief or $decision-brief.
disable-model-invocation: true
---

# Decision Brief

Help the user settle open decisions quickly. Spend their attention only where
their judgment changes the outcome.

## Input

Text after the invocation scopes the decisions. Without it, cover the
decisions pending in the work under discussion. If nothing is pending, say so
instead of inventing decisions.

## Procedure

1. **Collect.** List each open decision as one question. Leave out what the
   user has already decided; do not re-open it. Merge decisions that are one
   choice in disguise, and note dependencies (decision B only matters if A
   goes one way).
2. **Ground.** Verify each premise a recommendation depends on that a file
   read or a quick command can settle; read the code, config, or docs instead
   of answering from memory. Mark the premises you could not verify.
3. **Classify** each decision by the first rule that matches:
   1. **Compare** if the answer hinges on information only the user has.
   2. **Recommend-only** if the alternatives differ trivially or are cheap to
      reverse, even when the call is close.
   3. **Recommend-only** if one option is clearly better on what matters here.
   4. **Compare** otherwise: viable options trade off along dimensions where
      the user's priorities decide, or it is a close call.
4. **Challenge.** Run the challenger for every decision that meets at least
   one trigger, and record which trigger labels each decision meets:
   - `irreversible`: costly or hard to reverse, such as a data schema, public
     interface, architecture recorded in an ADR, migration, purchase, or
     external commitment.
   - `hidden alternatives`: classified recommend-only and affects behavior,
     interfaces, or data beyond the current change, even if reversible. The
     user will not see the alternatives, so nobody else can catch a wrong
     "this is obvious".
   - `unverified premise`: the recommendation rests on a premise marked in
     step 2.
   - `user request`: the user asks for verification.

   Send all triggered decisions to one fresh subagent. Pass the absolute path
   of [roles/challenger.md](roles/challenger.md) as its contract, the working
   directory, relevant file paths, and for each decision the question,
   context, constraints, and the options you know, unranked. Do not pass your
   recommendation, ranking, or classification. If no decision meets a
   trigger, skip this step.
5. **Reconcile** each challenged decision against the challenger's fields, in
   this order:
   1. Premises. If its Premises contradict one of yours, re-check that premise
      by a file read or command. If yours is wrong, correct it, redo your pick
      and step 3 with the corrected premise, apply items 2-4 to the result, and
      count it as a premise correction. If it verified a premise you marked
      unverified, confirm it the same way and drop that unverified-premise
      line.
   2. If its disagreement rests on a factual error of its own that you confirm
      by a file read or command, keep your result, count it as a rejection,
      and skip item 3.
   3. If its Pick differs, its Margin is `close`, or a Missing item would
      change your pick or add a cost the user must weigh: switch to compare
      and include its option and argument. If the decision is already a
      compare, add its option if new and answer its argument in the
      recommendation, and count it as incorporated. Otherwise keep your
      classification.
   4. If the decision ends up a compare, use its Strongest risk and its case
      for the best alternative in the cons entries and the flip condition.
6. **Present** in the format below, then stop. Do not act on the
   recommendations until the user responds, unless the invocation says to
   proceed.

## Output

Write in the language of the conversation. The labels in the templates, the
trigger labels in step 4, and the verification line are English examples;
translate every one of them into that language. Order decisions by
dependency, then by impact.
Add the optional lines when they apply: the dependency line right under the
question, the unverified-premise line last.

Recommend-only:

```
**1. <question>**
(applies only if #<n> is <option>)
Recommendation: <option>. <1-2 lines why.> (<rejected alternative>: <one-line reason>)
Unverified premise: <premise>
```

Include the rejected-alternative parenthetical only when that alternative is a
common default or one the user mentioned.

Compare:

```
**2. <question>**
(applies only if #<n> is <option>)
- <option A>: pros … / cons …
- <option B>: pros … / cons …
Recommendation: <option>. <why, given the trade-off.> <what would flip it to another option.>
Unverified premise: <premise>
```

Use a table instead of bullets when three or more options share the same
dimensions. Keep pros and cons to what discriminates between the options.

Close with one verification line, using the trigger labels from step 4:

- `Verification: challenger ran (<decision numbers>; triggers: <labels>) → <result>`,
  where `<result>` is `agreed`, or whichever of `<n> premise corrected`,
  `<n> switched to compare`, `<n> rebuttal incorporated`, and
  `<n> challenger factual error rejected` occurred, joined by commas.
- `Verification: skipped (no trigger met)`
