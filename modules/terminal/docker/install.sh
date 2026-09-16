#!/usr/bin/env bash

set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
source "$PROJECT_ROOT/lib/utils.sh"
export PATH="$PATH:$HOME/.local/bin:$HOME/.docker/bin"

if has_cmd docker; then
  if docker compose version >/dev/null 2>&1; then
    log_info "Docker and Compose are already installed; skipping."
    exit 0
  fi
  log_error "Docker exists but Compose is missing. Install the Compose plugin for your existing Docker distribution, then rerun setup."
  exit 1
fi

case "$(get_os)" in
  macos)
    if ! has_cmd brew; then
      log_error "Homebrew is required to install Docker Desktop on macOS."
      exit 1
    fi
    brew install --cask docker-desktop
    log_info "Open Docker Desktop once to complete setup and start the engine."
    ;;
  ubuntu)
    # Docker's development installer configures its repository and Compose plugin.
    installer=$(mktemp)
    trap 'rm -f "$installer"' EXIT
    curl -fsSL https://get.docker.com -o "$installer"
    sudo sh "$installer"
    log_info "Docker Engine installed. Configure rootless Docker or Docker group access separately if needed."
    ;;
  *)
    log_error "Unsupported OS for Docker; install it manually."
    exit 1
    ;;
esac

if ! has_cmd docker || ! docker compose version >/dev/null 2>&1; then
  log_error "Docker installation did not provide docker and docker compose on PATH."
  exit 1
fi
log_success "Docker and Compose installed."
