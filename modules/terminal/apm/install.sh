#!/usr/bin/env bash

set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
source "$PROJECT_ROOT/lib/utils.sh"
export PATH="$PATH:$HOME/.local/bin"

if has_cmd apm; then
  log_info "apm is already installed; skipping."
  exit 0
fi

case "$(get_os)" in
  macos)
    if ! has_cmd brew; then
      log_error "Homebrew is required to install apm on macOS."
      exit 1
    fi
    brew install apm
    ;;
  ubuntu)
    curl -fsSL https://aka.ms/apm-unix | sh
    ;;
  *)
    log_error "Unsupported OS for apm; install it manually."
    exit 1
    ;;
esac

if ! has_cmd apm; then
  log_error "apm installation did not provide the apm command."
  exit 1
fi
log_success "apm installed: $(apm --version)"
