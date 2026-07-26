# 毎週やること

1. 制作専用チャットで前週データを分析し、翌週21投稿を作る。
2. 本文、画像内文章、3択結果をこのチャットで修正する。
3. GPTから完成済みの`weekly_package.json`と`generated/`を含むZIPを受け取る。
4. ZIPの中身をGitHubへアップロードする。
5. Actions → Threads scheduled dispatch → Run workflow。
6. 実行内容で`install_week`を選び実行する。
7. 成功後、投稿待ちデータとして登録される。
8. 初回確認後、Repository variableの`AUTO_PUBLISH`を`true`にする。

`install_week`は原稿と完成画像の存在を検査して登録するだけで、
Threads APIを呼ばず、画像も生成しない。予約時刻の`dispatch`だけが投稿する。
