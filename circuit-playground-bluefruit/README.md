# Claude Hardware Buddy 🐾

A physical desk companion for **Claude Code**, built on the **Adafruit Circuit
Playground Bluefruit** (nRF52840). It connects to the Claude desktop app over
Bluetooth LE and turns your coding sessions into light, sound, and a pair of
real **approve / deny** buttons.

**Hardware used:** [Adafruit Circuit Playground Bluefruit — Bluetooth Low Energy
(product #4333)](https://www.adafruit.com/product/4333) · nRF52840 ·
[product guide](https://learn.adafruit.com/adafruit-circuit-playground-bluefruit)

> When Claude is generating, the ring spins teal. When Claude needs your
> permission to run a tool, the ring breathes amber and the speaker chimes —
> tap **A** to approve, **B** to deny, without leaving your keyboard.

---

## What hardware this is

The USB drive mounted as `VOTEBOOT` is the board's UF2 bootloader. Its
`INFO_UF2.TXT` identifies it as:

```
Model: VoteBoot (Circuit Playground nRF52840)
SoftDevice: S140 7.2.0
```

That is a **Circuit Playground Bluefruit (CPB)** — an nRF52840 with BLE plus a
whole sensor suite on one round board. The BLE radio is exactly what the
[Hardware Buddy protocol](https://github.com/anthropics/claude-desktop-buddy/blob/main/REFERENCE.md)
needs, so this board is an ideal fit.

### Capabilities used

| Hardware | Used for |
|---|---|
| 10× NeoPixel RGB ring | Session state: idle / running / waiting / error, level-up rainbow |
| Mini speaker | Chimes for permission requests, approve/deny confirmation |
| Button A / Button B | **Approve (once)** / **Deny** the pending permission prompt |
| Slide switch | **Do Not Disturb** — mutes the speaker |
| Light sensor | Auto-dims the ring to the room's brightness |
| Accelerometer (shake) | Snooze / dismiss the current alert |
| BLE (nRF52840) | Nordic UART Service transport to the desktop app |

---

## How it works

The Claude desktop app speaks a simple wire protocol over the **Nordic UART
Service** (newline-delimited JSON). The relevant flow this firmware implements:

- **Heartbeat snapshot** (every ~10 s and on change): `total`, `running`,
  `waiting`, `msg`, `tokens`, and — when a decision is needed — a `prompt`
  object. → drives the ring animation and the alert.
- **Permission decision**: when a `prompt` is present, pressing **A** sends
  `{"cmd":"permission","id":...,"decision":"once"}`; **B** sends `"deny"`.
- **Status poll** (`{"cmd":"status"}`): the buddy replies with its name, uptime,
  and a little gamification block (`appr`/`deny`/`lvl`) shown in the desktop
  stats panel.
- **`owner` / `name` / `unpair`** commands are acknowledged.

## Modes

The buddy is a small state machine. It's always in exactly one mode, chosen
from the latest heartbeat snapshot, and the mode decides what the ring and
speaker do. You never switch modes manually — they follow your Claude sessions.

1. **Disconnected** — not paired, or no heartbeat received for 30 s. The ring is
   dark except a faint red dot at pixel 0. This is the "I can't see Claude"
   mode; once the desktop reconnects and sends a snapshot it leaves immediately.

2. **Idle** — connected, sessions exist (`total > 0`) but none are generating.
   Slow cool-white breathing. Calm "everything's open, nothing's happening".

3. **Empty** — connected but no sessions at all (`total == 0`). Ring fully dark.
   Distinct from Idle so a blank desk really looks blank.

4. **Running** — at least one session is generating (`running > 0`). A teal dot
   spins around the ring; faster perceived motion = active work. Each completed
   turn adds a quick teal blink on top.

5. **Waiting (permission)** — a snapshot arrived with a `prompt`, meaning Claude
   is blocked needing your approval. The ring breathes **amber** and a rising
   3-note chime plays once (unless muted). This is the only mode that wants your
   input: **Button A approves** (`once`), **Button B denies**, **shake** snoozes
   the alert without deciding. The mode clears the moment you decide or the
   prompt disappears from a later snapshot.

6. **Celebration** — transient, ~1.2 s. Triggered when approvals cross a
   multiple of 10 and the level (`lvl`) goes up. A rainbow sweeps the ring with
   a two-note jingle, then it falls back to whatever mode is current.

Two **modifiers** apply on top of any mode, driven by the onboard sensors
rather than by Claude:

- **Do Not Disturb** — slide the switch toward the speaker icon to mute every
  chime. Lights still work; only sound is silenced.
- **Auto-dim** — the light sensor continuously scales ring brightness to the
  room (dimmer in the dark, brighter in daylight), so no mode is ever harsh.

### Quick reference

| Mode / trigger | Ring | Sound |
|---|---|---|
| Disconnected / no heartbeat 30 s | dark, faint red dot | — |
| `prompt` present (permission) | amber breathing | rising 3-note chime |
| `running > 0` | teal spinner | — |
| Turn completed | quick teal blink | — |
| Sessions open, idle | slow cool-white breathe | — |
| `total == 0` | dark | — |
| Level up (every 10 approvals) | rainbow sweep | two-note jingle |

Approving plays a happy two-note rise; denying plays a low two-note fall.
Slide the switch to mute all of it.

---

## Deploy

The firmware is **CircuitPython** — no compiler, just copy files.

### 1. Put CircuitPython on the board (one time)

If the board mounts as **`VOTEBOOT`** (bootloader), it isn't running
CircuitPython yet:

1. Download the latest **Circuit Playground Bluefruit** CircuitPython `.uf2`
   from <https://circuitpython.org/board/circuitplayground_bluefruit/>.
2. Drag that `.uf2` onto the `VOTEBOOT` drive. The board reboots and
   re-mounts as **`CIRCUITPY`**.

(If it already mounts as `CIRCUITPY`, skip this step. Double-tap the reset
button any time to return to the bootloader.)

### 2. Add the libraries

Download the matching **Adafruit CircuitPython Bundle** from
<https://circuitpython.org/libraries> and copy these into `CIRCUITPY/lib/`:

```
adafruit_circuitplayground/   adafruit_ble/   adafruit_bus_device/
neopixel.mpy   adafruit_lis3dh.mpy   adafruit_thermistor.mpy
```

### 3. Copy the firmware

Copy [`code.py`](code.py) to the root of the `CIRCUITPY` drive. It runs
immediately on save. The ring should light a faint dim white while it
advertises as `Claude<XXXX>`.

### 4. Pair from the desktop

In Claude for macOS/Windows:

1. **Help → Troubleshooting → Enable Developer Mode**
2. **Developer → Open Hardware Buddy…**
3. **Connect** → pick `Claude<XXXX>`.

---

## Controls cheat-sheet

| Control | Action |
|---|---|
| **Button A** | Approve the pending tool call (`once`) |
| **Button B** | Deny the pending tool call |
| **Shake** | Snooze the current alert (no decision sent) |
| **Slide switch** | Do Not Disturb / mute speaker |

---

## Ideas this board unlocks

Beyond what's shipped in `code.py`, the CPB's sensors leave a lot of room:

1. **Hands-free approve by tapping the desk** — use `cp.tapped` (double-tap on
   the accelerometer) as a third approve gesture.
2. **Capacitive-touch quick actions** — the 7 alligator pads (A1–A7) can each
   map to a macro: "approve", "deny", "deny-all-for-this-session", etc.
3. **Token velocity meter** — render `tokens_today` as a NeoPixel bar graph, or
   change the spinner speed with the `vel` stat so a fast burn literally spins
   faster.
4. **Temperature/“is it cooking” gauge** — tint the idle color warmer the longer
   a single session runs without finishing.
5. **Focus / Pomodoro mode** — slide switch one way = work timer that pulses,
   buddy nags you to take a break (`nap` stat already tracked).
6. **Ambient-aware alerts** — already auto-dimming; could also escalate the
   chime volume only when the room is bright (you're there) and stay silent in
   the dark.
7. **Multi-session weather** — split the ring into arcs: one arc per running
   session, color by waiting/running, so 3 parallel agents are visible at a
   glance.
8. **Streak gamification** — the `appr`/`deny`/`lvl` block is wired up; add a
   daily-streak rainbow and a "deny too fast" buzz to encourage reading prompts.

---

## Notes & limitations

- **Security:** the reference recommends LE Secure Connections bonding because
  transcript snippets flow over the link. CircuitPython's bonding support is
  limited, so this build advertises unencrypted and reports `"sec": false`. Keep
  it on a trusted desk; an Arduino/`Bluefruit nRF52` build can add bonding
  later.
- **No battery gauge:** the CPB has no fuel-gauge IC, so the `bat` field is
  omitted from status (the protocol allows leaving out fields you lack).
- **No folder push:** the buddy has no display/filesystem target, so it
  declines the `char_begin` folder-push by not acknowledging it.
