# Behavior Check

Compare the old snapshot from step 1 with the polished version on a few
realistic prompts. This is a lightweight check; building eval suites, graders,
or benchmarks with variance analysis is out of scope.

1. Write 2-3 prompts a user would send, with concrete paths and context.
   Include one near-miss: a related request the skill should decline or not
   trigger on. For an explicit-invocation-only skill, make the near-miss an
   invocation with an out-of-scope request.
2. Run each prompt in two fresh subagents, one given the old snapshot and one
   the new version. Give each only the skill path and the prompt, not the
   purpose of the comparison. Tell each to end its report with an ordered log
   of the files it opened and the steps it took; the parent sees only the
   report, not the subagent's transcript. Point them at scratch copies of any files the
   skill modifies. For a skill that commits, publishes, or calls external
   services, tell them to stop before that action and report what they would
   do. If the host cannot spawn subagents, report the check as not run.
3. Compare the logs and the outputs against the behavior inventory:
   - Each applicable inventory item is followed in both runs.
   - Both runs meet the output contract.
   - The near-miss is declined or left untriggered in both runs.
   - A section the new run rereads repeatedly belongs back in `SKILL.md`.
   - A reference the new run needed but did not open has a weak read condition.
   - An instruction both runs ignore is a candidate to cut.
4. When the outputs differ and the better one is unclear, give both outputs,
   unlabeled and in random order, with the prompt to a third subagent and ask
   which better serves the prompt and why.
5. If the new version regresses, restore the lost item and rerun that prompt.
6. If the runs show no difference, stop; do not add prompts to find one.
7. If added instructions do not improve the runs, revert them; remove only
   lines that are not on the behavior inventory.

Report each prompt, its verdict, and any fixes made.
