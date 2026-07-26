# 毎週やること

1. 制作専用チャットへ `GPT_WEEKLY_OPERATOR.md` と前週レポートを渡す。
2. 「翌週分を作成」と指示し、完成した `weekly_package.json` を受け取る。
3. GitHubの `data/weekly_package.json` を上書きする。
4. Actions → Threads scheduled dispatch → Run workflow。
5. 実行内容で `validate_week` を選び実行する。
6. 成功後、同じ画面で `prepare_week` を選び実行する。
7. `reports/latest/schedule.md` と生成画像を確認する。
8. 問題がなければRepository variableの `AUTO_PUBLISH` を `true` にする。

`validate_week`と`prepare_week`はThreads APIを呼ばず、投稿もしない。予約時刻の`dispatch`だけが投稿処理を行う。
