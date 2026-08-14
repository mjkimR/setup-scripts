#!/usr/bin/env bash

# Get script execution directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Load library files
if [ -f "$SCRIPT_DIR/lib/utils.sh" ] && [ -f "$SCRIPT_DIR/lib/ui.sh" ]; then
  source "$SCRIPT_DIR/lib/utils.sh"
  source "$SCRIPT_DIR/lib/ui.sh"
else
  echo "[ERROR] Required library files (lib/utils.sh or lib/ui.sh) not found."
  exit 1
fi

log_header "Development Environment Auto-Setup Script"

# Detect OS
OS_TYPE=$(get_os)
log_info "Detected OS environment: ${BOLD}${OS_TYPE}${NC}"

if [ "$OS_TYPE" = "unknown" ]; then
  log_warn "Unknown or unsupported OS environment. Unexpected issues may occur."
  read -rp "Do you want to proceed anyway? (y/N): " continue_unknown
  case "$continue_unknown" in
    [yY][eE][sS]|[yY]) log_info "Continuing setup..." ;;
    *) log_info "Exiting script."; exit 0 ;;
  esac
fi

# Menu configurations
options=(
  "Install & Configure Git"
  "Install NVM (Node Version Manager) & Node 24"
  "Install Astral UV (Python Package Manager)"
  "Configure Oh My Zsh & plugins"
  "Sync VS Code/Cursor/VSCodium configs & extensions"
  "Install agent notification hooks (Claude Code & Codex, macOS only)"
  "Sync AI Agent skills (Antigravity, etc.)"
)

# Default checkboxes (true for essential tools, false for optional candidates)
defaults=(
  "true"  # Git
  "true"  # NVM
  "true"  # UV
  "false" # Oh My Zsh
  "true"  # IDE Settings
  "false" # Agent notification hooks
  "true"  # Agent skills
)

# Target script paths
scripts=(
  "$SCRIPT_DIR/modules/terminal/git/install.sh"
  "$SCRIPT_DIR/modules/terminal/nvm/install.sh"
  "$SCRIPT_DIR/modules/terminal/uv/install.sh"
  "$SCRIPT_DIR/modules/terminal/zsh/install.sh"
  "$SCRIPT_DIR/modules/ide/vscode/install.sh"
  "$SCRIPT_DIR/modules/agents/hooks/install.sh"
  "$SCRIPT_DIR/modules/agents/skills/install.sh"
)

# Call Multi-select TUI menu
selected_indices=()
multi_select_menu "Select tools to install/configure:" options defaults selected_indices

# Exit if no items selected
if [ ${#selected_indices[@]} -eq 0 ]; then
  log_warn "No items selected. Exiting configuration."
  exit 0
fi

# Print chosen tools
log_info "Selected tools list:"
for idx in "${selected_indices[@]}"; do
  log_info "  - ${options[idx]}"
done
echo ""

read -rp "Do you want to apply the selected configurations now? (Y/n): " confirm_install
case "$confirm_install" in
  [nN][oO]|[nN])
    log_info "Configuration aborted."
    exit 0
    ;;
  *)
    ;;
esac

# Execute scripts sequentially
for idx in "${selected_indices[@]}"; do
  script_path="${scripts[idx]}"
  
  if [ -f "$script_path" ]; then
    chmod +x "$script_path"
    # Run in subshell
    if ! "$script_path"; then
      log_error "An error occurred during setting up ${options[idx]}."
      read -rp "Do you want to continue to the next step? (Y/n): " continue_next
      case "$continue_next" in
        [nN][oO]|[nN]) log_info "Setup aborted."; exit 1 ;;
        *) continue ;;
      esac
    fi
  else
    log_error "Install script file not found: $script_path"
  fi
done

log_header "All Settings Completed"
log_success "Selected environment configuration tasks are completed successfully!"
log_info "Tip: To use newly installed tools (nvm, node, uv, etc.) in the current session:"
log_info "     Open a new terminal window, or run 'source ~/.zshrc' (or 'source ~/.bashrc') to reload your profile."
