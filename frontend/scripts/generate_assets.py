"""Generate DayWell's original alarm sounds (WAV) and PWA icons (PNG) with only the Python standard library.

    python scripts/generate_assets.py

Sounds are synthesised tones (no third-party audio). Icons are the DayWell mark — a gold sun rising over sage hills on deep green (``--icons-only`` skips the sounds).
"""

from __future__ import annotations

import math
import struct
import wave
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "public"
RATE = 22050


def envelope(t: float, attack: float, decay: float) -> float:
    if t < attack:
        return t / attack
    return math.exp(-(t - attack) / decay)


def write_wav(name: str, samples: list[float]) -> None:
    path = ROOT / "sounds" / f"{name}.wav"
    path.parent.mkdir(parents=True, exist_ok=True)
    peak = max(1e-9, max(abs(s) for s in samples))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(b"".join(struct.pack("<h", int(32767 * 0.8 * s / peak)) for s in samples))


def tone_sequence(notes: list[tuple[float, float, float]], *, harmonics=(1.0,), decay=0.35, total: float | None = None) -> list[float]:
    """notes = [(start_s, freq_hz, length_s)]"""
    length = total or max(s + d for s, _, d in notes) + 0.2
    out = [0.0] * int(RATE * length)
    for start, freq, dur in notes:
        for i in range(int(RATE * dur)):
            t = i / RATE
            v = sum(math.sin(2 * math.pi * freq * h * t) / (k + 1) for k, h in enumerate(harmonics))
            idx = int(RATE * start) + i
            if idx < len(out):
                out[idx] += v * envelope(t, 0.01, decay)
    return out


def sounds() -> None:
    write_wav("chime", tone_sequence([(0, 880, 1.2), (0.25, 1108.7, 1.2), (0.5, 1318.5, 1.6)], harmonics=(1, 2.01), decay=0.5))
    write_wav("bell", tone_sequence([(0, 660, 2.2), (1.1, 660, 2.2)], harmonics=(1, 2.76, 5.4), decay=0.7))
    write_wav("marimba", tone_sequence([(i * 0.18, f, 0.5) for i, f in enumerate([523.3, 659.3, 784.0, 1046.5, 784.0, 659.3])], harmonics=(1, 4.0), decay=0.12))
    chirps = []
    for i in range(6):
        base = 2000 + (i % 3) * 300
        chirps += [(0.15 * i + j * 0.02, base + j * 120, 0.05) for j in range(4)]
    write_wav("birdsong", tone_sequence(chirps, decay=0.03, total=1.4))
    write_wav("soft-pulse", tone_sequence([(i * 0.6, 440, 0.45) for i in range(3)], decay=0.25))
    write_wav("classic", tone_sequence([(i * 0.25, 1000 if i % 2 == 0 else 800, 0.2) for i in range(8)], harmonics=(1, 3), decay=0.5))


# --- Icons -------------------------------------------------------------------------------------------------------------
# The mark matches the brand artwork: a gold sun with five rays rising over two rolling sage hills, on deep forest green.
# Geometry is defined once in unit coordinates (0..1) and rendered both as anti-aliased PNGs and as an SVG.

DEEP = (0x1F, 0x4D, 0x3A)  # tile background (brand artwork green)
GOLD = (0xE8, 0xB3, 0x5A)  # sun + rays
SAGE = (0x8F, 0xB8, 0x98)  # near hill
MIST = (0xD3, 0xE4, 0xCF)  # far hill
WHITE = (0xFF, 0xFF, 0xFF)

SUN = (0.5, 0.555, 0.15)  # cx, cy, r — a half sun resting on the hills
RAYS = [(-90 + a, 0.205, 0.295) for a in (-60, -30, 0, 30, 60)]  # angle (deg), inner r, outer r
RAY_W = 0.034
BAND_GAP = 0.016  # thin background-coloured line between the shapes, as in the artwork


def hill_top(x: float) -> float:  # upper wave band (sage)
    return 0.565 + 0.028 * math.sin((x - 0.12) * math.pi * 2.0)


def hill_mid(x: float) -> float:  # boundary between the two bands
    return 0.640 + 0.030 * math.sin((x + 0.25) * math.pi * 1.7)


def hill_bottom(x: float) -> float:  # lower edge of the second band (mist)
    return 0.700 + 0.022 * math.sin((x + 0.55) * math.pi * 1.4)


def _seg_dist(px, py, ax, ay, bx, by) -> float:
    vx, vy, wx, wy = bx - ax, by - ay, px - ax, py - ay
    t = max(0.0, min(1.0, (wx * vx + wy * vy) / (vx * vx + vy * vy)))
    return math.hypot(px - (ax + t * vx), py - (ay + t * vy))


def _rays():
    cx, cy, _ = SUN
    for ang, r0, r1 in RAYS:
        a = math.radians(ang)
        yield cx + r0 * math.cos(a), cy + r0 * math.sin(a), cx + r1 * math.cos(a), cy + r1 * math.sin(a)


def mark_color(u: float, v: float, *, mono: bool):
    """Colour of the mark at unit point (u, v), or None for background."""
    if v >= hill_bottom(u):
        return None
    if v >= hill_mid(u):
        return WHITE if mono else MIST
    if v >= hill_mid(u) - BAND_GAP:
        return None
    if v >= hill_top(u):
        return WHITE if mono else SAGE
    if v >= hill_top(u) - BAND_GAP:
        return None
    cx, cy, r = SUN
    if math.hypot(u - cx, v - cy) <= r:
        return WHITE if mono else GOLD
    for ax, ay, bx, by in _rays():
        if _seg_dist(u, v, ax, ay, bx, by) <= RAY_W / 2:
            return WHITE if mono else GOLD
    return None


def png(path: Path, size: int, *, maskable: bool = False, mono: bool = False) -> None:
    """Render with 4×4 supersampling. Maskable icons are full-bleed with the mark inside the 80% safe zone."""
    ss = 4
    radius = 0.0 if (maskable or mono) else 0.22
    scale, offset = (0.78, 0.11) if maskable else (0.92, 0.04)  # where the unit mark sits inside the tile
    if mono:
        scale, offset = 1.0, 0.0
    rows = []
    for y in range(size):
        row = bytearray([0])
        for x in range(size):
            acc = [0.0, 0.0, 0.0, 0.0]
            for sy in range(ss):
                for sx in range(ss):
                    fx = (x + (sx + 0.5) / ss) / size
                    fy = (y + (sy + 0.5) / ss) / size
                    if radius:  # rounded tile
                        dx = max(radius - fx, 0, fx - (1 - radius))
                        dy = max(radius - fy, 0, fy - (1 - radius))
                        if dx * dx + dy * dy > radius * radius:
                            continue
                    color = mark_color((fx - offset) / scale, (fy - offset) / scale, mono=mono)
                    if color is None:
                        if mono:
                            continue
                        color = DEEP
                    acc[0] += color[0]; acc[1] += color[1]; acc[2] += color[2]; acc[3] += 1
            n = ss * ss
            if acc[3] == 0:
                row += bytes((0, 0, 0, 0))
            else:
                row += bytes((round(acc[0] / acc[3]), round(acc[1] / acc[3]), round(acc[2] / acc[3]), round(255 * acc[3] / n)))
        rows.append(bytes(row))
    raw = b"".join(rows)

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    body = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)


def svg(path: Path) -> None:
    """Vector version of the tile for crisp in-app use (header, sign-in)."""
    def hex_(c):
        return "#%02x%02x%02x" % c

    s, o = 0.92, 0.04
    def P(u, v):
        return f"{(o + u * s) * 100:.2f},{(o + v * s) * 100:.2f}"

    def band(top, bottom, lift=0.0):
        up = " L".join(P(i / 40, top(i / 40) - lift) for i in range(41))
        down = " L".join(P(1 - i / 40, bottom(1 - i / 40)) for i in range(41))
        return f"M{up} L{down} Z"

    sky = " L".join(P(1 - i / 40, hill_top(1 - i / 40) - BAND_GAP) for i in range(41))
    sky_path = f"M{P(0, -0.2)} L{P(1, -0.2)} L{sky} Z"  # everything above the hills: the sun sets behind them

    cx, cy, r = SUN
    rays = "".join(f'<line x1="{(o + ax * s) * 100:.2f}" y1="{(o + ay * s) * 100:.2f}" x2="{(o + bx * s) * 100:.2f}" y2="{(o + by * s) * 100:.2f}"/>'
                   for ax, ay, bx, by in _rays())
    body = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" role="img" aria-label="DayWell">
<defs><clipPath id="t"><rect width="100" height="100" rx="22"/></clipPath><clipPath id="sky"><path d="{sky_path}"/></clipPath></defs>
<g clip-path="url(#t)">
<rect width="100" height="100" fill="{hex_(DEEP)}"/>
<g stroke="{hex_(GOLD)}" stroke-width="{RAY_W * s * 100:.2f}" stroke-linecap="round">{rays}</g>
<circle clip-path="url(#sky)" cx="{(o + cx * s) * 100:.2f}" cy="{(o + cy * s) * 100:.2f}" r="{r * s * 100:.2f}" fill="{hex_(GOLD)}"/>
<path d="{band(hill_top, hill_mid, BAND_GAP)}" fill="{hex_(DEEP)}"/>
<path d="{band(hill_top, lambda x: hill_mid(x) - BAND_GAP)}" fill="{hex_(SAGE)}"/>
<path d="{band(hill_mid, hill_bottom)}" fill="{hex_(MIST)}"/>
</g></svg>
"""
    path.write_text(body, encoding="utf-8")


def icons() -> None:
    png(ROOT / "icons" / "icon-192.png", 192)
    png(ROOT / "icons" / "icon-512.png", 512)
    png(ROOT / "icons" / "maskable-512.png", 512, maskable=True)
    png(ROOT / "icons" / "apple-touch-icon.png", 180, maskable=True)
    png(ROOT / "icons" / "badge-96.png", 96, mono=True)  # Android status-bar badge: white silhouette on transparent
    svg(ROOT / "icons" / "logo.svg")


if __name__ == "__main__":
    import sys

    if "--icons-only" not in sys.argv:
        sounds()
    icons()
    print("assets written to", ROOT)
