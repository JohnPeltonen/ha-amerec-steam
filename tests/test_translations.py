"""Checks on the UI text. They run without Home Assistant."""

import json
from pathlib import Path

FOLDER = Path(__file__).resolve().parents[1] / "custom_components" / "amerec_steam"


def test_translations_match_strings():
    # HA reads translations/en.json for a custom integration, and hassfest checks strings.json too.
    strings = json.loads((FOLDER / "strings.json").read_text(encoding="utf-8"))
    assert json.loads((FOLDER / "translations" / "en.json").read_text(encoding="utf-8")) == strings
