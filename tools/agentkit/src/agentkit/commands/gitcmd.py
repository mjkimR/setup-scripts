"""`agentkit git` — read-only views of the working tree, for skills to quote."""

from __future__ import annotations

import click

from .. import gitutil


@click.group("git")
def git_group() -> None:
    """Summaries of the current repository."""


@git_group.command()
def summary() -> None:
    """Branch, recent history, and staged / unstaged / untracked files."""
    root = gitutil.repo_root()

    branch = gitutil.run(["branch", "--show-current"], cwd=root).strip()
    click.echo("=== Git Working Tree Summary ===")
    click.echo(f"Branch: {branch or 'HEAD detached'}")

    _section("Recent Commit History (last 5)", _log(root), "(No commits yet)")
    _section(
        "Staged Files",
        gitutil.run(["diff", "--name-status", "--cached"], cwd=root).splitlines(),
        "(No staged changes)",
    )
    _section(
        "Unstaged / Modified Files",
        gitutil.run(["diff", "--name-status"], cwd=root).splitlines(),
        "(No unstaged changes)",
    )
    _section(
        "Untracked Files",
        gitutil.run(["ls-files", "--others", "--exclude-standard"], cwd=root).splitlines(),
        "(No untracked files)",
    )


def _log(root) -> list:
    if not gitutil.head_sha(cwd=root):
        return []
    return gitutil.log("HEAD", "%h %s", cwd=root)[:5]


def _section(title: str, lines: list, empty: str) -> None:
    click.echo(f"\n--- {title} ---")
    for line in lines or [empty]:
        click.echo(line)
