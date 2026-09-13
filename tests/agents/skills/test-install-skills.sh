#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
INSTALLER="$PROJECT_ROOT/modules/agents/skills/install.sh"

test_root=$(mktemp -d "${TMPDIR:-/tmp}/agentkit-skills-test.XXXXXX")
trap 'rm -rf -- "$test_root"' EXIT

test_home="$test_root/home"
mkdir -p "$test_home"

run_installer() {
  HOME="$test_home" PATH="/usr/bin:/bin" bash "$INSTALLER" "$@" >"$test_root/install.out" 2>&1
}

# 1. Non-interactive default run: should only install default: true skills (git-commit, handoff)
run_installer

gemini_skills="$test_home/.gemini/config/skills"
claude_skills="$test_home/.claude/skills"

[ -L "$gemini_skills/git-commit" ] || {
  echo "FAIL: git-commit was not symlinked by default" >&2
  exit 1
}

[ -L "$claude_skills/handoff" ] || {
  echo "FAIL: handoff was not symlinked to Claude by default" >&2
  exit 1
}

[ ! -e "$gemini_skills/git-commit-revise" ] || {
  echo "FAIL: git-commit-revise was installed despite default: false" >&2
  exit 1
}

[ ! -e "$gemini_skills/polish-doc" ] || {
  echo "FAIL: polish-doc was installed despite default: false" >&2
  exit 1
}

# 2. Selective run: install specific skill
run_installer git-commit-revise

[ -L "$gemini_skills/git-commit-revise" ] || {
  echo "FAIL: git-commit-revise was not installed when explicitly requested" >&2
  exit 1
}

# 3. Full install run with --all
run_installer --all

[ -L "$gemini_skills/polish-doc" ] || {
  echo "FAIL: polish-doc was not installed with --all" >&2
  exit 1
}

# 4. Backup behavior: if a real directory already exists, it is moved aside to .bak
rm "$gemini_skills/git-commit"
mkdir -p "$gemini_skills/git-commit"
printf '%s\n' 'local custom skill' >"$gemini_skills/git-commit/SKILL.md"

run_installer git-commit

[ -d "${gemini_skills}/git-commit.bak" ] || {
  echo "FAIL: installer did not back up the existing real directory" >&2
  exit 1
}

[ -L "$gemini_skills/git-commit" ] || {
  echo "FAIL: installer did not replace real directory with symlink" >&2
  exit 1
}

echo "PASS: skills installer respects defaults, accepts specific selections, and backs up existing directories"
