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

# Print help message
show_help() {
  echo "Usage: ./setup.sh [OPTION]"
  echo ""
  echo "Interactive development environment and AI agent setup wizard."
  echo ""
  echo "Options:"
  echo "  --env, env        Configure developer environment (Git, NVM, UV, Zsh, VS Code)"
  echo "  --agents, agents  Configure AI agents (Skills, Subagents, Notification hooks)"
  echo "  --all, all        Configure both developer environment and AI agents"
  echo "  -h, --help        Show this help message"
}

# Parse command-line options
MODE=""
if [ $# -gt 0 ]; then
  case "$1" in
    --env|env)
      MODE="env"
      ;;
    --agents|agents)
      MODE="agents"
      ;;
    --all|all)
      MODE="all"
      ;;
    -h|--help)
      show_help
      exit 0
      ;;
    *)
      log_error "Unknown option: $1"
      echo "Run './setup.sh --help' for usage."
      exit 1
      ;;
  esac
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

# Category 1: Development Environment tools
options_env=(
  "Install & Configure Git"
  "Install NVM (Node Version Manager) & Node 24"
  "Install Astral UV (Python Package Manager)"
  "Configure Oh My Zsh & plugins"
  "Sync VS Code/Cursor/VSCodium configs & extensions"
)

defaults_env=(
  "true"  # Git
  "true"  # NVM
  "true"  # UV
  "false" # Oh My Zsh
  "true"  # IDE Settings
)

scripts_env=(
  "$SCRIPT_DIR/modules/terminal/git/install.sh"
  "$SCRIPT_DIR/modules/terminal/nvm/install.sh"
  "$SCRIPT_DIR/modules/terminal/uv/install.sh"
  "$SCRIPT_DIR/modules/terminal/zsh/install.sh"
  "$SCRIPT_DIR/modules/ide/vscode/install.sh"
)

# Category 2: AI Agent Ecosystem
options_agent=(
  "Sync AI Agent skills & agentkit CLI (Antigravity, Claude Code, Codex)"
  "Sync AI Agent subagents (Claude Code; Codex sender profiles)"
  "Install agent notification hooks (Claude Code & Codex, macOS only)"
)

defaults_agent=(
  "true"  # Agent skills
  "true"  # Agent subagents
  "false" # Agent notification hooks
)

scripts_agent=(
  "$SCRIPT_DIR/modules/agents/skills/install.sh"
  "$SCRIPT_DIR/modules/agents/subagents/install.sh"
  "$SCRIPT_DIR/modules/agents/hooks/install.sh"
)

# Runner for a selected module category
run_selected_modules() {
  local prompt="$1"
  local _rsm_opts_name="$2"
  local _rsm_defs_name="$3"
  local _rsm_scripts_name="$4"

  local -a _rsm_opts=()
  local -a _rsm_defs=()
  local -a _rsm_scripts=()
  eval "_rsm_opts=(\"\${${_rsm_opts_name}[@]}\")"
  eval "_rsm_defs=(\"\${${_rsm_defs_name}[@]}\")"
  eval "_rsm_scripts=(\"\${${_rsm_scripts_name}[@]}\")"

  local -a selected_indices=()
  multi_select_menu "$prompt" _rsm_opts _rsm_defs selected_indices

  if [ ${#selected_indices[@]} -eq 0 ]; then
    log_warn "No items selected in this category."
    return 0
  fi

  log_info "Selected tools list:"
  for idx in "${selected_indices[@]}"; do
    log_info "  - ${_rsm_opts[idx]}"
  done
  echo ""

  read -rp "Do you want to apply the selected configurations now? (Y/n): " confirm_install
  case "$confirm_install" in
    [nN][oO]|[nN])
      log_info "Configuration aborted for this category."
      return 0
      ;;
    *)
      ;;
  esac

  for idx in "${selected_indices[@]}"; do
    local script_path="${_rsm_scripts[idx]}"

    if [ -f "$script_path" ]; then
      chmod +x "$script_path"
      if ! "$script_path"; then
        log_error "An error occurred during setting up ${_rsm_opts[idx]}."
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
}

# Prompt category if not specified via CLI
if [ -z "$MODE" ]; then
  categories=(
    "🛠️  Development Environment (Git, Node/NVM, UV, Zsh, VS Code)"
    "🤖 AI Agent Ecosystem (Skills, Subagents, Notification Hooks)"
    "🚀 Full Setup (Environment + AI Agents)"
    "❌ Exit"
  )
  chosen_category=0
  single_select_menu "Select setup category:" categories 0 chosen_category

  case "$chosen_category" in
    0) MODE="env" ;;
    1) MODE="agents" ;;
    2) MODE="all" ;;
    *) log_info "Exiting script."; exit 0 ;;
  esac
fi

# Execute according to chosen mode
case "$MODE" in
  env)
    run_selected_modules "Select environment tools to install/configure:" options_env defaults_env scripts_env
    ;;
  agents)
    run_selected_modules "Select AI Agent components to install/configure:" options_agent defaults_agent scripts_agent
    ;;
  all)
    run_selected_modules "Select environment tools to install/configure:" options_env defaults_env scripts_env
    run_selected_modules "Select AI Agent components to install/configure:" options_agent defaults_agent scripts_agent
    ;;
esac

log_header "Setup Completed"
log_success "Environment configuration tasks finished successfully!"
log_info "Tip: To use newly installed tools in the current terminal session:"
log_info "     Open a new terminal window, or run 'source ~/.zshrc' (or 'source ~/.bashrc') to reload your profile."
