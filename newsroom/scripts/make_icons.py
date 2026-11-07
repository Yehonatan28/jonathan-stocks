"""Render the PNG app icons (no image library needed): rounded blue square + four white bars."""
import struct
import sys
import zlib
from pathlib import Path


def png(size: int) -> bytes:
    bg, fg = (0x39, 0x87, 0xE5), (0xFF, 0xFF, 0xFF)
    s = size / 64
    bars = [(16, 30, 44), (26, 22, 44), (36, 34, 44), (46, 18, 44)]   # x, y_top, y_bottom (64 grid)
    rows = []
    for y in range(size):
        row = bytearray([0])
        for x in range(size):
            u, v = (x + 0.5) / s, (y + 0.5) / s
            px = bg
            for bx, top, bot in bars:                                     # capsules of width 6
                cy = min(max(v, top), bot)
                if (u - bx) ** 2 + (v - cy) ** 2 <= 9:
                    px = fg
            row += bytes(px) + b"\xff"
        rows.append(bytes(row))
    raw = zlib.compress(b"".join(rows), 9)

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", raw) + chunk(b"IEND", b""))


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "dashboard/public")
    for n in (192, 512):
        (out / f"icon-{n}.png").write_bytes(png(n))
    print("icons written")
