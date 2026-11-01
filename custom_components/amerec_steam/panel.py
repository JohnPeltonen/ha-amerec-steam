"""The Amerec Elite (A6) panel's local UDP protocol. No homeassistant imports, so its tests run anywhere."""

import asyncio
import logging
import socket
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

ANNOUNCE_PORT = 54377
CONNECTED = 10
MODE_OFF = 10
MODE_ON = 11

# The target range the panel reports: 30 to 52 C.
MIN_RAW = 270
MAX_RAW = 468

ANNOUNCE_TIMEOUT = 15.0
REPLY_TIMEOUT = 0.5
STATE_TIMEOUT = 5.0
COMMAND_TIMEOUT = 5.0
KEEPALIVE_INTERVAL = 15.0
RECONNECT_AFTER = 45.0
OFFLINE_AFTER = 60.0
HELLO_ATTEMPTS = 3
STOP_ATTEMPTS = 3

CLIENT_NAME = "Tylö remote control"
INIT = bytes.fromhex("8241020802")
HEAT_ON = bytes.fromhex("c24302500b")
HEAT_OFF = bytes.fromhex("c24302500a")
HEAT_AUX = bytes.fromhex("d23e02081f")
SET_TARGET_PREFIX = bytes.fromhex("d24105080a10")

FIELD_CONNECT_REPLY = 2000
FIELD_STATUS = 2010
FIELD_MODE = 2050
STATUS_TARGET = 10
STATUS_CURRENT = 12
STATUS_REMAINING = 22


class PanelError(Exception):
    """Something went wrong talking to the panel."""


class PanelTimeoutError(PanelError):
    """The panel didn't announce itself or didn't answer."""


class PinRejectedError(PanelError):
    """The panel answered the connection request with something other than accepted."""


class NotConfirmedError(PanelError):
    """A command was sent, but the status never showed it taking effect."""


def fahrenheit_to_raw(fahrenheit: int) -> int:
    return (fahrenheit - 32) * 5 + 3


def raw_to_fahrenheit(raw: int) -> int:
    """The whole number the panel shows. It drops the decimal: raw 418 is 115.6 and shows as 115."""
    return raw // 5 + 32


def celsius_to_raw(celsius: int) -> int:
    return celsius * 9


def raw_to_celsius(raw: int) -> int:
    return round(raw / 9)


def encode_varint(value: int) -> bytes:
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def decode_varint(data: bytes, index: int) -> tuple[int, int] | None:
    result = shift = 0
    while index < len(data):
        byte = data[index]
        index += 1
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return result, index
        shift += 7
    return None


def iter_fields(data: bytes) -> Iterator[tuple[int, int | bytes]]:
    """Yield (field number, value) for varint and length-delimited fields. Stops at anything malformed."""
    index = 0
    while index < len(data):
        decoded = decode_varint(data, index)
        if decoded is None:
            return
        key, index = decoded
        field, wire_type = key >> 3, key & 7
        if wire_type == 0:
            decoded = decode_varint(data, index)
            if decoded is None:
                return
            value, index = decoded
            yield field, value
        elif wire_type == 2:
            decoded = decode_varint(data, index)
            if decoded is None:
                return
            length, index = decoded
            if index + length > len(data):
                return
            yield field, data[index : index + length]
            index += length
        elif wire_type == 5:
            index += 4
        elif wire_type == 1:
            index += 8
        else:
            return


def text_from_repeated(values: list[int]) -> str:
    """The panel sends text as a repeated field with one character per value."""
    return "".join(chr(value) for value in values if 0 <= value < 0x110000)


def build_hello(pin: str) -> bytes:
    body = bytearray(b"\x08\x14")
    encoded_pin = pin.encode("ascii")
    body += b"\x12" + encode_varint(len(encoded_pin)) + encoded_pin
    for character in CLIENT_NAME:
        body += b"\x28" + encode_varint(ord(character))
    body += b"\x3a\x02\x50\x01"
    return b"\xc2\x3e" + encode_varint(len(body)) + bytes(body)


def parse_announce(data: bytes) -> tuple[str | None, int | None, str]:
    """(identity, control port, panel name) from an announcement."""
    identity = None
    port = None
    name: list[int] = []
    for field, value in iter_fields(data):
        if field == 1 and isinstance(value, bytes):
            identity = value.decode("ascii", errors="replace").strip("{}")
        elif field == 2 and isinstance(value, int):
            port = value
        elif field == 5 and isinstance(value, int):
            name.append(value)
    return identity, port, text_from_repeated(name)


class _UdpProtocol(asyncio.DatagramProtocol):
    def __init__(self, on_datagram: Callable[[bytes, tuple[str, int]], None]) -> None:
        self._on_datagram = on_datagram

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        self._on_datagram(data, addr)


async def open_udp(on_datagram: Callable[[bytes, tuple[str, int]], None], port: int) -> Any:
    """A UDP socket on the given port, or any free port for 0. The tests replace this."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setblocking(False)
        if port:
            # The running integration and its settings screens can both be listening for announcements.
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if hasattr(socket, "SO_REUSEPORT"):
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        sock.bind(("0.0.0.0", port))
        transport, _ = await asyncio.get_running_loop().create_datagram_endpoint(
            lambda: _UdpProtocol(on_datagram), sock=sock
        )
    except BaseException:
        sock.close()
        raise
    return transport


async def discover_panels(seconds: float) -> dict[str, str]:
    """Listen for announcements. Returns the panels heard, as {host: name}."""
    found: dict[str, str] = {}

    def on_datagram(data: bytes, addr: tuple[str, int]) -> None:
        identity, _, name = parse_announce(data)
        if identity:
            found[addr[0]] = name

    transport = await open_udp(on_datagram, ANNOUNCE_PORT)
    try:
        await asyncio.sleep(seconds)
    finally:
        transport.close()
    return found


@dataclass
class PanelStatus:
    connect_status: int | None = None
    mode: int | None = None
    target_raw: int | None = None
    current_raw: int | None = None
    remaining_minutes: int | None = None


class Panel:
    """One connection to the panel. Closing it doesn't stop the steamer: the panel's own timer does that."""

    def __init__(self, host: str, pin: str) -> None:
        self.host = host
        self.status = PanelStatus()
        self.identity: str | None = None
        self.name = ""
        self.version: str | None = None
        self._pin = pin
        self._control_port: int | None = None
        self._announce: Any = None
        self._control: Any = None
        self._keepalive_task: asyncio.Task[None] | None = None
        self._last_rx: float | None = None
        self._changed = asyncio.Event()
        self._lock = asyncio.Lock()
        self._listeners: list[Callable[[], None]] = []

    @property
    def available(self) -> bool:
        return (
            self.status.connect_status == CONNECTED
            and self._last_rx is not None
            and time.monotonic() - self._last_rx < OFFLINE_AFTER
        )

    def add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Call the listener when anything changes. Returns a function that removes it."""
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    async def connect(self) -> None:
        try:
            self._announce = await open_udp(self._on_announce, ANNOUNCE_PORT)
            self._control = await open_udp(self._on_control, 0)
            if not await self._wait_until(lambda: self._control_port is not None, ANNOUNCE_TIMEOUT):
                raise PanelTimeoutError(f"No announcement from {self.host}")
            for _ in range(HELLO_ATTEMPTS):
                self._send_hello()
                if await self._wait_until(lambda: self.status.connect_status is not None, REPLY_TIMEOUT):
                    break
            if self.status.connect_status is None:
                raise PanelTimeoutError(f"No connect reply from {self.host}")
            if self.status.connect_status != CONNECTED:
                raise PinRejectedError(f"Connect status {self.status.connect_status}")
            self._send(INIT, "INIT")
            state_arrived = await self._wait_until(
                lambda: self.status.mode is not None and self.status.target_raw is not None, STATE_TIMEOUT
            )
            if not state_arrived:
                raise PanelTimeoutError(f"No status from {self.host}")
        except BaseException:
            self.close()
            raise
        self._keepalive_task = asyncio.create_task(self._keepalive())

    def close(self) -> None:
        if self._keepalive_task is not None:
            self._keepalive_task.cancel()
            self._keepalive_task = None
        for transport in (self._announce, self._control):
            if transport is not None:
                transport.close()
        self._announce = self._control = None

    async def start(self) -> None:
        """Start the steamer. Sent once, never retried."""
        async with self._lock:
            self._send(HEAT_ON, "HEAT_ON")
            self._send(HEAT_AUX, "HEAT_AUX")
            if not await self._wait_until(lambda: self.status.mode == MODE_ON, COMMAND_TIMEOUT):
                raise NotConfirmedError("The steamer didn't start")

    async def stop(self) -> None:
        """Stop the steamer. Retried, because a stop that gets lost is the one that matters."""
        async with self._lock:
            for _ in range(STOP_ATTEMPTS):
                self._send(HEAT_OFF, "HEAT_OFF")
                self._send(HEAT_AUX, "HEAT_AUX")
                if await self._wait_until(lambda: self.status.mode == MODE_OFF, COMMAND_TIMEOUT):
                    return
            raise NotConfirmedError("The steamer didn't stop")

    async def set_target(self, raw: int) -> None:
        if not MIN_RAW <= raw <= MAX_RAW:
            raise ValueError(f"Target {raw} is outside {MIN_RAW} to {MAX_RAW}")
        async with self._lock:
            self._send(SET_TARGET_PREFIX + encode_varint(raw), f"SET_TARGET {raw}")
            if not await self._wait_until(lambda: self.status.target_raw == raw, COMMAND_TIMEOUT):
                raise NotConfirmedError("The target temperature didn't change")

    async def _wait_until(self, check: Callable[[], bool], timeout: float) -> bool:
        loop = asyncio.get_running_loop()
        end = loop.time() + timeout
        while not check():
            remaining = end - loop.time()
            if remaining <= 0:
                return False
            self._changed.clear()
            try:
                await asyncio.wait_for(self._changed.wait(), remaining)
            except TimeoutError:
                return check()
        return True

    async def _keepalive(self) -> None:
        while True:
            await asyncio.sleep(KEEPALIVE_INTERVAL)
            silent = self._last_rx is None or time.monotonic() - self._last_rx > RECONNECT_AFTER
            if silent:
                # The panel may have rebooted, which would end this session.
                self._send_hello()
            else:
                self._send(INIT, "KEEPALIVE")
            self._notify()

    def _send_hello(self) -> None:
        # Not logged as hex, because it holds the PIN.
        self._send(build_hello(self._pin), "HELLO", log_bytes=False)

    def _send(self, payload: bytes, label: str, log_bytes: bool = True) -> None:
        if self._control is None or self._control_port is None:
            raise PanelError("Not connected")
        if log_bytes:
            logger.debug("TX %s %s", label, payload.hex())
        else:
            logger.debug("TX %s", label)
        self._control.sendto(payload, (self.host, self._control_port))

    def _notify(self) -> None:
        self._changed.set()
        for listener in list(self._listeners):
            listener()

    def _on_announce(self, data: bytes, addr: tuple[str, int]) -> None:
        if addr[0] != self.host:
            return
        identity, port, name = parse_announce(data)
        if identity is None or port is None:
            return
        self.identity = identity
        self.name = name
        if port == self._control_port:
            return
        moved = self._control_port is not None
        self._control_port = port
        if moved:
            logger.debug("Control port is now %d", port)
            self._send_hello()
        self._changed.set()

    def _on_control(self, data: bytes, addr: tuple[str, int]) -> None:
        if addr[0] != self.host:
            return
        logger.debug("RX %s", data.hex())
        self._last_rx = time.monotonic()
        before = PanelStatus(**vars(self.status))
        for field, value in iter_fields(data):
            if not isinstance(value, bytes):
                continue
            if field == FIELD_CONNECT_REPLY:
                self._read_connect_reply(value)
            elif field == FIELD_STATUS:
                self._read_status_pair(value)
            elif field == FIELD_MODE:
                self._read_mode(value)
        if self.status != before:
            self._notify()

    def _read_connect_reply(self, data: bytes) -> None:
        version: list[int] = []
        for field, value in iter_fields(data):
            if field == 1 and isinstance(value, int):
                self.status.connect_status = value
            elif field == 10 and isinstance(value, int):
                version.append(value)
        if version:
            self.version = text_from_repeated(version)

    def _read_status_pair(self, data: bytes) -> None:
        pair = dict(iter_fields(data))
        key, value = pair.get(1), pair.get(2)
        if not isinstance(value, int):
            return
        if key == STATUS_TARGET:
            self.status.target_raw = value
        elif key == STATUS_CURRENT:
            self.status.current_raw = value
        elif key == STATUS_REMAINING:
            self.status.remaining_minutes = value

    def _read_mode(self, data: bytes) -> None:
        for field, value in iter_fields(data):
            if field == 11 and isinstance(value, int):
                self.status.mode = value
