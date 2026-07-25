from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class RomanceEvent:
    key: str
    name: str
    month: int
    day: int
    strength: int
    countdown_days: tuple[int, ...]
    angle: str


# strength=3 は大型イベント。指定日にカウントダウン投稿を強制的に候補上位へ入れる。
EVENTS = (
    RomanceEvent(
        "new_year", "元日", 1, 1, 3, (14, 7, 3, 2, 1),
        "新しい年を、過去と同じ関係の繰り返しにしないための行動を整理する",
    ),
    RomanceEvent(
        "valentine", "バレンタイン", 2, 14, 3, (14, 7, 5, 3, 2, 1),
        "当日までに連絡するか、待つか、何を整えるかを考える",
    ),
    RomanceEvent(
        "white_day", "ホワイトデー", 3, 14, 3, (7, 5, 3, 2, 1),
        "相手の反応を決めつけず、期待と現実を整理する",
    ),
    RomanceEvent(
        "new_life", "新生活", 4, 1, 2, (7, 3, 1),
        "環境が変わる時期に、復縁の連絡を急ぐべきか整理する",
    ),
    RomanceEvent(
        "golden_week", "ゴールデンウィーク", 5, 3, 2, (7, 3, 1),
        "連休を口実に連絡する前に、自然な距離感を考える",
    ),
    RomanceEvent(
        "tanabata", "七夕", 7, 7, 3, (7, 5, 3, 2, 1),
        "願うだけでなく、復縁に必要な現実的な一歩を選ぶ",
    ),
    RomanceEvent(
        "obon", "お盆休み", 8, 13, 2, (7, 3, 1),
        "帰省や休暇で思い出す相手に連絡するか整理する",
    ),
    RomanceEvent(
        "halloween", "ハロウィン", 10, 31, 1, (3, 1),
        "季節の話題を、重くならない連絡のきっかけにできるか考える",
    ),
    RomanceEvent(
        "christmas_eve", "クリスマスイブ", 12, 24, 3, (21, 14, 10, 7, 5, 3, 2, 1),
        "当日への焦りで衝動的に動かず、連絡と距離感を整理する",
    ),
    RomanceEvent(
        "new_year_eve", "大晦日", 12, 31, 3, (14, 7, 5, 3, 2, 1),
        "年内に連絡するか、新年まで待つかを整理する",
    ),
)


def _target(event: RomanceEvent, today: date) -> date:
    target = date(today.year, event.month, event.day)
    if target < today:
        target = date(today.year + 1, event.month, event.day)
    return target


def active_events(today: date | None = None) -> list[dict]:
    today = today or date.today()
    active = []
    for event in EVENTS:
        target = _target(event, today)
        days_left = (target - today).days
        if days_left == 0 or days_left in event.countdown_days:
            active.append({
                "key": event.key,
                "name": event.name,
                "date": target.isoformat(),
                "days_left": days_left,
                "strength": event.strength,
                "angle": event.angle,
                "forced": event.strength == 3,
            })
    return sorted(active, key=lambda x: (-x["strength"], x["days_left"]))


def next_events(today: date | None = None, limit: int = 5) -> list[dict]:
    today = today or date.today()
    upcoming = []
    for event in EVENTS:
        target = _target(event, today)
        upcoming.append({
            "key": event.key,
            "name": event.name,
            "date": target.isoformat(),
            "days_left": (target - today).days,
            "strength": event.strength,
        })
    return sorted(upcoming, key=lambda x: x["days_left"])[:limit]
