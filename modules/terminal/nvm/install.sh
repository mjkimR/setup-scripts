#!/usr/bin/env bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
source "$PROJECT_ROOT/lib/utils.sh"

log_header "Installing NVM (Node Version Manager) & Node 24"

# Set NVM_DIR
export NVM_DIR="$HOME/.nvm"

load_nvm() {
  if [ -s "$NVM_DIR/nvm.sh" ]; then
    source "$NVM_DIR/nvm.sh"
    return 0
  fi
  return 1
}

# Check if NVM is installed
if load_nvm && has_cmd nvm; then
  log_info "NVM is already installed. (Version: $(nvm --version))"
else
  log_info "Installing NVM..."
  # Use NVM official installer
  curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash

  # Load NVM immediately
  if ! load_nvm; then
    log_error "Failed to load NVM after installation. Please restart your terminal after the script finishes."
    exit 1
  fi
fi

# Install Node 24
log_info "Installing Node.js v24 (LTS)..."
nvm install 24
nvm use 24
nvm alias default 24

log_success "Node.js installation completed: $(node -v)"
log_success "npm version: $(npm -v)"
