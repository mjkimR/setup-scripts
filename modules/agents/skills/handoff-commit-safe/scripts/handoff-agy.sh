#!/usr/bin/env bash

# Hands the safe commit workflow to the Antigravity CLI (agy) in headless print
# mode, keeping the git-commit-safe guarantees on this side of the handoff.
#
# The email whitelist check and the timestamp resolution run here, not inside
# agy. Two reasons:
#
#   1. Fail-fast safety. A whitelist violation aborts before any quota is spent,
#      and enforcement never depends on a model choosing to run the check.
#   2. Narrow permissions. agy inherits GIT_AUTHOR_DATE / GIT_COMMITTER_DATE from
#      this process and runs a plain `git commit`, so it needs only
#      command(git add) and command(git commit) — no command(bash) or
#      command(eval), which the inline `eval "$(verify-safe.sh --env)"` form
#      would have required.
#
# Environment variables are fixed once a process starts, so agy is invoked once
# per atomic unit with a freshly resolved timestamp each time. That preserves the
# monotonic progression a single batched call would have collapsed into one
# identical timestamp for every commit.
#
# Verified against agy 1.1.12.

set -uo pipefail

TIMEOUT="${HANDOFF_AGY_TIMEOUT:-600s}"
EFFORT="${HANDOFF_AGY_EFFORT:-low}"
MAX_UNITS="${HANDOFF_MAX_UNITS:-10}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"

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

note() { printf '[handoff-safe] %s\n' "$*"; }
die() { printf '[handoff-safe] ERROR: %s\n' "$*" >&2; exit 1; }

# --- Pre-flight ------------------------------------------------------------

command -v agy >/dev/null 2>&1 \
  || die "agy not found on PATH. Install the Antigravity CLI first."
command -v python3 >/dev/null 2>&1 \
  || die "python3 is required by the git-commit-safe time resolver."

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
  printf '[handoff-safe] ERROR: agy is missing required permission grants:\n' >&2
  printf '                 %s\n' "${MISSING[@]}" >&2
  printf '[handoff-safe] Headless agy cannot prompt, so it would silently commit nothing.\n' >&2
  printf '[handoff-safe] Fix: bash %s\n' \
    "$SCRIPT_DIR/../../handoff-commit/scripts/setup-permissions.sh" >&2
  exit 1
fi

# pwd -P above resolved the install symlink back into the source repository, so
# the sibling skill is reachable relatively. The agy install path is a fallback.
RESOLVER="$SCRIPT_DIR/../../git-commit-safe/scripts/resolve-time.py"
if [ ! -f "$RESOLVER" ]; then
  RESOLVER="$HOME/.gemini/config/skills/git-commit-safe/scripts/resolve-time.py"
fi
[ -f "$RESOLVER" ] || die "git-commit-safe resolver not found. Install the git-commit-safe skill."

if [ -z "$(git status --porcelain)" ]; then
  note "Working tree is clean — nothing to commit. Skipping handoff."
  exit 0
fi

note "Delegating $(git status --porcelain | wc -l | tr -d ' ') pending file(s) to agy, one atomic unit per call…"

# --- One agy call per atomic unit ------------------------------------------

WORK_LOG="$(mktemp -t handoff-agy-safe)"
AGY_LOG="$(mktemp -t handoff-agy-safe-log)"
UNIT=0
COMMITTED=0

while [ -n "$(git status --porcelain)" ]; do
  UNIT=$((UNIT + 1))
  if [ "$UNIT" -gt "$MAX_UNITS" ]; then
    printf '[handoff-safe] ERROR: stopped after %s units with changes still pending.\n' \
      "$MAX_UNITS" >&2
    printf '[handoff-safe] Raise HANDOFF_MAX_UNITS if the split is legitimately this large.\n' >&2
    exit 2
  fi

  # Validates the whitelist and advances the timestamp state. A non-zero exit
  # here is a config or identity failure; its message is already on stderr.
  STAMP="$(python3 "$RESOLVER" --stamp)" || exit $?
  export GIT_AUTHOR_DATE="$STAMP"
  export GIT_COMMITTER_DATE="$STAMP"

  note "Unit $UNIT — delegating to agy (stamp: $STAMP)…"

  HEAD_BEFORE="$(git rev-parse HEAD 2>/dev/null || true)"

  # --add-dir is not optional. Without it agy resolves its own workspace from
  # its stored project list and runs commands in whatever repository it used
  # last, which with git add/commit granted means commits in the wrong repo.
  agy -p "/git-commit-safe

Work only in $REPO_ROOT — that is the repository to commit.

Only git commands are permitted, and only these: log, diff, status, ls-files,
add, commit. Anything else — cat, ls, pwd, bash, and notably \`git reset\` — is
denied, and in a && chain one denied segment kills the whole command. To read an
untracked file, \`git add\` it and use \`git diff --cached <path>\`; never the
\`git add -N\` … \`git reset\` round trip. A denial is not a reason to stop:
carry on with git and finish the job.

GIT_AUTHOR_DATE and GIT_COMMITTER_DATE are already set in your environment.
Do NOT run the pre-flight script and do NOT set the dates yourself — the caller
did both. Just run plain \`git add\` and \`git commit\`.

Commit EXACTLY ONE atomic unit of the pending changes, then stop. Leave every
other change uncommitted; you will be called again for the next unit." \
    --add-dir "$REPO_ROOT" \
    --effort "$EFFORT" \
    --print-timeout "$TIMEOUT" \
    --log-file "$AGY_LOG" \
    >"$WORK_LOG" 2>&1

  HEAD_AFTER="$(git rev-parse HEAD 2>/dev/null || true)"

  if [ "$HEAD_BEFORE" = "$HEAD_AFTER" ]; then
    printf '\n----- agy output -----\n'
    cat "$WORK_LOG"
    printf -- '----------------------\n\n'
    printf '[handoff-safe] ERROR: unit %s produced no commit — HEAD did not move.\n' "$UNIT" >&2

    if grep -qi 'headless mode cannot prompt' "$WORK_LOG"; then
      printf '[handoff-safe] Cause: a command was auto-denied for lack of permission:\n' >&2
      denied_commands | sed 's/^/                 /' >&2
      printf '[handoff-safe] Fix:   add a matching command(...) rule, e.g. via\n' >&2
      printf '[handoff-safe]        bash %s\n' \
        "$SCRIPT_DIR/../../handoff-commit/scripts/setup-permissions.sh" >&2
    elif grep -qiE 'auth|login|credential|unauthenticated|token' "$WORK_LOG"; then
      printf '[handoff-safe] Cause: looks like an authentication failure.\n' >&2
      printf '[handoff-safe] Fix:   run `agy` interactively once to refresh the login.\n' >&2
    else
      printf '[handoff-safe] See the agy output above for the cause.\n' >&2
    fi

    if [ "$COMMITTED" -gt 0 ]; then
      printf '[handoff-safe] %s commit(s) were already created and are left in place.\n' \
        "$COMMITTED" >&2
    fi
    printf '[handoff-safe] No retry was attempted.\n' >&2
    exit 1
  fi

  if [ -n "$HEAD_BEFORE" ]; then
    RANGE="$HEAD_BEFORE..$HEAD_AFTER"
  else
    RANGE="$HEAD_AFTER"
  fi

  UNIT_COUNT="$(git rev-list --count "$RANGE")"
  COMMITTED=$((COMMITTED + UNIT_COUNT))
  git log --format='  %h  %ad  %s' --date=format:'%Y-%m-%d %H:%M:%S' "$RANGE"
done

note "Created $COMMITTED commit(s) across $UNIT unit(s). Working tree is clean."
