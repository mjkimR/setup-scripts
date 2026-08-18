# 5. Hook policy and repo verify commands

- **Date**: 2026-08-18
- **Status**: Accepted
- **Extends**: [0004](./0004-carry-caller-context-into-the-commit-handoff.md)

## Context

Two gaps surfaced while reviewing 0004 against repos this tooling might meet
later:

- **Git hooks.** A pre-commit hook runs inside `git commit` itself, untouched
  by agy's allow-list, so a hook that runs tests collides head-on with 0004's
  "intermediate commits may be red": mid-split commits get rejected, and the
  receiver — limited to six git commands — cannot fix what the hook complains
  about. Worse, `command(git commit)` is a prefix grant, so `--no-verify` is
  *already permitted*; whether the receiver bypasses hooks was an accident of
  prompting, not a policy.
- **Verification asymmetry.** The sender attests tests (0004) but may skip
  lint; and `/git-commit` used directly — no handoff, no attestation — had no
  verification step at all. Each repo also spells "run the tests" differently,
  and nothing recorded it.

## Decision

### Hook policy is repo config, decided at onboarding, never by the receiver

`hooks.policy` in `agentkit-commit.json`:

- **`bypass-intermediate` (default).** Commits that leave further changes
  uncommitted use `git commit --no-verify`; the commit that empties the
  working tree runs plain `git commit`. Hooks therefore run exactly once, on
  the final state — the state 0004 already declares the only guaranteed one —
  and hook cost stays constant regardless of split size. The instruction is
  injected into the handoff prompt from config, with an explicit "this is
  configured, not yours to decide": the receiver never chooses bypass on its
  own, in either direction.
- **`run-all` — reserved, closed.** Keeping every intermediate commit
  hook-green would constrain grouping in ways nothing implements yet. The
  option is visible (onboarding choice, config value) so the option space is
  honest, but selecting it fails loudly as *not implemented* — at onboarding,
  at `config --set`, and at handoff preflight (the JSON is just a file; a
  hand-edited value must not slip through). Failing loudly beats silently
  degrading into bypass.

### Repo verify commands, captured at onboarding

`verify.test` and `verify.lint` hold the shell commands that verify this
repo's tree (e.g. `uv run pytest -q`, `ruff check`). Onboarding asks for
them; a repo without a ready entry point chooses between generating a script
(store its path) or storing the raw command. **Empty means skip** — an
unconfigured field disables that verification everywhere, deliberately.

Two properties are load-bearing:

- **Skippability is first-class.** `verify.enabled` switches all verification
  off while keeping the commands on record. The driving case is a shared repo
  whose tests are known-broken and mid-repair: it must be able to opt out
  without erasing configuration it will want back. Off means genuinely off —
  `agentkit commit verify` prints `[SKIP]` and exits 0, and the handoff nudge
  stays silent rather than nagging about an opt-out the repo made on purpose.
- **Transparency is the execution contract.** Whoever runs verification must
  show the exact command line. `agentkit commit verify` exists as the default
  runner precisely because it echoes each command verbatim (`[verify] $ …`)
  before executing it and propagates the failing exit code; skips and
  unconfigured states print too, never silently succeed. An agent may instead
  treat the config as a hint and run the commands itself — its own tool calls
  are visible — but running verification in a way that hides what executed is
  out of contract either way.

Who runs them, by entry point:

- **Sender, before a handoff.** Running the configured commands is part of
  finishing the work, not part of the handoff skill. Omitting `--tests` while
  verify commands are configured prints a one-line nudge (never a gate)
  naming the commands, since the receiver cannot recover a forgotten
  attestation. This supersedes 0004's "never launch a test run just to fill
  the flag in": the flag-filling ban remains for unconfigured repos, but
  configured commands are the definition of finished work — lint included.
- **`/git-commit` directly (interactive).** With no caller attestation, run
  the configured commands before staging anything; surface failures before
  committing rather than after. Committing anyway is the user's call, not a
  default.
- **Receiver, in a handoff.** Never. Only git is permitted, the attestation
  (or its absence) governs, and the verify commands are deliberately kept out
  of the handoff prompt.

## Consequences

- A hook-bearing repo now behaves predictably: intermediate red commits
  cannot be rejected by hooks, and the final commit still honors the repo's
  own gate. A modifying hook (formatter) can still dirty the tree at the
  final commit — that surfaces as the existing leftover-files INCOMPLETE
  path, which is the correct signal.
- Bypass is now an explicit, auditable config decision instead of an
  emergent behavior of a prefix permission. On shared repos where hooks are a
  team contract, onboarding is where that conversation happens.
- `run-all` is a promise of shape, not of delivery: implementing it later
  means teaching grouping to respect per-commit greenness (and paying hooks
  per commit), at which point the not-implemented guards turn into the
  feature.
- The sender-side nudge depends on honest attestations; nothing verifies
  them (0004's trust boundary, unchanged).
- `agentkit commit verify` executes repo-config shell strings, so a skill
  allow-list entry like `Bash(agentkit:*)` now transitively permits whatever
  the repo's own config names. That is the intended trust model — the config
  lives in `.git/`, written by the repo's owner — and the verbatim echo is
  what keeps the escalation visible rather than silent.
