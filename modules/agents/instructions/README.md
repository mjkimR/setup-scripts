# Gemini global instructions

`install.sh` installs [the English preset](../../../config/gemini/GEMINI.md) into
`~/.gemini/GEMINI.md`, the default global context file for Gemini CLI and a
supported global rule file for Antigravity. The setup wizard selects this module
by default under `--agents` and `--all`.

```sh
bash modules/agents/instructions/install.sh
```

The installer copies the preset only when `~/.gemini/GEMINI.md` is absent.
If the path already exists, including an empty file, directory, or symlink, it
logs an info message and skips installation. Existing files are never merged,
updated, or backed up. The installed file contains only the preset, without
management markers. To change existing instructions, edit the file manually.

Start a new agent session after installation. In Gemini CLI, `/memory show` displays
loaded context. A customized `context.fileName` must still include `GEMINI.md` to
load this preset. Other global files are left intact; conflicting instructions
there may need manual reconciliation.

## Authoring rationale

These are persistent preferences, so they belong in a global context file rather
than an on-demand skill. The preset targets reported failures: unsupported
numbers becoming design requirements, exaggerated claims, and speculative scope.
It allows estimates and proposals with clear assumptions and does not prescribe
an answer format, mandatory questions, or citations for every claim.

The authoring approach follows these official references:

- [Anthropic skill authoring best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices):
  keep instructions concise, choose appropriate freedom, and refine from observed
  failures rather than adding speculative rules.
- [Claude Code memory guidance](https://code.claude.com/docs/en/memory):
  use concrete, consistent instructions and keep always-loaded context small.
- [Gemini prompting guidance](https://ai.google.dev/gemini-api/docs/gemini-3):
  use clear, direct instructions rather than elaborate prompt machinery.
- [Gemini context files](https://geminicli.com/docs/cli/gemini-md/) and
  [Antigravity rules](https://antigravity.google/docs/rules/): global file locations.

## Validation

Installer integration tests use a temporary HOME and controlled PATH:

```sh
bash tests/run-all.sh instructions
```

Model behavior has not been benchmarked. For manual comparison in fresh sessions,
try a design request with no baseline measurements (no invented agreed targets),
a request explicitly asking for estimates (useful estimates with assumptions),
and a code search (prefer `rg`). Compare with and without the preset, including
whether ordinary explanations and design alternatives remain useful.
