"""Tests for `agentkit handoff work` — continuing work from a handoff document."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from agentkit.agy.client import AgyClient
from agentkit.cli import cli
from agentkit.codex.client import CodexClient, duration_seconds
from agentkit.errors import ConfigError, ExitCode
from agentkit.handoff.work import pickup_prompt, result_path, run_work

CODEX_STUB = Path(__file__).parent / "stubs" / "codex_stub.py"


@pytest.fixture
def stub_codex(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    calls = tmp_path / "codex-calls.jsonl"
    calls.touch()
    monkeypatch.setenv("CODEX_STUB_CALLS", str(calls))

    class Stub:
        executable = str(CODEX_STUB)

        @staticmethod
        def mode(value: str) -> None:
            monkeypatch.setenv("CODEX_STUB_MODE", value)

        @staticmethod
        def calls() -> list:
            return [json.loads(line) for line in calls.read_text(encoding="utf-8").splitlines() if line.strip()]

    CODEX_STUB.chmod(0o755)
    monkeypatch.setenv("CODEX_STUB_MODE", "ok")
    return Stub


@pytest.fixture
def doc(repo: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(repo)
    path = repo / "2026-08-18-demo-handoff.md"
    path.write_text("# Handoff\n\nNext steps: none.\n", encoding="utf-8")
    return path


def test_work_timeout_defaults_longer_than_commit() -> None:
    from agentkit.handoff.work import DEFAULT_WORK_TIMEOUT, _build_client

    assert duration_seconds(DEFAULT_WORK_TIMEOUT) > duration_seconds("600s")
    assert _build_client("agy", effort=None, model=None, timeout=None).timeout == DEFAULT_WORK_TIMEOUT
    assert _build_client("codex", effort=None, model=None, timeout="45m").timeout == "45m"


def test_duration_seconds() -> None:
    assert duration_seconds("600s") == 600
    assert duration_seconds("10m") == 600
    assert duration_seconds("1h") == 3600
    assert duration_seconds("42") == 42
    with pytest.raises(ValueError):
        duration_seconds("later")


def test_missing_document_refuses_to_run(doc: Path) -> None:
    with pytest.raises(ConfigError):
        run_work(doc.parent / "absent.md", to="agy")


def test_codex_receives_flags_and_prompt(doc: Path, stub_codex) -> None:
    client = CodexClient(effort="high", model="gpt-5.2-codex", executable=stub_codex.executable)
    result = run_work(doc, to="codex", client=client)

    assert result.exit_code == ExitCode.OK
    assert "Completed" in result.output

    argv = stub_codex.calls()[0]["argv"]
    assert argv[0] == "exec"
    assert argv[argv.index("--cd") + 1] == str(doc.parent)
    assert argv[argv.index("--model") + 1] == "gpt-5.2-codex"
    assert "model_reasoning_effort=high" in argv
    assert str(doc) in argv[-1]  # the prompt names the document


def test_codex_failure_maps_to_failed(doc: Path, stub_codex) -> None:
    stub_codex.mode("fail")
    client = CodexClient(executable=stub_codex.executable)
    result = run_work(doc, to="codex", client=client)
    assert result.exit_code == ExitCode.FAILED


def test_codex_timeout_maps_to_incomplete(doc: Path, stub_codex) -> None:
    stub_codex.mode("slow")
    client = CodexClient(timeout="1s", executable=stub_codex.executable)
    result = run_work(doc, to="codex", client=client)
    assert result.exit_code == ExitCode.INCOMPLETE


def test_agy_permission_wall_maps_to_incomplete(doc: Path, stub_agy) -> None:
    stub_agy.mode("none")
    result = run_work(doc, to="agy", client=stub_agy.client)
    assert result.exit_code == ExitCode.INCOMPLETE


def test_agy_cooperative_run_is_ok(doc: Path, stub_agy) -> None:
    stub_agy.mode("auth")  # any marker...
    stub_agy.mode("all")  # ...but the cooperative mode prints nothing suspicious
    result = run_work(doc, to="agy", client=stub_agy.client)
    assert result.exit_code == ExitCode.OK
    assert str(doc) in stub_agy.calls()[0]["prompt"]


def test_agy_client_omits_unset_effort_and_passes_model(doc: Path, stub_agy) -> None:
    client = AgyClient(effort=None, model="gemini-3-pro", executable=stub_agy.client.executable)
    run_work(doc, to="agy", client=client)

    call = stub_agy.calls()[0]
    assert call["effort"] == ""
    assert call["model"] == "gemini-3-pro"


def test_cli_missing_doc_exits_incomplete(doc: Path) -> None:
    result = CliRunner().invoke(cli, ["handoff", "work", "--doc", "absent.md"])
    assert result.exit_code == int(ExitCode.INCOMPLETE)


def test_pickup_prompt_names_doc_and_completion_report(doc: Path) -> None:
    prompt = pickup_prompt(doc)
    assert str(doc) in prompt
    assert str(result_path(doc)) in prompt
    assert result_path(doc).name == "2026-08-18-demo-handoff-result.md"

    with pytest.raises(ConfigError):
        pickup_prompt(doc.parent / "absent.md")


def test_cli_prompt_prints_the_pickup_prompt(doc: Path) -> None:
    result = CliRunner().invoke(cli, ["handoff", "prompt", "--doc", str(doc)])
    assert result.exit_code == 0
    assert str(result_path(doc)) in result.output


def test_receivers_get_the_completion_report_instruction(doc: Path, stub_agy) -> None:
    run_work(doc, to="agy", client=stub_agy.client)
    assert str(result_path(doc)) in stub_agy.calls()[0]["prompt"]


def test_missing_completion_report_downgrades_ok_to_incomplete(doc: Path, stub_codex) -> None:
    stub_codex.mode("noreport")
    result = run_work(doc, to="codex", client=CodexClient(executable=stub_codex.executable))
    assert result.exit_code == ExitCode.INCOMPLETE
    assert not result_path(doc).exists()


def test_completion_report_written_means_ok(doc: Path, stub_codex) -> None:
    result = run_work(doc, to="codex", client=CodexClient(executable=stub_codex.executable))
    assert result.exit_code == ExitCode.OK
    assert result_path(doc).read_text(encoding="utf-8").strip() == "stub completion report"
