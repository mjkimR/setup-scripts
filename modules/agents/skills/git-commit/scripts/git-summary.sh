#!/usr/bin/env bash

# Summarizes Git workspace status, recent history, and staged/unstaged changes.

echo "=== Git Working Tree Summary ==="
echo "Branch: $(git branch --show-current 2>/dev/null || echo 'HEAD detached')"
echo ""

echo "--- Recent Commit History (last 5) ---"
git log -n 5 --oneline 2>/dev/null || echo "(No commits yet)"
echo ""

echo "--- Staged Files ---"
staged_files=$(git diff --name-status --cached 2>/dev/null)
if [ -n "$staged_files" ]; then
  echo "$staged_files"
else
  echo "(No staged changes)"
fi
echo ""

echo "--- Unstaged / Modified Files ---"
unstaged_files=$(git diff --name-status 2>/dev/null)
if [ -n "$unstaged_files" ]; then
  echo "$unstaged_files"
else
  echo "(No unstaged changes)"
fi
echo ""

echo "--- Untracked Files ---"
untracked_files=$(git ls-files --others --exclude-standard 2>/dev/null)
if [ -n "$untracked_files" ]; then
  echo "$untracked_files"
else
  echo "(No untracked files)"
fi
