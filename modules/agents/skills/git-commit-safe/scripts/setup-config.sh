#!/usr/bin/env bash

# Interactive/automated setup script for git-commit-safe configuration.

CONFIG_DIR="$HOME/.config/git-commit-safe"
CONFIG_FILE="$CONFIG_DIR/config.yaml"

mkdir -p "$CONFIG_DIR"

if [ -f "$CONFIG_FILE" ]; then
  echo "[INFO] Existing config found at: $CONFIG_FILE"
  echo "--- Current Content ---"
  cat "$CONFIG_FILE"
  echo ""
  read -rp "Do you want to overwrite this config? (y/N): " confirm
  case "$confirm" in
    [yY][eE][sS]|[yY]) ;;
    *) echo "[INFO] Keeping existing config. Exiting."; exit 0 ;;
  esac
fi

CURRENT_EMAIL=$(git config user.email 2>/dev/null || echo "user@example.com")

cat <<EOF > "$CONFIG_FILE"
# ~/.config/git-commit-safe/config.yaml

allowed_emails:
  - $CURRENT_EMAIL

time:
  # Daily initial commit time range (HH:MM ~ HH:MM)
  range:
    start: "19:00"
    end: "21:00"

  timezone: "Asia/Seoul"

  # Minimum gap in seconds between consecutive commits
  min_gap_seconds: 30
EOF

echo "[SUCCESS] Created config file at: $CONFIG_FILE"
echo "--- Generated Content ---"
cat "$CONFIG_FILE"
echo ""
echo "[INFO] You can edit this file anytime to add more allowed emails or adjust time range."
