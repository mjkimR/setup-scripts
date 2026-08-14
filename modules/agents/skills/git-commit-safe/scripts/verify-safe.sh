#!/usr/bin/env bash

# Validates git email whitelist and resolves commit timestamp variables.
# Usage:
#   eval "$(bash verify-safe.sh --env)"   # Exports GIT_AUTHOR_DATE & GIT_COMMITTER_DATE
#   bash verify-safe.sh                   # Human-readable pre-flight verification

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_RESOLVER="$SCRIPT_DIR/resolve-time.py"

if ! command -v python3 >/dev/null 2>&1; then
  echo "[ERROR] python3 is required to run git-commit-safe time resolver." >&2
  exit 1
fi

if [ ! -f "$PYTHON_RESOLVER" ]; then
  echo "[ERROR] Missing time resolver script at: $PYTHON_RESOLVER" >&2
  exit 1
fi

python3 "$PYTHON_RESOLVER" "$@"
