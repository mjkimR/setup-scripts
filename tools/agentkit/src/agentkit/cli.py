"""The `agentkit` entry point.

One command with one group per domain. Skills reference subcommands of this
rather than scripts, because a PATH command resolves identically from Claude
Code, Codex and Antigravity — which install skills to three different places.
"""

from __future__ import annotations

import click

from . import __version__
from .commands.agy import agy
from .commands.commitcmd import commit_group
from .commands.commitsafe import commit_safe
from .commands.gitcmd import git_group
from .commands.handoff import handoff
from .errors import AgentkitError


class ErrorHandlingGroup(click.Group):
    """Turn expected failures into their documented exit codes.

    Catching at the root is enough: every subcommand runs inside this invoke.
    """

    def invoke(self, ctx: click.Context):
        try:
            return super().invoke(ctx)
        except AgentkitError as error:
            click.echo(f"[ERROR] {error}", err=True)
            for hint in error.hints:
                click.echo(f"[INFO]  {hint}", err=True)
            ctx.exit(int(error.exit_code))


@click.group(cls=ErrorHandlingGroup, context_settings={"max_content_width": 100})
@click.version_option(__version__)
def cli() -> None:
    """Shared machinery for this repository's AI agent skills."""


cli.add_command(commit_group)
cli.add_command(commit_safe)
cli.add_command(handoff)
cli.add_command(agy)
cli.add_command(git_group)


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
