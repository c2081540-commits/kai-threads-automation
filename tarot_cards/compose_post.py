#!/usr/bin/env python3
"""Create deterministic 4:5 three-choice and result images from the tarot assets."""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent
SIZE = (1080, 1350)
BG = "#071217"
GOLD = "#D8B76A"
IVORY = "#F3EBDD"
MUTED = "#B9B2A4"


def font_path(explicit: str | None) -> str:
    candidates = [
        explicit,
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
        "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    raise FileNotFoundError("Japanese font not found. Pass --font /path/to/font.ttc")


def load_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def fit_text(draw: ImageDraw.ImageDraw, text: str, path: str, max_width: int, start: int) -> ImageFont.FreeTypeFont:
    size = start
    while size > 24:
        font = load_font(path, size)
        if draw.textbbox((0, 0), text, font=font)[2] <= max_width:
            return font
        size -= 2
    return load_font(path, size)


def card_path(card: dict) -> Path:
    return ROOT / f"{card['id']:02d}_{card['slug']}.png"


def rounded_card(source: Path, size: tuple[int, int]) -> Image.Image:
    image = Image.open(source).convert("RGB")
    image.thumbnail(size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    x = (size[0] - image.width) // 2
    y = (size[1] - image.height) // 2
    canvas.paste(image, (x, y))
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=22, fill=255)
    canvas.putalpha(mask)
    return canvas


def base_canvas() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", SIZE, BG)
    draw = ImageDraw.Draw(image)
    draw.rectangle((20, 20, 1059, 1329), outline=GOLD, width=3)
    draw.rectangle((31, 31, 1048, 1318), outline="#5D4A25", width=1)
    return image, draw


def draw_centered(draw: ImageDraw.ImageDraw, y: int, text: str, font: ImageFont.FreeTypeFont, fill: str) -> None:
    box = draw.textbbox((0, 0), text, font=font)
    draw.text(((SIZE[0] - (box[2] - box[0])) / 2, y), text, font=font, fill=fill)


def create_choice(cards: list[dict], title: str, subtitle: str, out: Path, font: str) -> None:
    image, draw = base_canvas()
    title_font = fit_text(draw, title, font, 920, 70)
    draw_centered(draw, 72, title, title_font, IVORY)
    draw_centered(draw, 164, subtitle, load_font(font, 35), MUTED)

    card_w, card_h = 286, 429
    gap = 37
    start_x = (SIZE[0] - card_w * 3 - gap * 2) // 2
    top = 325
    label_font = load_font(font, 58)

    for i, card in enumerate(cards):
        x = start_x + i * (card_w + gap)
        art = rounded_card(card_path(card), (card_w, card_h))
        # Dark veil hides card identity while retaining visual richness.
        veil = Image.new("RGBA", art.size, (2, 9, 13, 105))
        art = Image.alpha_composite(art, veil)
        image.paste(art, (x, top), art)
        draw.rounded_rectangle((x - 3, top - 3, x + card_w + 2, top + card_h + 2), radius=23, outline=GOLD, width=3)
        label = "ABC"[i]
        box = draw.textbbox((0, 0), label, font=label_font)
        draw.text((x + (card_w - box[2]) / 2, top + card_h + 35), label, font=label_font, fill=GOLD)

    draw_centered(draw, 965, "直感で1枚選んでください", load_font(font, 47), IVORY)
    draw_centered(draw, 1050, "結果は次の画像へ", load_font(font, 32), MUTED)
    draw_centered(draw, 1228, "Kai 復縁タロット", load_font(font, 28), GOLD)
    image.save(out, quality=95)


def wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, width: int) -> list[str]:
    lines, current = [], ""
    for char in text:
        trial = current + char
        if draw.textbbox((0, 0), trial, font=font)[2] <= width:
            current = trial
        else:
            lines.append(current)
            current = char
    if current:
        lines.append(current)
    return lines


def create_result(card: dict, label: str, out: Path, font: str) -> None:
    image, draw = base_canvas()
    draw_centered(draw, 62, f"{label}を選んだあなたへ", load_font(font, 56), IVORY)

    art = rounded_card(card_path(card), (365, 548))
    image.paste(art, (72, 200), art)
    draw.rounded_rectangle((69, 197, 439, 751), radius=25, outline=GOLD, width=3)

    draw.text((500, 220), card["name_ja"], font=load_font(font, 62), fill=GOLD)
    keywords = "・".join(card["keywords"])
    for index, line in enumerate(wrap(draw, keywords, load_font(font, 33), 490)):
        draw.text((500, 310 + index * 48), line, font=load_font(font, 33), fill=MUTED)

    body_font = load_font(font, 41)
    body_lines = wrap(draw, card["love"], body_font, 500)
    y = 455
    for line in body_lines:
        draw.text((500, y), line, font=body_font, fill=IVORY)
        y += 62

    draw.line((75, 850, 1005, 850), fill="#5D4A25", width=2)
    draw_centered(draw, 905, "今日の行動", load_font(font, 38), GOLD)
    action = {
        2: "不安から連絡せず、まず事実を整理する",
        9: "相手の時間を尊重し、自分の生活を整える",
        12: "今は結論を急がず、見方を変えてみる",
        15: "連絡したい衝動を一晩置いて見直す",
        18: "想像ではなく、確認できる事実だけを見る",
    }.get(card["id"], "焦らず、できる小さな行動を一つ選ぶ")
    for index, line in enumerate(wrap(draw, action, load_font(font, 38), 850)):
        draw_centered(draw, 975 + index * 58, line, load_font(font, 38), IVORY)

    draw_centered(draw, 1228, "Kai 復縁タロット", load_font(font, 28), GOLD)
    image.save(out, quality=95)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--title", default="連絡が来ない彼の本音")
    parser.add_argument("--subtitle", default="今のあなたに必要なメッセージ")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--cards", help="Comma-separated IDs, e.g. 6,9,12")
    parser.add_argument("--font")
    parser.add_argument("--out", default=str(ROOT / "output"))
    args = parser.parse_args()

    cards = json.loads((ROOT / "cards.json").read_text(encoding="utf-8"))
    by_id = {card["id"]: card for card in cards}
    if args.cards:
        chosen = [by_id[int(value)] for value in args.cards.split(",")]
        if len(chosen) != 3 or len({card["id"] for card in chosen}) != 3:
            raise ValueError("--cards requires three different card IDs")
    else:
        rng = random.Random(args.seed)
        chosen = rng.sample(cards, 3)

    output = Path(args.out)
    output.mkdir(parents=True, exist_ok=True)
    font = font_path(args.font)
    create_choice(chosen, args.title, args.subtitle, output / "01_choice.png", font)
    for label, card in zip("ABC", chosen):
        create_result(card, label, output / f"result_{label}.png", font)

    manifest = {"title": args.title, "cards": [{"label": label, **card} for label, card in zip("ABC", chosen)]}
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
