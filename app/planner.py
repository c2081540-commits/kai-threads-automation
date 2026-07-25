import hashlib
import json
import math
import random
from pathlib import Path
from datetime import datetime
from difflib import SequenceMatcher
from .db import connect, jdump, log_event
from .events import active_events, next_events
from .market import load_research, write_empty_inbox
from .image_maker import render_post_image
from .safety import check
from .settings import settings

CARD_DATA_PATH = Path(__file__).resolve().parents[1] / "tarot_cards" / "cards.json"


def _load_cards():
    cards = json.loads(CARD_DATA_PATH.read_text(encoding="utf-8"))
    if len(cards) != 22:
        raise RuntimeError(f"大アルカナは22枚必要です。現在: {len(cards)}枚")
    ids = [int(card["id"]) for card in cards]
    if len(set(ids)) != 22:
        raise RuntimeError("cards.jsonに重複したカードIDがあります")
    return cards


CARDS = _load_cards()

TOPICS = {
    "相手の気持ち": ["連絡が来ない彼の本音", "別れたあとも残っている気持ち", "今、彼が言えずにいること"],
    "音信不通": ["音信不通の今、追うべきか待つべきか", "返信がないときに見落としやすいこと", "沈黙が続く二人へのメッセージ"],
    "冷却期間": ["冷却期間に今やるべきこと", "距離を置いている間の注意点", "連絡を再開する前に整えること"],
    "復縁行動": ["復縁を近づける次の一歩", "今送るならどんな連絡か", "復縁を遠ざけやすい行動"],
}

FORMATS = ("three_choice", "one_card", "checklist", "question")
CTA = {
    "comment": "A・B・Cのどれを選んだか、コメントで教えてください。",
    "save": "気持ちが揺れたときに見返せるよう、保存しておいてください。",
    "follow": "復縁に迷ったときの判断材料を、これからも発信します。",
}


def _knowledge(dimension, key):
    with connect() as con:
        row = con.execute(
            "SELECT score,samples FROM knowledge WHERE dimension=? AND key=?",
            (dimension, key),
        ).fetchone()
    return (float(row["score"]), int(row["samples"])) if row else (1.0, 0)


def _choose(items, dimension):
    if random.random() < settings.exploration_rate:
        return random.choice(list(items))
    total_samples = sum(_knowledge(dimension, x)[1] for x in items) + 1
    ranked = []
    for item in items:
        score, samples = _knowledge(dimension, item)
        bonus = math.sqrt(2 * math.log(total_samples + 1) / (samples + 1))
        ranked.append((score + bonus, item))
    return max(ranked)[1]


def _three_choice(topic, title, cards, cta):
    lines = [
        f"【3枚から選ぶ】{title}",
        "",
        "一度深呼吸して、気になるカードを1枚選んでください。",
        "",
    ]
    for label, card in zip(("A", "B", "C"), cards):
        lines.extend([f"{label}｜{card['name_ja']}", card["love"], ""])
    lines.append(cta)
    return "\n".join(lines)


def _one_card(topic, title, card, cta):
    return (
        f"{title}。\n\n"
        f"今日のカードは「{card['name_ja']}」。\n"
        f"{card['love']}\n\n"
        "占いは相手を決めつけるものではなく、次の行動を整理するためのヒントです。\n\n"
        f"{cta}"
    )


def _checklist(topic, title, card, cta):
    return (
        f"{title}。焦る前に3つ確認してください。\n\n"
        "①感情のまま長文を送ろうとしていないか\n"
        "②別れた原因が何も変わっていないままではないか\n"
        "③相手の反応だけで自分の価値を決めていないか\n\n"
        f"「{card['name_ja']}」はこう伝えています。\n{card['love']}\n\n{cta}"
    )


def _question(topic, title, card, cta):
    return (
        f"復縁したい相手に、今すぐ連絡するべき？\n\n"
        f"今回のカードは「{card['name_ja']}」。\n{card['love']}\n\n"
        "連絡するかどうかは、最後のやり取りと別れた原因によって変わります。"
        "あなたは今「追う」「待つ」のどちらで迷っていますか？\n\n"
        f"{cta}"
    )


def _event_post(event, card, cta):
    if event["days_left"] == 0:
        hook = f"今日は{event['name']}。連絡する前に、一度だけ確認してください。"
    else:
        hook = f"{event['name']}まであと{event['days_left']}日。焦って連絡する前に。"
    return (
        f"{hook}\n\n"
        f"「{card['name_ja']}」は、{card['love']}\n\n"
        f"{event['angle']}ことが大切です。\n"
        "記念日だから動くのではなく、今の二人に必要な距離を選んでください。\n\n"
        f"{cta}"
    )


def _market_post(idea, card, cta):
    angle = idea.get("angle") or idea.get("why_now") or "今の状況を落ち着いて整理する"
    return (
        f"{idea['title']}\n\n"
        f"今日のカードは「{card['name_ja']}」。\n{card['love']}\n\n"
        f"今回のポイントは、{angle}こと。\n"
        "相手の気持ちを決めつけず、自分が次に取れる行動へ落とし込んでください。\n\n"
        f"{cta}"
    )


def _similarity(body):
    with connect() as con:
        rows = con.execute("SELECT body FROM drafts ORDER BY id DESC LIMIT 100").fetchall()
    return max((SequenceMatcher(None, body, r["body"]).ratio() for r in rows), default=0)


def _recent_card_sets(limit=100):
    with connect() as con:
        rows = con.execute(
            "SELECT cards_json FROM drafts ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    sets = []
    for row in rows:
        try:
            cards = json.loads(row["cards_json"])
            ids = frozenset(
                int(card["id"]) for card in cards if isinstance(card, dict) and "id" in card
            )
            if ids:
                sets.append(ids)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
    return sets


def _select_cards(count=3):
    recent = _recent_card_sets()
    last = recent[0] if recent else frozenset()
    for _ in range(100):
        chosen = random.sample(CARDS, count)
        chosen_ids = frozenset(int(card["id"]) for card in chosen)
        if chosen_ids in recent:
            continue
        if count == 3 and last and len(chosen_ids & last) > 1:
            continue
        return chosen
    raise RuntimeError("重複しないカードの組み合わせを選定できませんでした")


def plan(seed=None):
    if seed is not None:
        random.seed(seed)
    else:
        random.seed(datetime.now().strftime("%Y-%m-%d"))

    write_empty_inbox()
    events = active_events()
    market = load_research()
    candidate_log = []

    # 大型イベントの指定日は通常ネタより必ず優先する。
    forced_event = next((event for event in events if event["forced"]), None)
    if forced_event:
        cta_type = "save" if forced_event["days_left"] else "comment"
        card = _select_cards(1)[0]
        body = _event_post(forced_event, card, CTA[cta_type])
        quality = check(body)
        quality["similarity"] = round(_similarity(body), 3)
        if quality["passed"] and quality["similarity"] < settings.duplicate_threshold:
            body_hash = hashlib.sha256(body.encode()).hexdigest()
            with connect() as con:
                cur = con.execute(
                    """INSERT INTO drafts(format,topic,hook_type,cta_type,cards_json,body,body_hash,quality_json)
                       VALUES(?,?,?,?,?,?,?,?)""",
                    ("event_countdown", "季節イベント", forced_event["name"], cta_type,
                     jdump([card]), body, body_hash, jdump(quality)),
                )
            image_path = render_post_image(
                cur.lastrowid, "event_countdown", forced_event["name"],
                [card], forced_event,
            )
            with connect() as con:
                con.execute("UPDATE drafts SET image_path=? WHERE id=?", (image_path, cur.lastrowid))
            result = {
                "draft_id": cur.lastrowid, "format": "event_countdown",
                "topic": "季節イベント", "cta": cta_type, "body": body,
                "quality": quality, "event": forced_event,
                "image_path": image_path,
                "top_candidates": [forced_event],
            }
            log_event("draft_created", result)
            return result

    # 市場調査候補を最大10件まで採点対象にする。
    for idea in market[:10]:
        fmt = idea.get("suggested_format", "one_card")
        topic = idea.get("topic", "復縁行動")
        cta_type = _choose(tuple(CTA), "cta")
        performance = _knowledge("topic", topic)[0] + _knowledge("format", fmt)[0]
        candidate_log.append({
            "source": "market", "idea": idea,
            "score": idea["market_score"] + performance * 3,
            "format": fmt, "topic": topic, "cta": cta_type,
        })

    # 中規模イベントも通常候補より高く評価する。
    for event in events:
        if event["forced"]:
            continue
        candidate_log.append({
            "source": "event", "event": event,
            "score": 20 + event["strength"] * 5 - min(event["days_left"], 10),
            "format": "event_countdown", "topic": "季節イベント", "cta": "save",
        })

    # 内蔵候補を補充し、合計30件から選ぶ。
    while len(candidate_log) < 30:
        fmt = _choose(FORMATS, "format")
        topic = _choose(tuple(TOPICS), "topic")
        cta_type = _choose(tuple(CTA), "cta")
        performance = _knowledge("topic", topic)[0] + _knowledge("format", fmt)[0]
        candidate_log.append({
            "source": "internal", "score": performance * 5 + random.random() * 3,
            "format": fmt, "topic": topic, "cta": cta_type,
        })
    candidate_log.sort(key=lambda x: x["score"], reverse=True)

    for candidate in candidate_log:
        fmt = candidate["format"]
        topic = candidate["topic"]
        cta_type = candidate["cta"]
        cards = _select_cards(3)
        if candidate["source"] == "market":
            title = candidate["idea"]["title"]
            body = _market_post(candidate["idea"], cards[0], CTA[cta_type])
        elif candidate["source"] == "event":
            title = candidate["event"]["name"]
            body = _event_post(candidate["event"], cards[0], CTA[cta_type])
        else:
            title = random.choice(TOPICS[topic])
            if fmt == "three_choice":
                body = _three_choice(topic, title, cards, CTA[cta_type])
            elif fmt == "one_card":
                body = _one_card(topic, title, cards[0], CTA[cta_type])
            elif fmt == "checklist":
                body = _checklist(topic, title, cards[0], CTA[cta_type])
            else:
                body = _question(topic, title, cards[0], CTA[cta_type])

        duplicate = _similarity(body)
        quality = check(body)
        quality["similarity"] = round(duplicate, 3)
        if duplicate >= settings.duplicate_threshold:
            continue
        if not quality["passed"]:
            continue
        body_hash = hashlib.sha256(body.encode()).hexdigest()
        with connect() as con:
            cur = con.execute(
                """INSERT INTO drafts(format,topic,hook_type,cta_type,cards_json,body,body_hash,quality_json)
                   VALUES(?,?,?,?,?,?,?,?)""",
                (fmt, topic, title, cta_type, jdump(cards), body, body_hash, jdump(quality)),
            )
        event = candidate.get("event")
        image_path = render_post_image(cur.lastrowid, fmt, title, cards, event)
        with connect() as con:
            con.execute("UPDATE drafts SET image_path=? WHERE id=?", (image_path, cur.lastrowid))
        result = {
            "draft_id": cur.lastrowid,
            "format": fmt,
            "topic": topic,
            "cta": cta_type,
            "body": body,
            "quality": quality,
            "image_path": image_path,
            "source": candidate["source"],
            "top_candidates": candidate_log[:5],
            "upcoming_events": next_events(),
        }
        log_event("draft_created", result)
        return result
    raise RuntimeError("重複しない投稿案を生成できませんでした")
