import pytest
from click.testing import CliRunner

from agentkit.cli import cli as agentkit_cli
from agentkit.devkit.cli import cli


@pytest.mark.parametrize(
    "args", [["--help"], ["copy-diff", "--help"], ["prompt", "--help"], ["prompt", "review", "--help"]]
)
def test_help_exits_successfully(args):
    result = CliRunner().invoke(cli, args)
    assert result.exit_code == 0, result.output
    assert "Error:" not in result.output


def test_agentkit_devkit_help():
    result = CliRunner().invoke(agentkit_cli, ["devkit", "--help"])
    assert result.exit_code == 0, result.output
    assert "copy-diff" in result.output
    assert "prompt" in result.output
