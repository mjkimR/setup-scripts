# Onboarding Guide: git-commit-safe Configuration

This document explains how to set up and configure the `git-commit-safe` skill.

---

## 1. Configuration File Location

The configuration file is stored at:
```text
~/.config/git-commit-safe/config.yaml
```

Keeping this file in your user home directory (`~/.config/`) ensures that personal email addresses and local timestamp rules are never accidentally tracked or committed to Git repositories.

---

## 2. Configuration Schema & Example

Create `~/.config/git-commit-safe/config.yaml` with the following format:

```yaml
# Whitelist of allowed email addresses for git commits
allowed_emails:
  - kwj4479@gmail.com
  - minjae@company.com

# Commit timestamp control settings
time:
  # Daily initial commit time range (HH:MM ~ HH:MM)
  # Today's 1st commit will pick a random timestamp within this window.
  range:
    start: "19:00"
    end: "21:00"

  # Timezone for formatting (e.g. Asia/Seoul, UTC, America/New_York)
  timezone: "Asia/Seoul"

  # Minimum gap in seconds between consecutive rapid commits
  min_gap_seconds: 30
```

---

## 3. How Timestamp Progression Works

- **Today's 1st Commit**: Generates a random base timestamp within `range.start` and `range.end` (e.g., `19:47:15`).
- **Today's Subsequent Commits**: Naturally accumulates the elapsed real-time since the 1st commit (`19:47:15 + elapsed_real_time`).
- **Rapid/Batch Commits**: Enforces a strictly increasing timestamp (+30s~90s minimum gap) to avoid time collisions.

---

## 4. Quick Setup

Run the interactive setup script to generate this file automatically:

```bash
bash modules/agents/skills/git-commit-safe/scripts/setup-config.sh
```

---

## 5. Verification

After creating the file, run the pre-check helper script:

```bash
bash modules/agents/skills/git-commit-safe/scripts/verify-safe.sh
```

If valid, it will output the verified email and resolved timestamp settings.
