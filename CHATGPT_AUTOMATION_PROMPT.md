# 毎日18時の市場調査タスク

以下をChatGPTの自動タスクとして毎日実行する。

```text
「Kai｜復縁タロット」のThreads投稿候補を調査してください。

目的：
当日21時に動くGitHub Actionsが、調査候補と過去投稿成績から1件を選び、
Threadsへ投稿できる状態にする。

毎回行うこと：
1. 日本のThreads、検索トレンド、恋愛相談で現在需要がある話題を調査する。
2. 復縁、音信不通、冷却期間、相手の気持ちに直接関係する候補だけ残す。
3. 日付、曜日、季節、連休、記念日、年末年始を必ず確認する。
4. バレンタイン、ホワイトデー、七夕、クリスマス、元日、大晦日など
   恋愛需要が強い日は、当日だけでなくカウントダウン候補も入れる。
5. 「必ず復縁」「○時間以内に連絡」「いいねで願いが叶う」など、
   未来保証や不安を煽る案は除外する。
6. 過去の research_inbox.json と post_history.csv を確認し、
   類似・重複テーマを避ける。
7. 最低10件、最大30件を採点する。
8. 結果をリポジトリの data/research_inbox.json へ保存する。

JSON形式：
{
  "generated_at": "YYYY-MM-DDTHH:MM:SS+09:00",
  "candidates": [
    {
      "title": "投稿テーマ",
      "topic": "相手の気持ち|音信不通|冷却期間|復縁行動",
      "angle": "投稿の切り口",
      "why_now": "今扱う理由",
      "suggested_format": "three_choice|one_card|checklist|question",
      "urgency": 0,
      "demand": 0,
      "comment_potential": 0,
      "discovered_at": "YYYY-MM-DD",
      "expires_at": "YYYY-MM-DD",
      "source_urls": ["確認したURL"]
    }
  ]
}

重要：
- source_urlsは実際に確認したページだけを記録する。
- SNS上の主張を事実として扱わない。
- 調査結果が弱い日は、無理に時事ネタを作らず普遍テーマを候補にする。
- GitHubへの保存が成功した場合だけ完了とする。
```
