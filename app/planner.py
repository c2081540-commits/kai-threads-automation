import hashlib
import json
import math
import random
from datetime import datetime
from difflib import SequenceMatcher
from .db import connect, jdump, log_event
from .events import active_events, next_events
from .market import load_research, write_empty_inbox
from .image_maker import render_post_image
from .safety import check
from .settings import settings

CARDS = [
    ("愚者", "まだ形は決まっていません。思い込みを手放すと関係が動きやすくなります。"),
    ("魔術師", "連絡を再開するきっかけを作れる時期です。短く自然な言葉が向いています。"),
    ("女教皇", "相手は感情を表に出していません。今は答えを急がず、静かに状況を見る段階です。"),
    ("女帝", "好意や安心感は残っています。結論を迫るより、穏やかな接点を育てる方が有効です。"),
    ("皇帝", "相手は自分のペースを守りたい状態です。追いかけすぎると距離を置かれやすくなります。"),
    ("恋人", "気持ちが完全に消えたとは限りません。ただし曖昧な関係をどう選び直すかが鍵です。"),
    ("戦車", "停滞を破る行動力が出ています。ただし感情の勢いだけで長文を送らないでください。"),
    ("隠者", "相手は一人で考える時間を必要としています。沈黙を拒絶と決めつけないことが大切です。"),
    ("運命の輪", "関係を見直す転機が近づいています。以前と同じ接し方を繰り返さないことが重要です。"),
    ("正義", "復縁には感情だけでなく、別れた原因の整理が必要です。公平に二人の問題を見直してください。"),
    ("吊るされた男", "今すぐ動かすより、見方を変える時間です。待つことにも意味があります。"),
    ("死神", "以前と同じ関係には戻れません。復縁するなら、新しい関係として作り直す必要があります。"),
    ("節制", "少しずつ距離を戻す流れです。挨拶や短いやり取りから始めるのが向いています。"),
    ("悪魔", "執着や不安が判断を曇らせています。相手の反応だけで一日を決めないようにしてください。"),
    ("塔", "予想外の変化を示します。衝動的な連絡より、まず状況を受け止めることが先です。"),
    ("星", "関係を立て直す希望はあります。期待だけでなく、自分の生活も整えておきましょう。"),
    ("月", "相手の本音が見えにくく、不安が膨らみやすい状態です。推測を事実として扱わないでください。"),
    ("太陽", "素直なコミュニケーションが助けになります。重い確認より、明るく短い接点が向いています。"),
    ("審判", "過去の関係を見直す機会です。謝罪や反省を伝えるなら、言い訳を混ぜないことが大切です。"),
    ("世界", "一つの区切りが見えています。復縁だけに固執せず、自分が納得できる結末を選べます。"),
]

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
    for label, (name, meaning) in zip(("A", "B", "C"), cards):
        lines.extend([f"{label}｜{name}", meaning, ""])
    lines.append(cta)
    return "\n".join(lines)


def _one_card(topic, title, card, cta):
    name, meaning = card
    return (
        f"{title}。\n\n"
        f"今日のカードは「{name}」。\n"
        f"{meaning}\n\n"
        "占いは相手を決めつけるものではなく、次の行動を整理するためのヒントです。\n\n"
        f"{cta}"
    )


def _checklist(topic, title, card, cta):
    name, meaning = card
    return (
        f"{title}。焦る前に3つ確認してください。\n\n"
        "①感情のまま長文を送ろうとしていないか\n"
        "②別れた原因が何も変わっていないままではないか\n"
        "③相手の反応だけで自分の価値を決めていないか\n\n"
        f"「{name}」はこう伝えています。\n{meaning}\n\n{cta}"
    )


def _question(topic, title, card, cta):
    name, meaning = card
    return (
        f"復縁したい相手に、今すぐ連絡するべき？\n\n"
        f"今回のカードは「{name}」。\n{meaning}\n\n"
        "連絡するかどうかは、最後のやり取りと別れた原因によって変わります。"
        "あなたは今「追う」「待つ」のどちらで迷っていますか？\n\n"
        f"{cta}"
    )


def _event_post(event, card, cta):
    name, meaning = card
    if event["days_left"] == 0:
        hook = f"今日は{event['name']}。連絡する前に、一度だけ確認してください。"
    else:
        hook = f"{event['name']}まであと{event['days_left']}日。焦って連絡する前に。"
    return (
        f"{hook}\n\n"
        f"「{name}」は、{meaning}\n\n"
        f"{event['angle']}ことが大切です。\n"
        "記念日だから動くのではなく、今の二人に必要な距離を選んでください。\n\n"
        f"{cta}"
    )


def _market_post(idea, card, cta):
    name, meaning = card
    angle = idea.get("angle") or idea.get("why_now") or "今の状況を落ち着いて整理する"
    return (
        f"{idea['title']}\n\n"
        f"今日のカードは「{name}」。\n{meaning}\n\n"
        f"今回のポイントは、{angle}こと。\n"
        "相手の気持ちを決めつけず、自分が次に取れる行動へ落とし込んでください。\n\n"
        f"{cta}"
    )


def _similarity(body):
    with connect() as con:
        rows = con.execute("SELECT body FROM drafts ORDER BY id DESC LIMIT 100").fetchall()
    return max((SequenceMatcher(None, body, r["body"]).ratio() for r in rows), default=0)


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
        card = random.choice(CARDS)
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
        cards = random.sample(CARDS, 3)
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
