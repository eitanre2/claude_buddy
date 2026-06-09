# Claude Hardware Buddy — Circuit Playground Bluefruit (nRF52840)
#
# Implements the "Hardware Buddy" BLE protocol (Nordic UART Service +
# newline-delimited JSON) so the Adafruit Circuit Playground Bluefruit reacts
# physically to your Claude Code sessions:
#
#   * NeoPixel ring  -> session state (idle / running / waiting / error)
#   * Speaker        -> chimes for turn-complete and permission requests
#   * Button A / B   -> APPROVE / DENY the pending permission prompt
#   * Slide switch   -> Do-Not-Disturb (mutes the speaker)
#   * Light sensor   -> auto-dims the NeoPixels to the room
#   * Shake          -> snooze / dismiss the current alert
#
# Deploy: copy this file to the CIRCUITPY drive as `code.py`.
# Requires (drop into CIRCUITPY/lib/, from the Adafruit CircuitPython bundle):
#   adafruit_circuitplayground/  adafruit_ble/  neopixel.mpy
#   adafruit_lis3dh.mpy  adafruit_thermistor.mpy  adafruit_bus_device/

import time
import json

from adafruit_circuitplayground import cp

from adafruit_ble import BLERadio
from adafruit_ble.advertising.standard import ProvideServicesAdvertisement
from adafruit_ble.services.nordic import UARTService

NUM_PIXELS = 10

# ----------------------------------------------------------------------------
# Colors
# ----------------------------------------------------------------------------
OFF    = (0, 0, 0)
IDLE   = (8, 8, 12)      # dim cool white — connected, nothing happening
RUN    = (0, 180, 120)   # teal spinner — at least one session generating
WAIT   = (255, 120, 0)   # amber pulse — permission needed (also a chime)
ERROR  = (255, 0, 0)
CELEB  = (120, 0, 255)   # level-up / celebration


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def scale(color, f):
    return (int(color[0] * f), int(color[1] * f), int(color[2] * f))


class Buddy:
    def __init__(self):
        self.ble = BLERadio()
        self.uart = UARTService()
        self.advert = ProvideServicesAdvertisement(self.uart)

        # Advertise "Claude" + a couple of MAC bytes so multiple buddies are
        # distinguishable in the desktop picker.
        suffix = "".join("%02X" % b for b in self.ble.address_bytes[:2])
        self.name = "Claude" + suffix
        self.ble.name = self.name
        self.advert.complete_name = self.name

        # ---- protocol / session state -------------------------------------
        self.owner = None
        self.total = 0
        self.running = 0
        self.waiting = 0
        self.msg = ""
        self.pending = None          # prompt dict when a decision is needed
        self.last_snapshot = 0.0     # monotonic of last heartbeat

        # ---- local gamification stats (reported back in status) -----------
        self.stats = {"appr": 0, "deny": 0, "vel": 0, "nap": 0, "lvl": 1}

        # ---- input edge tracking ------------------------------------------
        self._a_was = False
        self._b_was = False

        # ---- line reassembly ----------------------------------------------
        self._buf = b""

        self._boot_ms = time.monotonic()
        self._celebrate_until = 0.0

    # ------------------------------------------------------------------ I/O
    def send(self, obj):
        try:
            self.uart.write((json.dumps(obj) + "\n").encode("utf-8"))
        except Exception:
            pass

    def pump_rx(self):
        """Accumulate bytes, dispatch each complete newline-terminated line."""
        n = self.uart.in_waiting
        if n:
            self._buf += self.uart.read(n)
        while b"\n" in self._buf:
            line, self._buf = self._buf.split(b"\n", 1)
            line = line.strip()
            if not line:
                continue
            try:
                self.handle(json.loads(line))
            except Exception:
                pass

    # -------------------------------------------------------------- dispatch
    def handle(self, m):
        # Heartbeat snapshot (no "cmd"/"evt", has "total").
        if "total" in m:
            self.apply_snapshot(m)
            return

        evt = m.get("evt")
        if evt == "turn":
            # A turn finished — soft confirmation blink, no sound.
            self.blink(RUN, 0.06)
            return

        if "time" in m:               # one-shot time sync; we just note it
            return

        cmd = m.get("cmd")
        if cmd == "owner":
            self.owner = m.get("name")
            self.send({"ack": "owner", "ok": True})
        elif cmd == "name":
            self.name = m.get("name", self.name)
            self.send({"ack": "name", "ok": True})
        elif cmd == "status":
            self.send_status()
        elif cmd == "unpair":
            # CircuitPython can't easily purge bonds; ack so the UI clears.
            self.send({"ack": "unpair", "ok": True})
        # char_begin / file / chunk: we have no filesystem display, so we do
        # NOT ack char_begin — per the protocol the desktop then skips push.

    def apply_snapshot(self, m):
        self.last_snapshot = time.monotonic()
        self.total = m.get("total", 0)
        self.running = m.get("running", 0)
        self.waiting = m.get("waiting", 0)
        self.msg = m.get("msg", "")

        new = m.get("prompt")
        if new and (not self.pending or new.get("id") != self.pending.get("id")):
            # A fresh permission request arrived — alert once (respect DND).
            self.pending = new
            self.alert()
        elif not new:
            self.pending = None

    def send_status(self):
        up = int(time.monotonic() - self._boot_ms)
        self.stats["nap"] = up // 60
        data = {
            "name": self.name,
            "sec": False,                      # see README: bonding is a TODO
            "sys": {"up": up, "heap": 0},
            "stats": dict(self.stats),
        }
        # Circuit Playground Bluefruit has no battery fuel gauge, so "bat" is
        # omitted (the protocol allows leaving out fields you don't have).
        self.send({"ack": "status", "ok": True, "data": data})

    # ----------------------------------------------------------------- inputs
    def poll_buttons(self):
        """Edge-detect A/B and resolve a pending permission decision."""
        a, b = cp.button_a, cp.button_b

        if a and not self._a_was and self.pending:
            self.decide("once")
        if b and not self._b_was and self.pending:
            self.decide("deny")

        self._a_was, self._b_was = a, b

        # Shake to snooze the current alert without deciding.
        if self.pending and cp.shake(shake_threshold=20):
            self.flash(IDLE, 0.05)

    def decide(self, decision):
        pid = self.pending.get("id")
        self.send({"cmd": "permission", "id": pid, "decision": decision})
        if decision == "once":
            self.stats["appr"] += 1
            cp.play_tone(880, 0.08)
            cp.play_tone(1320, 0.10)
            # level up every 10 approvals
            lvl = 1 + self.stats["appr"] // 10
            if lvl > self.stats["lvl"]:
                self.stats["lvl"] = lvl
                self._celebrate_until = time.monotonic() + 1.2
        else:
            self.stats["deny"] += 1
            cp.play_tone(440, 0.12)
            cp.play_tone(220, 0.12)
        self.pending = None

    # ------------------------------------------------------------- feedback
    def muted(self):
        # Slide switch toward the speaker icon = Do Not Disturb.
        return cp.switch

    def alert(self):
        if self.muted():
            return
        cp.play_tone(660, 0.09)
        cp.play_tone(990, 0.09)
        cp.play_tone(1320, 0.12)

    def blink(self, color, dur):
        cp.pixels.fill(color)
        cp.pixels.show()
        time.sleep(dur)

    def flash(self, color, dur):
        self.blink(color, dur)

    # ------------------------------------------------------------- animation
    def brightness(self):
        # Auto-dim to the room: cp.light is ~0 (dark) .. ~320 (bright).
        return clamp(0.05 + cp.light / 320.0 * 0.45, 0.05, 0.5)

    def render(self):
        now = time.monotonic()
        cp.pixels.brightness = self.brightness()

        # Connection lost: no heartbeat for >30 s -> dark with a faint red dot.
        connected = self.ble.connected and (now - self.last_snapshot) < 30
        if not connected:
            cp.pixels.fill(OFF)
            cp.pixels[0] = scale(ERROR, 0.15)
            cp.pixels.show()
            return

        if now < self._celebrate_until:                 # rainbow level-up
            base = int(now * 200)
            for i in range(NUM_PIXELS):
                cp.pixels[i] = wheel((base + i * 25) & 255)
            cp.pixels.show()
            return

        if self.pending:                                # amber breathing alert
            f = 0.25 + 0.75 * (0.5 + 0.5 * triangle(now * 2))
            cp.pixels.fill(scale(WAIT, f))
            cp.pixels.show()
            return

        if self.running > 0:                            # teal spinner
            head = int(now * 8) % NUM_PIXELS
            for i in range(NUM_PIXELS):
                d = (head - i) % NUM_PIXELS
                cp.pixels[i] = scale(RUN, 1.0 if d == 0 else (0.25 if d == 1 else 0.04))
            cp.pixels.show()
            return

        if self.total == 0:                             # nothing open -> dark
            cp.pixels.fill(OFF)
            cp.pixels.show()
            return

        # Idle but sessions exist: slow cool-white breathe.
        f = 0.4 + 0.6 * (0.5 + 0.5 * triangle(now * 0.5))
        cp.pixels.fill(scale(IDLE, f))
        cp.pixels.show()

    # ----------------------------------------------------------------- run
    def run(self):
        cp.pixels.auto_write = False
        while True:
            # Advertise & wait for the desktop to connect.
            self.ble.start_advertising(self.advert)
            while not self.ble.connected:
                self.render()
                time.sleep(0.05)
            self.ble.stop_advertising()

            self.last_snapshot = time.monotonic()       # grace period
            while self.ble.connected:
                self.pump_rx()
                self.poll_buttons()
                self.render()
                time.sleep(0.02)

            # Disconnected — drop any stale prompt and loop to re-advertise.
            self.pending = None


# ---------------------------------------------------------------- helpers
def triangle(t):
    """Smooth-ish -1..1 oscillation from monotonic time (no float modulo gaps)."""
    t = t - int(t)
    return 1 - 4 * abs(t - 0.5)


def wheel(pos):
    pos &= 255
    if pos < 85:
        return (255 - pos * 3, pos * 3, 0)
    if pos < 170:
        pos -= 85
        return (0, 255 - pos * 3, pos * 3)
    pos -= 170
    return (pos * 3, 0, 255 - pos * 3)


Buddy().run()
