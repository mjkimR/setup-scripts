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

log_info "Codex uses the handoff-commit skill to spawn its native commit worker."
log_success "AI agent subagents have been synchronized!"
