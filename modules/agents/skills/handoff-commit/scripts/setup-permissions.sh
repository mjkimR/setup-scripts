#!/usr/bin/env bash

# Grants the Antigravity CLI the narrow command permissions that a headless
# `/handoff-commit` run needs.
#
# Headless agy cannot prompt, so anything missing from permissions.allow is
# auto-denied and the run silently does nothing. Granting these two rules is
# preferred over --dangerously-skip-permissions, which would auto-approve every
# tool call including arbitrary shell commands.
#
# Usage: setup-permissions.sh [--yes]

set -euo pipefail

SETTINGS="$HOME/.gemini/antigravity-cli/settings.json"
# git ls-files is how the agent enumerates untracked files; without it a
# repository with any untracked path stalls the run. Read-only, like the
# log/diff/status rules that are usually already present.
GRANTS=("command(git add)" "command(git commit)" "command(git ls-files)")

command -v python3 >/dev/null 2>&1 || {
  echo "[ERROR] python3 is required." >&2
  exit 1
}

if [ ! -f "$SETTINGS" ]; then
  echo "[ERROR] Antigravity CLI settings not found at: $SETTINGS" >&2
  echo "[INFO]  Run \`agy\` interactively once to create it." >&2
  exit 1
fi

echo "[INFO] Settings file: $SETTINGS"
echo "[INFO] Rules to grant:"
printf '         %s\n' "${GRANTS[@]}"
echo ""
echo "[WARN] This lets ANY headless agy run stage and create commits in any"
echo "[WARN] repository you launch it from, not just /handoff-commit."
echo ""

if [ "${1:-}" != "--yes" ]; then
  read -rp "Grant these permissions? (y/N): " confirm
  case "$confirm" in
    [yY][eE][sS]|[yY]) ;;
    *) echo "[INFO] Aborted. No changes made."; exit 0 ;;
  esac
fi

cp "$SETTINGS" "$SETTINGS.bak"
echo "[INFO] Backup written to: $SETTINGS.bak"

SETTINGS="$SETTINGS" python3 - "${GRANTS[@]}" <<'PY'
import json
import os
import sys

path = os.environ["SETTINGS"]
with open(path, encoding="utf-8") as fh:
    settings = json.load(fh)

allow = settings.setdefault("permissions", {}).setdefault("allow", [])
added = [rule for rule in sys.argv[1:] if rule not in allow]
allow.extend(added)

with open(path, "w", encoding="utf-8") as fh:
    json.dump(settings, fh, indent=2)
    fh.write("\n")

if added:
    print("[SUCCESS] Added: " + ", ".join(added))
else:
    print("[INFO] All rules were already present. Nothing changed.")
PY

echo ""
echo "[INFO] Current allow-list:"
agy -p "/permissions" 2>/dev/null | sed 's/^/         /' || true
