#!/usr/bin/env bash

# Installs and syncs agent hooks to their target agent configuration directories
# based on each hook's meta.yaml definition.

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

log_header "Installing / Syncing AI Agent Hooks"

# Helper to check if a target is enabled in meta.yaml
has_target() {
  local meta_file="$1"
  local target_name="$2"

  if [ ! -f "$meta_file" ]; then
    return 1
  fi

  awk -v target="$target_name" '
    BEGIN { in_targets = 0; found = 0 }
    /^[[:space:]]*targets:[[:space:]]*$/ { in_targets = 1; next }
    /^[[:space:]]*[a-zA-Z0-9_]+:[[:space:]]*$/ { in_targets = 0 }
    in_targets && $0 ~ "^[[:space:]]*-[[:space:]]*" target "([[:space:]]*#.*)?$" {
      found = 1
      exit
    }
    END { exit !found }
  ' "$meta_file"
}

# Collect all hook directories
hook_dirs=()
for dir in "$SCRIPT_DIR"/*/; do
  if [ -d "$dir" ] && [ -f "${dir}meta.yaml" ]; then
    hook_dirs+=("$dir")
  fi
done

if [ ${#hook_dirs[@]} -eq 0 ]; then
  log_warn "No hooks found with meta.yaml in $SCRIPT_DIR."
  exit 0
fi

log_info "Found ${#hook_dirs[@]} hook module(s) with metadata in repository."

for hook_path in "${hook_dirs[@]}"; do
  clean_hook_path="${hook_path%/}"
  hook_name=$(basename "$clean_hook_path")
  meta_file="${clean_hook_path}/meta.yaml"
  installer="${clean_hook_path}/install.sh"

  log_info "Processing hook module: ${BOLD}${hook_name}${NC}"

  # If hook module has its own dedicated install.sh, run it
  if [ -f "$installer" ]; then
    log_info "Executing installer for ${hook_name}..."
    bash "$installer"
  else
    log_warn "No install.sh found for ${hook_name} - skipping execution."
  fi
done

echo ""
log_success "All agent hooks processing finished!"
