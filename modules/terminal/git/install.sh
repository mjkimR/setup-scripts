#!/usr/bin/env bash

# Load utils.sh relative to script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
source "$PROJECT_ROOT/lib/utils.sh"

log_header "Installing and Configuring Git"

OS_TYPE=$(get_os)

# Check and install Git
if has_cmd git; then
  log_info "Git is already installed: $(git --version)"
else
  log_info "Installing Git..."
  if [ "$OS_TYPE" = "macos" ]; then
    if ! has_cmd brew; then
      log_error "Homebrew is not installed. Please install Homebrew and try again."
      exit 1
    fi
    brew install git
  elif [ "$OS_TYPE" = "ubuntu" ]; then
    sudo_keepalive
    sudo apt-get update && sudo apt-get install -y git
  else
    log_error "Unsupported OS or package manager not found. Please install Git manually."
    exit 1
  fi
fi

# Check and guide Git global configuration
current_name=$(git config --global user.name)
current_email=$(git config --global user.email)

log_info "Current Git Configuration:"
log_info "  user.name : ${current_name:-[Not Set]}"
log_info "  user.email: ${current_email:-[Not Set]}"

if [ -n "$current_name" ] && [ -n "$current_email" ]; then
  read -rp "Configuration already exists. Do you want to reconfigure? (y/N): " choice
  case "$choice" in
    [yY][eE][sS]|[yY]) reconfigure=true ;;
    *) reconfigure=false ;;
  esac
else
  reconfigure=true
fi

if [ "$reconfigure" = true ]; then
  read -rp "Enter your Git user.name: " new_name
  read -rp "Enter your Git user.email: " new_email

  if [ -n "$new_name" ]; then
    git config --global user.name "$new_name"
  fi
  if [ -n "$new_email" ]; then
    git config --global user.email "$new_email"
  fi

  log_success "Git configuration updated:"
  log_info "  user.name : $(git config --global user.name)"
  log_info "  user.email: $(git config --global user.email)"
else
  log_info "Keeping existing Git configuration."
fi
