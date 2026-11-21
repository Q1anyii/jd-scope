"""生成应用图标（纯标准库，无 Pillow 依赖）。

思路：4 倍超采样绘制 → 盒式降采样抗锯齿 → 编码成 PNG → 打包成多尺寸 ICO。
图案：深青底 + 白色放大镜 + 镜内三行文字，表达「透视 JD」。
"""

from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path

SS = 4  # 超采样倍数
SIZES = [256, 128, 64, 48, 32, 24, 16]

BG_TOP = (16, 121, 138)
BG_BOTTOM = (7, 92, 106)
WHITE = (255, 255, 255)
LINE = (255, 255, 255)


def _mix(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def _bg_color(y: float, n: int) -> tuple[int, int, int]:
    return _mix(BG_TOP, BG_BOTTOM, max(0.0, min(1.0, y / n)))


def _in_rounded_rect(x, y, x0, y0, x1, y1, r) -> bool:
    if x < x0 or x > x1 or y < y0 or y > y1:
        return False
    if (x0 + r) <= x <= (x1 - r) or (y0 + r) <= y <= (y1 - r):
        return True
    cx = x0 + r if x < x0 + r else x1 - r
    cy = y0 + r if y < y0 + r else y1 - r
    return (x - cx) ** 2 + (y - cy) ** 2 <= r * r


def _dist_to_segment(px, py, ax, ay, bx, by) -> float:
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def render(size: int) -> bytearray:
    n = size * SS
    px = bytearray(n * n * 4)

    margin = n * 0.06
    radius = n * 0.22
    lens_c = (n * 0.435, n * 0.435)
    lens_out = n * 0.275
    lens_in = lens_out - n * 0.062
    hx0, hy0 = lens_c[0] + lens_out * 0.70, lens_c[1] + lens_out * 0.70
    hx1, hy1 = n * 0.77, n * 0.77
    handle_w = n * 0.075

    text_lines = [
        (0.335, 0.535, 0.372, n * 0.030),
        (0.335, 0.535, 0.432, n * 0.030),
        (0.335, 0.470, 0.492, n * 0.030),
    ]

    for y in range(n):
        for x in range(n):
            inside = _in_rounded_rect(x, y, margin, margin, n - margin, n - margin, radius)
            if not inside:
                continue
            r_, g_, b_ = _bg_color(y, n)

            # 镜片外环
            d = math.hypot(x - lens_c[0], y - lens_c[1])
            if lens_in <= d <= lens_out:
                r_, g_, b_ = WHITE
            # 镜片内部三行「文字」
            elif d < lens_in:
                for x0f, x1f, yf, hf in text_lines:
                    if x0f * n <= x <= x1f * n and abs(y - yf * n) <= hf / 2:
                        r_, g_, b_ = LINE
                        break
            # 手柄
            if _dist_to_segment(x, y, hx0, hy0, hx1, hy1) <= handle_w / 2:
                r_, g_, b_ = WHITE

            i = (y * n + x) * 4
            px[i] = r_
            px[i + 1] = g_
            px[i + 2] = b_
            px[i + 3] = 255

    # 盒式降采样
    out = bytearray(size * size * 4)
    for oy in range(size):
        for ox in range(size):
            acc = [0, 0, 0, 0]
            for dy in range(SS):
                for dx in range(SS):
                    i = ((oy * SS + dy) * n + (ox * SS + dx)) * 4
                    for k in range(4):
                        acc[k] += px[i + k]
            o = (oy * size + ox) * 4
            for k in range(4):
                out[o + k] = acc[k] // (SS * SS)
    return out


def png_bytes(rgba: bytearray, size: int) -> bytes:
    raw = bytearray()
    for y in range(size):
        raw.append(0)  # filter type 0
        raw.extend(rgba[y * size * 4 : (y + 1) * size * 4])

    def chunk(tag: bytes, data: bytes) -> bytes:
        return tag + struct.pack(">I", len(data)) + data + struct.pack(
            ">I", zlib.crc32(tag + data) & 0xFFFFFFFF
        )

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + chunk(b"IEND", b"")
    )


def build_ico(path: Path) -> None:
    images = []
    for size in SIZES:
        images.append((size, png_bytes(render(size), size)))

    header = struct.pack("<HHH", 0, 1, len(images))
    offset = len(header) + 16 * len(images)
    entries = []
    payload = b""
    for size, data in images:
        entries.append(
            struct.pack("<BBBBHHII", 0 if size >= 256 else size, 0 if size >= 256 else size,
                        0, 0, 1, 32, len(data), offset)
        )
        offset += len(data)
        payload += data
    path.write_bytes(header + b"".join(entries) + payload)


if __name__ == "__main__":
    target = Path(__file__).resolve().parent.parent / "assets" / "icon.ico"
    target.parent.mkdir(parents=True, exist_ok=True)
    build_ico(target)
    print(f"icon written: {target} ({target.stat().st_size} bytes)")
