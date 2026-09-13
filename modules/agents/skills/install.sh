#!/usr/bin/env bash

# Installs and syncs agent skills to their target agent configuration directories
# based on each skill's meta.yaml definition.

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

log_header "Installing / Syncing AI Agent Skills & CLIs (agentkit)"

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

# Helper to extract a single top-level field value from meta.yaml
get_meta_field() {
  local meta_file="$1"
  local field_name="$2"

  if [ ! -f "$meta_file" ]; then
    return 1
  fi

  awk -v field="$field_name" '
    $1 ~ "^" field ":" {
      sub("^" field ":[[:space:]]*", "")
      sub(/[[:space:]]+$/, "")
      print
      exit
    }
  ' "$meta_file"
}

# Replace $dest with a symlink to $src. `ln -sfn` against a pre-existing real
# directory would create the link INSIDE it and report success, so a real
# directory is moved aside first instead of being silently kept.
link_skill() { # link_skill <src> <dest> <label>
  local src="$1" dest="$2" label="$3"
  if [ -e "$dest" ] && [ ! -L "$dest" ]; then
    local backup="${dest}.bak"
    if [ -e "$backup" ]; then
      log_warn "  ↳ $dest is a real directory and $backup already exists; skipping ${label}. Resolve manually and re-run."
      return 1
    fi
    mv "$dest" "$backup"
    log_warn "  ↳ Pre-existing $dest moved to $backup"
  fi
  ln -sfn "$src" "$dest"
  log_success "  ↳ Linked to ${label}: $dest"
}

# Collect all skill directories and metadata
all_skill_dirs=()
all_skill_names=()
all_skill_descriptions=()
all_skill_defaults=()

while IFS= read -r dir; do
  [ -d "$dir" ] && [ -f "${dir}/meta.yaml" ] || continue
  clean_path="${dir%/}"
  meta_file="${clean_path}/meta.yaml"
  name=$(get_meta_field "$meta_file" "name")
  if [ -z "$name" ]; then
    name=$(basename "$clean_path")
  fi
  desc=$(get_meta_field "$meta_file" "description")
  default_val=$(get_meta_field "$meta_file" "default")
  if [ "$default_val" = "true" ]; then
    default_val="true"
  else
    default_val="false"
  fi

  all_skill_dirs+=("$clean_path")
  all_skill_names+=("$name")
  all_skill_descriptions+=("$desc")
  all_skill_defaults+=("$default_val")
done < <(find "$SCRIPT_DIR" -mindepth 1 -maxdepth 1 -type d | sort)

if [ ${#all_skill_dirs[@]} -eq 0 ]; then
  log_warn "No skills found with meta.yaml in $SCRIPT_DIR."
  exit 0
fi

selected_skill_paths=()

if [ $# -gt 0 ]; then
  case "$1" in
    --all)
      selected_skill_paths=("${all_skill_dirs[@]}")
      ;;
    -h|--help)
      echo "Usage: $0 [--all | <skill-name> ...]"
      echo ""
      echo "Available skills in repository:"
      for ((i=0; i<${#all_skill_names[@]}; i++)); do
        printf "  - %-20s (default: %5s) %s\n" "${all_skill_names[i]}" "${all_skill_defaults[i]}" "${all_skill_descriptions[i]}"
      done
      exit 0
      ;;
    *)
      for target_arg in "$@"; do
        matched=0
        for ((i=0; i<${#all_skill_names[@]}; i++)); do
          if [ "${all_skill_names[i]}" = "$target_arg" ] || [ "$(basename "${all_skill_dirs[i]}")" = "$target_arg" ]; then
            selected_skill_paths+=("${all_skill_dirs[i]}")
            matched=1
            break
          fi
        done
        if [ "$matched" -eq 0 ]; then
          log_warn "Skill '$target_arg' not found in $SCRIPT_DIR."
        fi
      done
      ;;
  esac
elif [ -t 0 ] && [ -t 1 ]; then
  # Interactive terminal -> Prompt user with multi_select_menu
  menu_options=()
  for ((i=0; i<${#all_skill_names[@]}; i++)); do
    if [ -n "${all_skill_descriptions[i]}" ]; then
      menu_options+=("${all_skill_names[i]} - ${all_skill_descriptions[i]}")
    else
      menu_options+=("${all_skill_names[i]}")
    fi
  done

  selected_indices=()
  multi_select_menu "Select AI Agent skills to install/sync:" menu_options all_skill_defaults selected_indices

  if [ ${#selected_indices[@]} -eq 0 ]; then
    log_warn "No skills selected. Skipping skill synchronization."
    exit 0
  fi

  for idx in "${selected_indices[@]}"; do
    selected_skill_paths+=("${all_skill_dirs[idx]}")
  done
else
  # Non-interactive without arguments -> install skills where default: true
  for ((i=0; i<${#all_skill_dirs[@]}; i++)); do
    if [ "${all_skill_defaults[i]}" = "true" ]; then
      selected_skill_paths+=("${all_skill_dirs[i]}")
    fi
  done
fi

if [ ${#selected_skill_paths[@]} -eq 0 ]; then
  log_warn "No skills to install."
  exit 0
fi

log_info "Synchronizing ${#selected_skill_paths[@]} skill(s)..."

# Target destination directories
ANTIGRAVITY_SKILLS_DIR="$HOME/.gemini/config/skills"
CLAUDE_SKILLS_DIR="$HOME/.claude/skills"
CODEX_SKILLS_DIR="$HOME/.codex/skills"

for clean_skill_path in "${selected_skill_paths[@]}"; do
  skill_name=$(basename "$clean_skill_path")
  meta_file="${clean_skill_path}/meta.yaml"

  log_info "Processing skill: ${BOLD}${skill_name}${NC}"

  # 1. Antigravity Target
  if has_target "$meta_file" "antigravity"; then
    mkdir -p "$ANTIGRAVITY_SKILLS_DIR"
    link_skill "$clean_skill_path" "$ANTIGRAVITY_SKILLS_DIR/$skill_name" "Antigravity"
  fi

  # 2. Claude Code Target
  if has_target "$meta_file" "claude"; then
    mkdir -p "$CLAUDE_SKILLS_DIR"
    link_skill "$clean_skill_path" "$CLAUDE_SKILLS_DIR/$skill_name" "Claude Code"
  fi

  # 3. Codex Target
  if has_target "$meta_file" "codex"; then
    mkdir -p "$CODEX_SKILLS_DIR"
    link_skill "$clean_skill_path" "$CODEX_SKILLS_DIR/$skill_name" "Codex"
  fi
done

echo ""

# --- Skill CLIs ------------------------------------------------------------
#
# Skills are documentation; anything they need to *do* lives in a uv tool under
# tools/. A PATH command is the only reference that resolves identically from
# Claude Code, Codex and Antigravity, which install skills to three different
# places — so every package here is installed, not just the one skill in front
# of us.

if has_cmd uv; then
  UV_BIN="uv"
elif [ -x "$HOME/.local/bin/uv" ]; then
  UV_BIN="$HOME/.local/bin/uv"
else
  UV_BIN=""
fi

for tool_dir in "$PROJECT_ROOT"/tools/*/; do
  [ -f "${tool_dir}pyproject.toml" ] || continue
  tool_name="$(basename "${tool_dir%/}")"

  log_info "Installing skill CLI via uv tool: ${BOLD}${tool_name}${NC}"

  if [ -z "$UV_BIN" ]; then
    log_warn "  ↳ uv not found. Skipping — install uv first, then re-run this module."
    log_warn "    Without it, the commit skills will refuse to run."
    continue
  fi

  # --editable so edits to this repository apply without reinstalling.
  if install_output=$("$UV_BIN" tool install --force --editable "${tool_dir%/}" 2>&1); then
    log_success "  ↳ Installed as an editable tool from: ${tool_dir%/}"
  else
    log_error "  ↳ uv tool install failed:"
    printf '%s\n' "$install_output" | sed 's/^/        /' >&2
  fi
done

if [ -n "$UV_BIN" ]; then
  case ":$PATH:" in
    *":$HOME/.local/bin:"*) ;;
    *) log_warn "\$HOME/.local/bin is not on PATH. Run: $UV_BIN tool update-shell" ;;
  esac
fi

echo ""

log_success "Selected agent skills have been synchronized!"
