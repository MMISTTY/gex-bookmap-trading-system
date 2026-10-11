"""Reject malformed external settings before they reach trading decisions."""

from dataclasses import fields
import json

import pytest

from gexbook.config import Config


NUMERIC_FIELDS = [f.name for f in fields(Config) if type(f.default) in (int, float)]


@pytest.mark.parametrize("name", NUMERIC_FIELDS)
@pytest.mark.parametrize("value", [True, False, "10", None, [], {}])
def test_numeric_settings_reject_non_numbers(name, value, tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({name: value}))
    with pytest.raises(ValueError):
        Config.load(path)


@pytest.mark.parametrize("name", ["session_start", "session_end"])
def test_session_settings_reject_non_text(name):
    with pytest.raises(ValueError, match="must be text"):
        Config(**{name: 930})


def test_valid_settings_round_trip(tmp_path):
    settings = Config(risk_per_trade=75, slippage_ticks=2)
    path = tmp_path / "settings.json"
    settings.save(path)
    assert Config.load(path) == settings
