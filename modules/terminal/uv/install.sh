#!/usr/bin/env bash

set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
source "$PROJECT_ROOT/lib/utils.sh"

log_header "Installing Astral UV (Python Package Manager)"

# Check if UV is installed
if has_cmd uv || [ -x "$HOME/.local/bin/uv" ]; then
  log_info "Astral UV is already installed."
  if has_cmd uv; then
    log_info "UV Version: $(uv --version)"
  else
    log_info "UV Version: $("$HOME/.local/bin/uv" --version)"
  fi
else
  log_info "Installing Astral UV..."
  curl -LsSf https://astral.sh/uv/install.sh | sh

  # Verify installation
  if [ -x "$HOME/.local/bin/uv" ]; then
    log_success "UV installed successfully! (~/.local/bin/uv)"
  else
    log_error "UV installation did not provide $HOME/.local/bin/uv."
    exit 1
  fi
fi
