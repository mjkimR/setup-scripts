#!/usr/bin/env bash

# Installs repository-managed subagent definitions. Claude Code discovers
# Markdown definitions below ~/.claude/agents/. Codex has no equivalent
# on-disk registry, so its orchestration instructions live in the paired skill.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

if [ -f "$PROJECT_ROOT/lib/utils.sh" ] && [ -f "$PROJECT_ROOT/lib/ui.sh" ]; then
  source "$PROJECT_ROOT/lib/utils.sh"
  source "$PROJECT_ROOT/lib/ui.sh"
else
  echo "[ERROR] Required library files (lib/utils.sh or lib/ui.sh) not found." >&2
  exit 1
fi

log_header "Installing / Syncing AI Agent Subagents"

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

# Link skill directory helper
link_skill() { # link_skill <source skill directory> <destination> <label>
  local source="$1" destination="$2" label="$3"
  mkdir -p "$(dirname "$destination")"
  if [ -e "$destination" ] && [ ! -L "$destination" ]; then
    local backup="${destination}.bak"
    if [ -e "$backup" ]; then
      log_warn "  ↳ $destination is a real directory and $backup already exists; skipping ${label}."
      return
    fi
    mv "$destination" "$backup"
    log_warn "  ↳ Pre-existing $destination moved to $backup"
  fi
  ln -sfn "$source" "$destination"
  log_success "  ↳ Linked ${label}: $destination"
}

# Discover available subagent roles
all_role_dirs=()
all_role_names=()
all_role_descriptions=()
all_role_defaults=()

while IFS= read -r dir; do
  [ -d "$dir" ] || continue
  clean_path="${dir%/}"
  role_id="$(basename "$clean_path")"
  meta_file="${clean_path}/meta.yaml"

  if [ -f "$meta_file" ]; then
    name=$(get_meta_field "$meta_file" "name")
    [ -n "$name" ] || name="$role_id"
    desc=$(get_meta_field "$meta_file" "description")
    default_val=$(get_meta_field "$meta_file" "default")
    [ "$default_val" = "true" ] || default_val="false"
  else
    name="$role_id"
    desc=""
    default_val="true"
  fi

  all_role_dirs+=("$clean_path")
  all_role_names+=("$name")
  all_role_descriptions+=("$desc")
  all_role_defaults+=("$default_val")
done < <(find "$SCRIPT_DIR" -mindepth 1 -maxdepth 1 -type d | sort)

if [ ${#all_role_dirs[@]} -eq 0 ]; then
  log_warn "No subagent definitions found in $SCRIPT_DIR."
  exit 0
fi

selected_role_paths=()

if [ $# -gt 0 ]; then
  case "$1" in
    --all)
      selected_role_paths=("${all_role_dirs[@]}")
      ;;
    -h|--help)
      echo "Usage: $0 [--all | <role-name> ...]"
      echo ""
      echo "Available subagent roles in repository:"
      for ((i=0; i<${#all_role_names[@]}; i++)); do
        printf "  - %-20s (default: %5s) %s\n" "${all_role_names[i]}" "${all_role_defaults[i]}" "${all_role_descriptions[i]}"
      done
      exit 0
      ;;
    *)
      for target_arg in "$@"; do
        matched=0
        for ((i=0; i<${#all_role_names[@]}; i++)); do
          if [ "${all_role_names[i]}" = "$target_arg" ] || [ "$(basename "${all_role_dirs[i]}")" = "$target_arg" ]; then
            selected_role_paths+=("${all_role_dirs[i]}")
            matched=1
            break
          fi
        done
        if [ "$matched" -eq 0 ]; then
          log_warn "Subagent role '$target_arg' not found in $SCRIPT_DIR."
        fi
      done
      ;;
  esac
elif [ -t 0 ] && [ -t 1 ] && [ ${#all_role_names[@]} -gt 1 ]; then
  # Interactive terminal with multiple roles -> Prompt user with multi_select_menu
  menu_options=()
  for ((i=0; i<${#all_role_names[@]}; i++)); do
    if [ -n "${all_role_descriptions[i]}" ]; then
      menu_options+=("${all_role_names[i]} - ${all_role_descriptions[i]}")
    else
      menu_options+=("${all_role_names[i]}")
    fi
  done

  selected_indices=()
  multi_select_menu "Select AI Agent subagents to install/sync:" menu_options all_role_defaults selected_indices

  if [ ${#selected_indices[@]} -eq 0 ]; then
    log_warn "No subagents selected. Skipping subagent synchronization."
    exit 0
  fi

  for idx in "${selected_indices[@]}"; do
    selected_role_paths+=("${all_role_dirs[idx]}")
  done
else
  # Default roles where default: true
  for ((i=0; i<${#all_role_dirs[@]}; i++)); do
    if [ "${all_role_defaults[i]}" = "true" ]; then
      selected_role_paths+=("${all_role_dirs[i]}")
    fi
  done
fi

if [ ${#selected_role_paths[@]} -eq 0 ]; then
  log_warn "No subagent roles to install."
  exit 0
fi

log_info "Synchronizing ${#selected_role_paths[@]} subagent role(s)..."

CLAUDE_AGENTS_DIR="$HOME/.claude/agents/agentkit"
CLAUDE_SKILLS_DIR="$HOME/.claude/skills"
CODEX_SKILLS_DIR="$HOME/.codex/skills"

for role_dir in "${selected_role_paths[@]}"; do
  role_name="$(basename "$role_dir")"
  log_info "Processing subagent role: ${BOLD}${role_name}${NC}"

  # 1. Claude Code subagent Markdown definitions
  for definition in "$role_dir"/claude/*.md; do
    [ -f "$definition" ] || continue
    name="$(basename "$definition")"
    destination="$CLAUDE_AGENTS_DIR/$name"

    mkdir -p "$CLAUDE_AGENTS_DIR"
    if [ -e "$destination" ] && [ ! -L "$destination" ]; then
      backup="${destination}.bak"
      if [ -e "$backup" ]; then
        log_warn "  ↳ $destination is a real file and $backup already exists; skipping $name. Resolve manually and re-run."
        continue
      fi
      mv "$destination" "$backup"
      log_warn "  ↳ Pre-existing $destination moved to $backup"
    fi

    ln -sfn "$definition" "$destination"
    log_success "  ↳ Linked Claude Code subagent: $destination"
  done

  # 2. Claude Code skills
  for skill in "$role_dir"/claude/*/SKILL.md; do
    [ -f "$skill" ] || continue
    source_dir="$(dirname "$skill")"
    link_skill "$source_dir" "$CLAUDE_SKILLS_DIR/$(basename "$source_dir")" "Claude Code skill"
  done

  # 3. Codex skills
  for skill in "$role_dir"/codex/*/SKILL.md; do
    [ -f "$skill" ] || continue
    source_dir="$(dirname "$skill")"
    link_skill "$source_dir" "$CODEX_SKILLS_DIR/$(basename "$source_dir")" "Codex skill"
  done
done

log_success "AI agent subagents have been synchronized!"
