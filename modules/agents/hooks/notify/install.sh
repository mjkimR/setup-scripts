#!/usr/bin/env bash

# Installs the shared macOS notification hooks for Claude Code and Codex CLI.
#
# Both agents get one banner format and one click target:
#
#     <project_name> · done          <- project first; several sessions run at once
#     Claude Code · 49s · 14:23      <- which agent, how long it took, when it landed
#
# Clicking raises the exact terminal the turn came from - the iTerm2 split
# pane by session id, or the editor window already holding that project.
# Codex PermissionRequest hooks also alert when an approval needs input.
#
# Re-running is safe. Hook entries are matched by script name and replaced
# rather than appended, so this never stacks duplicates.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"

# Load library files
if [ -f "$PROJECT_ROOT/lib/utils.sh" ] && [ -f "$PROJECT_ROOT/lib/ui.sh" ]; then
  source "$PROJECT_ROOT/lib/utils.sh"
  source "$PROJECT_ROOT/lib/ui.sh"
else
  echo "[ERROR] Required library files (lib/utils.sh or lib/ui.sh) not found."
  exit 1
fi

log_header "Installing Agent Notification Hooks (Claude Code & Codex CLI)"

OS_TYPE=$(get_os)
if [ "$OS_TYPE" != "macos" ]; then
  log_warn "These hooks target macOS Notification Center (terminal-notifier, AppleScript)."
  log_warn "Detected '${OS_TYPE}' - skipping."
  exit 0
fi

# The hook scripts ship next to this installer - they are executables, not
# config, so they stay self-contained in the module rather than in config/.
SRC_DIR="$SCRIPT_DIR"
BIN_DIR="$HOME/.local/bin"
CLAUDE_SETTINGS="$HOME/.claude/settings.json"
CODEX_CONFIG="$HOME/.codex/config.toml"
CODEX_HOOKS="$HOME/.codex/hooks.json"
NOTIFY_CMD_BASE='"$HOME/.local/bin/agent-notify.sh"'
CODEX_HOOK_CMD='"$HOME/.local/bin/agent-notify.sh" codex start'
CODEX_INPUT_HOOK_CMD='"$HOME/.local/bin/agent-notify.sh" codex input'
NOTIFY_LOG_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/agent-notify"

# Probe for each agent before creating any directories. Detection is based on
# the executable or an actual config file, never a directory this module may
# create for its own state.
HAS_CLAUDE=false
HAS_CODEX=false
{ [ -f "$CLAUDE_SETTINGS" ] || has_cmd claude; } && HAS_CLAUDE=true
{ [ -f "$CODEX_CONFIG" ] || [ -f "$CODEX_HOOKS" ] || has_cmd codex; } && HAS_CODEX=true

if [ "$HAS_CLAUDE" = false ] && [ "$HAS_CODEX" = false ]; then
  log_warn "Neither Claude Code nor Codex CLI was found. Nothing to hook into - skipping."
  exit 0
fi

# ---------------------------------------------------------------------------
# 1. Preflight and staging
# ---------------------------------------------------------------------------

for script in agent-notify.sh agent-focus.sh; do
  if [ ! -f "$SRC_DIR/$script" ]; then
    log_error "Missing source file: $SRC_DIR/$script"
    exit 1
  fi
done

validate_target_type() {
  if [ -e "$1" ] && [ ! -f "$1" ]; then
    log_error "Expected a regular settings file but found another file type: $1"
    log_error "No notification scripts or agent settings were changed."
    return 1
  fi
}

validate_target_type "$BIN_DIR/agent-notify.sh" || exit 1
validate_target_type "$BIN_DIR/agent-focus.sh" || exit 1
[ "$HAS_CLAUDE" = false ] || validate_target_type "$CLAUDE_SETTINGS" || exit 1
if [ "$HAS_CODEX" = true ]; then
  validate_target_type "$CODEX_CONFIG" || exit 1
  validate_target_type "$CODEX_HOOKS" || exit 1
fi

# Codex supports inline hook tables and hooks.json, but using both in one
# config layer produces a merge warning. This installer owns hooks.json, so it
# refuses to guess how user-owned inline hooks should be migrated.
if [ "$HAS_CODEX" = true ] && [ -f "$CODEX_CONFIG" ] \
  && grep -qE '^[[:space:]]*\[+[[:space:]]*hooks(\]|\.|[[:space:]]|$)' "$CODEX_CONFIG"; then
  log_error "config.toml contains inline hooks, which conflict with this installer's hooks.json policy."
  log_error "Move those hooks to $CODEX_HOOKS or remove the inline [hooks] tables, then re-run."
  log_error "No notification scripts or agent settings were changed."
  exit 1
fi

if ! has_cmd brew; then
  log_warn "Homebrew not found. Install terminal-notifier and jq manually, then re-run."
fi

# jq is needed to validate and stage every JSON settings change. If it is not
# already available, installing it is the only action allowed before preflight.
if has_cmd jq; then
  log_info "jq is already installed."
elif has_cmd brew; then
  log_info "Installing jq..."
  brew install jq >/dev/null 2>&1 \
    && log_success "Installed jq." \
    || log_error "Failed to install jq."
else
  log_error "jq is required: brew install jq"
fi

if ! has_cmd jq; then
  log_error "jq is unavailable - cannot validate agent settings. Aborting."
  exit 1
fi

STAGE_DIR=$(mktemp -d "${TMPDIR:-/tmp}/agent-notify-install.XXXXXX") || {
  log_error "Failed to create the installation staging directory."
  exit 1
}
cleanup_stage() {
  rm -rf -- "$STAGE_DIR"
}
trap cleanup_stage EXIT

STAGED_NOTIFY="$STAGE_DIR/agent-notify.sh"
STAGED_FOCUS="$STAGE_DIR/agent-focus.sh"
STAGED_CLAUDE="$STAGE_DIR/claude-settings.json"
STAGED_CODEX_CONFIG="$STAGE_DIR/codex-config.toml"
STAGED_CODEX_HOOKS="$STAGE_DIR/codex-hooks.json"

if ! cp "$SRC_DIR/agent-notify.sh" "$STAGED_NOTIFY" \
  || ! cp "$SRC_DIR/agent-focus.sh" "$STAGED_FOCUS" \
  || ! chmod 755 "$STAGED_NOTIFY" "$STAGED_FOCUS"; then
  log_error "Failed to stage the notification scripts."
  exit 1
fi

validate_claude_settings() {
  jq -e '
    def valid_event($name):
      (.hooks[$name] // []) as $groups
      | ($groups | type) == "array"
        and all($groups[];
          type == "object"
          and ((.hooks // []) | type) == "array"
          and all((.hooks // [])[];
            type == "object" and ((.command // "") | type) == "string"));
    type == "object"
    and ((.hooks // {}) | type == "object")
    and valid_event("UserPromptSubmit")
    and valid_event("Stop")
    and valid_event("Notification")
  ' "$1" >/dev/null 2>&1
}

validate_codex_hooks() {
  jq -e '
    def valid_event($name):
      (.hooks[$name] // []) as $groups
      | ($groups | type) == "array"
        and all($groups[];
          type == "object"
          and ((.hooks // []) | type) == "array"
          and all((.hooks // [])[];
            type == "object" and ((.command // "") | type) == "string"));
    type == "object"
    and ((.hooks // {}) | type == "object")
    and valid_event("UserPromptSubmit")
    and valid_event("PermissionRequest")
  ' "$1" >/dev/null 2>&1
}

write_codex_notify_config() { # write_codex_notify_config <input> <output> <replacement>
  local input="$1" output="$2" replacement="$3"

  awk -v replacement="$replacement" '
    function bracket_delta(line,    i, c, escaped, in_basic, in_literal, delta) {
      escaped=0; in_basic=0; in_literal=0; delta=0
      for (i=1; i<=length(line); i++) {
        c=substr(line, i, 1)
        if (in_basic) {
          if (escaped) escaped=0
          else if (c == "\\") escaped=1
          else if (c == "\"") in_basic=0
          continue
        }
        if (in_literal) {
          if (c == "\047") in_literal=0
          continue
        }
        if (c == "#") break
        if (c == "\"") { in_basic=1; continue }
        if (c == "\047") { in_literal=1; continue }
        if (c == "[") delta++
        else if (c == "]") delta--
      }
      return delta
    }
    function emit(line) { output[++output_count]=line }
    BEGIN { in_root=1; depth=0; skipping=0; replaced=0; failed=0; output_count=0 }
    !in_root {
      emit($0)
      next
    }
    skipping {
      if ($0 ~ /^[[:space:]]*\][[:space:]]*(#.*)?$/) skipping=0
      next
    }
    /\"\"\"|\047\047\047/ { failed=1; exit }
    depth == 0 && /^[[:space:]]*\[.*\][[:space:]]*(#.*)?$/ {
      in_root=0
      emit($0)
      next
    }
    depth == 0 && /^[[:space:]]*(notify|"notify"|\047notify\047)[[:space:]]*=/ {
      if (replaced) { failed=1; exit }
      replaced=1
      value=$0
      sub(/^[^=]*=/, "", value)
      if (value !~ /^[[:space:]]*\[/) { failed=1; exit }
      emit(replacement)
      if (value ~ /\][[:space:]]*(#.*)?$/) next
      skipping=1
      next
    }
    {
      emit($0)
      depth += bracket_delta($0)
      if (depth < 0) { failed=1; exit }
    }
    END {
      if (failed || skipping || depth != 0) exit 42
      if (!replaced) print replacement
      for (i=1; i<=output_count; i++) print output[i]
    }
  ' "$input" >"$output"
}

if [ "$HAS_CLAUDE" = true ]; then
  claude_input="$CLAUDE_SETTINGS"
  if [ ! -f "$claude_input" ]; then
    claude_input="$STAGE_DIR/claude-seed.json"
    printf '{}\n' >"$claude_input" || exit 1
  fi

  if ! validate_claude_settings "$claude_input"; then
    log_error "settings.json has invalid JSON or hook structure. Fix it and re-run - refusing to overwrite."
    exit 1
  fi

  if ! jq \
    --arg start_cmd "$NOTIFY_CMD_BASE claude start" \
    --arg stop_cmd "$NOTIFY_CMD_BASE claude stop" \
    --arg input_cmd "$NOTIFY_CMD_BASE claude input" \
    --arg matcher 'permission_prompt|elicitation_dialog' \
    --arg pat 'agent-notify\.sh|claude-notify\.sh' '
      .hooks = (.hooks // {})
      | .hooks.UserPromptSubmit = (
          ((.hooks.UserPromptSubmit // [])
            | map(.hooks = ((.hooks // []) | map(select((.command // "") | test($pat) | not))))
            | map(select((.hooks | length) > 0)))
          + [{ hooks: [{ type: "command", command: $start_cmd, timeout: 5 }] }]
        )
      | .hooks.Stop = (
          ((.hooks.Stop // [])
            | map(.hooks = ((.hooks // []) | map(select((.command // "") | test($pat) | not))))
            | map(select((.hooks | length) > 0)))
          + [{ hooks: [{ type: "command", command: $stop_cmd, timeout: 10 }] }]
        )
      | .hooks.Notification = (
          ((.hooks.Notification // [])
            | map(.hooks = ((.hooks // []) | map(select((.command // "") | test($pat) | not))))
            | map(select((.hooks | length) > 0)))
          + [{ matcher: $matcher, hooks: [{ type: "command", command: $input_cmd, timeout: 10 }] }]
        )
    ' "$claude_input" >"$STAGED_CLAUDE" 2>/dev/null \
    || ! validate_claude_settings "$STAGED_CLAUDE"; then
    log_error "Failed to stage valid Claude Code hooks."
    exit 1
  fi
fi

if [ "$HAS_CODEX" = true ]; then
  toml_notify_path="$BIN_DIR/agent-notify.sh"
  toml_notify_path="${toml_notify_path//\\/\\\\}"
  toml_notify_path="${toml_notify_path//\"/\\\"}"
  CODEX_LINE="notify = [\"$toml_notify_path\", \"codex\"]"

  if [ -f "$CODEX_CONFIG" ]; then
    if ! write_codex_notify_config "$CODEX_CONFIG" "$STAGED_CODEX_CONFIG" "$CODEX_LINE"; then
      log_error "Could not safely update the top-level notify array in config.toml."
      log_error "Fix the existing notify value and re-run - refusing to overwrite."
      exit 1
    fi
  elif ! printf '%s\n' "$CODEX_LINE" >"$STAGED_CODEX_CONFIG"; then
    log_error "Failed to stage config.toml."
    exit 1
  fi

  codex_hooks_input="$CODEX_HOOKS"
  if [ ! -f "$codex_hooks_input" ]; then
    codex_hooks_input="$STAGE_DIR/codex-hooks-seed.json"
    printf '{}\n' >"$codex_hooks_input" || exit 1
  fi

  if ! validate_codex_hooks "$codex_hooks_input"; then
    log_error "hooks.json has invalid JSON or hook structure. Fix it and re-run - refusing to overwrite."
    exit 1
  fi

  if ! jq --arg prompt_cmd "$CODEX_HOOK_CMD" --arg input_cmd "$CODEX_INPUT_HOOK_CMD" '
      .hooks = (.hooks // {})
      | .hooks.UserPromptSubmit = (
          ((.hooks.UserPromptSubmit // [])
            | map(.hooks = ((.hooks // [])
                | map(select((.command // "") | test("agent-notify\\.sh") | not))))
            | map(select((.hooks | length) > 0)))
          + [{ hooks: [{ type: "command", command: $prompt_cmd, timeout: 5 }] }]
        )
      | .hooks.PermissionRequest = (
          ((.hooks.PermissionRequest // [])
            | map(.hooks = ((.hooks // [])
                | map(select((.command // "") | test("agent-notify\\.sh") | not))))
            | map(select((.hooks | length) > 0)))
          + [{ hooks: [{ type: "command", command: $input_cmd, timeout: 5, async: true }] }]
        )
    ' "$codex_hooks_input" >"$STAGED_CODEX_HOOKS" 2>/dev/null \
    || ! validate_codex_hooks "$STAGED_CODEX_HOOKS"; then
    log_error "Failed to stage valid Codex lifecycle hooks."
    exit 1
  fi
fi

log_success "Validated and staged all notification scripts and agent settings."

# ---------------------------------------------------------------------------
# 2. Optional delivery dependency
# ---------------------------------------------------------------------------

# terminal-notifier ships its own bundle id, so it registers under System
# Settings > Notifications and can be allowed on its own. Probe Homebrew's
# known prefixes because agent hooks inherit a minimal PATH.
have_notifier() {
  [ -x /opt/homebrew/bin/terminal-notifier ] || [ -x /usr/local/bin/terminal-notifier ]
}

if have_notifier; then
  log_info "terminal-notifier is already installed."
else
  if has_cmd brew; then
    log_info "Installing terminal-notifier..."
    brew install terminal-notifier >/dev/null 2>&1 || true
  fi
  if have_notifier; then
    log_success "Installed terminal-notifier."
  else
    log_warn "terminal-notifier is missing from /opt/homebrew/bin and /usr/local/bin."
    log_warn "Hooks will still be installed, but delivery falls back to osascript,"
    log_warn "which macOS drops silently - you would get the sound and no banner."
    log_warn "Fix it with: brew install terminal-notifier"
  fi
fi

# ---------------------------------------------------------------------------
# 3. Prepare backups and commit
# ---------------------------------------------------------------------------

if ! mkdir -p "$BIN_DIR" "$NOTIFY_LOG_DIR" || ! chmod 700 "$NOTIFY_LOG_DIR"; then
  log_error "Failed to create the notification script or log directory."
  exit 1
fi
if [ "$HAS_CLAUDE" = true ] && ! mkdir -p "$(dirname "$CLAUDE_SETTINGS")"; then
  log_error "Failed to create the Claude Code settings directory."
  exit 1
fi
if [ "$HAS_CODEX" = true ] && ! mkdir -p "$(dirname "$CODEX_CONFIG")"; then
  log_error "Failed to create the Codex settings directory."
  exit 1
fi

backup_file() { # backup_file <target>
  local target="$1" original_backup latest_backup tmp
  [ -f "$target" ] || return 0

  original_backup="$target.bak"
  latest_backup="$target.bak.latest"
  if { [ -e "$original_backup" ] && [ ! -f "$original_backup" ]; } \
    || { [ -e "$latest_backup" ] && [ ! -f "$latest_backup" ]; }; then
    log_error "A backup path is not a regular file for $target"
    return 1
  fi

  if [ ! -e "$original_backup" ]; then
    if ! tmp=$(mktemp "$original_backup.tmp.XXXXXX") \
      || ! cp -p "$target" "$tmp" \
      || ! mv "$tmp" "$original_backup"; then
      [ -z "${tmp:-}" ] || rm -f -- "$tmp"
      log_error "Failed to preserve the original file at $original_backup"
      return 1
    fi
    log_info "Preserved original file at $original_backup"
  fi

  tmp=""
  if ! tmp=$(mktemp "$latest_backup.tmp.XXXXXX") \
    || ! cp -p "$target" "$tmp" \
    || ! mv "$tmp" "$latest_backup"; then
    [ -z "$tmp" ] || rm -f -- "$tmp"
    log_error "Failed to back up the current file at $latest_backup"
    return 1
  fi
  log_info "Backed up the current file at $latest_backup"
}

QUEUE_SOURCES=()
QUEUE_TARGETS=()
QUEUE_MODES=()
QUEUE_EXISTED=()
READY_FILES=()

queue_file() { # queue_file <staged-source> <target> <mode>
  QUEUE_SOURCES[${#QUEUE_SOURCES[@]}]="$1"
  QUEUE_TARGETS[${#QUEUE_TARGETS[@]}]="$2"
  QUEUE_MODES[${#QUEUE_MODES[@]}]="$3"
  if [ -f "$2" ]; then
    QUEUE_EXISTED[${#QUEUE_EXISTED[@]}]=true
  else
    QUEUE_EXISTED[${#QUEUE_EXISTED[@]}]=false
  fi
}

cleanup_ready_files() {
  local ready
  for ready in "${READY_FILES[@]}"; do
    [ -z "$ready" ] || rm -f -- "$ready"
  done
}

# Early preflight failures only need the staging cleanup registered above.
# From this point on, also remove any target-side temporary commit files.
trap 'cleanup_ready_files; cleanup_stage' EXIT

prepare_queued_files() {
  local i tmp
  for ((i = 0; i < ${#QUEUE_TARGETS[@]}; i++)); do
    if ! tmp=$(mktemp "${QUEUE_TARGETS[$i]}.tmp.XXXXXX") \
      || ! cp "${QUEUE_SOURCES[$i]}" "$tmp" \
      || ! chmod "${QUEUE_MODES[$i]}" "$tmp"; then
      [ -z "${tmp:-}" ] || rm -f -- "$tmp"
      cleanup_ready_files
      log_error "Failed to prepare ${QUEUE_TARGETS[$i]} for installation."
      return 1
    fi
    READY_FILES[$i]="$tmp"
  done
}

rollback_committed_files() { # rollback_committed_files <count>
  local count="$1" i target restore
  log_warn "Commit failed; restoring files already changed by this run."
  for ((i = count - 1; i >= 0; i--)); do
    target="${QUEUE_TARGETS[$i]}"
    if [ "${QUEUE_EXISTED[$i]}" = true ]; then
      restore="$target.rollback.$$"
      if ! cp -p "$target.bak.latest" "$restore" || ! mv "$restore" "$target"; then
        rm -f -- "$restore"
        log_error "Rollback failed for $target; restore it manually from $target.bak.latest"
      fi
    else
      rm -f -- "$target"
    fi
  done
}

commit_queued_files() {
  local i
  for ((i = 0; i < ${#QUEUE_TARGETS[@]}; i++)); do
    if ! mv "${READY_FILES[$i]}" "${QUEUE_TARGETS[$i]}"; then
      rollback_committed_files "$i"
      cleanup_ready_files
      log_error "Failed to commit ${QUEUE_TARGETS[$i]}."
      return 1
    fi
    READY_FILES[$i]=""
  done
}

queue_file "$STAGED_NOTIFY" "$BIN_DIR/agent-notify.sh" 755
queue_file "$STAGED_FOCUS" "$BIN_DIR/agent-focus.sh" 755
[ "$HAS_CLAUDE" = false ] || queue_file "$STAGED_CLAUDE" "$CLAUDE_SETTINGS" 600
if [ "$HAS_CODEX" = true ]; then
  queue_file "$STAGED_CODEX_CONFIG" "$CODEX_CONFIG" 600
  queue_file "$STAGED_CODEX_HOOKS" "$CODEX_HOOKS" 600
fi

prepare_queued_files || exit 1

for target in "${QUEUE_TARGETS[@]}"; do
  if ! backup_file "$target"; then
    cleanup_ready_files
    exit 1
  fi
done

commit_queued_files || exit 1

log_info "----------------------------------------"
log_success "Installed agent-notify.sh and agent-focus.sh."
if [ "$HAS_CLAUDE" = true ]; then
  log_success "Registered Claude Code UserPromptSubmit, Stop, and Notification hooks."
else
  log_warn "Claude Code was not detected. Skipping its hooks."
fi
if [ "$HAS_CODEX" = true ]; then
  log_success "Registered Codex notify, UserPromptSubmit, and PermissionRequest hooks."
else
  log_warn "Codex CLI was not detected. Skipping its hooks."
fi

# ---------------------------------------------------------------------------
# 5. Done
# ---------------------------------------------------------------------------

log_info "----------------------------------------"
log_success "Agent notification hooks installed."
log_info "Claude Code notifies only for turns of 30s or longer; override with"
log_info "  export AGENT_NOTIFY_MIN_SECONDS=<seconds>"
log_info "Codex notifies on every turn; submitting the next prompt retracts that chat's banner."
log_info "Codex also notifies when an approval request needs input."
log_info "Debug log: ${NOTIFY_LOG_DIR}/notify.log"
log_info "Open Claude Code's /hooks menu to inspect its hooks."
log_info "Open Codex's /hooks menu once to review and trust its lifecycle hooks."
