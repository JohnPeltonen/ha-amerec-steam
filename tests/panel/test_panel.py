import asyncio

import panel as panel_module
import pytest
from panel import (
    MODE_OFF,
    MODE_ON,
    NotConfirmedError,
    Panel,
    PanelTimeoutError,
    PinRejectedError,
    build_hello,
    celsius_to_raw,
    discover_panels,
    fahrenheit_to_raw,
    iter_fields,
    raw_to_celsius,
    raw_to_fahrenheit,
)
from simulated_panel import HOST

CAPTURED_HELLO = bytes.fromhex(
    "c23e33081412043030303028542879286c28f601282028722865286d286f28"
    "74286528202863286f286e28742872286f286c3a025001"
)
HEAT_ON = bytes.fromhex("c24302500b")
HEAT_OFF = bytes.fromhex("c24302500a")
HEAT_AUX = bytes.fromhex("d23e02081f")


async def settle() -> None:
    for _ in range(5):
        await asyncio.sleep(0)


def test_hello_matches_what_the_panel_accepted():
    assert build_hello("0000") == CAPTURED_HELLO


def test_hello_holds_the_pin():
    hello = build_hello("1234")
    assert b"\x12\x041234" in hello
    assert len(hello) == len(CAPTURED_HELLO)


@pytest.mark.parametrize(("fahrenheit", "raw"), [(113, 408), (114, 413), (115, 418), (125, 468)])
def test_fahrenheit_matches_the_panel(fahrenheit, raw):
    assert fahrenheit_to_raw(fahrenheit) == raw
    assert raw_to_fahrenheit(raw) == fahrenheit


def test_celsius():
    assert celsius_to_raw(52) == 468
    assert raw_to_celsius(468) == 52
    assert raw_to_celsius(418) == 46


def test_malformed_packets_stop_quietly():
    assert list(iter_fields(b"\xff")) == []
    assert list(iter_fields(b"\x0a\x50abc")) == []
    assert list(iter_fields(b"\x07")) == []


async def test_connect_reads_the_panel(sim, connected):
    assert connected.available
    assert connected.identity == "00000000-0000-4000-8000-000000000001"
    assert connected.name == "Steam"
    assert connected.version == "1.0.5013"
    assert connected.status.mode == MODE_OFF
    assert connected.status.target_raw == 413
    assert connected.status.current_raw == 198
    assert connected.status.remaining_minutes == 0


async def test_connecting_never_sends_a_heat_command(sim, connected):
    assert HEAT_ON not in sim.sent
    assert HEAT_OFF not in sim.sent


async def test_mode_ignores_the_nested_field_with_the_same_number(sim, connected):
    # Field 2050 holds sub-messages that have their own field 11.
    assert connected.status.mode == MODE_OFF


async def test_wrong_pin_is_reported_and_closes_everything(sim):
    sim.pin = "1234"
    panel = Panel(HOST, "0000")
    with pytest.raises(PinRejectedError):
        await panel.connect()
    assert all(transport.closed for transport in sim.transports)


async def test_no_announcement_times_out_without_sending(sim):
    sim.announcing = False
    panel = Panel(HOST, "0000")
    with pytest.raises(PanelTimeoutError):
        await panel.connect()
    assert sim.sent == []
    assert all(transport.closed for transport in sim.transports)


async def test_silent_panel_times_out(sim):
    sim.silent = True
    panel = Panel(HOST, "0000")
    with pytest.raises(PanelTimeoutError):
        await panel.connect()
    assert sim.sent == [CAPTURED_HELLO] * 3
    assert all(transport.closed for transport in sim.transports)


async def test_announcements_from_another_host_are_ignored(sim):
    panel = Panel("192.0.2.99", "0000")
    with pytest.raises(PanelTimeoutError):
        await panel.connect()
    assert sim.sent == []


async def test_start_sends_both_packets_and_confirms(sim, connected):
    sim.sent.clear()
    await connected.start()
    assert sim.sent == [HEAT_ON, HEAT_AUX]
    assert connected.status.mode == MODE_ON
    assert connected.status.remaining_minutes == 60


async def test_unconfirmed_start_is_not_retried(sim, connected):
    sim.ignore_start = True
    sim.sent.clear()
    with pytest.raises(NotConfirmedError):
        await connected.start()
    assert sim.sent == [HEAT_ON, HEAT_AUX]


async def test_stop_sends_both_packets_and_confirms(sim, connected):
    await connected.start()
    sim.sent.clear()
    await connected.stop()
    assert sim.sent == [HEAT_OFF, HEAT_AUX]
    assert connected.status.mode == MODE_OFF


async def test_unconfirmed_stop_is_retried_then_reported(sim, connected):
    await connected.start()
    sim.ignore_stop = True
    sim.sent.clear()
    with pytest.raises(NotConfirmedError):
        await connected.stop()
    assert sim.sent == [HEAT_OFF, HEAT_AUX] * 3


async def test_set_target_matches_the_captured_packet(sim, connected):
    sim.sent.clear()
    await connected.set_target(408)
    assert sim.sent == [bytes.fromhex("d24105080a109803")]
    assert connected.status.target_raw == 408


async def test_unconfirmed_target_is_reported(sim, connected):
    sim.ignore_target = True
    with pytest.raises(NotConfirmedError):
        await connected.set_target(408)


@pytest.mark.parametrize("raw", [269, 469])
async def test_target_outside_the_panel_range_is_never_sent(sim, connected, raw):
    sim.sent.clear()
    with pytest.raises(ValueError):
        await connected.set_target(raw)
    assert sim.sent == []


async def test_change_at_the_wall_panel_reaches_listeners(sim, connected):
    calls = []
    remove = connected.add_listener(lambda: calls.append(connected.status.mode))
    sim.mode, sim.remaining = MODE_ON, 60
    sim.push_status()
    await settle()
    assert calls == [MODE_ON]
    assert connected.status.remaining_minutes == 60
    remove()
    sim.mode = MODE_OFF
    sim.push_status()
    await settle()
    assert calls == [MODE_ON]


async def test_control_port_change_reconnects(sim, connected):
    sim.sent.clear()
    sim.control_port = 41000
    sim.announce()
    await settle()
    assert sim.sent == [CAPTURED_HELLO]
    await connected.start()
    assert connected.status.mode == MODE_ON


async def test_keepalive_is_sent_and_silence_sends_hello(sim, connected, monkeypatch):
    connected.close()
    panel = Panel(HOST, "0000")
    monkeypatch.setattr(panel_module, "KEEPALIVE_INTERVAL", 0.001)
    await panel.connect()
    sim.sent.clear()
    await asyncio.sleep(0.01)
    assert bytes.fromhex("8241020802") in sim.sent

    monkeypatch.setattr(panel_module, "RECONNECT_AFTER", -1)
    monkeypatch.setattr(panel_module, "OFFLINE_AFTER", -1)
    sim.sent.clear()
    await asyncio.sleep(0.01)
    assert CAPTURED_HELLO in sim.sent
    assert not panel.available
    panel.close()


async def test_closing_stops_nothing_on_the_steamer(sim, connected):
    await connected.start()
    sim.sent.clear()
    connected.close()
    assert sim.sent == []
    assert sim.mode == MODE_ON
    assert all(transport.closed for transport in sim.transports)


async def test_closing_twice_is_fine(sim, connected):
    connected.close()
    connected.close()


async def test_commands_after_closing_raise(sim, connected):
    connected.close()
    with pytest.raises(panel_module.PanelError):
        await connected.start()


async def test_discover_returns_the_panels_heard(sim):
    assert await discover_panels(0.01) == {HOST: "Steam"}
    assert all(transport.closed for transport in sim.transports)


async def test_pin_never_reaches_the_debug_log(sim, caplog):
    sim.pin = "4321"
    caplog.set_level("DEBUG")
    panel = Panel(HOST, "4321")
    await panel.connect()
    panel.close()
    assert "4321" not in caplog.text
    assert b"4321".hex() not in caplog.text
