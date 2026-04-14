#!/usr/bin/env python3
"""
Generate minimal placeholder icons for Tauri desktop app.
Requires Pillow: pip install Pillow

Usage: python scripts/generate_icons.py
"""
import os
import struct
import zlib

ICONS_DIR = os.path.join(os.path.dirname(__file__), "..", "apps", "desktop", "src-tauri", "icons")


def make_minimal_png(width: int, height: int, color: tuple) -> bytes:
    """Generate a minimal valid RGBA PNG file."""
    r, g, b = color
    a = 255

    # PNG signature
    sig = b"\x89PNG\r\n\x1a\n"

    # IHDR chunk
    # color type 6 = RGBA
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    ihdr = _chunk(b"IHDR", ihdr_data)

    # IDAT chunk — one row per line, filter byte 0 = None
    raw_row = bytes([0] + [r, g, b, a] * width)
    raw = raw_row * height
    compressed = zlib.compress(raw)
    idat = _chunk(b"IDAT", compressed)

    # IEND chunk
    iend = _chunk(b"IEND", b"")

    return sig + ihdr + idat + iend


def _chunk(tag: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(tag + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)


def main():
    os.makedirs(ICONS_DIR, exist_ok=True)
    color = (99, 102, 241)  # indigo

    sizes = [
        ("32x32.png", 32),
        ("128x128.png", 128),
        ("128x128@2x.png", 256),
    ]

    for filename, size in sizes:
        path = os.path.join(ICONS_DIR, filename)
        with open(path, "wb") as f:
            f.write(make_minimal_png(size, size, color))
        print(f"Created {path}")

    # Create .ico placeholder (Windows) — minimal 1-frame ICO
    ico_path = os.path.join(ICONS_DIR, "icon.ico")
    png_32 = make_minimal_png(32, 32, color)
    # Minimal ICO: header + 1 dir entry + PNG data
    header = struct.pack("<HHH", 0, 1, 1)  # reserved, type=1 (ICO), count=1
    dir_entry = struct.pack("<BBBBHHII", 32, 32, 0, 0, 1, 32, len(png_32), 22)
    with open(ico_path, "wb") as f:
        f.write(header + dir_entry + png_32)
    print(f"Created {ico_path}")

    # .icns placeholder (macOS) — just a renamed PNG for dev purposes
    icns_path = os.path.join(ICONS_DIR, "icon.icns")
    with open(icns_path, "wb") as f:
        f.write(make_minimal_png(512, 512, color))
    print(f"Created {icns_path} (placeholder PNG — replace with real .icns for production)")

    print("\nDone. Replace these with real icons before production build.")


if __name__ == "__main__":
    main()
