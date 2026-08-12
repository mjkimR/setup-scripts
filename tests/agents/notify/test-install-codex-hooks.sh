#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
INSTALLER="$PROJECT_ROOT/modules/agents/notify/install.sh"
MANAGED_COMMAND='"$HOME/.local/bin/agent-notify.sh" codex start'

test_root=$(mktemp -d "${TMPDIR:-/tmp}/agent-notify-install-test.XXXXXX")
trap 'rm -rf -- "$test_root"' EXIT

run_installer() {
  local target_home="$1"
  HOME="$target_home" PATH="/opt/homebrew/bin:/usr/bin:/bin" \
    bash "$INSTALLER" >"$target_home/install.out" 2>&1
}

assert_managed_count() {
  local hooks_file="$1" expected="$2" actual
  actual=$(jq --arg command "$MANAGED_COMMAND" \
    '[.hooks.UserPromptSubmit[]?.hooks[]? | select(.command == $command)] | length' \
    "$hooks_file")
  [ "$actual" -eq "$expected" ] || {
    echo "FAIL: expected $expected managed Codex prompt hook, found $actual" >&2
    exit 1
  }
}

merge_home="$test_root/merge-home"
mkdir -p "$merge_home/.codex"
: >"$merge_home/.codex/config.toml"
printf '%s\n' \
  '{' \
  '  "hooks": {' \
  '    "Stop": [{"hooks":[{"type":"command","command":"keep-stop"}]}],' \
  '    "UserPromptSubmit": [' \
  '      {"hooks":[{"type":"command","command":"keep-prompt"}]},' \
  '      {"hooks":[{"type":"command","command":"old agent-notify.sh codex start"}]}' \
  '    ]' \
  '  }' \
  '}' >"$merge_home/.codex/hooks.json"

run_installer "$merge_home"
[ -f "$merge_home/.codex/hooks.json.bak" ] || {
  echo "FAIL: installer did not back up the existing Codex hooks file" >&2
  exit 1
}

jq -e '.hooks.Stop[]?.hooks[]? | select(.command == "keep-stop")' \
  "$merge_home/.codex/hooks.json" >/dev/null || {
  echo "FAIL: installer removed an unrelated Stop hook" >&2
  exit 1
}
jq -e '.hooks.UserPromptSubmit[]?.hooks[]? | select(.command == "keep-prompt")' \
  "$merge_home/.codex/hooks.json" >/dev/null || {
  echo "FAIL: installer removed an unrelated UserPromptSubmit hook" >&2
  exit 1
}
if jq -e '.hooks.UserPromptSubmit[]?.hooks[]? | select(.command == "old agent-notify.sh codex start")' \
  "$merge_home/.codex/hooks.json" >/dev/null; then
  echo "FAIL: installer retained its obsolete prompt hook" >&2
  exit 1
fi
assert_managed_count "$merge_home/.codex/hooks.json" 1

run_installer "$merge_home"
assert_managed_count "$merge_home/.codex/hooks.json" 1

absent_home="$test_root/absent-home"
mkdir -p "$absent_home/.codex"
: >"$absent_home/.codex/config.toml"
run_installer "$absent_home"
[ -f "$absent_home/.codex/hooks.json" ] || {
  echo "FAIL: installer did not create an absent Codex hooks file" >&2
  exit 1
}
assert_managed_count "$absent_home/.codex/hooks.json" 1

invalid_home="$test_root/invalid-home"
mkdir -p "$invalid_home/.codex"
: >"$invalid_home/.codex/config.toml"
printf '%s\n' '{not-json' >"$invalid_home/.codex/hooks.json"
before_checksum=$(shasum "$invalid_home/.codex/hooks.json" | awk '{print $1}')
if run_installer "$invalid_home"; then
  echo "FAIL: installer accepted invalid Codex hooks JSON" >&2
  exit 1
fi
after_checksum=$(shasum "$invalid_home/.codex/hooks.json" | awk '{print $1}')
[ "$before_checksum" = "$after_checksum" ] || {
  echo "FAIL: installer overwrote invalid Codex hooks JSON" >&2
  exit 1
}

echo "PASS: Codex lifecycle hook installation is safe and idempotent"
