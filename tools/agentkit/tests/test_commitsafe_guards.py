"""Pre-commit guardrails: the branch a commit lands on, the content it carries.

Every credential-shaped string here is assembled at runtime. Writing one as a
literal would put it in this file's own staged diff, and the scanner would then
refuse to let this repository commit its own tests.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from click.testing import CliRunner

from agentkit.cli import cli
from agentkit.repoconfig import load_repo_config, save_repo_config

AWS_KEY = "AKIA" + "IOSFODNN7EXAMPLE"
GITHUB_TOKEN = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"
PRIVATE_KEY = "-----BEGIN " + "RSA PRIVATE KEY-----"


def _guards(repo: Path, **fields):
    cfg = load_repo_config(cwd=repo)
    assert cfg is not None, "the safe_setup fixture onboards the repo"
    for key, value in fields.items():
        setattr(cfg.guards, key, value)
    save_repo_config(cfg, cwd=repo)


def _stage(repo: Path, name: str, content: str) -> None:
    (repo / name).write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", name], cwd=str(repo), check=True)


def _committed(repo: Path) -> bool:
    return subprocess.run(["git", "log", "-1"], cwd=str(repo), capture_output=True).returncode == 0


def _onboard(repo: Path) -> None:
    CliRunner().invoke(cli, ["commit", "onboard", "--email", "test@example.com"])


def test_a_staged_credential_blocks_the_commit(safe_setup, repo):
    _onboard(repo)
    _stage(repo, "settings.py", f'AWS_ACCESS_KEY_ID = "{AWS_KEY}"\n')

    result = CliRunner().invoke(cli, ["commit-safe", "commit", "-m", "settings"])

    assert result.exit_code != 0
    assert "SECRET_DETECTED" in result.output
    assert "BLOCKED" in result.output
    assert not _committed(repo)


def test_the_secret_itself_is_never_echoed_back(safe_setup, repo):
    _onboard(repo)
    _stage(repo, "settings.py", f'token = "{GITHUB_TOKEN}"\n')

    result = CliRunner().invoke(cli, ["commit-safe", "commit", "-m", "settings"])

    assert "[redacted]" in result.output
    assert GITHUB_TOKEN not in result.output


def test_a_placeholder_env_example_commits_normally(safe_setup, repo):
    """The discriminator is content, not filename — `.env.example` is a normal file."""
    _onboard(repo)
    _stage(repo, ".env.example", "AWS_ACCESS_KEY_ID=your-key-here\nAPI_TOKEN=changeme\n")

    result = CliRunner().invoke(cli, ["commit-safe", "commit", "-m", "docs: add env example"])

    assert result.exit_code == 0, result.output
    assert _committed(repo)


def test_ordinary_code_does_not_trip_the_scanner(safe_setup, repo):
    _onboard(repo)
    _stage(repo, "app.py", "sk = compute_sk()\nsku = 'sk-1234'\nkey = os.environ['API_KEY']\n")

    result = CliRunner().invoke(cli, ["commit-safe", "commit", "-m", "feat: app"])

    assert result.exit_code == 0, result.output


def test_allow_secret_exempts_one_named_path_and_says_so(safe_setup, repo):
    _onboard(repo)
    _stage(repo, "fixture.py", f'FAKE_KEY = "{AWS_KEY}"\n')

    result = CliRunner().invoke(cli, ["commit-safe", "commit", "--allow-secret", "fixture.py", "-m", "test: fixture"])

    assert result.exit_code == 0, result.output
    assert "fixture.py" in result.output


def test_allow_secret_does_not_exempt_a_different_path(safe_setup, repo):
    _onboard(repo)
    _stage(repo, "fixture.py", f'FAKE_KEY = "{AWS_KEY}"\n')
    _stage(repo, "real.py", f'KEY = "{PRIVATE_KEY}"\n')

    result = CliRunner().invoke(cli, ["commit-safe", "commit", "--allow-secret", "fixture.py", "-m", "test: fixture"])

    assert result.exit_code != 0
    assert "real.py" in result.output


def test_allow_paths_exempts_a_configured_glob(safe_setup, repo):
    _onboard(repo)
    _guards(repo, allow_paths=["tests/**"])
    (repo / "tests").mkdir()
    _stage(repo, "tests/fixture.py", f'FAKE_KEY = "{AWS_KEY}"\n')

    result = CliRunner().invoke(cli, ["commit-safe", "commit", "-m", "test: fixture"])

    assert result.exit_code == 0, result.output


def test_a_secret_already_in_history_does_not_block_later_commits(safe_setup, repo):
    """Only added lines are scanned: context would re-flag what is already committed."""
    _onboard(repo)
    _stage(repo, "settings.py", f'KEY = "{AWS_KEY}"\n')
    CliRunner().invoke(cli, ["commit-safe", "commit", "--allow-secret", "settings.py", "-m", "initial"])

    _stage(repo, "settings.py", f'KEY = "{AWS_KEY}"\nDEBUG = True\n')
    result = CliRunner().invoke(cli, ["commit-safe", "commit", "-m", "chore: debug flag"])

    assert result.exit_code == 0, result.output


def test_the_scan_can_be_switched_off(safe_setup, repo):
    _onboard(repo)
    _guards(repo, scan_secrets=False)
    _stage(repo, "settings.py", f'KEY = "{AWS_KEY}"\n')

    result = CliRunner().invoke(cli, ["commit-safe", "commit", "-m", "settings"])

    assert result.exit_code == 0, result.output


def test_no_branch_is_protected_by_default(safe_setup, repo):
    _onboard(repo)
    _stage(repo, "a.txt", "x\n")

    result = CliRunner().invoke(cli, ["commit-safe", "commit", "-m", "feat: a"])

    assert result.exit_code == 0, result.output
    assert load_repo_config(cwd=repo).guards.protected_branches == []


def test_a_protected_branch_refuses_a_direct_commit(safe_setup, repo):
    _onboard(repo)
    branch = subprocess.run(
        ["git", "branch", "--show-current"], cwd=str(repo), capture_output=True, text=True, check=True
    ).stdout.strip()
    _guards(repo, protected_branches=[branch])
    _stage(repo, "a.txt", "x\n")

    result = CliRunner().invoke(cli, ["commit-safe", "commit", "-m", "feat: a"])

    assert result.exit_code != 0
    assert "PROTECTED_BRANCH" in result.output
    assert not _committed(repo)


def test_a_protected_glob_leaves_other_branches_alone(safe_setup, repo):
    _onboard(repo)
    _guards(repo, protected_branches=["release/*"])
    subprocess.run(["git", "checkout", "-q", "-b", "feature/x"], cwd=str(repo), check=True)
    _stage(repo, "a.txt", "x\n")

    result = CliRunner().invoke(cli, ["commit-safe", "commit", "-m", "feat: a"])

    assert result.exit_code == 0, result.output


def test_a_denied_path_blocks_the_commit(safe_setup, repo):
    _onboard(repo)
    _guards(repo, deny_paths=["*.pem"])
    _stage(repo, "server.pem", "not actually a key\n")

    result = CliRunner().invoke(cli, ["commit-safe", "commit", "-m", "chore: cert"])

    assert result.exit_code != 0
    assert "PATH_DENIED" in result.output
    assert not _committed(repo)
