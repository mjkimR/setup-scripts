#!/usr/bin/env bash
# Bring the terminal that produced a notification back to the front.
# Usage: agent-focus.sh <host-bundle-id> <iterm-session-id> <project-root>
#
# terminal-notifier's -activate only raises an app, so with several agent
# sessions open you land in whichever window was last active - which is how
# a Claude notification could drop you into a terminal that never ran it.
# iTerm2 exposes its sessions to AppleScript under the same UUID that
# ITERM_SESSION_ID carries, so the exact split pane can be selected instead.
# Editors that host an integrated terminal have no such handle, so they get
# the folder opened, which raises the window already holding that workspace.
#
# The third argument is the editor's project root, already resolved by
# agent-notify.sh - NOT the session's cwd. Handing an editor a subdirectory
# makes it open that as a new project instead of raising the existing window.

set -u

bundle="${1:-}"
iterm_session="${2:-}"
cwd="${3:-}"

if [ -n "$iterm_session" ] && [ "$bundle" = "com.googlecode.iterm2" ]; then
  hit=$(osascript <<APPLESCRIPT 2>/dev/null
tell application "iTerm2"
  repeat with w in windows
    repeat with t in tabs of w
      repeat with s in sessions of t
        if id of s is "$iterm_session" then
          select w
          select t
          select s
          activate
          return "ok"
        end if
      end repeat
    end repeat
  end repeat
  return "gone"
end tell
APPLESCRIPT
)
  # A closed pane falls through to the plain app activation below.
  [ "$hit" = "ok" ] && exit 0
fi

case "$bundle" in
  com.google.antigravity*|com.microsoft.VSCode*|com.todesktop.*|com.exafunction.*|dev.zed.Zed|com.jetbrains.*)
    # VS Code and JetBrains apps focus the window already holding this folder.
    if [ -n "$cwd" ] && [ -d "$cwd" ]; then
      open -b "$bundle" "$cwd" >/dev/null 2>&1 && exit 0
    fi
    ;;
esac

[ -n "$bundle" ] && open -b "$bundle" >/dev/null 2>&1
exit 0
