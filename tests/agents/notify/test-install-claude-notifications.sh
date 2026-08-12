#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
INSTALLER="$PROJECT_ROOT/modules/agents/notify/install.sh"
MANAGED_COMMAND='"$HOME/.local/bin/agent-notify.sh" claude input'
MANAGED_MATCHER='permission_prompt|elicitation_dialog'

test_root=$(mktemp -d "${TMPDIR:-/tmp}/agent-notify-claude-test.XXXXXX")
trap 'rm -rf -- "$test_root"' EXIT

test_home="$test_root/home"
mkdir -p "$test_home/.claude"
printf '%s\n' \
  '{' \
  '  "hooks": {' \
  '    "Notification": [' \
  '      {' \
  '        "matcher": "permission_prompt",' \
  '        "hooks": [' \
  '          {"type":"command","command":"keep-permission"},' \
  '          {"type":"command","command":"old agent-notify.sh claude input"}' \
  '        ]' \
  '      },' \
  '      {' \
  '        "matcher": "idle_prompt",' \
  '        "hooks": [{"type":"command","command":"old agent-notify.sh claude input"}]' \
  '      },' \
  '      {' \
  '        "matcher": "auth_success",' \
  '        "hooks": [{"type":"command","command":"keep-auth"}]' \
  '      }' \
  '    ]' \
  '  }' \
  '}' >"$test_home/.claude/settings.json"

run_installer() {
  HOME="$test_home" PATH="/opt/homebrew/bin:/usr/bin:/bin" \
    bash "$INSTALLER" >"$test_home/install.out" 2>&1
}

assert_filtered_notification_hook() {
  local settings="$test_home/.claude/settings.json" managed_count wrong_count
  managed_count=$(jq --arg command "$MANAGED_COMMAND" --arg matcher "$MANAGED_MATCHER" \
    '[.hooks.Notification[]? | select(.matcher == $matcher) | .hooks[]? | select(.command == $command)] | length' \
    "$settings")
  [ "$managed_count" -eq 1 ] || {
    echo "FAIL: expected one filtered Claude input hook, found $managed_count" >&2
    exit 1
  }

  wrong_count=$(jq --arg command "$MANAGED_COMMAND" --arg matcher "$MANAGED_MATCHER" \
    '[.hooks.Notification[]? | select((.matcher // "") != $matcher) | .hooks[]? | select(.command == $command)] | length' \
    "$settings")
  [ "$wrong_count" -eq 0 ] || {
    echo "FAIL: Claude input hook still handles idle or unfiltered notifications" >&2
    exit 1
  }
}

run_installer

jq -e '.hooks.Notification[]?.hooks[]? | select(.command == "keep-permission")' \
  "$test_home/.claude/settings.json" >/dev/null || {
  echo "FAIL: installer removed an unrelated permission hook" >&2
  exit 1
}
jq -e '.hooks.Notification[]?.hooks[]? | select(.command == "keep-auth")' \
  "$test_home/.claude/settings.json" >/dev/null || {
  echo "FAIL: installer removed an unrelated auth hook" >&2
  exit 1
}
assert_filtered_notification_hook

run_installer
assert_filtered_notification_hook

echo "PASS: Claude input notifications exclude idle prompts"
