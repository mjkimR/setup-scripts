from __future__ import annotations


def test_a_run_keeps_its_log_and_finds_its_conversation(tmp_path, monkeypatch, stub_agy):
    from agentkit.agy import client as client_module

    monkeypatch.setattr(client_module, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(client_module, "CONVERSATIONS_DIR", tmp_path / "conversations")
    stub_agy.mode("none")
    monkeypatch.setenv("AGY_STUB_DENIED", "git ls-files --others")

    run = stub_agy.client.run("do it", add_dir=tmp_path)

    assert run.log_path is not None and run.log_path.parent == tmp_path / "logs"
    assert run.log_path.read_text(encoding="utf-8") == run.log
    assert run.denied_commands() == ["git ls-files --others"]
    assert any(line.startswith("Log: ") for line in run.evidence())
