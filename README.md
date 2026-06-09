# Claude Buddy 🐾

A collection of **physical desk companions for Claude Code**. Each buddy
connects to the Claude desktop app over Bluetooth LE (Nordic UART Service +
newline-delimited JSON, per the
[Hardware Buddy protocol](https://github.com/anthropics/claude-desktop-buddy/blob/main/REFERENCE.md))
and turns your coding sessions into light, sound, and physical controls —
including real **approve / deny** buttons for permission prompts.

The protocol is hardware-agnostic, so this repo holds one folder per board.

## Buddies

| Folder | Hardware | Highlights |
|---|---|---|
| [`circuit-playground-bluefruit/`](circuit-playground-bluefruit/) | Adafruit Circuit Playground Bluefruit (nRF52840) | 10× NeoPixel ring, speaker chimes, A/B approve-deny buttons, slide-switch DND, light/shake sensors |

More boards (e.g. an Arduino `Bluefruit nRF52` build with encrypted bonding) can
be added as sibling folders.

## Adding a new buddy

1. Create a folder named after the board.
2. Implement the BLE protocol from the
   [reference](https://github.com/anthropics/claude-desktop-buddy/blob/main/REFERENCE.md):
   advertise as `Claude<XXXX>`, parse heartbeat snapshots, send permission
   decisions, answer `status`.
3. Add a `README.md` in the folder with the board's capabilities and deploy
   steps, and link it in the table above.
