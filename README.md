# Sony Headphones for Omarchy

A bar widget for the [Omarchy](https://omarchy.org) shell that controls Sony
WH-1000XM headphones the way the phone app does — noise cancelling, ambient
sound, the equalizer, DSEE Extreme, Speak-to-Chat and battery — without a
phone, a vendor app, or a desktop GUI.

It talks Sony's own Bluetooth protocol directly over RFCOMM, in about seven
hundred lines of dependency-free Python.

```
Left click    open the panel
Right click   cycle noise cancelling → ambient sound → off
Scroll        ambient sound level
Middle click  refresh
```

## Requirements

- Omarchy 4.0 or newer
- `python3` and `bluez-utils` (both already on a stock Omarchy install)
- Headphones paired and connected

## Install

```bash
omarchy plugin add https://github.com/gabamnml/omarchy-sony-headphones --enable
```

To place it somewhere specific in the bar:

```bash
omarchy bar move gabamnml.sony-headphones --section right --index 0
```

## Supported models

The plugin speaks Sony's **v1** protocol, used by the over-ear 1000X line up to
the XM4:

| Model | Status |
|---|---|
| WH-1000XM4 | Verified against real hardware |
| WH-1000XM3, WH-1000XM2 | Same protocol, untested — reports welcome |
| WF-1000XM4/XM5, WH-1000XM5/XM6, LinkBuds, CH720N | **Not supported.** These speak the v2 protocol; the plugin detects them and says so instead of sending bytes they will ignore |

Features are read back from the headphones themselves, so anything a given
model does not implement simply never appears in the panel.

## What you can change

| Setting | Notes |
|---|---|
| Noise cancelling / Ambient sound / Wind noise reduction / Off | Wind noise reduction appears only on models that report it |
| Ambient level | 0–20, with Focus on Voice |
| Equalizer | The nine presets plus Manual; custom bands via the CLI |
| DSEE Extreme | Upscaling of compressed audio |
| Speak-to-Chat | On/off, sensitivity, resume timeout, voice focus |
| Pause when taken off, touch controls, voice guidance | |
| Automatic power off | Never, when taken off, or on a timer |
| Battery, firmware, codec | Read-only |

## Keyboard

Inside the panel: `j`/`k` or the arrow keys move, `h`/`l` adjust the row under
the cursor, `Enter` toggles, `Esc` closes. Shortcuts: `n` cycles the mode, `d`
toggles DSEE, `s` toggles Speak-to-Chat, `r` refreshes.

## A keybinding

The widget exposes IPC, so noise cancelling can hang off a key. In
`~/.config/hypr/bindings.lua`:

```lua
o.bind("SUPER", "N", "Cycle noise cancelling",
  "omarchy-shell gabamnml.sony-headphones cycle")
```

Also available: `open`, `close`, `toggle`, `mode <name>`, `ambient <0-20>`,
`status`.

## Settings

Configured from the shell's widget settings, or directly on the entry in
`~/.config/omarchy/shell.json`:

| Key | Default | Meaning |
|---|---|---|
| `showBattery` | `On` | Show the battery percentage next to the icon |
| `address` | — | Pin a MAC address when several Sony devices are connected |

## The command line

The helper works on its own, with or without the widget:

```bash
bin/sony-headphones status              # everything the headphones report
bin/sony-headphones probe               # diagnose the connection
bin/sony-headphones cycle               # noise cancelling → ambient → off
bin/sony-headphones set nc ambient-sound
bin/sony-headphones set ambient-level 12
bin/sony-headphones set eq bass-boost
bin/sony-headphones set eq-bands "2,0,1,0,-1,3"   # clear bass + 5 bands, -10..10
bin/sony-headphones set dsee toggle
bin/sony-headphones watch               # stream state changes as JSON lines
```

## How it works

Sony's app protocol runs over an RFCOMM serial channel. Messages are framed as
`0x3e <type> <seq> <length:4> <payload> <checksum> 0x3c`, escaped so the marker
bytes never appear inside a message, and every message — in both directions —
is answered with an acknowledgement carrying the flipped sequence number.

`bin/sony-headphones watch` keeps that link open and serves a unix socket, so
the widget gets push updates when you press the button on the earcup, and short
CLI calls apply instantly instead of paying for a fresh connection each time.

BlueZ exposes no way to read a remote SDP record and `sdptool` is gone from
bluez-utils, so the RFCOMM channel is found by trying: the init handshake tells
a Sony control endpoint from anything else that answers, and the winning
channel is cached under `~/.cache/omarchy-sony-headphones/`.

Nothing here touches the network. The only things it talks to are the
headphones and `bluetoothctl`.

## Development

```bash
python3 tests/test_protocol.py     # 61 tests, no headphones required
omarchy plugin validate .
```

There is a stand-in device for working without hardware. It answers requests
with real reply payloads through the real framing, so the widget can be driven
end to end and every setting is round-tripped in the test suite:

```bash
SONY_HEADPHONES_DEMO=1 bin/sony-headphones status
SONY_HEADPHONES_DEMO=1 bin/sony-headphones watch   # the widget attaches to this
```

Editing the QML reloads the widget on save. Editing `Model.js` does not — the
QML engine caches `.pragma library` imports, so run `omarchy restart shell`
after changing it.

## Credits

The v1 protocol — payload opcodes, byte layouts, and what each field means —
was reverse engineered by [Gadgetbridge](https://codeberg.org/Freeyourgadget/Gadgetbridge),
whose `SonyProtocolImplV1` is the reference this implementation follows. The
message framing was cross-checked against
[SonyHeadphonesClient](https://github.com/Plutoberth/SonyHeadphonesClient) and
[SonyBridge](https://github.com/AmitRajput-Dev/SonyBridge), and the RFCOMM
layer against [ohm-app's protocol notes](https://github.com/ohm-app/sony-headphones-bluetooth-documentation).

This is an independent project. Sony has nothing to do with it.

## License

AGPL-3.0-or-later, matching Gadgetbridge, from which the protocol knowledge
comes. See [LICENSE](LICENSE).
