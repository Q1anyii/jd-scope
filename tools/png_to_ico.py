"""把一张方形源图转成 Windows 应用图标（.ico）。

处理四件事：
1. 裁掉四周多余留白，让底卡铺满画布（否则任务栏里图标会显小）；
2. 把圆角外的白底做成透明，避免深色任务栏上露出白角；
3. 生成 256/128/64/48/32/24/16 七个尺寸，各自选择合适的重采样；
4. 16px 用「简化版」：去掉镜片内三条细线，否则缩小后糊成一团。

用法：python tools/png_to_ico.py [源图] [输出]
默认：assets/icon-src.png -> assets/icon.ico
"""

from __future__ import annotations

import collections
import io
import struct
import sys
from pathlib import Path

from PIL import Image, ImageFilter

BG_MIN = 244        # 判定为「白底」的通道下限
WHITE_MIN = 232     # 判定为「白色图形」的通道下限
SIZES = [256, 128, 64, 48, 32, 24, 16]
SMALL_SIMPLIFIED = 16   # 该尺寸及以下使用简化图形


def _is_bg(pixel) -> bool:
    r, g, b, a = pixel
    return a > 0 and r >= BG_MIN and g >= BG_MIN and b >= BG_MIN


def crop_to_card(img: Image.Image) -> Image.Image:
    """按非白像素的包围盒裁剪，让底卡贴边并补成正方形。"""
    px = img.load()
    w, h = img.size
    left, top, right, bottom = w, h, -1, -1
    for y in range(h):
        for x in range(w):
            if not _is_bg(px[x, y]):
                if x < left:
                    left = x
                if x > right:
                    right = x
                if y < top:
                    top = y
                if y > bottom:
                    bottom = y
    if right < 0 or bottom < 0:
        return img
    box = (left, top, right + 1, bottom + 1)
    side = max(box[2] - box[0], box[3] - box[1])
    crop = img.crop(box)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(crop, ((side - crop.width) // 2, (side - crop.height) // 2))
    return canvas


def transparent_outer(img: Image.Image) -> Image.Image:
    """从四角出发把连通的白色区域设成透明，圆角外的白边就不会带进图标。"""
    img = img.convert("RGBA")
    w, h = img.size
    px = img.load()
    visited = bytearray(w * h)
    queue: collections.deque[tuple[int, int]] = collections.deque()

    for x in range(w):
        for y in (0, h - 1):
            if not visited[y * w + x] and _is_bg(px[x, y]):
                visited[y * w + x] = 1
                queue.append((x, y))
    for y in range(h):
        for x in (0, w - 1):
            if not visited[y * w + x] and _is_bg(px[x, y]):
                visited[y * w + x] = 1
                queue.append((x, y))

    while queue:
        x, y = queue.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < w and 0 <= ny < h and not visited[ny * w + nx] and _is_bg(px[nx, ny]):
                visited[ny * w + nx] = 1
                queue.append((nx, ny))

    mask = Image.new("L", (w, h), 255)
    mpx = mask.load()
    for y in range(h):
        row = y * w
        for x in range(w):
            if visited[row + x]:
                mpx[x, y] = 0
    mask = mask.filter(ImageFilter.GaussianBlur(1.2))
    img.putalpha(mask)
    return img


def _white(pixel) -> bool:
    r, g, b, a = pixel
    return a > 0 and r >= WHITE_MIN and g >= WHITE_MIN and b >= WHITE_MIN


def simplify_glyph(img: Image.Image, keep_ratio: float = 0.08) -> Image.Image:
    """去掉「白色连通块」里的小块（镜片内的三条细线），只留主图形（镜环+手柄）。"""
    out = img.copy()
    w, h = out.size
    px = out.load()
    visited = bytearray(w * h)
    comps: list[tuple[int, list[tuple[int, int]]]] = []

    for y in range(h):
        for x in range(w):
            idx = y * w + x
            if visited[idx] or not _white(px[x, y]):
                continue
            queue = collections.deque([(x, y)])
            visited[idx] = 1
            pts = []
            while queue:
                cx, cy = queue.popleft()
                pts.append((cx, cy))
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = cx + dx, cy + dy
                    if 0 <= nx < w and 0 <= ny < h:
                        nidx = ny * w + nx
                        if not visited[nidx] and _white(px[nx, ny]):
                            visited[nidx] = 1
                            queue.append((nx, ny))
            comps.append((len(pts), pts))

    if not comps:
        return out
    total = sum(c[0] for c in comps)
    largest = max(c[0] for c in comps)
    for area, pts in comps:
        if area >= largest or area > total * keep_ratio:
            continue
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        # 取包围盒外扩一圈的中位色作为填充色（也就是镜片底色）
        samples = []
        for y in range(max(0, min(ys) - 3), min(h, max(ys) + 4)):
            for x in range(max(0, min(xs) - 3), min(w, max(xs) + 4)):
                p = px[x, y]
                if p[3] > 0 and not _white(p):
                    samples.append(p[:3])
        if not samples:
            continue
        samples.sort(key=lambda c: (c[0] + c[1] + c[2]))
        fill = samples[len(samples) // 2]
        for x, y in pts:
            px[x, y] = (*fill, 255)
    return out


def _png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def build(src: Path, dst: Path) -> None:
    base = Image.open(src).convert("RGBA")
    base = crop_to_card(base)
    base = transparent_outer(base)
    if base.width < 256:
        base = base.resize((256, 256), Image.LANCZOS)
    else:
        base = base.resize((256, 256), Image.LANCZOS)

    simplified = simplify_glyph(base)

    payloads = []
    for size in SIZES:
        source = simplified if size <= SMALL_SIMPLIFIED else base
        payloads.append((size, _png_bytes(source.resize((size, size), Image.LANCZOS))))

    header = struct.pack("<HHH", 0, 1, len(payloads))
    offset = len(header) + 16 * len(payloads)
    entries, body = [], b""
    for size, data in payloads:
        entries.append(
            struct.pack(
                "<BBBBHHII",
                0 if size >= 256 else size,
                0 if size >= 256 else size,
                0, 0, 1, 32, len(data), offset,
            )
        )
        offset += len(data)
        body += data
    dst.write_bytes(header + b"".join(entries) + body)
    print(f"ico written: {dst} ({dst.stat().st_size} bytes, {len(payloads)} sizes)")


if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else root / "assets" / "icon-src.png"
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else root / "assets" / "icon.ico"
    build(src, dst)
