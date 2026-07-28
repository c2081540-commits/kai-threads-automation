import json
from pathlib import Path

from PIL import Image

from app.image_maker import render_choice_image, render_result_image


ROOT = Path(__file__).resolve().parents[1]
CARD_DIR = ROOT / "tarot_cards"


def _cards():
    return json.loads((CARD_DIR / "cards.json").read_text(encoding="utf-8"))


def test_choice_and_result_dimensions(tmp_path, monkeypatch):
    monkeypatch.setattr("app.image_maker.CARD_DIR", CARD_DIR)
    cards = _cards()[:3]
    choice = tmp_path / "choice.png"
    result = tmp_path / "result.png"

    render_choice_image(choice, cards)
    render_result_image(result, cards[0])

    with Image.open(choice) as image:
        assert image.size == (1080, 608)
    with Image.open(result) as image:
        assert image.size == (1080, 1350)


def test_choice_requires_three_distinct_cards(tmp_path, monkeypatch):
    monkeypatch.setattr("app.image_maker.CARD_DIR", CARD_DIR)
    cards = _cards()
    duplicate = [cards[0], cards[0], cards[1]]

    try:
        render_choice_image(tmp_path / "choice.png", duplicate)
    except ValueError:
        return
    raise AssertionError("duplicate cards must be rejected")


def test_choice_labels_are_above_card_art(tmp_path, monkeypatch):
    monkeypatch.setattr("app.image_maker.CARD_DIR", CARD_DIR)
    choice = tmp_path / "choice.png"
    render_choice_image(choice, _cards()[:3])

    # The label center/badge ends above y=63; card artwork starts at y=76.
    # This guards against moving A/B/C back onto the card artwork.
    with Image.open(choice) as image:
        assert image.getpixel((180, 41)) != image.getpixel((180, 76))


def test_images_have_no_outer_frame_and_are_fully_readable(tmp_path, monkeypatch):
    monkeypatch.setattr("app.image_maker.CARD_DIR", CARD_DIR)
    choice = tmp_path / "choice.png"
    result = tmp_path / "result.png"
    cards = _cards()[:3]
    render_choice_image(choice, cards)
    render_result_image(result, cards[0])

    for path, expected_size in (
        (choice, (1080, 608)),
        (result, (1080, 1350)),
    ):
        with Image.open(path) as image:
            image.load()
            assert image.size == expected_size
            assert image.getpixel((12, 12)) == image.getpixel((0, 0))
