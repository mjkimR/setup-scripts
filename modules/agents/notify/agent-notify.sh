#!/usr/bin/env bash
# Shared macOS notification hook for Claude Code and Codex CLI.
#
#   Claude Code - ~/.claude/settings.json, hook JSON arrives on stdin:
#     agent-notify.sh claude start   UserPromptSubmit  stamp the turn start
#     agent-notify.sh claude stop    Stop              notify if the turn was slow
#     agent-notify.sh claude input   Notification      notify that it wants you
#
#   Codex CLI - ~/.codex/config.toml and ~/.codex/hooks.json:
#     notify = ["…/agent-notify.sh", "codex"]
#     agent-notify.sh codex start   UserPromptSubmit  retract the last banner
#     agent-notify.sh codex input   PermissionRequest notify that it wants you
#   Codex appends completion JSON to notify as the final argument, while the
#   lifecycle hooks send JSON on stdin. This integration uses those events for
#   retraction and approval prompts; Codex completion still
#   notifies on every turn.
#
# The banner is two lines and nothing more:
#
#     <project_name> · done          <- project first; several sessions run at once
#     Claude Code · 49s · 14:23      <- which agent, how long it took, when it landed
#
# A session started below the project root names both, as <subdir>(<project>),
# because the click lands on the project while the work is in the subdirectory.
#
# No -subtitle, no assistant text. Prose gets truncated by the banner
# anyway, so it costs a line and pays nothing back - the project name and a
# click that lands in the right terminal are the whole job. terminal-notifier
# requires -message, so the agent line goes there rather than in -subtitle.
#
# Clicking runs agent-focus.sh, which raises the exact pane the turn came
# from. Tweak MIN_SECONDS to change how long a Claude turn must run before
# it notifies.
#
# Delivery goes through terminal-notifier (brew install terminal-notifier).
# It ships its own bundle id, so it registers under System Settings >
# Notifications and is allowed on its own. osascript has no bundle id, so
# macOS attributes its notifications elsewhere and drops them silently -
# it still exits 0, which is why a broken setup looks like a working one.
# The osascript branch is kept only as a fallback, paired with afplay so
# there is at least a sound when the banner never arrives.

set -u
umask 077

MIN_SECONDS="${AGENT_NOTIFY_MIN_SECONDS:-30}"
STATE_DIR="${AGENT_NOTIFY_STATE_DIR:-${TMPDIR:-/tmp}/agent-notify-$UID}"
LOG_DIR="${AGENT_NOTIFY_LOG_DIR:-${XDG_STATE_HOME:-$HOME/.local/state}/agent-notify}"
LOG="$LOG_DIR/notify.log"
FOCUS="$HOME/.local/bin/agent-focus.sh"

if ! mkdir -p "$LOG_DIR" 2>/dev/null; then
  LOG="/dev/null"
fi
if ! mkdir -p "$STATE_DIR" 2>/dev/null || ! chmod 700 "$STATE_DIR" 2>/dev/null; then
  log_state_error="state directory unavailable: $STATE_DIR"
  STATE_DIR=""
else
  log_state_error=""
fi

# Terminal identity, inherited from the shell that launched the agent.
HOST_BUNDLE="${__CFBundleIdentifier:-}"
ITERM_ID="${ITERM_SESSION_ID:-}"
ITERM_ID="${ITERM_ID##*:}"   # w0t0p0:UUID -> UUID

# Hooks inherit a bare PATH that lacks /opt/homebrew/bin, so resolve by path.
# The override is a narrow test seam; normal installations leave it unset.
NOTIFIER="${AGENT_NOTIFY_NOTIFIER:-}"
if [ -z "$NOTIFIER" ]; then
  for candidate in /opt/homebrew/bin/terminal-notifier /usr/local/bin/terminal-notifier; do
    [ -x "$candidate" ] && { NOTIFIER="$candidate"; break; }
  done
fi

log() { printf '%s %s\n' "$(date '+%F %T')" "$*" >>"$LOG" 2>/dev/null || true; }

[ -z "$log_state_error" ] || log "$log_state_error"

case "$MIN_SECONDS" in
  ''|*[!0-9]*)
    log "invalid AGENT_NOTIFY_MIN_SECONDS=$MIN_SECONDS; using 30"
    MIN_SECONDS=30
    ;;
esac

# Keep the debug log bounded.
if [ -f "$LOG" ] && [ "$(wc -c <"$LOG")" -gt 262144 ]; then
  tail -n 200 "$LOG" >"$LOG.tmp" && mv "$LOG.tmp" "$LOG"
fi

shq() { printf "'%s'" "$(printf '%s' "${1:-}" | sed "s/'/'\\\\''/g")"; }

# Resolve which folder the editor should be handed on click, and which name the
# banner should carry. Handing over the raw cwd makes an editor open a
# subdirectory as a NEW project instead of raising the window that already has
# the real one - and that window is where the terminal actually lives.
#
# Both editor families publish which projects are open right now, so that
# answer is used verbatim. A marker directory like .idea only proves a folder
# was opened as a project once, which is exactly how a stale subproject wins.
# Anything else falls back to the VCS root, then to the directory itself.

# List the folders the owning editor currently has open, one per line.
open_projects_for() { # open_projects_for <bundle-id>
  local bundle="$1" glob="" dir="" f s u

  case "$bundle" in
    com.jetbrains.pycharm*)  glob="PyCharm*" ;;
    com.jetbrains.intellij*) glob="Idea*" ;;
    com.jetbrains.goland*)   glob="GoLand*" ;;
    com.jetbrains.WebStorm*) glob="WebStorm*" ;;
    com.jetbrains.*)         glob="*" ;;
  esac

  if [ -n "$glob" ]; then
    for f in "$HOME/Library/Application Support/JetBrains/"$glob"/options/recentProjects.xml"; do
      [ -f "$f" ] || continue
      awk -v home="$HOME" '
        /<entry key=/    { k = $0 }
        /opened="true"/  { gsub(/.*entry key="/, "", k); gsub(/">.*/, "", k)
                           sub(/\$USER_HOME\$/, home, k); print k }' "$f" 2>/dev/null
    done
    return
  fi

  case "$bundle" in
    com.google.antigravity-ide)   dir="Antigravity IDE" ;;
    com.google.antigravity)       dir="Antigravity" ;;
    com.microsoft.VSCodeInsiders) dir="Code - Insiders" ;;
    com.microsoft.VSCode)         dir="Code" ;;
    com.todesktop.*)              dir="Cursor" ;;
    com.exafunction.*)            dir="Windsurf" ;;
    *)                            return ;;
  esac

  s="$HOME/Library/Application Support/$dir/User/globalStorage/storage.json"
  [ -f "$s" ] || return
  # Multi-root .code-workspace windows carry no .folder and simply drop out,
  # falling through to the VCS root below.
  jq -r '.windowsState.openedWindows[]?.folder // empty' "$s" 2>/dev/null |
    while IFS= read -r u; do
      u="${u#file://}"
      printf '%b\n' "${u//%/\\x}"   # file:// URIs percent-encode spaces
    done
}

resolve_project_root() { # resolve_project_root <cwd> <bundle-id>
  local dir="$1" bundle="$2" proj best=""

  # Read in this shell, not a pipeline, so $best survives the loop.
  while IFS= read -r proj; do
    [ -n "$proj" ] || continue
    case "$dir" in
      "$proj"|"$proj"/*)
        # Deepest match wins: a subproject nested inside another open project
        # is still the window this terminal belongs to.
        [ "${#proj}" -gt "${#best}" ] && best="$proj"
        ;;
    esac
  done < <(open_projects_for "$bundle")
  [ -n "$best" ] && { printf '%s' "$best"; return; }

  # /usr/bin/git ships with macOS, so this resolves even under the bare PATH
  # a hook inherits.
  if best=$(git -C "$dir" rev-parse --show-toplevel 2>/dev/null) && [ -n "$best" ]; then
    printf '%s' "$best"
    return
  fi

  printf '%s' "$dir"
}

tool="${1:-agent}"
shift || true
case "$tool" in
  claude) label="Claude Code" ;;
  codex)  label="Codex" ;;
  *)      label="$tool" ;;
esac

notify() { # notify <title> <message> <sound>
  local execute msg
  # A posted notification's text is frozen, so "N minutes ago" would rot the moment
  # it's written. Stamp the wall clock instead - it stays true, and it reads
  # against the relative age macOS puts in the header once it's in
  # Notification Center.
  msg="$2 · $(date '+%H:%M')"
  execute="$(shq "$FOCUS") $(shq "$HOST_BUNDLE") $(shq "$ITERM_ID") $(shq "$root")"
  if [ -n "$NOTIFIER" ]; then
    "$NOTIFIER" -title "$1" -message "$msg" -sound "$3" \
      -group "$group" -execute "$execute" >/dev/null 2>&1
    log "notify  rc=$? via terminal-notifier :: $1 | $msg"
  else
    osascript - "$1" "$msg" "$3" <<'APPLESCRIPT' >/dev/null 2>&1
on run argv
  display notification (item 2 of argv) with title (item 1 of argv) sound name (item 3 of argv)
end run
APPLESCRIPT
    log "notify  rc=$? via osascript (banner may be dropped) :: $1 | $msg"
    afplay "/System/Library/Sounds/$3.aiff" >/dev/null 2>&1 &
  fi
}

# Codex notify hands completion JSON as an argument. Codex lifecycle hooks and
# Claude Code hooks pipe their payload on stdin.
if [ "$tool" = "codex" ]; then
  case "${1:-}" in
    start|input)
      action="$1"
      payload=$(cat)
      ;;
    *)
      action="turn-end"
      payload="${1:-}"
      [ -n "$payload" ] || payload='{}'
      ;;
  esac
else
  action="${1:-}"
  payload=$(cat)
fi

jqr() { printf '%s' "$payload" | jq -r "$1" 2>/dev/null; }

# `notify` currently supports only agent-turn-complete. Ignore future event
# types until their meaning and payload are handled deliberately.
if [ "$action" = "turn-end" ] && [ "$(jqr '.type // empty')" != "agent-turn-complete" ]; then
  log "skip    codex unsupported notify event"
  exit 0
fi

cwd=$(jqr '(.cwd // empty) | select(type == "string")')
[ -n "$cwd" ] || cwd="$PWD"
root=$(resolve_project_root "$cwd" "$HOST_BUNDLE")
project=$(basename "$cwd")
# Name both when the session sits below the project root, so the banner does
# not silently disagree with where the click lands.
if [ "$root" = "$cwd" ]; then
  title_project="$project"
else
  title_project="$project($(basename "$root"))"
fi
# The group id is what makes a banner REPLACE the previous one instead of
# piling up, so it has to stay stable for as long as you'd think of it as
# "the same terminal". Lifecycle hooks call it session_id, while the
# Codex notify payload calls the same stable chat identity thread-id. Payloads
# without either identifier retain the project-level fallback.
session=$(jqr '(.session_id // .["thread-id"] // empty) | select(type == "string")')
[ -n "$session" ] || session="$project"
group="agent-$tool-$session"
if [ -n "$STATE_DIR" ]; then
  state_key=$(printf '%s:%s' "$tool" "$session" | /usr/bin/shasum -a 256 | /usr/bin/awk '{print $1}')
  if [ -n "$state_key" ]; then
    stamp="$STATE_DIR/agent-notify-$state_key"
  else
    log "state key unavailable for $tool/$project"
    stamp=""
  fi
else
  stamp=""
fi

case "$action" in
  start)
    # Claude Stop consumes this timestamp to enforce MIN_SECONDS. Codex uses
    # its start hook only for retraction and its completion path does
    # not consume duration state.
    if [ "$tool" = "claude" ] && [ -n "$stamp" ]; then
      stamp_tmp="$stamp.$$"
      if date +%s >"$stamp_tmp" && mv "$stamp_tmp" "$stamp"; then
        :
      else
        rm -f "$stamp_tmp"
        log "start   $tool/$project failed to write duration stamp"
      fi
    fi
    # Submitting a prompt means you're already here, so retract whatever
    # this session left sitting in Notification Center.
    if [ -n "$NOTIFIER" ]; then
      "$NOTIFIER" -remove "$group" >/dev/null 2>&1
      remove_rc=$?
      log "remove rc=$remove_rc tool=$tool project=$project session=$session group=$group"
    fi
    log "start   $tool/$project session=$session"
    ;;
  stop)
    # No stamp means this Stop came from /clear, resume or compact - stay quiet.
    if [ -z "$stamp" ] || [ ! -f "$stamp" ]; then
      log "stop    $tool/$project no stamp, skipped"
      exit 0
    fi
    start=$(cat "$stamp")
    rm -f "$stamp"
    case "$start" in
      ''|*[!0-9]*)
        log "stop    $tool/$project invalid stamp, skipped"
        exit 0
        ;;
    esac
    now=$(date +%s)
    if [ "$start" -gt "$now" ]; then
      log "stop    $tool/$project future stamp, skipped"
      exit 0
    fi
    elapsed=$((now - start))
    if [ "$elapsed" -lt "$MIN_SECONDS" ]; then
      log "stop    $tool/$project ${elapsed}s < ${MIN_SECONDS}s, skipped"
      exit 0
    fi
    if [ "$elapsed" -ge 60 ]; then
      took="$((elapsed / 60))m $((elapsed % 60))s"
    else
      took="${elapsed}s"
    fi
    notify "$title_project · done" "$label · $took" "Glass"
    ;;
  input)
    notify "$title_project · input needed" "$label" "Ping"
    ;;
  turn-end)
    notify "$title_project · done" "$label" "Glass"
    ;;
esac

exit 0
