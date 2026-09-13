#!/usr/bin/env bash

# Installs repository-managed subagent definitions.  Claude Code discovers
# Markdown definitions below ~/.claude/agents/.  Codex has no equivalent
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

CLAUDE_AGENTS_DIR="$HOME/.claude/agents/agentkit"
CLAUDE_SKILLS_DIR="$HOME/.claude/skills"
CODEX_SKILLS_DIR="$HOME/.codex/skills"
found=0

for definition in "$SCRIPT_DIR"/*/claude/*.md; do
  [ -f "$definition" ] || continue
  found=1
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

if [ "$found" -eq 0 ]; then
  log_warn "No Claude Code subagent definitions found in $SCRIPT_DIR."
fi

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

for skill in "$SCRIPT_DIR"/*/claude/*/SKILL.md; do
  [ -f "$skill" ] || continue
  source="$(dirname "$skill")"
  link_skill "$source" "$CLAUDE_SKILLS_DIR/$(basename "$source")" "Claude Code skill"
done

for skill in "$SCRIPT_DIR"/*/codex/*/SKILL.md; do
  [ -f "$skill" ] || continue
  source="$(dirname "$skill")"
  link_skill "$source" "$CODEX_SKILLS_DIR/$(basename "$source")" "Codex skill"
done

log_success "AI agent subagents have been synchronized!"
