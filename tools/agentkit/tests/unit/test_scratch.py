from __future__ import annotations

import pytest

from agentkit.errors import ConfigError
from agentkit.scratch import (
    parse_duration,
)


def test_parse_duration() -> None:
    assert parse_duration("30d") == 30 * 86400
    assert parse_duration("12h") == 12 * 3600
    assert parse_duration("15m") == 15 * 60
    assert parse_duration("45s") == 45
    assert parse_duration("60") == 60

    for bad in ("bad", "-5d", "30days", "10x", "", "   "):
        with pytest.raises(ConfigError):
            parse_duration(bad)
