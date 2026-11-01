"""A stand-in Elite panel that answers byte for byte, without real sockets. No imports from the integration."""

import asyncio

HOST = "192.0.2.10"
ANNOUNCE_PORT = 54377
IDENTITY = b"{00000000-0000-4000-8000-000000000001}"


def varint(value: int) -> bytes:
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def number(field: int, value: int) -> bytes:
    return varint(field << 3) + varint(value)


def message(field: int, body: bytes) -> bytes:
    return varint(field << 3 | 2) + varint(len(body)) + body


def text(field: int, value: str) -> bytes:
    return b"".join(number(field, ord(character)) for character in value)


class SimulatedTransport:
    def __init__(self, panel: "SimulatedPanel", on_datagram, port: int) -> None:
        self.panel = panel
        self.on_datagram = on_datagram
        self.port = port
        self.closed = False

    def sendto(self, data: bytes, addr: tuple[str, int]) -> None:
        self.panel.received(self, data, addr)

    def close(self) -> None:
        self.closed = True


class SimulatedPanel:
    def __init__(self) -> None:
        self.pin = "0000"
        self.control_port = 40000
        self.mode = 10
        self.target = 413
        self.current = 198
        self.remaining = 0
        self.announcing = True
        self.silent = False
        self.ignore_start = False
        self.ignore_stop = False
        self.ignore_target = False
        self.open_error: OSError | None = None
        self.sent: list[bytes] = []
        self.clock_packets: list[bytes] = []
        self.transports: list[SimulatedTransport] = []

    async def open_udp(self, on_datagram, port: int) -> SimulatedTransport:
        if self.open_error:
            raise self.open_error
        transport = SimulatedTransport(self, on_datagram, port)
        self.transports.append(transport)
        if port == ANNOUNCE_PORT and self.announcing:
            self.announce(transport)
        return transport

    def announce(self, transport: SimulatedTransport | None = None) -> None:
        data = message(1, IDENTITY) + number(2, self.control_port) + number(3, 43) + text(5, "Steam")
        for target in [transport] if transport else [t for t in self.transports if t.port == ANNOUNCE_PORT]:
            asyncio.get_running_loop().call_soon(target.on_datagram, data, (HOST, self.control_port))

    def status_packet(self) -> bytes:
        pairs = ((10, self.target), (12, self.current), (22, self.remaining), (17, 60))
        return b"".join(message(2010, number(1, key) + number(2, value)) for key, value in pairs) + message(
            2050, number(11, self.mode) + message(14, number(10, 0) + number(11, 99))
        )

    def received(self, transport: SimulatedTransport, data: bytes, addr: tuple[str, int]) -> None:
        self.sent.append(data)
        if self.silent or addr != (HOST, self.control_port):
            return
        reply = self.reply_to(data)
        if reply is not None:
            asyncio.get_running_loop().call_soon(transport.on_datagram, reply, (HOST, self.control_port))

    def reply_to(self, data: bytes) -> bytes | None:
        if data.startswith(b"\xc2\x3e"):
            length = data[6]
            pin = data[7 : 7 + length].decode()
            if pin != self.pin:
                return message(2000, number(1, 20))
            return message(2000, number(1, 10) + text(7, "Steam") + text(10, "1.0.5013")) + self.status_packet()
        if data == bytes.fromhex("8241020802"):
            return self.status_packet()
        if data == bytes.fromhex("c24302500b"):
            if not self.ignore_start:
                self.mode, self.remaining = 11, 60
                return self.status_packet()
            return None
        if data == bytes.fromhex("c24302500a"):
            if not self.ignore_stop:
                self.mode, self.remaining = 10, 0
                return self.status_packet()
            return None
        if data.startswith(bytes.fromhex("c243")):
            self.clock_packets.append(data)
            return self.status_packet()
        if data.startswith(bytes.fromhex("d24105080a10")):
            if not self.ignore_target:
                self.target = self.read_varint(data[6:])
                return self.status_packet()
            return None
        return None

    @staticmethod
    def read_varint(data: bytes) -> int:
        result = shift = 0
        for byte in data:
            result |= (byte & 0x7F) << shift
            shift += 7
        return result

    def push_status(self) -> None:
        """Send the status on the panel's own, as after a button press on the wall."""
        for transport in self.transports:
            if transport.port == 0 and not transport.closed:
                asyncio.get_running_loop().call_soon(
                    transport.on_datagram, self.status_packet(), (HOST, self.control_port)
                )
