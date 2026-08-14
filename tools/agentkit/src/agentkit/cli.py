"""The `agentkit` entry point.

One command with one group per domain. Skills reference subcommands of this
rather than scripts, because a PATH command resolves identically from Claude
Code, Codex and Antigravity — which install skills to three different places.
"""

from __future__ import annotations

import traceback

import click

from . import __version__
from .commands.agy import agy
from .commands.commitcmd import commit_group
from .commands.commitsafe import commit_safe
from .commands.gitcmd import git_group
from .commands.handoff import handoff
from .errors import Actor, Advisory, AgentkitError, ErrorCode, ExitCode, Retry


class ErrorHandlingGroup(click.Group):
    """Turn expected failures into their documented exit codes.

    Catching at the root is enough: every subcommand runs inside this invoke.
    """

    def invoke(self, ctx: click.Context):
        try:
            return super().invoke(ctx)
        except click.UsageError as error:
            # Click renders and exits these itself; only the number is ours.
            # Click's own default is 2, which already means INCOMPLETE here, so
            # a bad flag would be indistinguishable from a partial commit.
            error.exit_code = int(ExitCode.USAGE)
            raise
        except (click.exceptions.Exit, click.Abort, click.ClickException, SystemExit):
            # Click's own control flow, not failures: `--help`, `--version`,
            # Ctrl-C, and every ctx.exit() a subcommand makes to set its exit
            # code. click.exceptions.Exit is a RuntimeError, so without this it
            # falls through to the catch-all below and a clean exit is reported
            # as a tool crash.
            raise
        except AgentkitError as error:
            _echo(error.advisory.lines(str(error)))
            ctx.exit(int(error.exit_code))
        except Exception as error:
            crash = Advisory(
                code=ErrorCode.TOOL_INTERNAL_ERROR,
                actor=Actor.DEVELOPER,
                retry=Retry.AFTER_FIX,
                target_files=("tools/agentkit/",),
                what_to_report="agentkit crashed unexpectedly; the stack trace below is the whole story.",
                details=("Traceback:",),
            )
            _echo(crash.lines(f"Unhandled exception in agentkit: {error}"))
            for line in traceback.format_exc().strip().splitlines():
                click.echo(f"  {line}", err=True)
            ctx.exit(int(ExitCode.FAILED))


def _echo(lines: list[str]) -> None:
    for line in lines:
        click.echo(line, err=True)


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
