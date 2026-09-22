from __future__ import annotations

from agentkit.codex.client import duration_seconds


def test_work_timeout_defaults_longer_than_commit() -> None:
    from agentkit.handoff.work import DEFAULT_WORK_TIMEOUT, _build_client

    assert duration_seconds(DEFAULT_WORK_TIMEOUT) > duration_seconds("600s")
    assert _build_client("agy", effort=None, model=None, timeout=None).timeout == DEFAULT_WORK_TIMEOUT
    assert _build_client("codex", effort=None, model=None, timeout="45m").timeout == "45m"
