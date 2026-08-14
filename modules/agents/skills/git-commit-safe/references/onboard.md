# Onboarding Guide: git-commit-safe

The skill holds the commit workflow. The whitelist, the config and the timestamp
state belong to the `agentkit` CLI, which is installed separately — a `PATH`
command resolves identically from Claude Code, Codex and Antigravity, and none of
them install skills to the same place.

---

## 1. Install the CLI

From the repository root:

```bash
uv tool install --editable tools/agentkit
```

`modules/agents/skills/install.sh` does this for you as part of the skill sync.
`--editable` means edits to the source apply immediately, without reinstalling.

Verify:

```bash
agentkit --version
```

If the command is not found, `~/.local/bin` is missing from `PATH` — `uv tool
update-shell` fixes that.

---

## 2. Create the config

```bash
agentkit commit-safe init
```

It seeds the whitelist with your current `git config user.email`. Add `--force`
to overwrite an existing file.

The config lives at:

```text
~/.config/git-commit-safe/config.yaml
```

Keeping it in `~/.config/` ensures personal email addresses and local timestamp
rules are never accidentally committed to a repository.
`AGENTKIT_COMMIT_SAFE_CONFIG` overrides the location.

---

## 3. Config schema

```yaml
# Whitelist of allowed email addresses for git commits
allowed_emails:
  - kwj4479@gmail.com
  - minjae@company.com

# Commit timestamp control settings
time:
  # Daily initial commit time range (HH:MM ~ HH:MM)
  # Today's 1st commit picks a random timestamp inside this window.
  range:
    start: "19:00"
    end: "21:00"

  # Timezone for formatting (e.g. Asia/Seoul, UTC, America/New_York)
  timezone: "Asia/Seoul"

  # Minimum gap in seconds between consecutive commits
  min_gap_seconds: 30
```

---

## 4. How timestamp progression works

- **Today's 1st commit**: a random base inside `range.start`–`range.end`
  (e.g. `19:47:15`).
- **Later commits today**: the base plus the real time that has actually elapsed
  since it, so a session's commits keep their real spacing.
- **Back-to-back commits**: forced at least `min_gap_seconds` apart, so a batch
  never collapses onto one second.

State lives at `~/.local/state/git-commit-safe/state.json` and resets daily.
`XDG_STATE_HOME` is respected.

---

## 5. Verify

```bash
agentkit commit-safe verify
```

Prints the config path, the whitelisted email, the configured range and the
timestamp the next commit would get. It is a preview — checking never consumes a
timestamp.

Exit codes: `1` identity rejected, `2` config missing or unusable.

---

## 6. For the handoff

`/handoff-commit-safe` uses the same config, so this is all it needs. It also
needs `agy` permission grants, which are separate:

```bash
agentkit agy check    # what is missing
agentkit agy grant    # add it
```
