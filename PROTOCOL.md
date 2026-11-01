# Amerec Elite (A6) panel: local UDP protocol

What one panel actually sent on the local network. Tested on an Amerec AX7.5 steam generator with the Elite touchscreen, software 1.0.5013. The steamer was off for every test below. No start, stop, temperature, timer or light command has been sent yet.

Status words used here:

- **Observed:** seen in a capture from this panel.
- **From skyer:** the meaning comes from the [skyer Tylo integration](https://github.com/skyer/home-assistant-tylo-sauna) (built for a sauna), and the value here fits it, but nothing has proved it on this panel yet.
- **Unknown:** seen, meaning not known.

## Packet format

Messages are protobuf-style: each field is a tag followed by a value. There's no outer frame or checksum. One UDP packet can hold many fields.

## Discovery (observed)

The panel sends a packet from its control port to UDP 54377, in pairs, every 10 seconds. No request is needed. Nothing arrived on 54378.

| Field | Meaning |
|---|---|
| 1 | Panel identity, a text GUID in braces. Same as the Identity line on the panel's Network screen. |
| 2 | Control port. Same as the packet's source port. |
| 5 | Panel name, sent as a repeated field with one character per value. |
| 3, 4, 6, 7 | Unknown |

The control port stayed the same for 30 minutes. skyer reports it can change after a reboot. Not tested here.

## Connecting (observed)

Send these to the control port from any local UDP port:

| Packet | Hex | Reply |
|---|---|---|
| HELLO | `c23e33081412043030303028542879286c28f601282028722865286d286f2874286528202863286f286e28742872286f286c3a025001` | Connect reply and full state |
| INIT / keepalive | `8241020802` | Status, repeated about every 15 seconds in the test |
| Favorites request | `d23e03089303` | Echo of the request ID (field 2002 = 403) |

HELLO holds the PIN as text in its field 1000, sub-field 2 (`12 04 30 30 30 30` is `0000`). The rest of it is a client name, "Tylö remote control".

The connect reply is field 2000. Its sub-field 1 is the status: 10 was returned here with PIN 0000. A pull request on the skyer repo reports that 10 means accepted and 20 means wrong PIN. Wrong PIN was not tested here.

The connect reply also has the panel name (sub-field 7), "Control Panel" (9) and the software version (10).

## Status: field 2010 (key and value pairs)

Each entry has sub-field 1 as the ID and sub-field 2 as the value.

Temperatures are °C × 9. To get °F: `raw / 5 + 32`.

| ID | Raw value seen | Reads as | Meaning | Status |
|---|---|---|---|---|
| 10 | 418 | 115.6°F | Target temperature | From skyer |
| 12 | 198 and 207, flipping | 71.6 and 73.4°F (22 and 23°C) | Current temperature | From skyer. Changing by whole °C in this short sample. |
| 13, 15 | 270 | 86°F (30°C) | Probably lowest allowed target | Unknown |
| 14, 16 | 468 | 125.6°F (52°C) | Probably highest allowed target | Unknown |
| 17 | 60 | 60 minutes | Configured stop time | From skyer |
| 18 | 60 | 60 | Possibly the longest allowed stop time | Unknown |
| 19, 20 | 0 | 0 | Humidity, current and target (skyer's order). Zero here. | From skyer |
| 22 | 0 | 0 minutes | Remaining time, 0 when off | From skyer |
| Others | | | | Unknown |

Stored targets all end in .6 when converted to °F (105.6, 110.6, 112.6, 114.6, 115.6). That fits whole °F steps counted down from 52°C (125.6°F). How the panel rounds these for display isn't checked yet.

## Other fields (observed)

| Field | Contents |
|---|---|
| 2011 | More key and value pairs, on/off flags. skyer reads ID 10 as the light. |
| 2030 | Sub-field 1 repeats the current temperature (raw 207 when the status said 207). |
| 2040 | Favorites: slot (1), enabled (2), name (3), temperature (5), stop minutes (6). |
| 2045 | Schedule slots: slot (1), enabled (2), start time in ms since 2000-01-01 by the panel's clock (3), stop minutes (4), temperature (6). |
| 2050 | Sub-field 13 is the panel's clock, sent each minute. Sub-field 11 was 10, which skyer maps to off (11 = heat, 12 = standby). |
| 2070 | Unknown. skyer ties it to steam aroma events. |
| 2120 | A long list of character codes, sent repeatedly. Looks like the panel's font table, not status. |

skyer looks for the mode as the exact bytes `9280010258`. In these captures that exact pattern didn't appear, even though sub-field 11 did. So a parser should read the fields, not match fixed bytes.

## Commands

None sent to this panel yet. skyer lists these for a sauna, and they need testing with someone standing by the steamer:

| Action | Hex (from skyer) |
|---|---|
| Heat on | `c24302500b`, then `d23e02081f` |
| Heat off | `c24302500a`, then `d23e02081f` |
| Light on / off | `a24204080a1001` / `a24204080a1000` |
| Set target | `d24105080a10` + varint of °C × 9 |
| Set stop minutes | `d24105080e10` + varint, then `d23e020801` |
