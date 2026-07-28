import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


WIDTH = 1080
CHOICE_HEIGHT = 608
RESULT_HEIGHT = 1350
BG = "#071217"
GOLD = "#D8B76A"
CARD_DIR = Path(__file__).resolve().parents[1] / "tarot_cards"
FONT_CANDIDATES = (
    os.getenv("FONT_PATH", ""),
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansJP-Bold.ttf",
    "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
    "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
)


def _font(size):
    for candidate in FONT_CANDIDATES:
        if candidate and Path(candidate).is_file():
            return ImageFont.truetype(candidate, size)
    raise RuntimeError(
        "表示用フォントがありません。GitHub Actionsではfonts-noto-cjkを"
        "インストールするか、FONT_PATHを設定してください。"
    )


def _canvas(height):
    image = Image.new("RGB", (WIDTH, height), BG)
    draw = ImageDraw.Draw(image)
    return image, draw


def _card_art(card, size):
    source = CARD_DIR / f"{int(card['id']):02d}_{card['slug']}.png"
    if not source.is_file():
        raise FileNotFoundError(f"タロットカード画像がありません: {source}")
    with Image.open(source) as raw:
        canvas = raw.convert("RGB")
    canvas.thumbnail(size, Image.Resampling.LANCZOS)
    output = Image.new("RGB", size, BG)
    x = (size[0] - canvas.width) // 2
    y = (size[1] - canvas.height) // 2
    output.paste(canvas, (x, y))
    return output


def _paste_card(image, draw, card, xy, size):
    x, y = xy
    art = _card_art(card, size)
    image.paste(art, (x, y))
    draw.rounded_rectangle(
        (x - 4, y - 4, x + size[0] + 3, y + size[1] + 3),
        radius=18,
        outline=GOLD,
        width=4,
    )


def render_choice_image(path, cards):
    if len(cards) != 3 or len({int(card["id"]) for card in cards}) != 3:
        raise ValueError("3択画像には異なるカードが3枚必要です")
    image, draw = _canvas(CHOICE_HEIGHT)
    card_w, card_h = 341, 511
    gap = 14
    start_x = (WIDTH - card_w * 3 - gap * 2) // 2
    # Keep labels outside the artwork so they never cover a card character.
    top = 76
    label_y = 41
    label_radius = 22
    for index, card in enumerate(cards):
        card_x = start_x + index * (card_w + gap)
        _paste_card(
            image,
            draw,
            card,
            (card_x, top),
            (card_w, card_h),
        )
        label_x = card_x + card_w // 2
        draw.ellipse(
            (
                label_x - label_radius,
                label_y - label_radius,
                label_x + label_radius,
                label_y + label_radius,
            ),
            fill=BG,
            outline=GOLD,
            width=3,
        )
        draw.text(
            (label_x, label_y - 1),
            "ABC"[index],
            font=_font(36),
            fill=GOLD,
            anchor="mm",
        )
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp.png")
    image.save(temporary, "PNG", optimize=True)
    with Image.open(temporary) as check:
        check.load()
        if check.size != (WIDTH, CHOICE_HEIGHT):
            raise RuntimeError(f"3択画像の寸法が不正です: {check.size}")
    temporary.replace(target)
    return str(target)


def render_result_image(path, card):
    image, draw = _canvas(RESULT_HEIGHT)
    card_w, card_h = 620, 930
    _paste_card(
        image,
        draw,
        card,
        ((WIDTH - card_w) // 2, (RESULT_HEIGHT - card_h) // 2),
        (card_w, card_h),
    )
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp.png")
    image.save(temporary, "PNG", optimize=True)
    with Image.open(temporary) as check:
        check.load()
        if check.size != (WIDTH, RESULT_HEIGHT):
            raise RuntimeError(f"結果画像の寸法が不正です: {check.size}")
    temporary.replace(target)
    return str(target)


def render_post_image(
    draft_id,
    fmt,
    title,
    cards=None,
    event=None,
    image_copy=None,
):
    cards = cards or []
    if fmt != "three_choice":
        return None
    main = Path("generated") / f"post-{draft_id:05d}.png"
    render_choice_image(main, cards[:3])
    for label, card in zip("ABC", cards[:3]):
        result = Path("generated") / f"post-{draft_id:05d}-result-{label}.png"
        render_result_image(result, card)
    return str(main)
