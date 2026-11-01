# Amerec Steam for Home Assistant

A Home Assistant custom integration for Amerec steam generators with the Elite (A6) Wi-Fi touchscreen panel, over the local network.

I built this for my own Amerec AX7.5, and it's provided as-is. It's written from what my panel actually sends, which is recorded in [PROTOCOL.md](PROTOCOL.md). It may work on other Tylö-family panels, but I haven't tried any.

## What it does

- A climate entity: on and off, target temperature and current temperature, in °F or °C to match your Home Assistant setting.
- A sensor for the time left on the panel's timer.
- A PIN setting, in case yours isn't the default 0000.

Each start uses whatever run time the panel has set. Setting the run time from Home Assistant isn't in yet.

## Safety

The panel's own timer always stays in charge of shutting the steamer off. If Home Assistant or your Wi-Fi goes down, the panel still ends the run when its timer runs out. The wall panel's stop button keeps working as usual.

The panel's own schedule also keeps running, and this integration doesn't touch it. A steamer can start while nobody's there, so think about who could be in or near the shower before you automate it.

## Install

1. In HACS, add this repository as a custom repository, with the type set to Integration.
2. Install **Amerec Steam** and restart Home Assistant.
3. Go to Settings > Devices & services > Add integration > **Amerec Steam**. The panel's address is filled in if it's found on your network, which takes about 10 seconds. Otherwise, it's on the panel's Network screen.

Home Assistant and the panel need to be on the same network, because the panel announces itself with UDP broadcasts. Home Assistant in Docker needs host networking.
