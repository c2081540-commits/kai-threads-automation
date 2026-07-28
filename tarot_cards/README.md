# Kai 復縁タロット画像素材

大アルカナ22枚と、投稿画像を固定生成するためのデータを置くフォルダです。

## 現在の画像仕様

- 3択の親画像：1080×608
- A・B・Cの結果画像：1080×1350
- 元カードの縦横比は変更しない
- 親画像では3枚を同じ縮尺で横並びにする
- A・B・Cは各カードの外側・真上へ表示し、カード絵柄には重ねない
- 画像全体を囲む外周枠は入れない
- 親画像にタイトル、案内文、結果文は入れない
- 結果画像に説明文は入れず、返信本文で説明する

## 実行

リポジトリ直下から実行します。

```bash
python tarot_cards/compose_post.py --cards 6,9,12
```

カード指定を省略するとランダムで3枚を選びます。再現可能にする場合は
`--seed 20260725`を指定します。

出力：

- `tarot_cards/output/01_choice.png`
- `tarot_cards/output/result_A.png`
- `tarot_cards/output/result_B.png`
- `tarot_cards/output/result_C.png`
- `tarot_cards/output/manifest.json`

GitHub ActionsのUbuntu環境では`fonts-noto-cjk`をインストールしてください。
Macではヒラギノ角ゴシックを自動検出します。
