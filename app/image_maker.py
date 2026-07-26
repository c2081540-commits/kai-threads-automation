from pathlib import Path
import math
import os

from PIL import Image, ImageDraw, ImageFont


WIDTH, HEIGHT = 1080, 1350
BG = "#071217"
CREAM = "#F3EBDD"
GOLD = "#D8B76A"
MUTED = "#B9B2A4"
CARD_DIR = Path(__file__).resolve().parents[1] / "tarot_cards"

FONT_CANDIDATES = (
    os.getenv("FONT_PATH", ""),
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansJP-Bold.ttf",
    "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
    "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
)


def _font(size):
    for path in FONT_CANDIDATES:
        if path and Path(path).exists():
            return ImageFont.truetype(path, size=size)
    raise RuntimeError(
        "日本語フォントがありません。GitHub Actionsではfonts-noto-cjkをインストールしてください。"
    )


def _canvas():
    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)
    draw.rectangle((20, 20, WIDTH - 21, HEIGHT - 21), outline=GOLD, width=3)
    draw.rectangle((31, 31, WIDTH - 32, HEIGHT - 32), outline="#5D4A25", width=1)
    return image, draw


def _center_text(draw, text, y, font, fill=CREAM):
    box = draw.textbbox((0, 0), text, font=font)
    x = (WIDTH - (box[2] - box[0])) // 2
    draw.text((x, y), text, font=font, fill=fill)


def _wrap_by_width(draw, text, font, max_width):
    lines, current = [], ""
    for char in text:
        candidate = current + char
        if draw.textbbox((0, 0), candidate, font=font)[2] <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = char
    if current:
        lines.append(current)
    return lines


def _fit_font(draw, text, max_width, start=68, minimum=30):
    for size in range(start, minimum - 1, -2):
        font = _font(size)
        if draw.textbbox((0, 0), text, font=font)[2] <= max_width:
            return font
    return _font(minimum)


def _title(draw, text):
    cleaned = text.replace("【3枚から選ぶ】", "").strip("。 ")
    font = _fit_font(draw, cleaned, 920)
    lines = _wrap_by_width(draw, cleaned, font, 920)
    y = 82
    for line in lines[:2]:
        _center_text(draw, line, y, font)
        y += font.size + 18
    return y


def _card_path(card):
    path = CARD_DIR / f"{int(card['id']):02d}_{card['slug']}.png"
    if not path.is_file():
        raise FileNotFoundError(f"カード画像がありません: {path}")
    return path


def _card_art(card, size, darken=False):
    source = Image.open(_card_path(card)).convert("RGB")
    source.thumbnail(size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    x = (size[0] - source.width) // 2
    y = (size[1] - source.height) // 2
    canvas.paste(source, (x, y))
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, size[0] - 1, size[1] - 1), radius=22, fill=255
    )
    canvas.putalpha(mask)
    if darken:
        canvas = Image.alpha_composite(
            canvas, Image.new("RGBA", size, (2, 9, 13, 95))
        )
    return canvas


def _paste_card(image, draw, card, xy, size, darken=False):
    x, y = xy
    art = _card_art(card, size, darken=darken)
    image.paste(art, (x, y), art)
    draw.rounded_rectangle(
        (x - 3, y - 3, x + size[0] + 2, y + size[1] + 2),
        radius=23,
        outline=GOLD,
        width=3,
    )


def _render_choice(draft_id, title, cards):
    if len(cards) != 3:
        raise ValueError("3枚選択画像には異なるカードが3枚必要です")
    if len({int(card["id"]) for card in cards}) != 3:
        raise ValueError("同じカードを重複配置できません")

    image, draw = _canvas()
    _title(draw, title)
    _center_text(draw, "一度深呼吸して、直感で1枚選んでください", 235, _font(34), MUTED)

    card_w, card_h = 286, 429
    gap = 37
    start_x = (WIDTH - card_w * 3 - gap * 2) // 2
    top = 345
    label_font = _font(58)
    for index, (label, card) in enumerate(zip("ABC", cards)):
        x = start_x + index * (card_w + gap)
        _paste_card(image, draw, card, (x, top), (card_w, card_h), darken=False)
        box = draw.textbbox((0, 0), label, font=label_font)
        draw.text(
            (x + (card_w - (box[2] - box[0])) / 2, top + card_h + 36),
            label,
            font=label_font,
            fill=GOLD,
        )

    _center_text(draw, "結果は返信欄へ", 1015, _font(44), CREAM)
    _center_text(draw, "Kai 復縁タロット", 1235, _font(28), GOLD)
    out = Path("generated") / f"post-{draft_id:05d}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    image.save(out, "PNG", optimize=True)
    return str(out)


def _render_result(draft_id, label, card):
    image, draw = _canvas()
    _center_text(draw, f"{label}を選んだあなたへ", 70, _font(56), CREAM)
    _paste_card(image, draw, card, (72, 205), (365, 548))

    draw.text((500, 225), card["name_ja"], font=_font(62), fill=GOLD)
    keyword_text = "・".join(card["keywords"])
    y = 320
    for line in _wrap_by_width(draw, keyword_text, _font(32), 500):
        draw.text((500, y), line, font=_font(32), fill=MUTED)
        y += 46

    y = 470
    body_font = _font(40)
    for line in _wrap_by_width(draw, card["love"], body_font, 500):
        draw.text((500, y), line, font=body_font, fill=CREAM)
        y += 60

    draw.line((75, 850, 1005, 850), fill="#5D4A25", width=2)
    _center_text(draw, "焦って結論を出さず、今日できる一歩を選ぶ", 930, _font(38), CREAM)
    _center_text(draw, "Kai 復縁タロット", 1235, _font(28), GOLD)
    out = Path("generated") / f"post-{draft_id:05d}-result-{label}.png"
    image.save(out, "PNG", optimize=True)
    return str(out)


def _render_single(draft_id, fmt, title, card, event=None):
    image, draw = _canvas()
    _title(draw, title)
    _paste_card(image, draw, card, (358, 360), (365, 548))

    if fmt == "event_countdown" and event:
        badge = "TODAY" if event["days_left"] == 0 else f"あと {event['days_left']} 日"
        _center_text(draw, badge, 980, _font(58), GOLD)
    else:
        _center_text(draw, card["name_ja"], 980, _font(58), GOLD)
    _center_text(draw, "Kai 復縁タロット", 1235, _font(28), GOLD)

    out = Path("generated") / f"post-{draft_id:05d}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    image.save(out, "PNG", optimize=True)
    return str(out)


def render_post_image(draft_id, fmt, title, cards=None, event=None):
    cards = cards or []
    if not cards:
        raise ValueError("画像生成に使うカードが指定されていません")
    if fmt == "three_choice":
        main = _render_choice(draft_id, title, cards[:3])
        for label, card in zip("ABC", cards[:3]):
            _render_result(draft_id, label, card)
        return main
    return _render_single(draft_id, fmt, title, cards[0], event)
