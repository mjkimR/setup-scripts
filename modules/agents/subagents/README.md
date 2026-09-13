# Subagents

This directory holds reusable role definitions, not executable installer logic.
Each role has one portable contract and provider adapters below it:

```text
subagents/
  <role>/
    README.md             # portable job contract and safety boundary
    codex/README.md       # Codex spawn contract and selected model
    codex/<skill>/        # Codex-only sender skill
    claude/<role>.md      # Claude Code agent definition, installed under ~/.claude/agents/agentkit/
    claude/<skill>/       # Claude-only sender skill
```

`install.sh` installs the Claude Code definitions and each provider's sender
skill. Claude Code has a documented file registry for custom subagents; it
recursively discovers Markdown files under `~/.claude/agents/`. Codex's native
subagents are spawned by the active session, with the model selected at that
call, rather than loaded from an equivalent on-disk role registry. Its
`codex/README.md` and Codex-only sender skill therefore form the Codex adapter.
The same skill name may have a separate Claude implementation under `claude/`;
`install.sh` installs each into that provider's skill directory.

Do not put implementation scripts here. Shared executable policy remains in
`tools/agentkit/`; skills and subagent files describe when and how to use it.

## Adding a role

1. Add `<role>/README.md` with its input, authority, completion signal, and
   explicit non-goals.
2. Add `<role>/codex/README.md` when Codex should run it. State the exact spawn
   fields and why an on-disk Codex CLI profile is not used.
3. Add `<role>/claude/<role>.md` when Claude Code should run it. Keep the
   frontmatter description short; it is always loaded, while the body is loaded
   only when the agent runs.
4. Add a provider-specific sender skill below the adapter. Do not put
   provider branches in one shared `SKILL.md`: the installer already knows
   which target it is linking.
5. Add an installer test using a temporary `HOME` before registering the role
   in user-facing documentation.

The commit role intentionally operates in the shared worktree. A commit changes
repository history, so a worktree-isolated subagent would create commits the
parent cannot directly hand back. Never run another agent in that checkout
while the commit role is active.
