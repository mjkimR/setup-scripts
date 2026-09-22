import pytest
from click.testing import CliRunner

from devkit.cli import cli


@pytest.mark.parametrize(
    "args", [["--help"], ["copy-diff", "--help"], ["prompt", "--help"], ["prompt", "review", "--help"]]
)
def test_help_exits_successfully(args):
    result = CliRunner().invoke(cli, args)
    assert result.exit_code == 0, result.output
    assert "Error:" not in result.output
