#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
source "$PROJECT_ROOT/lib/utils.sh"

target="$HOME/.gemini/GEMINI.md"
preset="$PROJECT_ROOT/config/gemini/GEMINI.md"
if [ -e "$target" ] || [ -L "$target" ]; then
  log_info "Skipping Gemini global instructions: $target already exists."
  exit 0
fi

mkdir -p "$(dirname "$target")"
cp "$preset" "$target"
log_success "Installed Gemini global instructions to $target"
