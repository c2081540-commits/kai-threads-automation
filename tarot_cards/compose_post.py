#!/usr/bin/env python3
"""Create deterministic choice and result images from the tarot assets."""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = ROOT.parent
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from app.image_maker import render_choice_image, render_result_image


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--cards", help="Comma-separated IDs, e.g. 6,9,12")
    parser.add_argument("--out", default=str(ROOT / "output"))
    args = parser.parse_args()

    cards = json.loads((ROOT / "cards.json").read_text(encoding="utf-8"))
    by_id = {int(card["id"]): card for card in cards}
    if args.cards:
        chosen = [by_id[int(value.strip())] for value in args.cards.split(",")]
        if len(chosen) != 3 or len({int(card["id"]) for card in chosen}) != 3:
            raise ValueError("--cards requires three different card IDs")
    else:
        chosen = random.Random(args.seed).sample(cards, 3)

    output = Path(args.out)
    output.mkdir(parents=True, exist_ok=True)
    render_choice_image(output / "01_choice.png", chosen)
    for label, card in zip("ABC", chosen):
        render_result_image(output / f"result_{label}.png", card)

    manifest = {
        "choice_size": [1080, 608],
        "result_size": [1080, 1350],
        "cards": [
            {"label": label, **card} for label, card in zip("ABC", chosen)
        ],
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
