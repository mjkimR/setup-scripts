#!/usr/bin/env bash

# Runs every test in the repository: the shell suites that cover installers and
# hooks, and the pytest suite that covers the agentkit package.
#
# Usage: tests/run-all.sh [pattern] [unit|integration|all]
#   pattern  substring; only suites whose name contains it are run

set -uo pipefail

TESTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$TESTS_DIR/.." && pwd)"
FILTER="${1:-}"
TEST_TIER="${2:-all}"
case "$TEST_TIER" in
  all|unit|integration) ;;
  *) echo "usage: tests/run-all.sh [pattern] [unit|integration|all]" >&2; exit 2 ;;
esac

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
  [ "$TEST_TIER" = all ] || [[ "$name" == "$TEST_TIER/"* ]] || continue

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
  suite="$package_dir/tests"
  [ -d "$suite" ] || continue
  matches "tools/$package" || continue

  test_args=()
  if [ "$TEST_TIER" != all ]; then
    if [ ! -d "$suite/$TEST_TIER" ]; then
      echo "No $TEST_TIER tests in tools/$package."
      continue
    fi
    test_args+=("tests/$TEST_TIER")
  fi
  heading "tools/$package ($TEST_TIER pytest)"
  if ! command -v uv >/dev/null 2>&1; then
    skipped+=("tools/$package — uv not installed")
    continue
  fi

  # `uv run` from inside the package resolves its own environment, so the tests
  # import the package under test rather than whatever is installed globally.
  if (cd "$package_dir" && uv run --no-active --quiet pytest ${test_args[@]+"${test_args[@]}"}); then
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
