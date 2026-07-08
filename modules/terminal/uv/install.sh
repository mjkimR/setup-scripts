#!/usr/bin/env bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
source "$PROJECT_ROOT/lib/utils.sh"

log_header "Installing Astral UV (Python Package Manager)"

# Check if UV is installed
if has_cmd uv || [ -f "$HOME/.local/bin/uv" ]; then
  log_info "Astral UV is already installed."
  if has_cmd uv; then
    log_info "UV Version: $(uv --version)"
  else
    log_info "UV Version: $($HOME/.local/bin/uv --version)"
  fi
else
  log_info "Installing Astral UV..."
  curl -LsSf https://astral.sh/uv/install.sh | sh

  # Verify installation
  if [ -f "$HOME/.local/bin/uv" ]; then
    log_success "UV installed successfully! (~/.local/bin/uv)"
  else
    log_warn "UV install script executed, but couldn't find $HOME/.local/bin/uv. Please verify your PATH configuration."
  fi
fi
