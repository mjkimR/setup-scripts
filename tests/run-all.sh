#!/usr/bin/env bash

# Runs every test in the repository: the shell suites that cover installers and
# hooks, and the pytest suite that covers the agentkit package.
#
# Usage: tests/run-all.sh [pattern]
#   pattern  substring; only suites whose name contains it are run

set -uo pipefail

TESTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$TESTS_DIR/.." && pwd)"
FILTER="${1:-}"

failed=()
skipped=()

heading() { printf '\n\033[1m=== %s\033[0m\n' "$*"; }

matches() {
  [ -z "$FILTER" ] || case "$1" in *"$FILTER"*) return 0 ;; *) return 1 ;; esac
}

# --- Shell suites ----------------------------------------------------------

while IFS= read -r suite; do
  name="${suite#"$TESTS_DIR"/}"
  matches "$name" || continue

  heading "$name"
  if bash "$suite"; then
    :
  else
    failed+=("$name")
  fi
done < <(find "$TESTS_DIR" -name 'test-*.sh' -type f | sort)

# --- Python suites ---------------------------------------------------------

for package_dir in "$PROJECT_ROOT"/tools/*/; do
  package="$(basename "$package_dir")"
  suite="$TESTS_DIR/tools/$package"
  [ -d "$suite" ] || continue
  matches "tools/$package" || continue

  heading "tools/$package (pytest)"
  if ! command -v uv >/dev/null 2>&1; then
    skipped+=("tools/$package — uv not installed")
    continue
  fi

  # `uv run` from inside the package resolves its own environment, so the tests
  # import the package under test rather than whatever is installed globally.
  if (cd "$package_dir" && uv run --quiet pytest "$suite"); then
    :
  else
    failed+=("tools/$package")
  fi
done

# --- Result ----------------------------------------------------------------

echo ""
for note in ${skipped+"${skipped[@]}"}; do
  printf '\033[0;33m[SKIP]\033[0m %s\n' "$note"
done

if [ "${#failed[@]}" -gt 0 ]; then
  printf '\033[0;31m[FAIL]\033[0m %s\n' "${failed[@]}"
  exit 1
fi

printf '\033[0;32m[PASS]\033[0m every suite passed.\n'
