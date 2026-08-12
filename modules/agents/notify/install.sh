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
#
# Re-running is safe. Hook entries are matched by script name and replaced
# rather than appended, so this never stacks duplicates.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

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

# Probe for each agent BEFORE creating any directory below - the log directory
# lives under ~/.claude, so creating it first would make every machine look
# like it has Claude Code installed.
HAS_CLAUDE=false
HAS_CODEX=false
{ [ -d "$HOME/.claude" ] || has_cmd claude; } && HAS_CLAUDE=true
{ [ -d "$HOME/.codex" ] || has_cmd codex; } && HAS_CODEX=true

if [ "$HAS_CLAUDE" = false ] && [ "$HAS_CODEX" = false ]; then
  log_warn "Neither Claude Code nor Codex CLI was found. Nothing to hook into - skipping."
  exit 0
fi

# ---------------------------------------------------------------------------
# 1. Dependencies
# ---------------------------------------------------------------------------

if ! has_cmd brew; then
  log_warn "Homebrew not found. Install terminal-notifier and jq manually, then re-run."
fi

# terminal-notifier ships its own bundle id, so it registers under System
# Settings > Notifications and can be allowed on its own. osascript has no
# bundle id, so macOS attributes its notifications elsewhere and drops them
# silently while still exiting 0 - a broken setup that looks like a working one.
#
# Probe the two Homebrew prefixes directly instead of PATH: hooks inherit a
# bare PATH that lacks /opt/homebrew/bin, so agent-notify.sh resolves these
# same two paths at runtime. A binary only PATH can see would never be found.
have_notifier() {
  [ -x /opt/homebrew/bin/terminal-notifier ] || [ -x /usr/local/bin/terminal-notifier ]
}

if have_notifier; then
  log_info "terminal-notifier is already installed."
else
  if has_cmd brew; then
    log_info "Installing terminal-notifier..."
    brew install terminal-notifier >/dev/null 2>&1
  fi
  # Re-probe rather than trust brew's exit code - what matters is whether the
  # binary landed where the hook will look for it.
  if have_notifier; then
    log_success "Installed terminal-notifier."
  else
    log_warn "terminal-notifier is missing from /opt/homebrew/bin and /usr/local/bin."
    log_warn "Hooks will still be installed, but delivery falls back to osascript,"
    log_warn "which macOS drops silently - you would get the sound and no banner."
    log_warn "Fix it with: brew install terminal-notifier"
  fi
fi

# jq parses the hook payload at runtime and edits settings.json below.
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
  log_error "jq is unavailable - cannot patch Claude Code settings. Aborting."
  exit 1
fi

# ---------------------------------------------------------------------------
# 2. Install the scripts
# ---------------------------------------------------------------------------

log_info "----------------------------------------"
log_info "Installing scripts into ${BIN_DIR}..."

mkdir -p "$BIN_DIR"
# agent-notify.sh writes its debug log here; create the directory up front so
# a Codex-only machine (no Claude Code) does not spew redirection errors.
mkdir -p "$HOME/.claude/hooks"

for script in agent-notify.sh agent-focus.sh; do
  if [ ! -f "$SRC_DIR/$script" ]; then
    log_error "Missing source file: $SRC_DIR/$script"
    exit 1
  fi
  if [ -f "$BIN_DIR/$script" ]; then
    cp "$BIN_DIR/$script" "$BIN_DIR/$script.bak"
    log_info "Backed up existing $script to $script.bak"
  fi
  cp "$SRC_DIR/$script" "$BIN_DIR/$script"
  chmod +x "$BIN_DIR/$script"
  log_success "Installed $script"
done

# ---------------------------------------------------------------------------
# 3. Claude Code hooks
# ---------------------------------------------------------------------------

log_info "----------------------------------------"

if [ "$HAS_CLAUDE" = false ]; then
  log_warn "Claude Code was not detected. Skipping its hooks."
else
  log_info "Registering Claude Code hooks in ${CLAUDE_SETTINGS}..."

  if [ ! -f "$CLAUDE_SETTINGS" ]; then
    echo '{}' > "$CLAUDE_SETTINGS"
    log_info "Created a new settings.json."
  else
    cp "$CLAUDE_SETTINGS" "$CLAUDE_SETTINGS.bak"
    log_info "Backed up settings.json to settings.json.bak"
  fi

  if ! jq -e . "$CLAUDE_SETTINGS" >/dev/null 2>&1; then
    log_error "settings.json is not valid JSON. Fix it and re-run - refusing to overwrite."
    exit 1
  fi

  # Drop any prior entry pointing at this script (or its claude-notify.sh
  # predecessor) before appending, so re-runs replace instead of stacking.
  upsert_hook() { # upsert_hook <event> <command> <timeout> [matcher]
    local tmp matcher="${4:-}"
    tmp=$(mktemp)
    if jq --arg ev "$1" --arg cmd "$2" --argjson to "$3" --arg matcher "$matcher" \
       --arg pat 'agent-notify\.sh|claude-notify\.sh' '
        .hooks[$ev] = (
          ((.hooks[$ev] // [])
            | map(.hooks = ((.hooks // []) | map(select((.command // "") | test($pat) | not))))
            | map(select((.hooks | length) > 0)))
          + [(
              { hooks: [ { type: "command", command: $cmd, timeout: $to } ] }
              + (if $matcher == "" then {} else { matcher: $matcher } end)
            )]
        )' "$CLAUDE_SETTINGS" > "$tmp" 2>/dev/null; then
      mv "$tmp" "$CLAUDE_SETTINGS"
      log_success "Registered $1 hook."
    else
      rm -f "$tmp"
      log_error "Failed to register $1 hook."
    fi
  }

  upsert_hook "UserPromptSubmit" "$NOTIFY_CMD_BASE claude start" 5
  upsert_hook "Stop"             "$NOTIFY_CMD_BASE claude stop"  10
  upsert_hook "Notification"     "$NOTIFY_CMD_BASE claude input" 10 \
    "permission_prompt|elicitation_dialog"
fi

# ---------------------------------------------------------------------------
# 4. Codex CLI notify
# ---------------------------------------------------------------------------

log_info "----------------------------------------"

if [ "$HAS_CODEX" = false ]; then
  log_warn "Codex CLI was not detected. Skipping its notify hook."
else
  mkdir -p "$HOME/.codex"
  log_info "Registering Codex notify hook in ${CODEX_CONFIG}..."

  CODEX_LINE="notify = [\"$BIN_DIR/agent-notify.sh\", \"codex\"]"

  if [ ! -f "$CODEX_CONFIG" ]; then
    echo "$CODEX_LINE" > "$CODEX_CONFIG"
    log_success "Created config.toml with the notify hook."
  else
    cp "$CODEX_CONFIG" "$CODEX_CONFIG.bak"
    log_info "Backed up config.toml to config.toml.bak"

    tmp=$(mktemp)
    if grep -qE '^[[:space:]]*notify[[:space:]]*=' "$CODEX_CONFIG"; then
      awk -v repl="$CODEX_LINE" '
        !replaced && /^[[:space:]]*notify[[:space:]]*=/ { print repl; replaced=1; next }
        { print }
      ' "$CODEX_CONFIG" > "$tmp" && mv "$tmp" "$CODEX_CONFIG"
      log_success "Replaced the existing notify hook."
    else
      # A bare key appended at the end of a TOML file lands inside whatever
      # table header came last, so prepend it instead - top-level keys are
      # only top-level before the first [table].
      { echo "$CODEX_LINE"; cat "$CODEX_CONFIG"; } > "$tmp" && mv "$tmp" "$CODEX_CONFIG"
      log_success "Added the notify hook."
    fi
  fi

  log_info "Registering Codex UserPromptSubmit hook in ${CODEX_HOOKS}..."

  hooks_input="$CODEX_HOOKS"
  seed=""
  if [ -f "$CODEX_HOOKS" ]; then
    if ! jq -e . "$CODEX_HOOKS" >/dev/null 2>&1; then
      log_error "hooks.json is not valid JSON. Fix it and re-run - refusing to overwrite."
      exit 1
    fi
    cp "$CODEX_HOOKS" "$CODEX_HOOKS.bak"
    log_info "Backed up hooks.json to hooks.json.bak"
  else
    seed=$(mktemp)
    printf '{}\n' >"$seed"
    hooks_input="$seed"
  fi

  tmp=$(mktemp "$HOME/.codex/hooks.json.tmp.XXXXXX")
  if jq --arg cmd "$CODEX_HOOK_CMD" '
      .hooks = (.hooks // {})
      | .hooks.UserPromptSubmit = (
          ((.hooks.UserPromptSubmit // [])
            | map(.hooks = ((.hooks // [])
                | map(select((.command // "") | test("agent-notify\\.sh") | not))))
            | map(select((.hooks | length) > 0)))
          + [{ hooks: [ { type: "command", command: $cmd, timeout: 5 } ] }]
        )
    ' "$hooks_input" >"$tmp" 2>/dev/null; then
    mv "$tmp" "$CODEX_HOOKS"
    log_success "Registered Codex UserPromptSubmit hook."
  else
    rm -f "$tmp"
    [ -z "$seed" ] || rm -f "$seed"
    log_error "Failed to register Codex UserPromptSubmit hook."
    exit 1
  fi
  [ -z "$seed" ] || rm -f "$seed"
fi

# ---------------------------------------------------------------------------
# 5. Done
# ---------------------------------------------------------------------------

log_info "----------------------------------------"
log_success "Agent notification hooks installed."
log_info "Claude Code notifies only for turns of 30s or longer; override with"
log_info "  export AGENT_NOTIFY_MIN_SECONDS=<seconds>"
log_info "Codex notifies on every turn; submitting the next prompt retracts that chat's banner."
log_info "Debug log: ~/.claude/hooks/notify.log"
log_info "Open Claude Code's /hooks menu to inspect its hooks."
log_info "Open Codex's /hooks menu once to review and trust its lifecycle hook."
