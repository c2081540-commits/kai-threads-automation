from pathlib import Path
import os
import math
from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 1080, 1350
NAVY = "#121B38"
NAVY_2 = "#202A4C"
CREAM = "#FFF8EB"
GOLD = "#D9AD57"
MUTED = "#C8C2B7"

FONT_CANDIDATES = (
    os.getenv("FONT_PATH", ""),
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansJP-Bold.ttf",
    "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)


def _font(size, bold=False):
    candidates = list(FONT_CANDIDATES)
    if not bold:
        candidates.reverse()
    for path in candidates:
        if path and Path(path).exists():
            return ImageFont.truetype(path, size=size)
    raise RuntimeError(
        "日本語フォントがありません。GitHub Actionsではfonts-noto-cjkをインストールしてください。"
    )


def _gradient():
    image = Image.new("RGB", (WIDTH, HEIGHT), NAVY)
    px = image.load()
    start = (18, 27, 56)
    end = (41, 31, 58)
    for y in range(HEIGHT):
        t = y / (HEIGHT - 1)
        color = tuple(int(a * (1 - t) + b * t) for a, b in zip(start, end))
        for x in range(WIDTH):
            px[x, y] = color
    return image


def _wrap(text, max_chars=14):
    text = text.replace("【3枚から選ぶ】", "").strip("。 ")
    count = min(3, max(1, math.ceil(len(text) / max_chars)))
    base, extra = divmod(len(text), count)
    sizes = [base + (1 if i < extra else 0) for i in range(count)]
    lines, offset = [], 0
    for size in sizes:
        lines.append(text[offset:offset + size])
        offset += size
    return lines


def _center_text(draw, text, y, font, fill=CREAM):
    box = draw.textbbox((0, 0), text, font=font)
    x = (WIDTH - (box[2] - box[0])) // 2
    draw.text((x, y), text, font=font, fill=fill)


def _card(draw, x, y, w, h, label=None):
    draw.rounded_rectangle((x, y, x + w, y + h), radius=28, fill="#F0E4C9", outline=GOLD, width=8)
    inset = 22
    draw.rounded_rectangle(
        (x + inset, y + inset, x + w - inset, y + h - inset),
        radius=20, fill=NAVY_2, outline=GOLD, width=4,
    )
    cx, cy = x + w // 2, y + h // 2
    draw.ellipse((cx - 56, cy - 56, cx + 56, cy + 56), outline=GOLD, width=5)
    draw.polygon(
        [(cx, cy - 82), (cx + 24, cy - 24), (cx + 82, cy),
         (cx + 24, cy + 24), (cx, cy + 82), (cx - 24, cy + 24),
         (cx - 82, cy), (cx - 24, cy - 24)],
        outline=GOLD,
    )
    if label:
        font = _font(54, bold=True)
        box = draw.textbbox((0, 0), label, font=font)
        draw.ellipse((cx - 45, y + h + 26, cx + 45, y + h + 116), fill=GOLD)
        draw.text((cx - (box[2] - box[0]) / 2, y + h + 34), label, font=font, fill=NAVY)


def render_post_image(draft_id, fmt, title, cards=None, event=None):
    image = _gradient()
    draw = ImageDraw.Draw(image)
    draw.ellipse((-260, -330, 440, 370), fill="#26355F")
    draw.ellipse((760, 980, 1300, 1520), fill="#3B2946")

    small = _font(34, bold=True)
    title_font = _font(68, bold=True)
    _center_text(draw, "KAI  復縁タロット", 72, small, GOLD)

    title_y = 185
    for line in _wrap(title, 13):
        _center_text(draw, line, title_y, title_font)
        title_y += 92

    if fmt == "event_countdown" and event:
        if event["days_left"] == 0:
            badge = "TODAY"
            sub = f"今日は{event['name']}"
        else:
            badge = f"あと {event['days_left']} 日"
            sub = event["name"]
        _center_text(draw, badge, 520, _font(108, bold=True), GOLD)
        _center_text(draw, sub, 665, _font(48, bold=True))
        _card(draw, 420, 790, 240, 360)
    elif fmt == "three_choice":
        for x, label in zip((105, 420, 735), ("A", "B", "C")):
            _card(draw, x, 660, 240, 360, label)
        _center_text(draw, "直感で1枚選んでください", 1190, _font(42, bold=True), MUTED)
    elif fmt == "checklist":
        for i, text in enumerate(("感情の勢い", "別れた原因", "今の距離感"), 1):
            y = 620 + (i - 1) * 155
            draw.ellipse((135, y, 215, y + 80), fill=GOLD)
            _center = _font(42, bold=True)
            draw.text((160, y + 12), str(i), font=_center, fill=NAVY)
            draw.text((255, y + 8), text, font=_font(52, bold=True), fill=CREAM)
        _center_text(draw, "焦って動く前に確認", 1130, _font(42, bold=True), MUTED)
    else:
        _card(draw, 390, 625, 300, 450)
        _center_text(draw, "今日の1枚から読み解く", 1140, _font(42, bold=True), MUTED)

    out = Path("generated") / f"post-{draft_id:05d}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    image.save(out, "PNG", optimize=True)
    return str(out)
