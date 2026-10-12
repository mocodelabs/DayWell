"""Generate DayWell's original alarm sounds (WAV) and PWA icons (PNG) with only the Python standard library.

    python scripts/generate_assets.py

Sounds are synthesised tones (no third-party audio). Icons are a forest-green rounded square with a cream sun/leaf mark.
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

FOREST = (0x46, 0x6B, 0x52)
CREAM = (0xF7, 0xF4, 0xED)
AMBER = (0xD7, 0xAA, 0x62)


def png(path: Path, size: int, *, maskable: bool) -> None:
    rows = []
    radius = 0 if maskable else size * 0.22
    cx = cy = size / 2
    sun_r = size * (0.17 if maskable else 0.2)
    for y in range(size):
        row = bytearray([0])
        for x in range(size):
            # rounded-square background (full bleed for maskable icons)
            inside = True
            if radius:
                dx = max(radius - x, 0, x - (size - 1 - radius))
                dy = max(radius - y, 0, y - (size - 1 - radius))
                inside = dx * dx + dy * dy <= radius * radius
            if not inside:
                row += bytes((0, 0, 0, 0))
                continue
            color = FOREST
            d = math.hypot(x - cx, y - cy * 0.92)
            if d <= sun_r:
                color = AMBER
            # horizon line / hill in cream below the sun
            hill = cy + size * 0.12 + 0.0018 * ((x - cx) ** 2) / max(size / 256, 1)
            if y > hill:
                color = CREAM
            row += bytes((*color, 255))
        rows.append(bytes(row))
    raw = b"".join(rows)

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    body = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)


def icons() -> None:
    png(ROOT / "icons" / "icon-192.png", 192, maskable=False)
    png(ROOT / "icons" / "icon-512.png", 512, maskable=False)
    png(ROOT / "icons" / "maskable-512.png", 512, maskable=True)
    png(ROOT / "icons" / "apple-touch-icon.png", 180, maskable=True)
    png(ROOT / "icons" / "badge-96.png", 96, maskable=False)


if __name__ == "__main__":
    sounds()
    icons()
    print("assets written to", ROOT)
