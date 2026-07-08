#!/usr/bin/env bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
source "$PROJECT_ROOT/lib/utils.sh"

log_header "Configuring Zsh & Oh My Zsh"

OS_TYPE=$(get_os)

# 1. Verify and Install Zsh
if has_cmd zsh; then
  log_info "Zsh is already installed: $(zsh --version)"
else
  log_info "Installing Zsh..."
  if [ "$OS_TYPE" = "macos" ]; then
    # macOS comes with zsh by default
    brew install zsh 2>/dev/null || log_info "Skipping Zsh installation via Homebrew and using system default Zsh."
  elif [ "$OS_TYPE" = "ubuntu" ]; then
    sudo_keepalive
    sudo apt-get update && sudo apt-get install -y zsh
  else
    log_error "Unsupported OS. Please install Zsh manually."
    exit 1
  fi
fi

# 2. Install Oh My Zsh
ZSH_DIR="$HOME/.oh-my-zsh"
if [ -d "$ZSH_DIR" ]; then
  log_info "Oh My Zsh is already installed."
else
  log_info "Installing Oh My Zsh (unattended mode)..."
  sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)" "" --unattended
  log_success "Oh My Zsh installation completed."
fi

# 3. Install Plugins (zsh-autosuggestions, zsh-syntax-highlighting)
ZSH_CUSTOM="${ZSH_CUSTOM:-$HOME/.oh-my-zsh/custom}"
PLUGINS_DIR="$ZSH_CUSTOM/plugins"

# zsh-autosuggestions
if [ ! -d "$PLUGINS_DIR/zsh-autosuggestions" ]; then
  log_info "Cloning zsh-autosuggestions plugin..."
  git clone https://github.com/zsh-users/zsh-autosuggestions "$PLUGINS_DIR/zsh-autosuggestions"
else
  log_info "zsh-autosuggestions plugin already exists."
fi

# zsh-syntax-highlighting
if [ ! -d "$PLUGINS_DIR/zsh-syntax-highlighting" ]; then
  log_info "Cloning zsh-syntax-highlighting plugin..."
  git clone https://github.com/zsh-users/zsh-syntax-highlighting "$PLUGINS_DIR/zsh-syntax-highlighting"
else
  log_info "zsh-syntax-highlighting plugin already exists."
fi

# 4. Update .zshrc Configurations
ZSHRC="$HOME/.zshrc"
if [ -f "$ZSHRC" ]; then
  log_info "Updating .zshrc configuration..."

  # Replace plugins=(git) with plugins=(git zsh-autosuggestions zsh-syntax-highlighting)
  if grep -q "plugins=(git)" "$ZSHRC"; then
    sed -i.bak 's/plugins=(git)/plugins=(git zsh-autosuggestions zsh-syntax-highlighting)/g' "$ZSHRC" 2>/dev/null || \
    sed -i "" 's/plugins=(git)/plugins=(git zsh-autosuggestions zsh-syntax-highlighting)/g' "$ZSHRC"
    log_success "Successfully added plugin configs to .zshrc."
  else
    log_warn "Could not find 'plugins=(git)' in .zshrc. Skipping auto-registration. Please manually add 'zsh-autosuggestions' and 'zsh-syntax-highlighting' to your plugins list."
  fi
else
  log_warn ".zshrc file does not exist."
fi

# 5. Change Default Shell to Zsh
CURRENT_SHELL=$(basename "$SHELL")
if [ "$CURRENT_SHELL" != "zsh" ]; then
  log_info "Your current default shell is not zsh ($CURRENT_SHELL)."
  read -rp "Do you want to change your default shell to zsh? (y/N): " change_shell
  case "$change_shell" in
    [yY][eE][sS]|[yY])
      log_info "Changing default shell to zsh. (This may require sudo password)"
      chsh -s "$(which zsh)"
      log_success "Default shell changed to zsh. Please reboot or log out and log back in for changes to take effect."
      ;;
    *)
      log_info "Skipping default shell change."
      ;;
  esac
fi
