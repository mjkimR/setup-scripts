#!/usr/bin/env bash

set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
source "$PROJECT_ROOT/lib/utils.sh"
export PATH="$PATH:$HOME/.local/bin"

if has_cmd gh; then
  log_info "gh is already installed; skipping."
  exit 0
fi

case "$(get_os)" in
  macos)
    if ! has_cmd brew; then
      log_error "Homebrew is required to install gh on macOS."
      exit 1
    fi
    brew install gh
    ;;
  ubuntu)
    sudo apt-get update
    sudo apt-get install -y gh
    ;;
  *)
    log_error "Unsupported OS for gh; install it manually."
    exit 1
    ;;
esac

if ! has_cmd gh; then
  log_error "gh installation did not provide the gh command."
  exit 1
fi
log_success "gh installed: $(gh --version)"
