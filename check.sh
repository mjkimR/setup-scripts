#!/usr/bin/env bash

# check.sh — Automatically formats, fixes lint, and runs all test suites.
#
# Usage:
#   ./check.sh           Default: Auto-format, auto-fix lint, and run all tests
#   ./check.sh --check   Check-only (CI mode): fails if unformatted or lint errors exist

set -uo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHECK_ONLY=false

for arg in "$@"; do
  case "$arg" in
    --check|--ci)
      CHECK_ONLY=true
      ;;
    -h|--help)
      echo "Usage: $0 [--check]"
      echo "  (default)  Automatically apply formatting, auto-fix safe lint rules, and run tests"
      echo "  --check    Verify-only mode (fails if formatting or lint errors are found without modifying files)"
      exit 0
      ;;
    *)
      echo "Unknown argument: $arg" >&2
      echo "Usage: $0 [--check]" >&2
      exit 1
      ;;
  esac
done

# Load shared utilities if available
if [ -f "$PROJECT_ROOT/lib/utils.sh" ]; then
  source "$PROJECT_ROOT/lib/utils.sh"
else
  log_header() { printf '\n\033[1;34m=== %s ===\033[0m\n\n' "$*"; }
  log_info() { printf '\033[0;34m[INFO]\033[0m %s\n' "$*"; }
  log_success() { printf '\033[0;32m[SUCCESS]\033[0m %s\n' "$*"; }
  log_error() { printf '\033[0;31m[ERROR]\033[0m %s\n' "$*" >&2; }
  log_warn() { printf '\033[0;33m[WARN]\033[0m %s\n' "$*"; }
fi

log_header "Running Quality Checks (Format, Lint, Tests)"

failed_steps=()

# --- 1. Python Code Formatting & Linting (tools/*) ---------------------------

for tool_dir in "$PROJECT_ROOT"/tools/*/; do
  [ -f "${tool_dir}pyproject.toml" ] || continue
  tool_name="$(basename "${tool_dir%/}")"

  log_info "Processing tool: ${BOLD:-}${tool_name}${NC:-}"

  if ! command -v uv >/dev/null 2>&1; then
    log_warn "  ↳ uv not found. Skipping python checks for ${tool_name}."
    continue
  fi

  if [ "$CHECK_ONLY" = true ]; then
    log_info "  ↳ [Format] Checking code format..."
    if (cd "$tool_dir" && uv run ruff format --check); then
      log_success "  ↳ [Format] Format is clean."
    else
      log_error "  ↳ [Format] Code formatting issues found."
      failed_steps+=("format:${tool_name}")
    fi

    log_info "  ↳ [Lint] Checking lint rules..."
    if (cd "$tool_dir" && uv run ruff check); then
      log_success "  ↳ [Lint] Lint passed."
    else
      log_error "  ↳ [Lint] Lint errors found."
      failed_steps+=("lint:${tool_name}")
    fi
  else
    log_info "  ↳ [Format] Formatting with ruff..."
    if (cd "$tool_dir" && uv run ruff format); then
      log_success "  ↳ [Format] Format applied."
    else
      log_error "  ↳ [Format] ruff format failed."
      failed_steps+=("format:${tool_name}")
    fi

    log_info "  ↳ [Lint] Checking & fixing lint with ruff..."
    if (cd "$tool_dir" && uv run ruff check --fix); then
      log_success "  ↳ [Lint] Lint passed / auto-fixed."
    else
      log_error "  ↳ [Lint] ruff check found errors."
      failed_steps+=("lint:${tool_name}")
    fi
  fi
done

# --- 2. Test Suites --------------------------------------------------------

log_header "Running Test Suites"

if [ -f "$PROJECT_ROOT/tests/run-all.sh" ]; then
  if bash "$PROJECT_ROOT/tests/run-all.sh"; then
    log_success "All test suites passed."
  else
    log_error "Test suites failed."
    failed_steps+=("tests")
  fi
else
  log_warn "tests/run-all.sh not found. Skipping tests."
fi

# --- Summary ---------------------------------------------------------------

echo ""
if [ "${#failed_steps[@]}" -gt 0 ]; then
  log_error "Checks failed on: ${failed_steps[*]}"
  exit 1
fi

log_success "All checks passed cleanly!"
exit 0
