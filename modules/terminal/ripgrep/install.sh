#!/usr/bin/env bash

set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
source "$PROJECT_ROOT/lib/utils.sh"
export PATH="$PATH:$HOME/.local/bin"

if has_cmd rg; then
  log_info "ripgrep is already installed; skipping."
  exit 0
fi

case "$(get_os)" in
  macos)
    if ! has_cmd brew; then
      log_error "Homebrew is required to install ripgrep on macOS."
      exit 1
    fi
    brew install ripgrep
    ;;
  ubuntu)
    sudo apt-get update
    sudo apt-get install -y ripgrep
    ;;
  *)
    log_error "Unsupported OS for ripgrep; install it manually."
    exit 1
    ;;
esac

if ! has_cmd rg; then
  log_error "ripgrep installation did not provide the rg command."
  exit 1
fi
log_success "ripgrep installed: $(rg --version)"
