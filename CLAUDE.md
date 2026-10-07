# gov-movie

政府の公開データから「都道府県ランキング」などの TikTok ショート動画（1080×1920、60秒以上）を自動生成するプロジェクト。
経緯・技術詳細・TODO は [docs/HANDOFF.md](docs/HANDOFF.md)（チャットでの試作からの引き継ぎ資料）を参照。

## 作業ルール

- ユーザーは動画制作のノウハウがなく、手を動かしたくない。調査・データ取得・台本・映像・音声・書き出しまで自動で完結させる。ユーザーに頼むのは TikTok への投稿・アカウント操作・判断が必要な選択だけ。
- 返答は日本語で簡潔に。途中経過を細かく報告せず、できたものを渡す。
- 細かい見た目の修正は後回し。まず量産の型を固める。
- **検証できていない数字を動画に載せない。** 出典URL・年・単位・読み取り方法を記録し、可能なら2系統で照合する。最大/最小/全国平均の妥当性をコードで確認する。画面とナレーションには「出典：〇〇（年）」を入れる。
- 政府データは使う前に商用利用可否と出典表記ルールを確認する（再生数収益は商用）。
- TikTok への自動投稿はしない（アカウント停止リスク）。投稿用の概要欄・固定コメント案までを生成する。
- 差別・決めつけに見える表現を避ける。
- VOICEVOX のクレジット表記（動画内＋概要欄）を必ず入れる。話者を変えたら表記も変える。

## パイプライン（`src/` 内で実行）

```
python3 geo.py          # 初回のみ。ne_admin1.geojson が必要
python3 narration.py    # VOICEVOX 環境で実行 → narr/*.wav, narration.json
python3 common.py       # 時間割と検証値の確認
python3 audio.py        # → audio.wav
python3 render.py out.mp4 audio.wav
ffmpeg -i out.mp4 -c:v copy -af loudnorm=I=-16:TP=-1.5:LRA=11 -c:a aac -b:a 160k final.mp4
```

読み上げ文を変えたら必ず `narration.py` → `audio.py` → `render.py` をやり直す（時間割が `narration.json` の長さに依存するため）。

## 現状と次の課題

- 現状は `common.py` / `render.py` が離婚率に直書き。次の最重要課題は、テーマ入力（YAML/CSV/JSON）を差し替えるだけで動画ができるテンプレ化（HANDOFF 7.2）。
- `render.py` のフォントパスと `narration.py` の onnxruntime パスは環境依存（HANDOFF 5 参照）。
