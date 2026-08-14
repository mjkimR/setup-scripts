#!/usr/bin/env bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# Load library files
if [ -f "$PROJECT_ROOT/lib/utils.sh" ] && [ -f "$PROJECT_ROOT/lib/ui.sh" ]; then
  source "$PROJECT_ROOT/lib/utils.sh"
  source "$PROJECT_ROOT/lib/ui.sh"
else
  echo "[ERROR] Required library files (lib/utils.sh or lib/ui.sh) not found."
  exit 1
fi

log_header "Applying IDE Configurations (VS Code & derivatives)"

OS_TYPE=$(get_os)

# Define configuration base paths
if [ "$OS_TYPE" = "macos" ]; then
  CONFIG_BASE="$HOME/Library/Application Support"
elif [ "$OS_TYPE" = "ubuntu" ] || [ "$OS_TYPE" = "linux-other" ] || [ "$OS_TYPE" = "linux" ]; then
  CONFIG_BASE="$HOME/.config"
else
  log_error "Unsupported OS environment."
  exit 1
fi

# Arrays to store detected IDEs
detected_ides=()
detected_paths=()
detected_clis=()

# macOS specific: Auto-link CLI binaries if they are installed in /Applications but not in PATH
if [ "$OS_TYPE" = "macos" ]; then
  log_info "Checking for installed editor apps in macOS /Applications to link CLI tools..."
  
  # Helper to link CLI tools
  link_macos_cli() {
    local app_name="$1"
    local bin_rel_path="$2"
    local dest_name="$3"
    
    local app_path="/Applications/${app_name}.app"
    local bin_path="${app_path}/${bin_rel_path}"
    
    if [ -d "$app_path" ] && ! has_cmd "$dest_name"; then
      log_info "Found ${app_name} app. Attempting to link '${dest_name}' CLI..."
      mkdir -p "/usr/local/bin"
      if ln -sf "$bin_path" "/usr/local/bin/${dest_name}" 2>/dev/null; then
        log_success "Linked '${dest_name}' CLI to /usr/local/bin/${dest_name}"
      else
        log_info "Sudo permission required to link '${dest_name}' CLI..."
        sudo_keepalive
        sudo ln -sf "$bin_path" "/usr/local/bin/${dest_name}" && \
        log_success "Linked '${dest_name}' CLI to /usr/local/bin/${dest_name} (via sudo)"
      fi
    fi
  }

  link_macos_cli "Visual Studio Code" "Contents/Resources/app/bin/code" "code"
  link_macos_cli "Cursor" "Contents/Resources/app/bin/cursor" "cursor"
  link_macos_cli "VSCodium" "Contents/Resources/app/bin/codium" "codium"
  link_macos_cli "Antigravity IDE" "Contents/Resources/app/bin/antigravity-ide" "antigravity-ide"
fi

# Detect function
check_ide() {
  local name="$1"
  local folder_name="$2"
  local cli_cmd="$3"
  local custom_path="$4"

  local target_dir=""
  if [ -n "$custom_path" ]; then
    target_dir="$custom_path"
  else
    target_dir="$CONFIG_BASE/$folder_name/User"
  fi
  
  # Detected if target config folder exists or CLI executable exists
  if [ -d "$target_dir" ] || has_cmd "$cli_cmd"; then
    detected_ides+=("$name")
    detected_paths+=("$target_dir")
    detected_clis+=("$cli_cmd")
  fi
}

# Define Antigravity IDE custom configuration path if exists
antigravity_path=""
if [ -d "$HOME/.antigravity-ide-server/data" ]; then
  antigravity_path="$HOME/.antigravity-ide-server/data/User"
else
  antigravity_path="$CONFIG_BASE/antigravity-ide/User"
fi

check_ide "Visual Studio Code" "Code" "code" ""
check_ide "Cursor" "Cursor" "cursor" ""
check_ide "VSCodium" "VSCodium" "codium" ""
check_ide "Antigravity IDE" "antigravity-ide" "antigravity-ide" "$antigravity_path"

# If nothing detected, fallback to Visual Studio Code as default
if [ ${#detected_ides[@]} -eq 0 ]; then
  log_warn "No VS Code based IDEs detected."
  log_info "Defaulting to Visual Studio Code configuration path."
  detected_ides+=("Visual Studio Code")
  detected_paths+=("$CONFIG_BASE/Code/User")
  detected_clis+=("code")
fi

# Determine which IDEs to configure
final_indices=()
if [ ${#detected_ides[@]} -eq 1 ]; then
  # Only 1 IDE detected, use it directly without TUI selection
  final_indices=(0)
else
  # Multiple IDEs detected, prompt user to select target IDEs
  log_info "Multiple IDEs detected on your system."
  
  # Prepare selection menu configs
  menu_defaults=()
  for ((i=0; i<${#detected_ides[@]}; i++)); do
    menu_defaults+=("true")
  done
  
  multi_select_menu "Select target IDEs to apply configuration:" detected_ides menu_defaults final_indices
  
  if [ ${#final_indices[@]} -eq 0 ]; then
    log_warn "No IDEs selected. Skipping IDE configuration."
    exit 0
  fi
fi

# Print chosen target IDEs
log_info "Target IDEs for configuration:"
for idx in "${final_indices[@]}"; do
  log_info "  - ${detected_ides[idx]} (${detected_paths[idx]})"
done

# Apply configuration for selected IDEs
for idx in "${final_indices[@]}"; do
  # No 'local' here - this loop is at file scope, and bash rejects 'local'
  # outside a function, which would leave every one of these unset.
  ide_name="${detected_ides[idx]}"
  ide_path="${detected_paths[idx]}"
  ide_cli="${detected_clis[idx]}"

  log_info "----------------------------------------"
  log_info "Configuring ${ide_name}..."
  log_info "Target path: ${ide_path}"

  # 1. Create config directory if not exists
  if [ ! -d "$ide_path" ]; then
    log_info "Creating configuration directory..."
    mkdir -p "$ide_path"
  fi

  # 2. settings.json Configuration
  if [ -f "$PROJECT_ROOT/config/vscode/settings.json" ]; then
    if backup_file "$ide_path/settings.json"; then
      cp "$PROJECT_ROOT/config/vscode/settings.json" "$ide_path/settings.json"
      log_success "Successfully applied settings.json"
    else
      log_error "Skipping settings.json — could not back up the existing file."
    fi
  fi

  # 3. keybindings.json Configuration
  if [ -f "$PROJECT_ROOT/config/vscode/keybindings.json" ]; then
    if backup_file "$ide_path/keybindings.json"; then
      cp "$PROJECT_ROOT/config/vscode/keybindings.json" "$ide_path/keybindings.json"
      log_success "Successfully applied keybindings.json"
    else
      log_error "Skipping keybindings.json — could not back up the existing file."
    fi
  fi

  # 4. Install Extensions
  ext_file="$PROJECT_ROOT/config/extensions.txt"
  if [ -f "$ext_file" ]; then
    if has_cmd "$ide_cli"; then
      log_info "Installing extensions using '${ide_cli}' CLI..."
      while IFS= read -r line || [ -n "$line" ]; do
        # Ignore empty lines and comments
        [[ -z "$line" || "$line" =~ ^# ]] && continue
        # Trim whitespace
        ext_id=$(echo "$line" | xargs)
        log_info "Installing: $ext_id"
        "$ide_cli" --install-extension "$ext_id" >/dev/null 2>&1
      done < "$ext_file"
      log_success "Completed installing extensions."
    else
      log_warn "Could not find '${ide_cli}' in system PATH. Skipping automatic extension installation. (You may need to run 'Shell Command: Install...' from within the IDE)"
    fi
  fi
done

log_success "All selected IDE configurations successfully applied."
