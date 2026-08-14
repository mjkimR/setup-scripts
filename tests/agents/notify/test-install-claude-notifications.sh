#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
INSTALLER="$PROJECT_ROOT/modules/agents/hooks/notify/install.sh"
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

original_settings_checksum=$(shasum "$test_home/.claude/settings.json" | awk '{print $1}')

run_installer() {
  local target_home="${1:-$test_home}"
  HOME="$target_home" PATH="/opt/homebrew/bin:/usr/bin:/bin" \
    bash "$INSTALLER" >"$target_home/install.out" 2>&1
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

[ -f "$test_home/.claude/settings.json.bak" ] || {
  echo "FAIL: installer did not preserve the original Claude settings" >&2
  exit 1
}
[ -f "$test_home/.claude/settings.json.bak.latest" ] || {
  echo "FAIL: installer did not create the latest Claude settings backup" >&2
  exit 1
}

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

before_second_settings_checksum=$(shasum "$test_home/.claude/settings.json" | awk '{print $1}')
run_installer
assert_filtered_notification_hook
[ "$(shasum "$test_home/.claude/settings.json.bak" | awk '{print $1}')" = "$original_settings_checksum" ] || {
  echo "FAIL: reinstall overwrote the original Claude settings backup" >&2
  exit 1
}
[ "$(shasum "$test_home/.claude/settings.json.bak.latest" | awk '{print $1}')" = "$before_second_settings_checksum" ] || {
  echo "FAIL: latest Claude settings backup is not the pre-reinstall version" >&2
  exit 1
}

invalid_schema_home="$test_root/invalid-schema-home"
mkdir -p "$invalid_schema_home/.claude"
printf '%s\n' '{"hooks":{"Stop":{}}}' \
  >"$invalid_schema_home/.claude/settings.json"
before_checksum=$(shasum "$invalid_schema_home/.claude/settings.json" | awk '{print $1}')
if run_installer "$invalid_schema_home"; then
  echo "FAIL: installer reported success for invalid Claude hook structure" >&2
  exit 1
fi
after_checksum=$(shasum "$invalid_schema_home/.claude/settings.json" | awk '{print $1}')
[ "$before_checksum" = "$after_checksum" ] || {
  echo "FAIL: installer partially changed invalid Claude hook settings" >&2
  exit 1
}
[ ! -e "$invalid_schema_home/.local/bin/agent-notify.sh" ] || {
  echo "FAIL: installer copied scripts before rejecting invalid Claude settings" >&2
  exit 1
}
[ ! -e "$invalid_schema_home/.claude/settings.json.bak" ] || {
  echo "FAIL: installer created backups before completing Claude preflight" >&2
  exit 1
}

echo "PASS: Claude input notifications exclude idle prompts"
