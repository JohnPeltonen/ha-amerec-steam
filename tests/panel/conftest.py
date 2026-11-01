import sys
from pathlib import Path

import pytest

# The package's __init__.py imports homeassistant, so these tests load panel.py on its own.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "custom_components" / "amerec_steam"))

import panel as panel_module
from simulated_panel import HOST, SimulatedPanel


@pytest.fixture
def sim(monkeypatch: pytest.MonkeyPatch) -> SimulatedPanel:
    simulated = SimulatedPanel()
    monkeypatch.setattr(panel_module, "open_udp", simulated.open_udp)
    monkeypatch.setattr(panel_module, "ANNOUNCE_TIMEOUT", 0.05)
    monkeypatch.setattr(panel_module, "REPLY_TIMEOUT", 0.02)
    monkeypatch.setattr(panel_module, "STATE_TIMEOUT", 0.05)
    monkeypatch.setattr(panel_module, "COMMAND_TIMEOUT", 0.02)
    return simulated


@pytest.fixture
async def connected(sim: SimulatedPanel):
    panel = panel_module.Panel(HOST, "0000")
    await panel.connect()
    yield panel
    panel.close()
