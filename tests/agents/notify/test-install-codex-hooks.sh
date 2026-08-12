#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
INSTALLER="$PROJECT_ROOT/modules/agents/notify/install.sh"
MANAGED_PROMPT_COMMAND='"$HOME/.local/bin/agent-notify.sh" codex start'
MANAGED_INPUT_COMMAND='"$HOME/.local/bin/agent-notify.sh" codex input'

test_root=$(mktemp -d "${TMPDIR:-/tmp}/agent-notify-install-test.XXXXXX")
trap 'rm -rf -- "$test_root"' EXIT

run_installer() {
  local target_home="$1"
  HOME="$target_home" PATH="/opt/homebrew/bin:/usr/bin:/bin" \
    bash "$INSTALLER" >"$target_home/install.out" 2>&1
}

assert_managed_count() {
  local hooks_file="$1" event="$2" command="$3" expected="$4" actual
  actual=$(jq --arg event "$event" --arg command "$command" \
    '[.hooks[$event][]?.hooks[]? | select(.command == $command)] | length' \
    "$hooks_file")
  [ "$actual" -eq "$expected" ] || {
    echo "FAIL: expected $expected managed Codex $event hook, found $actual" >&2
    exit 1
  }
}

assert_managed_hooks() {
  local hooks_file="$1"
  assert_managed_count "$hooks_file" "UserPromptSubmit" "$MANAGED_PROMPT_COMMAND" 1
  assert_managed_count "$hooks_file" "PermissionRequest" "$MANAGED_INPUT_COMMAND" 1
  jq -e --arg command "$MANAGED_INPUT_COMMAND" '
    .hooks.PermissionRequest[]?.hooks[]?
    | select(.command == $command and .async == true)
  ' "$hooks_file" >/dev/null || {
    echo "FAIL: Codex permission notification hook is not asynchronous" >&2
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

original_config_checksum=$(shasum "$merge_home/.codex/config.toml" | awk '{print $1}')
original_hooks_checksum=$(shasum "$merge_home/.codex/hooks.json" | awk '{print $1}')

run_installer "$merge_home"
[ -f "$merge_home/.codex/hooks.json.bak" ] || {
  echo "FAIL: installer did not back up the existing Codex hooks file" >&2
  exit 1
}
[ -f "$merge_home/.codex/hooks.json.bak.latest" ] || {
  echo "FAIL: installer did not create the latest Codex hooks backup" >&2
  exit 1
}
[ -f "$merge_home/.codex/config.toml.bak" ] || {
  echo "FAIL: installer did not preserve the original Codex config" >&2
  exit 1
}
[ -f "$merge_home/.codex/config.toml.bak.latest" ] || {
  echo "FAIL: installer did not create the latest Codex config backup" >&2
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
assert_managed_hooks "$merge_home/.codex/hooks.json"

before_second_config_checksum=$(shasum "$merge_home/.codex/config.toml" | awk '{print $1}')
before_second_hooks_checksum=$(shasum "$merge_home/.codex/hooks.json" | awk '{print $1}')
run_installer "$merge_home"
assert_managed_hooks "$merge_home/.codex/hooks.json"
[ "$(shasum "$merge_home/.codex/config.toml.bak" | awk '{print $1}')" = "$original_config_checksum" ] || {
  echo "FAIL: reinstall overwrote the original Codex config backup" >&2
  exit 1
}
[ "$(shasum "$merge_home/.codex/hooks.json.bak" | awk '{print $1}')" = "$original_hooks_checksum" ] || {
  echo "FAIL: reinstall overwrote the original Codex hooks backup" >&2
  exit 1
}
[ "$(shasum "$merge_home/.codex/config.toml.bak.latest" | awk '{print $1}')" = "$before_second_config_checksum" ] || {
  echo "FAIL: latest Codex config backup is not the pre-reinstall version" >&2
  exit 1
}
[ "$(shasum "$merge_home/.codex/hooks.json.bak.latest" | awk '{print $1}')" = "$before_second_hooks_checksum" ] || {
  echo "FAIL: latest Codex hooks backup is not the pre-reinstall version" >&2
  exit 1
}
[ ! -e "$merge_home/.claude/settings.json" ] || {
  echo "FAIL: a Codex-only reinstall falsely configured Claude Code" >&2
  exit 1
}

absent_home="$test_root/absent-home"
mkdir -p "$absent_home/.codex"
: >"$absent_home/.codex/config.toml"
run_installer "$absent_home"
[ -f "$absent_home/.codex/hooks.json" ] || {
  echo "FAIL: installer did not create an absent Codex hooks file" >&2
  exit 1
}
assert_managed_hooks "$absent_home/.codex/hooks.json"

multiline_home="$test_root/multiline-home"
mkdir -p "$multiline_home/.codex"
printf '%s\n' \
  'other = [' \
  '  [1, 2],' \
  '  [3, 4],' \
  ']' \
  '' \
  'notify = [' \
  '  "/old/notifier",' \
  ']' \
  '' \
  '[some_table]' \
  'notify = ["keep-nested"]' \
  'value = true' >"$multiline_home/.codex/config.toml"
run_installer "$multiline_home"
grep -Fq -- "$multiline_home/.local/bin/agent-notify.sh" \
  "$multiline_home/.codex/config.toml" || {
  echo "FAIL: installer did not replace a multiline top-level notify value" >&2
  exit 1
}
grep -Fq -- 'notify = ["keep-nested"]' "$multiline_home/.codex/config.toml" || {
  echo "FAIL: installer replaced a table-scoped notify key" >&2
  exit 1
}
if grep -Fq -- '/old/notifier' "$multiline_home/.codex/config.toml"; then
  echo "FAIL: installer left part of the old multiline notify array behind" >&2
  exit 1
fi

inline_hooks_home="$test_root/inline-hooks-home"
mkdir -p "$inline_hooks_home/.codex"
printf '%s\n' '[hooks]' >"$inline_hooks_home/.codex/config.toml"
inline_checksum=$(shasum "$inline_hooks_home/.codex/config.toml" | awk '{print $1}')
if run_installer "$inline_hooks_home"; then
  echo "FAIL: installer accepted inline Codex hooks alongside hooks.json management" >&2
  exit 1
fi
[ "$(shasum "$inline_hooks_home/.codex/config.toml" | awk '{print $1}')" = "$inline_checksum" ] || {
  echo "FAIL: installer changed config.toml after rejecting inline hooks" >&2
  exit 1
}
[ ! -e "$inline_hooks_home/.codex/hooks.json" ] || {
  echo "FAIL: installer created hooks.json despite rejecting inline hooks" >&2
  exit 1
}
[ ! -e "$inline_hooks_home/.local/bin/agent-notify.sh" ] || {
  echo "FAIL: installer copied scripts before rejecting inline hooks" >&2
  exit 1
}
grep -Fq -- 'inline hooks' "$inline_hooks_home/install.out" || {
  echo "FAIL: installer did not explain the inline hooks conflict" >&2
  exit 1
}

quoted_notify_home="$test_root/quoted-notify-home"
mkdir -p "$quoted_notify_home/.codex"
printf '%s\n' '"notify" = ["/old/quoted-notifier"]' \
  >"$quoted_notify_home/.codex/config.toml"
run_installer "$quoted_notify_home"
if grep -Fq -- '/old/quoted-notifier' "$quoted_notify_home/.codex/config.toml"; then
  echo "FAIL: installer left a semantically duplicate quoted notify key" >&2
  exit 1
fi

malformed_toml_home="$test_root/malformed-toml-home"
mkdir -p "$malformed_toml_home/.codex"
printf '%s\n' 'notify = [' '  "/unterminated"' \
  >"$malformed_toml_home/.codex/config.toml"
before_checksum=$(shasum "$malformed_toml_home/.codex/config.toml" | awk '{print $1}')
if run_installer "$malformed_toml_home"; then
  echo "FAIL: installer accepted an unterminated multiline notify array" >&2
  exit 1
fi
after_checksum=$(shasum "$malformed_toml_home/.codex/config.toml" | awk '{print $1}')
[ "$before_checksum" = "$after_checksum" ] || {
  echo "FAIL: installer changed an unsafe Codex TOML file" >&2
  exit 1
}
[ ! -e "$malformed_toml_home/.local/bin/agent-notify.sh" ] || {
  echo "FAIL: installer copied scripts before rejecting unsafe Codex TOML" >&2
  exit 1
}
[ ! -e "$malformed_toml_home/.codex/hooks.json" ] || {
  echo "FAIL: installer created hooks.json before rejecting unsafe Codex TOML" >&2
  exit 1
}

invalid_home="$test_root/invalid-home"
mkdir -p "$invalid_home/.claude" "$invalid_home/.codex"
printf '%s\n' '{"theme":"dark"}' >"$invalid_home/.claude/settings.json"
: >"$invalid_home/.codex/config.toml"
printf '%s\n' '{not-json' >"$invalid_home/.codex/hooks.json"
before_checksum=$(shasum "$invalid_home/.codex/hooks.json" | awk '{print $1}')
before_claude_checksum=$(shasum "$invalid_home/.claude/settings.json" | awk '{print $1}')
if run_installer "$invalid_home"; then
  echo "FAIL: installer accepted invalid Codex hooks JSON" >&2
  exit 1
fi
after_checksum=$(shasum "$invalid_home/.codex/hooks.json" | awk '{print $1}')
[ "$before_checksum" = "$after_checksum" ] || {
  echo "FAIL: installer overwrote invalid Codex hooks JSON" >&2
  exit 1
}
[ "$(shasum "$invalid_home/.claude/settings.json" | awk '{print $1}')" = "$before_claude_checksum" ] || {
  echo "FAIL: Codex preflight failure partially changed Claude settings" >&2
  exit 1
}
[ ! -e "$invalid_home/.local/bin/agent-notify.sh" ] || {
  echo "FAIL: installer copied scripts before rejecting invalid Codex hooks JSON" >&2
  exit 1
}
[ ! -e "$invalid_home/.codex/hooks.json.bak" ] || {
  echo "FAIL: installer created backups before completing preflight" >&2
  exit 1
}
[ ! -e "$invalid_home/.claude/settings.json.bak" ] || {
  echo "FAIL: Codex preflight failure created a Claude backup" >&2
  exit 1
}

invalid_schema_home="$test_root/invalid-schema-home"
mkdir -p "$invalid_schema_home/.codex"
: >"$invalid_schema_home/.codex/config.toml"
printf '%s\n' '{"hooks":{"UserPromptSubmit":{}}}' \
  >"$invalid_schema_home/.codex/hooks.json"
if run_installer "$invalid_schema_home"; then
  echo "FAIL: installer reported success for invalid Codex hook structure" >&2
  exit 1
fi
[ ! -e "$invalid_schema_home/.local/bin/agent-notify.sh" ] || {
  echo "FAIL: installer copied scripts before rejecting invalid Codex hook structure" >&2
  exit 1
}

echo "PASS: Codex lifecycle hook installation is safe and idempotent"
