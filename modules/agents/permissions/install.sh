#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
source "$PROJECT_ROOT/lib/utils.sh"

target="${CODEX_HOME:-$HOME/.codex}/config.toml"
if [ ! -e "$target" ] && [ ! -L "$target" ]; then
  log_info "Skipping Codex permissions: $target does not exist."
  exit 0
fi
if [ -L "$target" ] || [ ! -f "$target" ]; then
  log_error "Expected a regular config file at $target; no changes made."
  exit 1
fi
if ! has_cmd python3 || ! python3 -c 'import tomllib' 2>/dev/null; then
  log_info "Skipping Codex permissions: Python 3.11 or newer is required."
  exit 0
fi

uv_command="$(command -v uv || true)"
if [ -z "$uv_command" ] && [ -x "$HOME/.local/bin/uv" ]; then
  uv_command="$HOME/.local/bin/uv"
fi
if [ -z "$uv_command" ]; then
  log_info "Skipping Codex permissions: uv is required to locate its global cache."
  exit 0
fi
cache_dir=$(cd "$HOME" && "$uv_command" cache dir)

tmp=$(mktemp "$target.tmp.XXXXXX")
trap 'rm -f -- "$tmp"' EXIT
cp -p "$target" "$tmp"
python3 "$SCRIPT_DIR/configure.py" "$target" "$tmp" "$cache_dir"
if cmp -s "$target" "$tmp"; then
  exit 0
fi
backup_file "$target"
mv "$tmp" "$target"
log_success "Configured workspace .git and global uv cache writes in $target"
