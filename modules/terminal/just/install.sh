#!/usr/bin/env bash

set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
source "$PROJECT_ROOT/lib/utils.sh"
export PATH="$PATH:$HOME/.local/bin"

if has_cmd just; then
  log_info "just is already installed; skipping."
  exit 0
fi

case "$(get_os)" in
  macos)
    if ! has_cmd brew; then
      log_error "Homebrew is required to install just on macOS."
      exit 1
    fi
    brew install just
    ;;
  ubuntu)
    mkdir -p "$HOME/.local/bin"
    curl -fsSL https://just.systems/install.sh | bash -s -- --to "$HOME/.local/bin"
    ;;
  *)
    log_error "Unsupported OS for just; install it manually."
    exit 1
    ;;
esac

if ! has_cmd just; then
  log_error "just installation did not provide the just command."
  exit 1
fi
log_success "just installed: $(just --version)"
