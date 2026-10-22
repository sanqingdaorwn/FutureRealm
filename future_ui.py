"""Vector-style artwork for 未来漫境.

Everything here is drawn with Pillow at runtime so the packaged exe stays
self-contained (no external image files besides the app icon).
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent


def _rgba(color: str, alpha: int = 255) -> tuple[int, int, int, int]:
    color = color.lstrip("#")
    return (int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16), alpha)


def _lerp(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return (
        round(a[0] + (b[0] - a[0]) * t),
        round(a[1] + (b[1] - a[1]) * t),
        round(a[2] + (b[2] - a[2]) * t),
    )


def _linear_gradient(size: tuple[int, int], start: str, end: str, angle: float = 45.0) -> Image.Image:
    """Small per-pixel gradient; sizes here are tiny so plain Python is fine."""
    width, height = size
    base = Image.new("RGBA", size)
    start_rgb = _rgba(start)[:3]
    end_rgb = _rgba(end)[:3]
    radians = math.radians(angle)
    dx, dy = math.cos(radians), math.sin(radians)
    span = abs(dx) * width + abs(dy) * height
    offset = dx * width + dy * height if dx < 0 or dy < 0 else 0.0
    pixels = base.load()
    for y in range(height):
        for x in range(width):
            t = (x * dx + y * dy - offset) / max(1.0, span)
            t = min(1.0, max(0.0, t))
            pixels[x, y] = (*_lerp(start_rgb, end_rgb, t), 255)
    return base


def _rounded_mask(size: tuple[int, int], radius: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=radius, fill=255)
    return mask


def _line(draw: ImageDraw.ImageDraw, points, color, width: int, joint: str = "curve") -> None:
    draw.line(points, fill=color, width=width, joint=joint)


def _icon(draw: ImageDraw.ImageDraw, name: str, box: tuple[float, float, float, float], color, width: int) -> None:
    x0, y0, x1, y1 = box
    side = x1 - x0

    def point(u: float, v: float) -> tuple[float, float]:
        return (x0 + u * side, y0 + v * side)

    if name == "download":
        _line(draw, [point(0.50, 0.14), point(0.50, 0.61)], color, width)
        _line(draw, [point(0.33, 0.45), point(0.50, 0.62), point(0.67, 0.45)], color, width)
        _line(
            draw,
            [point(0.18, 0.60), point(0.18, 0.80), point(0.82, 0.80), point(0.82, 0.60)],
            color,
            width,
        )
    elif name == "book":
        _line(
            draw,
            [
                point(0.50, 0.29),
                point(0.40, 0.24),
                point(0.26, 0.22),
                point(0.13, 0.26),
                point(0.13, 0.72),
                point(0.28, 0.70),
                point(0.41, 0.73),
                point(0.50, 0.79),
            ],
            color,
            width,
        )
        _line(
            draw,
            [
                point(0.50, 0.29),
                point(0.60, 0.24),
                point(0.74, 0.22),
                point(0.87, 0.26),
                point(0.87, 0.72),
                point(0.72, 0.70),
                point(0.59, 0.73),
                point(0.50, 0.79),
            ],
            color,
            width,
        )
        _line(draw, [point(0.50, 0.31), point(0.50, 0.78)], color, max(1, width - 1))
        _line(draw, [point(0.22, 0.38), point(0.38, 0.36)], color, max(1, width - 1))
        _line(draw, [point(0.62, 0.36), point(0.78, 0.38)], color, max(1, width - 1))
    elif name == "sparkle":
        def star(cx: float, cy: float, radius: float) -> None:
            points = [
                point(cx, cy - radius),
                point(cx + radius * 0.17, cy - radius * 0.17),
                point(cx + radius, cy),
                point(cx + radius * 0.17, cy + radius * 0.17),
                point(cx, cy + radius),
                point(cx - radius * 0.17, cy + radius * 0.17),
                point(cx - radius, cy),
                point(cx - radius * 0.17, cy - radius * 0.17),
                point(cx, cy - radius),
            ]
            _line(draw, points, color, width)

        star(0.38, 0.40, 0.28)
        star(0.72, 0.70, 0.17)
        draw.ellipse([point(0.76, 0.18), point(0.84, 0.26)], fill=color)
    elif name == "search":
        draw.ellipse([point(0.16, 0.14), point(0.68, 0.66)], outline=color, width=width)
        _line(draw, [point(0.62, 0.62), point(0.86, 0.86)], color, width + 1)
    elif name == "folder":
        _line(
            draw,
            [
                point(0.12, 0.30),
                point(0.12, 0.78),
                point(0.88, 0.78),
                point(0.88, 0.30),
                point(0.52, 0.30),
                point(0.44, 0.20),
                point(0.12, 0.20),
                point(0.12, 0.30),
            ],
            color,
            width,
        )
    elif name == "image":
        draw.rounded_rectangle([point(0.12, 0.16), point(0.88, 0.84)], radius=side * 0.14, outline=color, width=width)
        draw.ellipse([point(0.28, 0.30), point(0.42, 0.44)], fill=color)
        _line(
            draw,
            [point(0.16, 0.74), point(0.40, 0.50), point(0.56, 0.66), point(0.68, 0.55), point(0.84, 0.74)],
            color,
            width,
        )
    elif name == "sliders":
        for index, (y, knob) in enumerate(((0.28, 0.38), (0.52, 0.66), (0.76, 0.30))):
            _line(draw, [point(0.14, y), point(0.86, y)], color, width)
            draw.ellipse([point(knob - 0.08, y - 0.08), point(knob + 0.08, y + 0.08)], fill=color)
    elif name == "chart":
        _line(draw, [point(0.14, 0.20), point(0.14, 0.82), point(0.86, 0.82)], color, width)
        draw.rounded_rectangle([point(0.24, 0.56), point(0.40, 0.82)], radius=side * 0.04, fill=color)
        draw.rounded_rectangle([point(0.45, 0.42), point(0.61, 0.82)], radius=side * 0.04, fill=color)
        draw.rounded_rectangle([point(0.66, 0.26), point(0.82, 0.82)], radius=side * 0.04, fill=color)
    elif name == "terminal":
        draw.rounded_rectangle(
            [point(0.10, 0.16), point(0.90, 0.84)], radius=side * 0.13, outline=color, width=width
        )
        _line(draw, [point(0.25, 0.38), point(0.38, 0.50), point(0.25, 0.62)], color, width)
        _line(draw, [point(0.48, 0.64), point(0.72, 0.64)], color, width)
    elif name == "chevron-right":
        _line(draw, [point(0.38, 0.20), point(0.64, 0.50), point(0.38, 0.80)], color, width)
    elif name == "plus":
        _line(draw, [point(0.50, 0.20), point(0.50, 0.80)], color, width)
        _line(draw, [point(0.20, 0.50), point(0.80, 0.50)], color, width)
    elif name == "minus":
        _line(draw, [point(0.20, 0.50), point(0.80, 0.50)], color, width)
    elif name == "check":
        _line(draw, [point(0.20, 0.52), point(0.42, 0.74), point(0.80, 0.28)], color, width)
    elif name == "heart":
        points = []
        for step in range(72):
            angle = math.pi * 2 * step / 72
            x = 16 * math.sin(angle) ** 3
            y = -(13 * math.cos(angle) - 5 * math.cos(2 * angle) - 2 * math.cos(3 * angle) - math.cos(4 * angle))
            points.append(point(0.50 + x / 40.0, 0.46 + y / 40.0))
        _line(draw, points, color, width)
    else:
        raise ValueError(f"unknown icon: {name}")


def _tile(size: int, radius: int, fill, icon: str, icon_color, icon_size: float, stroke: float, active_gradient=None, dpi: int = 4) -> Image.Image:
    scale = dpi
    big = size * scale
    mask = _rounded_mask((big, big), radius * scale)
    if active_gradient is None:
        base = Image.new("RGBA", (big, big), _rgba(fill) if len(fill) == 7 else fill)
    else:
        base = _linear_gradient((big, big), active_gradient[0], active_gradient[1], angle=48).convert("RGBA")
    tile = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    tile.paste(base, (0, 0), mask)
    draw = ImageDraw.Draw(tile)
    inset = (size - icon_size) / 2 * scale
    _icon(draw, icon, (inset, inset, big - inset, big - inset), icon_color, max(1, round(stroke * scale)))
    return tile.resize((size, size), Image.Resampling.LANCZOS)


def nav_tile(icon: str, active: bool, size: int = 30) -> Image.Image:
    if active:
        return _tile(
            size,
            9,
            "#FFFFFF",
            icon,
            "#FFFFFF",
            size * 0.62,
            1.7,
            active_gradient=("#F394B7", "#8F7BE8"),
        )
    return _tile(size, 9, "#352C4D", icon, "#B9AECB", size * 0.62, 1.7)


CARD_TONES = {
    "rose": ("#FCECF2", "#D9678F"),
    "lilac": ("#F1EDFC", "#7B6AD8"),
    "amber": ("#FBF1E1", "#B07A22"),
    "mint": ("#E8F5F0", "#3E8F70"),
    "plum": ("#F2ECF6", "#705A86"),
}


def card_icon(icon: str, tone: str = "rose", size: int = 34) -> Image.Image:
    fill, ink = CARD_TONES.get(tone, CARD_TONES["rose"])
    return _tile(size, 11, fill, icon, ink, size * 0.56, 1.8)


def empty_scan_art(size: int = 64) -> Image.Image:
    return _tile(size, size // 3, "#F5EEF8", "search", "#A08CB8", size * 0.50, 2.0)


def glow(size: int = 110, color: str = "#E27FA2", alpha: int = 80) -> Image.Image:
    scale = 2
    big = size * scale
    mask = Image.new("L", (big, big), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((big * 0.14, big * 0.14, big * 0.86, big * 0.86), fill=alpha)
    mask = mask.filter(ImageFilter.GaussianBlur(big * 0.12))
    image = Image.new("RGBA", (big, big), _rgba(color, 0))
    image.putalpha(mask)
    return image.resize((size, size), Image.Resampling.LANCZOS)


def _petal(draw: ImageDraw.ImageDraw, cx: float, cy: float, radius: float, angle: float, fill, outline=None, width: int = 1) -> None:
    points = []
    for step in range(25):
        t = math.pi * 2 * step / 24
        x = math.sin(t) * radius * 0.62
        y = -math.cos(t) * radius
        # sakura notch at the tip
        if math.cos(t) > 0.75:
            x *= 0.55
            y *= 0.86
        ca, sa = math.cos(angle), math.sin(angle)
        points.append((cx + x * ca - y * sa, cy + x * sa + y * ca))
    draw.polygon(points, fill=fill)
    if outline is not None:
        draw.line(points + [points[0]], fill=outline, width=width)


def _blossom(draw, cx, cy, radius, petal_fill, center_fill, angle=0.0, outline=None, width=1) -> None:
    for index in range(5):
        _petal(
            draw,
            cx,
            cy,
            radius,
            angle + math.pi * 2 * index / 5,
            petal_fill,
            outline,
            width,
        )
    draw.ellipse((cx - radius * 0.20, cy - radius * 0.20, cx + radius * 0.20, cy + radius * 0.20), fill=center_fill)


def _sparkle(draw, cx, cy, radius, fill) -> None:
    draw.polygon(
        [
            (cx, cy - radius),
            (cx + radius * 0.16, cy - radius * 0.16),
            (cx + radius, cy),
            (cx + radius * 0.16, cy + radius * 0.16),
            (cx, cy + radius),
            (cx - radius * 0.16, cy + radius * 0.16),
            (cx - radius, cy),
            (cx - radius * 0.16, cy - radius * 0.16),
        ],
        fill=fill,
    )


def _soft_blob(image: Image.Image, center, radius, color, alpha, blur: float = 0.4) -> None:
    mask = Image.new("L", image.size, 0)
    ImageDraw.Draw(mask).ellipse(
        (center[0] - radius, center[1] - radius, center[0] + radius, center[1] + radius),
        fill=alpha,
    )
    mask = mask.filter(ImageFilter.GaussianBlur(max(1.0, radius * blur)))
    layer = Image.new("RGBA", image.size, _rgba(color, 255))
    layer.putalpha(mask)
    image.alpha_composite(layer)


def hero_art(width: int = 430, height: int = 148) -> Image.Image:
    """Sakura branch + aurora glow for the dark hero header."""
    scale = 3
    size = (width * scale, height * scale)
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    _soft_blob(image, (size[0] * 0.80, size[1] * 0.28), size[1] * 0.48, "#8C5FC4", 88)
    _soft_blob(image, (size[0] * 0.96, size[1] * 0.76), size[1] * 0.36, "#E07097", 72)
    _soft_blob(image, (size[0] * 0.66, size[1] * 0.86), size[1] * 0.24, "#C79BDD", 34)

    draw = ImageDraw.Draw(image)
    branch = _rgba("#7E5F8C", 210)
    twig = _rgba("#8D6E9B", 190)
    _line(
        draw,
        [
            (size[0] * 1.02, size[1] * 0.10),
            (size[0] * 0.88, size[1] * 0.20),
            (size[0] * 0.79, size[1] * 0.34),
            (size[0] * 0.70, size[1] * 0.46),
            (size[0] * 0.58, size[1] * 0.60),
            (size[0] * 0.52, size[1] * 0.78),
            (size[0] * 0.44, size[1] * 0.94),
        ],
        branch,
        max(2, round(2.6 * scale)),
    )
    _line(
        draw,
        [
            (size[0] * 0.80, size[1] * 0.35),
            (size[0] * 0.71, size[1] * 0.24),
            (size[0] * 0.66, size[1] * 0.14),
        ],
        twig,
        max(1, round(1.4 * scale)),
    )
    _line(
        draw,
        [
            (size[0] * 0.66, size[1] * 0.50),
            (size[0] * 0.58, size[1] * 0.44),
            (size[0] * 0.51, size[1] * 0.45),
        ],
        twig,
        max(1, round(1.3 * scale)),
    )

    blossoms = (
        (0.84, 0.22, 0.085, 12),
        (0.72, 0.40, 0.105, 42),
        (0.62, 0.30, 0.062, -18),
        (0.56, 0.57, 0.078, 8),
        (0.48, 0.76, 0.056, 28),
        (0.66, 0.68, 0.048, -24),
    )
    for cx, cy, radius, angle in blossoms:
        _blossom(
            draw,
            size[0] * cx,
            size[1] * cy,
            size[1] * radius,
            _rgba("#F3A9C4", 236),
            _rgba("#FFE4EF", 250),
            math.radians(angle),
            _rgba("#E287AA", 180),
            max(1, round(0.8 * scale)),
        )

    leaves = ((0.78, 0.30, 22), (0.60, 0.50, -30), (0.52, 0.82, 18))
    for cx, cy, angle in leaves:
        _petal(
            draw,
            size[0] * cx,
            size[1] * cy,
            size[1] * 0.045,
            math.radians(angle),
            _rgba("#9B7EB4", 160),
            _rgba("#86699F", 120),
            max(1, round(0.7 * scale)),
        )

    for cx, cy, radius, alpha in (
        (0.94, 0.46, 7, 190),
        (0.76, 0.76, 6, 180),
        (0.58, 0.20, 5, 160),
        (0.90, 0.84, 4, 140),
    ):
        _sparkle(draw, size[0] * cx, size[1] * cy, radius * scale, (255, 255, 255, alpha))

    draw.arc(
        (size[0] * 0.52, size[1] * -0.30, size[0] * 1.16, size[1] * 1.34),
        start=110,
        end=250,
        fill=_rgba("#E9B7D0", 42),
        width=max(1, round(1.2 * scale)),
    )
    return image.resize((width, height), Image.Resampling.LANCZOS)


def sidebar_art(width: int = 210, height: int = 150) -> Image.Image:
    scale = 2
    size = (width * scale, height * scale)
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    color = _rgba("#9C89B6", 58)
    _line(
        draw,
        [
            (size[0] * 0.06, size[1] * 0.98),
            (size[0] * 0.30, size[1] * 0.78),
            (size[0] * 0.46, size[1] * 0.62),
            (size[0] * 0.60, size[1] * 0.40),
            (size[0] * 0.82, size[1] * 0.24),
            (size[0] * 0.96, size[1] * 0.12),
        ],
        color,
        max(1, round(1.1 * scale)),
    )
    for cx, cy, radius in ((0.28, 0.81, 0.055), (0.47, 0.61, 0.042), (0.62, 0.39, 0.050), (0.84, 0.23, 0.038)):
        _blossom(
            draw,
            size[0] * cx,
            size[1] * cy,
            size[1] * radius,
            (243, 169, 196, 52),
            (255, 228, 239, 56),
            0.5,
            (226, 135, 170, 40),
            max(1, round(0.6 * scale)),
        )
    for cx, cy, radius, alpha in ((0.18, 0.90, 4, 60), (0.55, 0.52, 3, 52), (0.75, 0.30, 5, 55)):
        _sparkle(draw, size[0] * cx, size[1] * cy, radius * scale, (255, 255, 255, alpha))
    return image.resize((width, height), Image.Resampling.LANCZOS)


def _soft_ellipse(image: Image.Image, box, color, alpha, blur: float = 6.0) -> None:
    mask = Image.new("L", image.size, 0)
    ImageDraw.Draw(mask).ellipse(box, fill=alpha)
    mask = mask.filter(ImageFilter.GaussianBlur(blur))
    layer = Image.new("RGBA", image.size, _rgba(color, 255))
    layer.putalpha(mask)
    image.alpha_composite(layer)


def reading_nook(width: int = 430, height: int = 200) -> Image.Image:
    """Quiet little reading still-life: books, a cup, a sprig, petals."""
    scale = 3
    size = (width * scale, height * scale)
    image = Image.new("RGBA", size, (0, 0, 0, 0))

    def p(u: float, v: float) -> tuple[float, float]:
        return (size[0] * u, size[1] * v)

    _soft_ellipse(
        image,
        (size[0] * 0.24, size[1] * 0.83, size[0] * 0.84, size[1] * 0.93),
        "#D8BFCC",
        60,
        blur=size[1] * 0.032,
    )
    draw = ImageDraw.Draw(image)

    ink = _rgba("#8E7A9C", 160)
    rose = _rgba("#D48FA8", 200)
    lilac = _rgba("#A995D1", 200)
    amber = _rgba("#CDA274", 200)
    page = _rgba("#FFFFFF", 238)

    # stack of closed books
    books = (
        (0.28, 0.68, 0.73, 0.81, "#F8DFE9", rose),
        (0.34, 0.55, 0.70, 0.67, "#E8DFF8", lilac),
        (0.40, 0.43, 0.66, 0.54, "#FBEBD9", amber),
    )
    for left, top, right, bottom, fill, outline in books:
        draw.rounded_rectangle(
            [p(left, top), p(right, bottom)],
            radius=size[1] * 0.016,
            fill=_rgba(fill, 240),
            outline=outline,
            width=max(1, round(1.1 * scale)),
        )
        draw.rounded_rectangle(
            [p(left + 0.008, top + 0.012), p(left + 0.030, bottom - 0.012)],
            radius=size[1] * 0.006,
            fill=_rgba("#FFFFFF", 70),
        )
        draw.line(
            [p(left + 0.040, top + 0.015), p(right - 0.018, top + 0.015)],
            fill=_rgba("#FFFFFF", 160),
            width=max(1, round(0.8 * scale)),
        )
        draw.rectangle(
            [p(right - 0.020, top + 0.022), p(right - 0.014, bottom - 0.022)],
            fill=page,
        )
    draw.line([p(0.61, 0.43), p(0.61, 0.58), p(0.625, 0.62), p(0.64, 0.58), p(0.64, 0.47)], fill=rose, width=max(1, round(1.0 * scale)))
    draw.line([p(0.44, 0.43), p(0.44, 0.53), p(0.455, 0.565), p(0.47, 0.53), p(0.47, 0.43)], fill=lilac, width=max(1, round(0.8 * scale)))

    # cup and saucer
    draw.ellipse([p(0.72, 0.78), p(0.90, 0.84)], fill=_rgba("#F4E4EB", 210), outline=rose, width=max(1, round(1.0 * scale)))
    draw.rounded_rectangle(
        [p(0.755, 0.62), p(0.865, 0.79)],
        radius=size[1] * 0.032,
        fill=_rgba("#FFFFFF", 245),
        outline=rose,
        width=max(1, round(1.2 * scale)),
    )
    draw.arc([p(0.855, 0.66), p(0.905, 0.75)], start=-85, end=95, fill=rose, width=max(1, round(1.2 * scale)))
    draw.arc([p(0.762, 0.665), p(0.858, 0.705)], start=200, end=340, fill=_rgba("#E9CBD6", 180), width=max(1, round(0.8 * scale)))
    for cx, cy, box in ((0.79, 0.56, 0.028), (0.815, 0.50, 0.036), (0.785, 0.435, 0.026)):
        draw.arc(
            [p(cx - box, cy - box * 0.7), p(cx + box, cy + box * 0.7)],
            start=35,
            end=225,
            fill=_rgba("#C9AFC0", 100),
            width=max(1, round(0.7 * scale)),
        )

    # sprig in a little vase
    draw.rounded_rectangle(
        [p(0.135, 0.70), p(0.230, 0.82)],
        radius=size[1] * 0.022,
        fill=_rgba("#F4DFD3", 230),
        outline=amber,
        width=max(1, round(1.0 * scale)),
    )
    draw.line([p(0.135, 0.735), p(0.230, 0.735)], fill=amber, width=max(1, round(0.8 * scale)))
    stem = _rgba("#A3B3A4", 190)
    for base_x, tip_x, tip_y, angle in ((0.168, 0.100, 0.50, -28), (0.186, 0.188, 0.44, 2), (0.204, 0.275, 0.52, 26)):
        base = p(base_x, 0.715)
        tip = p(tip_x, tip_y)
        draw.line([base, tip], fill=stem, width=max(1, round(0.9 * scale)))
        mid_x = (base_x + tip_x) / 2
        mid_y = (0.715 + tip_y) / 2
        for lx, ly, langle in ((mid_x - 0.012, mid_y, angle - 42), (mid_x + 0.014, mid_y + 0.02, angle + 42)):
            cx, cy = p(lx, ly)
            _petal(draw, cx, cy, size[1] * 0.026, math.radians(langle), _rgba("#DDE8D8", 210), stem, max(1, round(0.5 * scale)))
        cx, cy = p(tip_x, tip_y)
        _blossom(draw, cx, cy, size[1] * 0.026, _rgba("#F3BFD1", 210), _rgba("#FFE7F0", 230), 0.3, None)

    # petals drifting
    for cx, cy, radius, angle in (
        (0.19, 0.18, 0.022, 20),
        (0.07, 0.45, 0.014, -20),
        (0.88, 0.25, 0.018, 40),
        (0.93, 0.48, 0.012, 5),
        (0.61, 0.16, 0.012, -35),
    ):
        _petal(
            draw,
            p(cx, cy)[0],
            p(cx, cy)[1],
            size[1] * radius,
            math.radians(angle),
            _rgba("#F3BFD1", 170),
        )
    for cx, cy, radius in ((0.28, 0.28, 5), (0.70, 0.22, 4), (0.90, 0.60, 3)):
        _sparkle(draw, p(cx, cy)[0], p(cx, cy)[1], radius * scale, (255, 255, 255, 160))
    return image.resize((width, height), Image.Resampling.LANCZOS)


def icon_image(kind: str, tone: str = "rose", size: int = 34) -> Image.Image:
    return card_icon(kind, tone, size)
