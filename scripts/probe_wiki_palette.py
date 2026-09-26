"""一次性探针：从 wiki 首页截图里统计真实配色 token。

用途：为 L3 前端定视觉规范提供**实测**色值，而不是肉眼估计。
产出物是数据，不是资产；脚本本身可复现（依赖 docs/ref/wiki-home.png，该图已 gitignore）。

用法：
    python scripts/probe_wiki_palette.py

先取参考图（需 stealth 代理，Cloudflare 会挡直连）：
    用 firecrawl 抓 https://res1999.huijiwiki.com/wiki/首页 的整页截图，
    存为 docs/ref/wiki-home.png。
"""

from __future__ import annotations

import colorsys
import sys
from collections import Counter

from PIL import Image

SRC = r"docs\ref\wiki-home.png"

# 采样区域用相对坐标 (x0, y0, x1, y1) 表示，便于换分辨率复用。
REGIONS: dict[str, tuple[float, float, float, float]] = {
    "顶栏背景(huiji)": (0.35, 0.001, 0.65, 0.012),
    "站点头部/导航条": (0.35, 0.014, 0.65, 0.030),
    "轮播卡片深色条": (0.05, 0.280, 0.31, 0.302),
    "图标格第一行": (0.05, 0.323, 0.31, 0.352),
    "最近更新卡片体": (0.35, 0.265, 0.55, 0.282),
    "中部大卡片体": (0.39, 0.487, 0.61, 0.502),
    "页脚背景": (0.08, 0.855, 0.92, 0.875),
    "页脚底部": (0.08, 0.960, 0.92, 0.985),
}

# 小面积 UI 强调色采样（矩形 + 饱和度门槛），用于钉准 accent。
ACCENT_BOXES: dict[str, tuple[float, float, float, float]] = {
    "日期块 accent": (0.040, 0.145, 0.200, 0.172),
    "国服版本芯片": (0.355, 0.230, 0.420, 0.252),
    "倒计时胶囊": (0.395, 0.230, 0.430, 0.248),
}
# 卡片正文字色（几乎无饱和，要求高亮度）
INK_BOXES: dict[str, tuple[float, float, float, float]] = {
    "卡片正文色": (0.390, 0.560, 0.610, 0.590),
}
# 顶部导航未激活文字（低饱和中亮度）
MUTED_BOXES: dict[str, tuple[float, float, float, float]] = {
    "顶部导航文字": (0.170, 0.014, 0.360, 0.028),
}


def quantize(rgb: tuple[int, int, int], step: int = 6) -> tuple[int, int, int]:
    return tuple(min(255, (c // step) * step + step // 2) for c in rgb)  # type: ignore[return-value]


def hexs(rgb: tuple[int, int, int]) -> str:
    return "#%02X%02X%02X" % rgb


def hue(rgb: tuple[int, int, int]) -> float:
    return colorsys.rgb_to_hsv(*[x / 255 for x in rgb])[0] * 360


def pixels(img: Image.Image):
    """Pillow 12+ 弃用了 getdata()，这里兼容两个版本。"""
    getter = getattr(img, "get_flattened_data", None)
    return getter() if callable(getter) else img.getdata()


def crop(img: Image.Image, rel: tuple[float, float, float, float]) -> Image.Image:
    w, h = img.size
    box = (int(rel[0] * w), int(rel[1] * h), int(rel[2] * w), int(rel[3] * h))
    return img.crop(box).convert("RGB")


def top_colors(img: Image.Image, rel, n: int = 5):
    px = crop(img, rel)
    counts = Counter(quantize(p) for p in pixels(px))
    total = sum(counts.values()) or 1
    return px.size, [(hexs(c), round(100 * k / total, 1)) for c, k in counts.most_common(n)]


def filtered(img: Image.Image, rel, *, sat: float, val: float, n: int = 4):
    counts: Counter = Counter()
    for r, g, b in pixels(crop(img, rel)):
        _, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        if s > sat and v > val:
            counts[quantize((r, g, b))] += 1
    total = sum(counts.values()) or 1
    return [(hexs(c), 100 * k / total, hue(c)) for c, k in counts.most_common(n)], total


def write_swatch() -> None:
    """把定稿色板导成一张对照图，供与参考截图并排比对。

    色值本身来自上面的实测统计（写死在 TOKENS 里）；
    这张图只是可视化，不是新数据。
    """
    from PIL import ImageDraw

    tokens: list[tuple[str, str, str]] = [
        ("--canvas", "#0F0F0F", "页面底色"),
        ("--canvas-deep", "#030303", "顶栏/最深"),
        ("--chrome", "#212121", "页脚/导航外壳（实测 94-100%）"),
        ("--surface", "#1B1B1B", "卡片填充"),
        ("--surface-2a", "#211B21", "半透明叠加卡"),
        ("--surface-2b", "#27271B", "半透明叠加卡"),
        ("--accent", "#CF8D2D", "强调（实测 h≈36°）"),
        ("--accent-hi", "#E7A93C", "派生：hover/聚焦"),
        ("--ink", "#E7DBCF", "正文暖米白"),
        ("--ink-2", "#B7B19F", "次级正文"),
        ("--muted", "#877B6F", "弱化/未激活"),
        ("--muted-2", "#695D51", "更弱"),
    ]

    sw, sh = 150, 92
    cols, pad = 4, 24
    rows = (len(tokens) + cols - 1) // cols
    W = pad + cols * (sw + pad)
    H = pad + rows * (sh + pad) + 46
    canvas = Image.new("RGB", (W, H), (15, 15, 15))
    d = ImageDraw.Draw(canvas)
    d.text((pad, 14), "1999 RAG frontend - style tokens measured from wiki home", fill=(231, 219, 207))

    for i, (name, hexv, note) in enumerate(tokens):
        cx = pad + (i % cols) * (sw + pad)
        cy = pad + 34 + (i // cols) * (sh + pad)
        rgb = tuple(int(hexv[j : j + 2], 16) for j in (1, 3, 5))
        d.rectangle([cx, cy, cx + sw, cy + sh - 30], fill=rgb, outline=(90, 90, 90))
        d.text((cx, cy + sh - 26), f"{name}", fill=(231, 219, 207))
        d.text((cx, cy + sh - 14), f"{hexv}  {note}", fill=(135, 123, 111))

    out = r"docs\ref\palette-tokens.png"
    canvas.save(out)
    print(f"已导出色板对照图: {out}  ({W}x{H})")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # 避免 Windows 控制台把中文打成乱码

    if "--swatch" in sys.argv:
        write_swatch()
        return

    img = Image.open(SRC)
    print(f"图像: {SRC}  尺寸={img.size[0]}x{img.size[1]}\n")

    print("=== 1. 分区主色（量化到 6 级）===")
    for name, rel in REGIONS.items():
        box, colors = top_colors(img, rel)
        print(f"\n{name}  {box[0]}x{box[1]}px")
        print("  " + "  ".join(f"{h}({p}%)" for h, p in colors))

    print("\n=== 2. UI 强调色（高饱和暖色）===")
    for name, rel in ACCENT_BOXES.items():
        hits, total = filtered(img, rel, sat=0.35, val=0.25)
        print(f"\n{name}  ({total} 命中像素)")
        for h, pct, deg in hits:
            print(f"  {h}  {pct:5.1f}%  hue≈{deg:.0f}°")

    print("\n=== 3. 正文字色（低饱和高亮）===")
    for name, rel in INK_BOXES.items():
        hits, total = filtered(img, rel, sat=0.0, val=0.55)
        print(f"\n{name}  ({total} 命中像素)")
        for h, pct, deg in hits:
            print(f"  {h}  {pct:5.1f}%")

    print("\n=== 4. 弱化文字色（低饱和中亮）===")
    for name, rel in MUTED_BOXES.items():
        hits, total = filtered(img, rel, sat=0.15, val=0.40)
        print(f"\n{name}  ({total} 命中像素)")
        for h, pct, deg in hits:
            print(f"  {h}  {pct:5.1f}%  hue≈{deg:.0f}°")

    print("\n=== 5. 亮度分布（判断整体明暗）===")
    small = img.convert("RGB").resize((img.size[0] // 2, img.size[1] // 2))
    lum = sorted(0.2126 * r + 0.7152 * g + 0.0722 * b for r, g, b in pixels(small))
    n = len(lum)
    print(
        f"  p10={lum[n // 10]:.0f}  p50={lum[n // 2]:.0f}  p90={lum[9 * n // 10]:.0f}  "
        f"均值={sum(lum) / n:.0f}  (0-255)"
    )
    print(f"  暗部(<60)占比 = {sum(1 for x in lum if x < 60) / n * 100:.1f}%  → >50% 即深色主题")


if __name__ == "__main__":
    main()
