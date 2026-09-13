#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
INSTALLER="$PROJECT_ROOT/modules/agents/subagents/install.sh"
SOURCE="$PROJECT_ROOT/modules/agents/subagents/commit/claude/agentkit-commit.md"

test_root=$(mktemp -d "${TMPDIR:-/tmp}/agentkit-subagents-test.XXXXXX")
trap 'rm -rf -- "$test_root"' EXIT

test_home="$test_root/home"
destination="$test_home/.claude/agents/agentkit/agentkit-commit.md"

run_installer() {
  HOME="$test_home" PATH="/usr/bin:/bin" bash "$INSTALLER" >"$test_root/install.out" 2>&1
}

run_installer

[ -L "$destination" ] || {
  echo "FAIL: Claude subagent definition was not symlinked" >&2
  exit 1
}
[ "$(readlink "$destination")" = "$SOURCE" ] || {
  echo "FAIL: Claude subagent points at the wrong source" >&2
  exit 1
}

rm "$destination"
printf '%s\n' 'user-owned definition' >"$destination"
run_installer

[ -f "${destination}.bak" ] || {
  echo "FAIL: installer did not preserve a user-owned definition" >&2
  exit 1
}
[ "$(<"${destination}.bak")" = 'user-owned definition' ] || {
  echo "FAIL: backup content changed" >&2
  exit 1
}
[ -L "$destination" ] || {
  echo "FAIL: installer did not replace the managed destination with a symlink" >&2
  exit 1
}

echo "PASS: Claude subagent installer links and preserves definitions"
