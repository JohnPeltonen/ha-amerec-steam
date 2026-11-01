# Amerec Steam integration: design

Date: 2026-10-31. Read [PROTOCOL.md](../../../PROTOCOL.md) first. It records what the panel actually sends and which commands have been proven.

**Status:** the owner chose to build plain steamer control first (climate, time remaining, PIN). The rest of this document is parked and not approved, including alarm start. Phone alarms proved unreliable on Samsung phones: Sleep mode and Routines add entries the app can't see past.

"Owner" below is the person this was built for. "Builder's call" marks a decision the owner hasn't reviewed.

## Why this exists

The owner has an Amerec AX7.5 steam generator with the Elite (A6) Wi-Fi panel. No app connects to it. The panel's own schedule is hard to live with. It treats the time you set as "ready at" and starts 2 or more hours early, and its clock runs fast.

The owner and another household member want two things:

1. The steamer starts by itself before their phone alarm on mornings they're home.
2. They can start it from a phone from anywhere, for example when driving home cold from a winter dive.

Success: the household stops using the panel's schedule, and the steam is ready when they get up.

## Goals

- A public Home Assistant custom integration, installable through HACS, for this panel on the local network.
- Control and status: on/off, target temperature, current temperature, run time, time remaining.
- Alarm start, with its settings in the integration, so nobody needs hand-made helpers or automations.
- Optional notifications for reaching a temperature and for timing out, with a Restart button on the timeout notification.

## Non-goals

- A single panel timer longer than 60 minutes. A longer heat-up is a possible private experiment later, and isn't part of this code.
- Editing or deleting schedule entries on the panel. It only warns about them (see "Panel schedule warning").
- A light entity. The owner's shower light isn't wired to this panel.
- Favorites, aroma and standby.
- Other models. It may work on other Tylö-family panels, but nothing is built or tested for them.

## Anti-goals

- **Home Assistant must never be the only way the steamer turns off.** The panel's timer is always running, and the integration never sets it above 60 minutes. If Home Assistant, Wi-Fi or the integration dies, the panel stops the steamer within 60 minutes of the last start.
- **An alarm start must not happen when its phone's owner is away.** The risk is a door left open by a cleaner while the household is out.
- **It must not start the steamer on its own because of a restart, a reload or a reconnect.** Only an alarm start or a person does that.

## Constraints

- Home Assistant 2026.10 and Python 3.14. Forms use `probatio`, not `voluptuous`.
- HA OS on the same subnet as the panel. The integration needs to hear UDP broadcasts on port 54377.
- Written from scratch. The skyer integration has no license, so its code can't be copied. Protocol facts are fine.
- The owner develops on native Windows, where Home Assistant doesn't run. Keep the protocol code free of `homeassistant` imports so its tests run locally. Everything else is tested in GitHub Actions, as in the owner's `ha-monoprice-8zone` repo, whose layout and test setup this should follow.
- Public repo: no panel identity, IP addresses, Wi-Fi names, household names or captured schedules in code, docs or test data. Test data uses made-up identity values.
- Use `type`, never `kind`, for a category field.

## Tests needed on the real panel before building

These need someone standing by the panel. Record the results in PROTOCOL.md.

1. **Restart while running.** Done in part: heat-on while running is ignored and the timer keeps counting down. The owner's decision: the second alarm does a stop, then a start. Check that the timer goes back to the full time when this is built.
2. **Set run time.** Does `d24105080e10` + varint, then `d23e020801`, change status ID 17? Does it change a run already in progress, and is it kept for later runs?
3. **Natural timeout.** Set a 1-minute run time, start, and let it run out. Record the status sequence, which is what tells a timeout from a manual stop.
4. **Above-limit run time.** Don't send a value above 60. Status ID 18 is assumed to be the panel's limit and the code enforces 60 itself.

Test 1 decides how the second alarm in "Alarm start" works.

The Phase 1 plan stops after these tests, before any building, and reports the results to the owner. If test 1 or test 2 fails, the owner decides what to do. If test 3 shows a timeout looks the same as a manual stop, use the builder's call in "Notifications".

## How the owner uses it

### Dashboard

From any phone, wherever it is:

- Turn the steamer on and off. A phone start is never blocked by location.
- Set the target temperature and run time.
- See current temperature and time remaining.
- Turn on "skip tomorrow".

### Alarm start

Off by default, because it starts a heater.

- **Phone list.** The integration's settings list every phone it finds with a next-alarm sensor, each with a checkbox. As far as is known, only the Android companion app has this sensor, so the README states that iPhones aren't supported for alarm start or notifications. Both phones in the owner's household have the sensor. A checked phone's alarm can trigger a start, and that phone gets any notifications that are turned on. The next-alarm sensor is turned off by default in Home Assistant, so the settings screen should say how to turn it on.
- **Timing.** The steamer starts a set number of minutes before each checked phone's alarm. Default 30.
- **Home check.** An alarm only counts if that phone is home. If the phone's location or alarm time is unavailable, that alarm doesn't count.
- **Length.** Alarm starts always run the full 60 minutes, whatever the run time setting says.
- **Skip tomorrow.** One switch that cancels all alarm starts for the next morning, for everyone, then turns itself off.

### Two alarms

Each alarm gets its own start, and the second puts the panel's timer back to a full 60 minutes. Examples, with a 30-minute lead:

| First alarm | Second alarm | Steamer runs |
|---|---|---|
| 7:00 | 8:00 | 6:30 to 7:30, then 7:30 to 8:30 |
| 7:00 | 7:30 | 6:30 to 7:00, then restarted at 7:00 until 8:00 (90 minutes in total) |

The panel's timer is never set above 60, so a morning can total more than 60 minutes while the safety rule still holds.

Builder's call: two phones with the same alarm time produce one start.

Builder's call: each phone triggers at most one start in any 12 hours. Without this, a phone that reports a snoozed alarm as a new next alarm could keep restarting the steamer. Whether phones do this isn't known yet.

Builder's call: if Home Assistant was down at the start time, it doesn't catch up. A start more than 5 minutes late is dropped.

Builder's call: the skip switch turns itself off at noon the next day, or at noon the same day if it was turned on before 3:00am.

Builder's call: an alarm counts at any time of day. The feature is named "alarm start" for this reason.

### Notifications

Each one can be turned on or off, and each is off by default.

- **Reached temperature.** Sent once per run when the current temperature reaches a chosen value. The current temperature appears to change in whole °C steps, so this can land up to about 2°F past the chosen value.
- **Timed out.** Sent when the panel's timer ran out, not when someone stopped it. Includes a Restart button. Restart isn't blocked by location.

Builder's call: Restart uses the run time setting.

Builder's call: if status can't tell a timeout from a manual stop, count a stop with one minute or less remaining as a timeout. A stop in the last minute would then send a timed-out notification, which does little harm.

### Panel schedule warning

The panel's own schedule ignores all of the above, including the home check. If status shows any enabled schedule entry (field 2045, enabled = 1), the integration shows a warning. The owner's panel has one entry that doesn't appear on the panel's calendar screen, which is why this matters.

Builder's call: a diagnostic binary sensor plus a Home Assistant repair notice.

## Entities

One device. Builder's call on exact names.

- Climate: off and heat, target temperature, current temperature.
- Sensor: time remaining.
- Number: run time, 1 to 60 minutes.
- Switch: alarm start.
- Number: minutes before alarm.
- Switch: skip tomorrow.
- Switch: reached-temperature notification, and number: temperature to notify at.
- Switch: timed-out notification.
- Binary sensor: panel schedule present.

## Run time

Builder's calls, all of them, subject to test 2:

- The run time number is stored by the integration and is the value used for phone starts and Restart.
- Each phone start or Restart sends the stored value to the panel just before starting. An alarm start sends 60 instead.
- After an alarm run ends, the integration sends the stored value back, so a later start at the wall panel uses the chosen time. It waits until the run has ended, because changing the value mid-run might shorten that run.
- A change made at the wall panel updates the stored value, unless the change came from the integration itself.
- If setting the time isn't confirmed, the start still goes ahead. The panel's own limit still applies, so the run could be the wrong length but can't run past the limit.

## Temperature

The panel stores °C × 9.

- **In °F:** the panel shows `raw / 5 + 32` with the decimal dropped, and `raw = (°F - 32) * 5 + 3` for a whole °F target. Proven for 113, 114 and 115.
- **In °C:** `raw = °C * 9`. Not checked against the panel's display.
- The climate entity uses Home Assistant's unit setting, so the number shown matches the panel. Relying on Home Assistant's automatic conversion from °C would show 115.6 where the panel shows 115.
- Target range comes from the panel. IDs 13 to 16 appear to be the range (86 to 125.6°F), but this is unproven. Builder's call: use 86 to 125°F or 30 to 52°C if they aren't confirmed.

## Connection

- One UDP socket per config entry, closed on unload.
- Read the panel's control port from its announcements and follow it if it changes.
- Connect with HELLO, with the PIN built into the packet. Read the status in the connect reply: 10 is accepted. Any other status is shown as an error. A wrong PIN is reported to mean 20, which hasn't been checked on this panel.
- Send a keepalive every 15 seconds. The panel replies with status and also pushes changes.
- Parse fields properly, not fixed byte patterns.
- If no packet arrives for a while, entities become unavailable. Builder's call on the timeout.
- Log raw packets at debug level. The PIN must be redacted from logs.

**Sending commands:**

- Start is sent once with no retry, then confirmed from status.
- Stop is retried up to 3 times until status shows off.
- Set target is sent, then confirmed from status.

## Setup

- Config flow: discovered panels by name, or a manual IP address, then the PIN (default 0000).
- Options flow: PIN, phone list, and the host if it changes.
- Errors for a wrong PIN and an unreachable panel.

## Delivery

Split into phases, each with its own plan:

1. **Panel tests and core integration:** the real-panel tests, setup, connection, climate, time remaining, run time, repo tooling and CI.
2. **Alarm start and notifications:** phone list, skip, two-alarm rule, notifications, Restart, schedule warning.
3. **Steam card:** built by this project and kept in the owner's private Home Assistant repo. Another session places it on the dashboard. Showing a card here is fine, but the owner's dashboard itself isn't part of this repo.

Installing on the owner's server needs a restart, so ask the owner first and coordinate with any other session working on that server.

## Left to the builder

File layout, class names, entity names, translation text, the status timeout, and how the simulated panel used in tests is built.
