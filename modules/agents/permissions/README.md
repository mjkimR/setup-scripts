# Codex development permissions

`install.sh` adds write access for the active workspace roots' `.git` paths and
the global uv cache. It operates on `${CODEX_HOME:-$HOME/.codex}/config.toml`
only when that file already exists. A Codex CLI executable is not required;
the existing configuration can belong to the desktop app.

```sh
bash modules/agents/permissions/install.sh
```

The setup wizard selects this module by default under `--agents` and `--all`.
Python 3.11+ (for standard-library TOML validation) and uv must be available.
The installer checks `PATH`, then `~/.local/bin/uv`. Missing prerequisites or a
missing configuration produce an info message and no configuration changes.

## Managed profile

The installer selects `setup-scripts-dev`, extending the previously selected
`default_permissions` profile, or `:workspace` if none was specified. It adds
exactly two filesystem entries: workspace-relative `.git` and the absolute path
returned by `uv cache dir`, run from HOME to avoid project-local uv settings.
That command honors the user's uv cache configuration, including `UV_CACHE_DIR`.
No virtual environment paths or network settings are added. Other protections
in the parent profile remain in effect.

The profile and default selection live in one `# BEGIN / # END` comment block
at the top of the TOML file. Dotted keys keep subsequent user tables in their
original scope. Repeated runs update this block without duplicating it. Before
an actual change, `.bak` preserves the original configuration and `.bak.latest`
preserves the state before the latest change. Unchanged runs create no backups.
Symlinks, malformed TOML or markers, and collisions with a user-owned profile
of the same name are rejected without rewriting the configuration.

Configurations containing legacy `sandbox_mode` or `sandbox_workspace_write`
settings (including named config profiles) are skipped with an info message:
these settings take precedence over permission profiles and require a deliberate
migration. Full-access profiles are also skipped because they already allow
these writes. Higher-precedence project or managed configuration, command-line
sandbox flags, or a different profile selected in the app can override this
user-level default. Start a new session and check the active permissions.

The `.git` grant is relative to each active workspace root; it does not grant
writes to every Git repository on disk. External Git metadata in linked
worktrees may need an additional explicit grant for its actual location.

References: [OpenAI permission profiles](https://learn.chatgpt.com/docs/permissions)
and [uv cache directory](https://docs.astral.sh/uv/concepts/cache/#cache-directory).

## Verification

```sh
bash tests/run-all.sh permissions
```

Tests use temporary homes, a controlled PATH, and a stubbed uv command. No real
agent is started and no developer settings are changed.
