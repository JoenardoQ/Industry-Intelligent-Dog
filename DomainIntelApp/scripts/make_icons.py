# -*- coding: utf-8 -*-
"""用纯标准库生成 PWA 图标 PNG（无需 Pillow）."""
import struct
import zlib
from pathlib import Path


def make_png(size: int, path: Path):
    """生成一个带圆角感的渐变图标：深蓝底 + 白色雷达圆环."""
    rows = []
    cx = cy = size / 2
    for y in range(size):
        row = bytearray()
        for x in range(size):
            # 背景：从左上到右下的蓝色渐变
            t = (x + y) / (2 * size)
            r = int(30 + 25 * t)
            g = int(64 + 60 * t)
            b = int(150 + 80 * t)
            # 雷达圆环
            dx, dy = x - cx, y - cy
            dist = (dx * dx + dy * dy) ** 0.5
            for ring_r in (size * 0.32, size * 0.20):
                if abs(dist - ring_r) < size * 0.018:
                    r, g, b = 240, 245, 255
            # 中心点
            if dist < size * 0.045:
                r, g, b = 255, 255, 255
            # 扫描线（对角线）
            if abs(dx - dy) < size * 0.012 and dx > 0 and dist < size * 0.34:
                r, g, b = 220, 235, 255
            row += bytes((r, g, b))
        rows.append(bytes(row))

    raw = b"".join(b"\x00" + row for row in rows)

    def chunk(tag, data):
        c = tag + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw, 9))
           + chunk(b"IEND", b""))
    path.write_bytes(png)
    print(f"[OK] {path} ({size}x{size}, {len(png)} bytes)")
    return png


def make_ico(png: bytes, size: int, path: Path):
    """ICO can embed a PNG directly (Windows Vista+)."""
    header = struct.pack("<HHH", 0, 1, 1)
    width = 0 if size >= 256 else size
    entry = struct.pack("<BBBBHHII", width, width, 0, 0, 1, 32,
                        len(png), 6 + 16)
    path.write_bytes(header + entry + png)
    print(f"[OK] {path} ({len(png)} embedded PNG bytes)")


if __name__ == "__main__":
    app_dir = Path(__file__).resolve().parent.parent / "app"
    app_dir.mkdir(exist_ok=True)
    make_png(192, app_dir / "icon-192.png")
    make_png(512, app_dir / "icon-512.png")
    icon_png = make_png(256, app_dir / "icon-256.png")
    make_ico(icon_png, 256, app_dir / "intdog.ico")
