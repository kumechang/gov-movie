# gov-movie

政府の公開データから「都道府県ランキング」などの TikTok ショート動画（1080×1920、60秒以上）を自動生成するプロジェクト。
経緯・技術詳細は [docs/HANDOFF.md](docs/HANDOFF.md)（チャットでの試作からの引き継ぎ資料）、
テーマ定義の書き方は [docs/THEME_SPEC.md](docs/THEME_SPEC.md)、今後の計画は [docs/ROADMAP.md](docs/ROADMAP.md)。

**新しいセッションは [docs/NEXT_SESSION.md](docs/NEXT_SESSION.md)（環境の立ち上げ手順・次の作業・appId の扱い）から読むこと。**

## 作業ルール

- ユーザーは動画制作のノウハウがなく、手を動かしたくない。調査・データ取得・台本・映像・音声・書き出しまで自動で完結させる。ユーザーに頼むのは TikTok への投稿・アカウント操作・判断が必要な選択だけ。
- 返答は日本語で簡潔に。途中経過を細かく報告せず、できたものを渡す。
- 細かい見た目の修正は後回し。まず量産の型を固める。
- **検証できていない数字を動画に載せない。** 出典URL・年・単位・読み取り方法を記録し、可能なら2系統で照合する。最大/最小/全国平均の妥当性をコードで確認する。画面とナレーションには「出典：〇〇（年）」を入れる。
- 政府データは使う前に商用利用可否と出典表記ルールを確認する（再生数収益は商用）。
- TikTok への自動投稿はしない（アカウント停止リスク）。投稿用の概要欄・固定コメント案までを生成する（`post.md`）。
- 差別・決めつけに見える表現を避ける。
- VOICEVOX のクレジット表記（動画内＋概要欄）を必ず入れる。話者を変えたら表記も変える（`voice.credit`）。

## 使い方

```
python3 src/run.py themes/<id>.yaml              # 検証→地図→ナレーション→音声→映像→音量調整→投稿文
python3 src/run.py themes/<id>.yaml --no-voice   # VOICEVOXなしのプレビュー
python3 src/fetch_estat.py themes/<id>.yaml      # e-Stat 取得と検証レポートだけ（--refetch で取り直し）
python3 -m unittest discover -s tests            # テスト
```

- 新しい動画 = `themes/` に YAML を足すだけ。`src/` にテーマ固有の文言を書かない。
- 成果物は `build/<id>/`（git 管理外）。`narration.json` は読み上げ文と一致するときだけ長さを使い、違えば見積もりに切り替わる。
- 環境依存: フォントは `FONT_PATH`（`render.py` 冒頭）、VOICEVOX は `VOICEVOX_DIR`（既定 `tts/vv`、`narration.py`）。
  macOS のフォント候補は未検証。VOICEVOX の配置は `scripts/setup_voicevox.sh`（Linux x86_64 用。Mac は配布物名を差し替える）。

## 現状

- 離婚率（2024）で、元の動画と静止画がピクセル単位で一致することを確認済み（テンプレ化の回帰確認）。
- e-Stat からのデータ取得は実装済み（`src/fetch_estat.py`）。`source.fetch: estat` のテーマは、取得・検証（年・単位・欠損・全国値・2系統照合）が通らないと動画にしない。
- 未実装: 地図なしテンプレ（市区町村・業種・企業など）、台本→統計表の選択（ROADMAP 3）。
- **e-Stat の appId（環境変数 `ESTAT_APP_ID`）はコード・YAML・ドキュメント・コミット・ログに書かない。** URL や例外をそのまま表示しない（`estat.redact()` を通す）。
- VOICEVOX は `scripts/setup_voicevox.sh` で配置できる（このクラウド環境で動作確認済み。公式 download ツールは GitHub API が使えず失敗するため、配布物を直接取得する）。
- e-Stat API（api.e-stat.go.jp）はこの環境から届く。appId は環境変数 `ESTAT_APP_ID`。
