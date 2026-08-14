"""Config value coercion: the type gate keeps strings and ints out of bool."""

from __future__ import annotations

import click
import pytest

from agentkit.commands.commitcmd import _coerce


def test_bool_fields_accept_boolean_words():
    assert _coerce("false", bool) is False
    assert _coerce("YES", bool) is True


def test_bool_fields_reject_non_boolean_words():
    with pytest.raises(click.ClickException):
        _coerce("maybe", bool)


def test_string_fields_keep_boolean_looking_values():
    # "no" is a language code here, not False.
    assert _coerce("no", str) == "no"
    assert _coerce("off", str) == "off"


def test_int_fields_keep_boolean_looking_digits():
    assert _coerce("0", int) == 0
    assert _coerce("1", int) == 1
