"""Human-facing Git exports and prompts. No staging, commits, or AI calls."""

import tempfile
from pathlib import Path

import click

from . import clipboard, git
from .templates import CODE_REVIEW_PROMPT_TEMPLATE, COMMIT_MESSAGE_PROMPT_TEMPLATE


class Errors(click.Group):
    def invoke(self, ctx):
        try:
            return super().invoke(ctx)
        except (click.exceptions.Exit, click.Abort, click.ClickException):
            raise
        except (RuntimeError, OSError) as error:
            raise click.ClickException(str(error)) from error


@click.group(cls=Errors)
def cli():
    """Personal utilities for sharing Git changes with a chat UI."""


def diff_options(function):
    function = click.option("--exclude", multiple=True, help="Exclude a Git path pattern; repeatable.")(function)
    function = click.option("--last", is_flag=True, help="Use the latest commit, including a root commit.")(function)
    return click.option("--head", is_flag=True, help="Use staged + unstaged tracked changes.")(function)


def patch(head, last, exclude):
    if head and last:
        raise click.UsageError("--head and --last are mutually exclusive.")
    return git.get_diff("last" if last else "head" if head else "staged", exclude)


def write_export(text: str, filename: str | None = None) -> Path:
    # A private, unique directory avoids overwriting another export or following a stale symlink.
    if filename and (Path(filename).name != filename or filename in {".", ".."}):
        raise click.BadParameter("Use a filename without directories.", param_hint="FILENAME")
    name = filename or "diff.txt"
    if not Path(name).suffix:
        name += ".txt"
    path = Path(tempfile.mkdtemp(prefix="devkit-")) / name
    path.write_text(text, encoding="utf-8")
    return path


@cli.command("copy-diff")
@click.argument("filename", required=False)
@diff_options
@click.option("--no-copy", is_flag=True, help="Only write the file and print its path.")
def copy_diff(filename, head, last, exclude, no_copy):
    """Export staged changes to a temp file and copy it as a macOS attachment."""
    path = write_export(patch(head, last, exclude), filename)
    click.echo(str(path))
    if not no_copy:
        try:
            clipboard.copy_file(path)
        except RuntimeError as error:
            click.echo(f"File saved; {error}", err=True)
        else:
            click.echo("Copied file to clipboard.", err=True)


@cli.group()
def prompt():
    """Generate a prompt to paste into your preferred AI chat."""


def emit_prompt(template, language, diff, stdout):
    text = template.format(language=language, diff=diff)
    if stdout:
        click.echo(text)
        return
    try:
        clipboard.copy_text(text)
    except RuntimeError as error:
        click.echo(f"{error}\nPrompt printed below instead.", err=True)
        click.echo(text)
    else:
        click.echo("Copied prompt to clipboard.", err=True)


@prompt.command()
@click.option("--language", "-l", default="English", show_default=True)
@click.option("--stdout", is_flag=True, help="Print instead of copying to the clipboard.")
@click.option("--exclude", multiple=True, help="Exclude a Git path pattern; repeatable.")
def commit(language, stdout, exclude):
    """Generate a Conventional Commits message prompt from staged changes."""
    emit_prompt(COMMIT_MESSAGE_PROMPT_TEMPLATE, language, git.get_diff(exclude=exclude), stdout)


@prompt.command()
@diff_options
@click.option("--language", "-l", default="English", show_default=True)
@click.option("--stdout", is_flag=True, help="Print instead of copying to the clipboard.")
def review(head, last, exclude, language, stdout):
    """Generate a review prompt (staged by default)."""
    emit_prompt(CODE_REVIEW_PROMPT_TEMPLATE, language, patch(head, last, exclude), stdout)


def main():
    cli()
