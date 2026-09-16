# devkit

Personal developer utilities for sending Git changes to an AI chat. Independent
of agentkit: no agent skills, onboarding, app-common dependency, or AI API calls.

## Install

From the setup-scripts repository root:

```sh
uv tool install --editable tools/devkit
```

This is opt-in; the agent skill installer installs only agentkit. Ensure uv's
tool bin directory is on PATH (`uv tool update-shell` if needed).

## Commands

```sh
devkit copy-diff                         # staged diff file, copied as a macOS attachment
devkit copy-diff feature --head          # tracked staged + unstaged changes, feature.txt
devkit copy-diff --last --no-copy         # latest commit to a file; print its path
devkit prompt commit -l Korean           # copy a commit-message prompt
devkit prompt review -l Korean           # copy a staged review prompt
devkit prompt review --last --stdout     # print a prompt without clipboard access
devkit prompt review --head --exclude uv.lock --stdout
```

All commands read from the repository root, even when run in a subdirectory.
They never stage, commit, push, or change repository configuration. Untracked
files are omitted; explicitly stage the intended files to include them.

The default is staged changes. `--head` compares tracked working files to HEAD
and requires an existing commit. `--last` reads the latest commit, including the
initial commit; merges are compared to their first parent. These flags are
mutually exclusive. Commit prompts always use staged changes.

Lockfiles are included by default. Repeat `--exclude PATTERN` to omit paths
using Git pathspec patterns. Excluded content is not available to the reviewer.
Commit prompts use a fixed Conventional Commits template and do not read
agentkit's per-repository conventions.

`copy-diff` creates a unique private OS temporary directory each time. Its
optional argument is a filename, not a path; a missing extension becomes `.txt`.
The path goes to stdout and clipboard status goes to stderr. Files persist until
removed by you or OS temporary-file cleanup; no persistent repo files are made.

File-object clipboard support uses macOS `osascript`. On other systems, or if
copying fails, the file is still saved and its path printed (exit 0).
Text prompts support macOS, Windows/WSL, Wayland (`wl-copy`), and X11
(`xclip`/`xsel`). If copying fails, the prompt is printed with a warning instead
(exit 0). Use `--stdout` for predictable piping. Git errors and empty diffs exit
nonzero. Prompts and files are never uploaded automatically.

## Development

```sh
uv run pytest
```

Repository-wide `./check.sh --check` discovers this package automatically.
