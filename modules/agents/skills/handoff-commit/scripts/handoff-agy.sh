#!/usr/bin/env bash

# Hands the commit workflow to the Antigravity CLI (agy) in headless print mode
# and verifies the outcome from git state.
#
# agy exits 0 and reports "status":"SUCCESS" even when a tool call was
# auto-denied for lack of permission — headless mode has nobody to prompt, so it
# soft-denies and finishes cleanly with an empty response. The exit code and the
# JSON status therefore carry no signal at all. Whether HEAD moved is the only
# trustworthy result, so every run is verified against a snapshot taken first.
#
# Verified against agy 1.1.12.

set -uo pipefail

TIMEOUT="${HANDOFF_AGY_TIMEOUT:-600s}"
EFFORT="${HANDOFF_AGY_EFFORT:-low}"

WORK_LOG=""
AGY_LOG=""
cleanup() { rm -f ${WORK_LOG:+"$WORK_LOG"} ${AGY_LOG:+"$AGY_LOG"}; }
trap cleanup EXIT

# agy's own log records the exact command string that failed a permission check,
# which its stdout never reveals. Pinning the log path is the only way to tell
# "you never granted anything" apart from "one specific command is missing".
denied_commands() {
  [ -n "$AGY_LOG" ] && [ -f "$AGY_LOG" ] || return 0
  sed -n 's/.*permission check failed for command "\([^"]*\)".*/\1/p' "$AGY_LOG" | sort -u
}

note() { printf '[handoff] %s\n' "$*"; }
die() { printf '[handoff] ERROR: %s\n' "$*" >&2; exit 1; }

# --- Pre-flight ------------------------------------------------------------

command -v agy >/dev/null 2>&1 \
  || die "agy not found on PATH. Install the Antigravity CLI first."

git rev-parse --git-dir >/dev/null 2>&1 \
  || die "not inside a git repository."

REPO_ROOT="$(git rev-parse --show-toplevel)"

# Refuse to start without the grants rather than discovering it after a wasted
# agy round trip. Headless agy soft-denies and reports success, so a missing
# grant otherwise looks like "the model decided not to commit".
AGY_SETTINGS="$HOME/.gemini/antigravity-cli/settings.json"
AGY_CONFIG="$HOME/.gemini/config/config.json"
MISSING=()
for grant in "command(git add)" "command(git commit)" "command(git ls-files)"; do
  grep -qF "\"$grant\"" "$AGY_SETTINGS" "$AGY_CONFIG" 2>/dev/null || MISSING+=("$grant")
done
if [ "${#MISSING[@]}" -gt 0 ]; then
  printf '[handoff] ERROR: agy is missing required permission grants:\n' >&2
  printf '            %s\n' "${MISSING[@]}" >&2
  printf '[handoff] Headless agy cannot prompt, so it would silently commit nothing.\n' >&2
  printf '[handoff] Fix: bash %s\n' \
    "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)/setup-permissions.sh" >&2
  exit 1
fi

if [ -z "$(git status --porcelain)" ]; then
  note "Working tree is clean — nothing to commit. Skipping handoff."
  exit 0
fi

# An empty repository has no HEAD yet; the empty string stands in for "no commits".
HEAD_BEFORE="$(git rev-parse HEAD 2>/dev/null || true)"

PENDING_COUNT="$(git status --porcelain | wc -l | tr -d ' ')"
note "Delegating $PENDING_COUNT pending file(s) to agy (effort=$EFFORT, timeout=$TIMEOUT)…"

# --- Handoff ---------------------------------------------------------------

WORK_LOG="$(mktemp -t handoff-agy)"
AGY_LOG="$(mktemp -t handoff-agy-log)"

# --add-dir is not optional. Without it agy resolves its own workspace from its
# stored project list and runs commands in whatever repository it used last,
# which with git add/commit granted means commits landing in the wrong repo.
agy -p "/git-commit

Work only in $REPO_ROOT — that is the repository to commit. Commit every pending
change in it now.

Only git commands are permitted, and only these: log, diff, status, ls-files,
add, commit. Anything else — cat, ls, pwd, bash, git-summary.sh, and notably
\`git reset\` — is denied, and in a && chain one denied segment kills the whole
command. To read an untracked file, \`git add\` it and use
\`git diff --cached <path>\`; never the \`git add -N\` … \`git reset\` round trip.
A denial is not a reason to stop: carry on with git and finish the job.
If you cannot tell whether some file belongs in a commit, leave it uncommitted
and say so at the end." \
  --add-dir "$REPO_ROOT" \
  --effort "$EFFORT" \
  --print-timeout "$TIMEOUT" \
  --log-file "$AGY_LOG" \
  >"$WORK_LOG" 2>&1

# agy narrates what it did, at this user's `verbosity: high` setting and with
# absolute file:// links. On success that prose is unbounded and says nothing the
# git-derived summary below does not say authoritatively, so it is dropped —
# the caller is a coding agent paying for every token of it. Failures print it
# in full, where it is the only diagnostic available.
show_agy_output() {
  printf '\n----- agy output -----\n'
  cat "$WORK_LOG"
  printf -- '----------------------\n\n'
}

[ -n "${HANDOFF_VERBOSE:-}" ] && show_agy_output

# --- Verification ----------------------------------------------------------

HEAD_AFTER="$(git rev-parse HEAD 2>/dev/null || true)"

if [ "$HEAD_BEFORE" = "$HEAD_AFTER" ]; then
  [ -z "${HANDOFF_VERBOSE:-}" ] && show_agy_output
  printf '[handoff] ERROR: agy produced no commit — HEAD did not move.\n' >&2

  if grep -qi 'headless mode cannot prompt' "$WORK_LOG"; then
    printf '[handoff] Cause: a command was auto-denied for lack of permission:\n' >&2
    denied_commands | sed 's/^/            /' >&2
    printf '[handoff] Fix:   add a matching command(...) rule, e.g. via\n' >&2
    printf '[handoff]        bash %s\n' \
      "$(dirname "${BASH_SOURCE[0]}")/setup-permissions.sh" >&2
  elif grep -qiE 'auth|login|credential|unauthenticated|token' "$WORK_LOG"; then
    printf '[handoff] Cause: looks like an authentication failure.\n' >&2
    printf '[handoff] Fix:   run `agy` interactively once to refresh the login.\n' >&2
  else
    printf '[handoff] See the agy output above for the cause.\n' >&2
  fi

  printf '[handoff] The working tree was left untouched. No retry was attempted.\n' >&2
  exit 1
fi

if [ -n "$HEAD_BEFORE" ]; then
  RANGE="$HEAD_BEFORE..$HEAD_AFTER"
else
  RANGE="$HEAD_AFTER"
fi

NEW_COUNT="$(git rev-list --count "$RANGE")"
note "Created $NEW_COUNT commit(s):"
git log --format='  %h  %s' "$RANGE"

REMAINING="$(git status --porcelain)"
if [ -n "$REMAINING" ]; then
  # A partial commit is an anomaly the caller has to act on, so the reason agy
  # gave for stopping short is worth the tokens here.
  [ -z "${HANDOFF_VERBOSE:-}" ] && show_agy_output
  note "WARNING: uncommitted changes remain:"
  printf '%s\n' "$REMAINING" | sed 's/^/  /'
  exit 2
fi

note "Working tree is clean."
