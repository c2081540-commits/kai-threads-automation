# Kai 復縁タロット画像素材

大アルカナ22枚と、Threads／Instagram向け4:5投稿画像を固定生成するスクリプトです。

## 実行

```bash
python compose_post.py --cards 6,9,12 --title "連絡が来ない彼の本音"
```

カード指定を省略するとランダムで3枚を選びます。再現可能にする場合は `--seed 20260725` を指定します。

出力:

- `output/01_choice.png`
- `output/result_A.png`
- `output/result_B.png`
- `output/result_C.png`
- `output/manifest.json`

GitHub ActionsのUbuntu環境では先に `fonts-noto-cjk` をインストールしてください。Macではヒラギノ角ゴシックを自動検出します。
