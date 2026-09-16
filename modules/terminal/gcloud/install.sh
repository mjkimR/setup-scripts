#!/usr/bin/env bash

set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
source "$PROJECT_ROOT/lib/utils.sh"
export PATH="$PATH:$HOME/.local/bin:/snap/bin"

if has_cmd gcloud; then
  log_info "gcloud is already installed; skipping."
  exit 0
fi

case "$(get_os)" in
  macos)
    if ! has_cmd brew; then
      log_error "Homebrew is required to install gcloud on macOS."
      exit 1
    fi
    brew install --cask gcloud-cli
    ;;
  ubuntu)
    if ! has_cmd snap; then
      sudo apt-get update
      sudo apt-get install -y snapd
    fi
    sudo snap install google-cloud-cli --classic
    ;;
  *)
    log_error "Unsupported OS for gcloud; install it manually."
    exit 1
    ;;
esac

if ! has_cmd gcloud; then
  log_error "gcloud installation did not provide the gcloud command."
  exit 1
fi
log_success "gcloud installed: $(gcloud --version)"
