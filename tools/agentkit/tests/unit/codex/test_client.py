from __future__ import annotations

import pytest

from agentkit.codex.client import duration_seconds


def test_duration_seconds() -> None:
    assert duration_seconds("600s") == 600
    assert duration_seconds("10m") == 600
    assert duration_seconds("1h") == 3600
    assert duration_seconds("42") == 42
    with pytest.raises(ValueError):
        duration_seconds("later")
