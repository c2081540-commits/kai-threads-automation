# Kai 復縁タロット：Threads自動運用システム

無料で試験運用するための最小構成です。OpenAI APIなどの有料AIは使用しません。

毎日、次の処理を一巡させます。

1. 18時間以上経過した未評価投稿のインサイトを取得
2. ChatGPTが保存した当日の市場調査候補を読み込む
3. 日付イベントとカウントダウン対象を確認
4. 投稿形式・テーマ・CTAごとの成績を更新
5. 市場候補・日付・過去成績を加味して30候補を採点
6. 過去100案との類似度を調べて重複を排除
7. 誇大・不安を煽る表現を品質ゲートで排除
8. 最上位の投稿案と4:5画像を作成
9. 画像を公開してからThreadsへ本文と画像を投稿
10. SQLiteとCSVに履歴・評価を保存

## 投稿形式

- 3枚から選ぶタロット：A・B・Cのカード画像
- 1枚引き：中央にカード1枚
- 復縁行動チェックリスト：タイトルと3項目
- 「追う・待つ」を問う参加型投稿：タイトルとカード
- 強い日：イベント名とカウントダウン

テーマは「相手の気持ち」「音信不通」「冷却期間」「復縁行動」です。
男性心理はアカウントの主軸にしていません。

## 無料運用の構成

- 実行：GitHub Actions
- 投稿・数値取得：Threads API
- データ：SQLite + CSV
- 文章生成：内蔵テンプレートとタロットカード解釈
- 有料AI API：不使用

GitHub Actionsは毎日21:00（日本時間）に起動する設定です。GitHubの混雑時は開始が遅れる場合があります。

市場調査はChatGPTの自動タスクを毎日18:00に起動し、
`data/research_inbox.json` を更新する構成です。設定用の完全な指示は
`CHATGPT_AUTOMATION_PROMPT.md` にあります。

## 日付イベント

毎日、投稿選定前にイベントカレンダーを確認します。

- 元日
- バレンタイン
- ホワイトデー
- 新生活
- ゴールデンウィーク
- 七夕
- お盆休み
- ハロウィン
- クリスマスイブ
- 大晦日

特に強いイベントは、当日だけでなく14日前、7日前、5日前、3日前、
2日前、前日など、イベントごとに設定した日程でカウントダウン候補を
通常投稿より優先します。

## まずローカルで確認

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m app.cli init
python -m app.cli plan --seed 100
python -m app.cli pending
```

この段階では投稿されません。

## コマンド

```bash
# 投稿案を1件作る
python -m app.cli plan

# 未投稿案を確認
python -m app.cli pending

# 指定した案を手動投稿
python -m app.cli publish 1

# 18時間以上経過した未評価投稿を分析
python -m app.cli analyze

# 分析→企画→必要なら投稿→CSV出力
python -m app.cli cycle

# 履歴CSVを再出力
python -m app.cli export
```

## GitHubで必要な設定

リポジトリの `Settings → Secrets and variables → Actions` に設定します。

### Secrets

- `THREADS_USER_ID`
- `THREADS_ACCESS_TOKEN`

### Variables

- `THREADS_API_VERSION`：通常は `v1.0`
- `AUTO_PUBLISH`：最初は `false`

初回はActions画面から `Threads daily cycle` を手動実行し、投稿案と履歴だけ生成されることを確認します。
問題がなければ `AUTO_PUBLISH` を `true` に変更します。

## リポジトリをPublicにする理由

Threads APIへ画像を添付するには、Meta側から取得できる公開画像URLが必要です。
この最小構成では、Actionsが生成したPNGを同じPublicリポジトリへ保存し、
`raw.githubusercontent.com` のURLをThreads APIへ渡します。

アクセストークンはGitHub Secretsにだけ保存されるため、Publicリポジトリでも
コード上には表示されません。ただし投稿履歴や公開インサイトの集計は
リポジトリから見えるため、非公開にしたい場合は別途画像ホスティングが必要です。

## Threads API側で必要なもの

Meta for DevelopersでThreads API用アプリを作成し、対象アカウントについて投稿とインサイト取得ができるアクセストークンを発行します。認証情報はコードやCSVへ書かず、GitHub Secretsだけに保存してください。

## 評価方法

投稿後18時間以上経過した時点で一度評価します。

```text
評価値 =
  いいね率
  + 返信率 × 4
  + シェア系率 × 5
```

フォロワー0人から始めるため、再生数の絶対値だけではなく反応率を重視します。蓄積された評価は次回以降の投稿形式・テーマ・CTA選択に反映されます。

## データ

- `data/tarot_growth.db`：全履歴、評価、学習重み
- `data/post_history.csv`：人間が確認しやすい最新集計
- `data/analysis_report.md`：強い形式・テーマ・CTAと上位投稿
- `data/research_inbox.json`：毎日の市場調査から得た投稿候補

過去本文も保存するため、重複投稿を抑制できます。

## 安全装置

次のような表現は自動的に却下します。

- 「必ず復縁できる」
- 「○時間以内に連絡が来る」
- 「いいねすると願いが叶う」
- 「スキップすると二度とない」
- 波動、呪いなどで不安を煽る表現

このシステムは、相手の行動や未来を事実として保証しません。占いを行動整理のヒントとして扱います。
