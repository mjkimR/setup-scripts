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

log_header "Installing / Syncing AI Agent Skills"

# Helper to check if a target is enabled in meta.yaml
has_target() {
  local meta_file="$1"
  local target_name="$2"

  if [ ! -f "$meta_file" ]; then
    return 1
  fi

  # Awk parses the 'targets:' block and checks for list items like '- target_name'
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

# Collect all skill directories
skill_dirs=()
for dir in "$SCRIPT_DIR"/*/; do
  if [ -d "$dir" ] && [ -f "${dir}meta.yaml" ]; then
    skill_dirs+=("$dir")
  fi
done

if [ ${#skill_dirs[@]} -eq 0 ]; then
  log_warn "No skills found with meta.yaml in $SCRIPT_DIR."
  exit 0
fi

log_info "Found ${#skill_dirs[@]} skill(s) with metadata in repository."

# Target destination directories
ANTIGRAVITY_SKILLS_DIR="$HOME/.gemini/config/skills"
CLAUDE_SKILLS_DIR="$HOME/.claude/skills"
CODEX_SKILLS_DIR="$HOME/.codex/skills"

for skill_path in "${skill_dirs[@]}"; do
  # Remove trailing slash
  clean_skill_path="${skill_path%/}"
  skill_name=$(basename "$clean_skill_path")
  meta_file="${clean_skill_path}/meta.yaml"

  log_info "Processing skill: ${BOLD}${skill_name}${NC}"

  # 1. Antigravity Target
  if has_target "$meta_file" "antigravity"; then
    mkdir -p "$ANTIGRAVITY_SKILLS_DIR"
    link_skill "$clean_skill_path" "$ANTIGRAVITY_SKILLS_DIR/$skill_name" "Antigravity"
  fi

  # 2. Claude Code Target (extensible)
  if has_target "$meta_file" "claude"; then
    mkdir -p "$CLAUDE_SKILLS_DIR"
    link_skill "$clean_skill_path" "$CLAUDE_SKILLS_DIR/$skill_name" "Claude Code"
  fi

  # 3. Codex Target (extensible)
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

  log_info "Installing skill CLI: ${BOLD}${tool_name}${NC}"

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

log_success "All agent skills have been synchronized!"
