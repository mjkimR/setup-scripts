#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
SOURCE_NOTIFY="$PROJECT_ROOT/modules/agents/notify/agent-notify.sh"
FAKE_NOTIFIER="$SCRIPT_DIR/fixtures/fake-notifier.sh"
REJECT_NOTIFIER="$SCRIPT_DIR/fixtures/reject-notifier.sh"

test_root=$(mktemp -d "${TMPDIR:-/tmp}/agent-notify-test.XXXXXX")
trap 'rm -rf -- "$test_root"' EXIT

test_home="$test_root/home"
state_dir="$test_root/state"
log_dir="$test_root/log"
project="$test_root/project-one"
calls="$test_root/notifier.calls"
runtime_notify="$test_root/agent-notify.sh"

mkdir -p "$test_home" "$state_dir" "$log_dir" "$project"
: >"$calls"

# Keep the test isolated from the machine's real Notification Center. The
# discovered notifier deliberately fails, proving the explicit test override
# is the executable that receives calls.
sed "s#for candidate in /opt/homebrew/bin/terminal-notifier /usr/local/bin/terminal-notifier; do#for candidate in \"$REJECT_NOTIFIER\"; do#" \
  "$SOURCE_NOTIFY" >"$runtime_notify"

run_notify() {
  HOME="$test_home" \
    TMPDIR="$state_dir" \
    AGENT_NOTIFY_STATE_DIR="$state_dir" \
    AGENT_NOTIFY_LOG_DIR="$log_dir" \
    AGENT_NOTIFY_NOTIFIER="$FAKE_NOTIFIER" \
    FAKE_NOTIFIER_CALLS="$calls" \
    bash "$runtime_notify" "$@"
}

completion_one=$(jq -cn --arg cwd "$project" \
  '{type:"agent-turn-complete", "thread-id":"thread-123", cwd:$cwd}')
completion_two=$(jq -cn --arg cwd "$project" \
  '{type:"agent-turn-complete", "thread-id":"thread-456", cwd:$cwd}')
completion_legacy=$(jq -cn --arg cwd "$project" \
  '{type:"agent-turn-complete", cwd:$cwd}')
prompt=$(jq -cn --arg cwd "$project" \
  '{hook_event_name:"UserPromptSubmit", session_id:"thread-123", cwd:$cwd}')
permission=$(jq -cn --arg cwd "$project" \
  '{hook_event_name:"PermissionRequest", session_id:"thread-123", cwd:$cwd,
    tool_name:"Bash", tool_input:{command:"echo test"}}')
special_session=$(jq -cn --arg cwd "$project" \
  '{hook_event_name:"UserPromptSubmit", session_id:"segment/with spaces", cwd:$cwd}')
corrupt_session=$(jq -cn --arg cwd "$project" \
  '{hook_event_name:"UserPromptSubmit", session_id:"corrupt-stamp", cwd:$cwd}')
future_event=$(jq -cn --arg cwd "$project" \
  '{type:"future-event", "thread-id":"thread-123", cwd:$cwd}')

run_notify codex "$completion_one"
run_notify codex "$completion_two"
run_notify codex "$completion_legacy"
printf '%s' "$prompt" | run_notify codex start
printf '%s' "$permission" | run_notify codex input
calls_before_future=$(wc -l <"$calls")
run_notify codex "$future_event"
calls_after_future=$(wc -l <"$calls")
printf '%s' "$special_session" | run_notify claude start
state_file_count=$(find "$state_dir" -maxdepth 1 -type f -name 'agent-notify-*' | wc -l | tr -d ' ')
[ "$state_file_count" -eq 1 ] || {
  echo "FAIL: session id was not reduced to one safe state filename" >&2
  exit 1
}
AGENT_NOTIFY_MIN_SECONDS=0 printf '%s' "$special_session" | \
  AGENT_NOTIFY_MIN_SECONDS=0 run_notify claude stop
printf '%s' "$corrupt_session" | run_notify claude start
corrupt_stamp=$(find "$state_dir" -maxdepth 1 -type f -name 'agent-notify-*' -print -quit)
[ -n "$corrupt_stamp" ] || {
  echo "FAIL: Claude start did not create a duration stamp" >&2
  exit 1
}
printf '%s\n' 'not-a-timestamp' >"$corrupt_stamp"
calls_before_corrupt_stop=$(wc -l <"$calls")
printf '%s' "$corrupt_session" | run_notify claude stop
calls_after_corrupt_stop=$(wc -l <"$calls")

grep -Fq -- '-group agent-codex-thread-123' "$calls" || {
  echo "FAIL: completion did not use thread-id thread-123" >&2
  exit 1
}
grep -Fq -- '-group agent-codex-thread-456' "$calls" || {
  echo "FAIL: chats in one project did not receive distinct groups" >&2
  exit 1
}
grep -Fq -- '-group agent-codex-project-one' "$calls" || {
  echo "FAIL: legacy payload did not fall back to the project basename" >&2
  exit 1
}
grep -Fq -- '-remove agent-codex-thread-123' "$calls" || {
  echo "FAIL: UserPromptSubmit did not remove the matching thread group" >&2
  exit 1
}
grep -Fq -- '-title project-one · input needed' "$calls" || {
  echo "FAIL: Codex PermissionRequest did not trigger an input-needed notification" >&2
  exit 1
}
[ "$calls_before_future" -eq "$calls_after_future" ] || {
  echo "FAIL: an unsupported Codex notify event triggered a completion banner" >&2
  exit 1
}
[ "$calls_before_corrupt_stop" -eq "$calls_after_corrupt_stop" ] || {
  echo "FAIL: a corrupt duration stamp triggered a completion banner" >&2
  exit 1
}
grep -Fq -- 'invalid stamp, skipped' "$log_dir/notify.log" || {
  echo "FAIL: a corrupt duration stamp was not diagnosed" >&2
  exit 1
}
grep -Fq -- 'remove rc=0 tool=codex project=project-one session=thread-123 group=agent-codex-thread-123' \
  "$log_dir/notify.log" || {
  echo "FAIL: successful notification removal was not logged" >&2
  exit 1
}
if find "$state_dir" -maxdepth 1 -type f -name 'agent-notify-*' | grep -q .; then
  echo "FAIL: notification hooks left an unused duration stamp" >&2
  exit 1
fi

printf '%s' "$prompt" | HOME="$test_home" TMPDIR="$state_dir" \
  AGENT_NOTIFY_STATE_DIR="$state_dir" AGENT_NOTIFY_LOG_DIR="$log_dir" \
  AGENT_NOTIFY_NOTIFIER="$REJECT_NOTIFIER" bash "$runtime_notify" codex start
grep -Fq -- 'remove rc=99 tool=codex project=project-one session=thread-123 group=agent-codex-thread-123' \
  "$log_dir/notify.log" || {
  echo "FAIL: failed notification removal did not retain its exit code" >&2
  exit 1
}

echo "PASS: Codex notification groups follow the chat session"
