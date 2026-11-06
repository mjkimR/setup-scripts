#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../../../.." && pwd)"
INSTALLER="$PROJECT_ROOT/modules/agents/instructions/install.sh"
test_root=$(mktemp -d "${TMPDIR:-/tmp}/gemini-instructions-test.XXXXXX")
trap 'rm -rf -- "$test_root"' EXIT
test_home="$test_root/home with spaces"
target="$test_home/.gemini/GEMINI.md"
run_installer() {
  HOME="$test_home" PATH=/usr/bin:/bin bash "$INSTALLER" >"$test_root/install.out" 2>&1
}

assert_skipped() {
  run_installer
  case "$(cat "$test_root/install.out")" in
    *'[INFO]'*'Skipping Gemini global instructions:'*) ;;
    *) echo 'FAIL: missing skip info message' >&2; exit 1 ;;
  esac
  [ ! -e "$target.bak" ]
  [ ! -e "$target.bak.latest" ]
}

# Install the exact preset without adding management markers.
run_installer
cmp "$target" "$PROJECT_ROOT/config/gemini/GEMINI.md"
assert_skipped
cmp "$target" "$PROJECT_ROOT/config/gemini/GEMINI.md"

# Preserve custom content byte for byte, including a missing final newline.
printf '%s' 'Personal instructions' >"$target"
cp "$target" "$test_root/original"
assert_skipped
cmp "$target" "$test_root/original"

# An empty file is still an existing configuration.
: >"$target"
assert_skipped
[ ! -s "$target" ]
rm "$target"

# Existing links, including broken links, and directories are skipped.
for destination in "$test_root/original" "$test_root/missing"; do
  ln -s "$destination" "$target"
  assert_skipped
  [ -L "$target" ]
  rm "$target"
done
cmp "$test_root/original" <(printf '%s' 'Personal instructions')
[ ! -e "$test_root/missing" ]
mkdir "$target"
assert_skipped
[ -d "$target" ]

echo 'PASS: global instructions install the preset once and skip existing paths with an info message'
