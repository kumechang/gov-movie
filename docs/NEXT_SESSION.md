# 次のセッションへの引き継ぎ（2026-10-07 時点）

まず [CLAUDE.md](../CLAUDE.md)（作業ルール・使い方）を読むこと。経緯は [HANDOFF.md](HANDOFF.md)、計画は [ROADMAP.md](ROADMAP.md)、テーマの書き方は [THEME_SPEC.md](THEME_SPEC.md)。

## 現状

- 1層目（テーマ定義 YAML → 動画・投稿文まで1コマンド）: 完了。地図ランキング（`prefecture_map`）に加えて、**一覧型（`ranked_list`: grid / scroll / steps）**を実装（2026-10-12）。使い方は [THEME_SPEC.md](THEME_SPEC.md)。
- 2層目（e-Stat 取得）: 完了。離婚率・合計特殊出生率で2系統照合済み。
- 動画の型の整理（ユーザーが集めた15本の分類、国のデータの候補、作る順番）は [FORMATS.md](FORMATS.md)。**まずここを読む。**
- デモ: `themes/tfr_2024_grid.yaml`（カード一覧、音声つきで通し実行まで確認。読み（kana）に誤読なし）、`tfr_2024_scroll.yaml`（全47県の横スクロール）、`tfr_2024_steps.yaml`（階段）。scroll と steps は静止画で見た目を確認済み、音声つきの通しは未実施。
- ブランチ: `claude/dreamy-bell-rwvipw`（PR は未作成。ユーザーが頼むまで作らない）。

## 新しいコンテナの立ち上げ手順

`build/`（地図・生成物）と `tts/`（VOICEVOX）は git 管理外なので、新しい環境では作り直す。

```
pip install -r requirements.txt
apt-get update && apt-get install -y fonts-noto-cjk     # 日本語フォント（IPAゴシックだけでも動くが太さが出ない）
bash scripts/setup_voicevox.sh                          # VOICEVOX 一式を tts/vv に配置
python3 -m unittest discover -s tests                   # テストが全部通ること
python3 src/run.py themes/divorce_rate_2024.yaml        # 通し実行（地図データは初回に自動ダウンロード）
```

## 環境で分かっていること

- `api.e-stat.go.jp` と `www.e-stat.go.jp` は届く。appId が必要。
- 環境変数名は **`ESTAT_APP_ID`**（ユーザーが環境設定に登録済み。新しいセッションから読めるはず。`[ -n "$ESTAT_APP_ID" ]` で有無だけ確認し、値は表示しない）。
- github.com の配布物（リリースアセット）は直接 URL なら取れる。GitHub API（api.github.com）は使えない。公式 VOICEVOX の download ツールは API を使うため失敗する。
- 他のリポジトリを見たいときは `add_repo` を使う（「ネットワーク制限」ではなくセッションへの紐づけの問題だった）。

## appId の扱い（重要）

- appId をコード・YAML・ドキュメント・コミットメッセージに書かない。環境変数 `ESTAT_APP_ID` からだけ読む。
- 前のセッションで appId をチャットに貼ってしまい、コマンドに直接書こうとして権限の仕組みに拒否された。迂回しない。ユーザーが再発行して差し替える可能性がある。
- e-Stat API は appId を URL のクエリで送る。**URL・例外メッセージ・ログをそのまま表示しない**（取得コードでは appId を伏せてから出力する）。

## 次にやること

優先順位と理由は [FORMATS.md](FORMATS.md)。

1. **一覧型の拡張**: 都道府県以外の軸（役職別・学歴別・年齢別など）を e-Stat から取る。`fetch_estat.py` の地域軸を一般化し、`items` を取得結果で埋める。階段・カードで「役職別の月給」型の動画を作る（賃金構造基本統計調査は e-Stat 上で2023年まで。年を明記して使う）。
2. **外務省の海外安全情報**の取得層 →「世界の危険度ランキング」（世界地図の国境データが要る。取得日を動画に入れる）。
3. **国土地理院の年代別空中写真** →「同じ場所の変遷」。動画に画像として使う場合の利用条件を最終確認する。
4. 推移の棒グラフ（時系列型）。5. EDINET（企業プロフィール）。API キーが必要なはずなので、そのときユーザーに発行を頼む。
6. Tier（段階表）の見せ方（一覧型の layout に追加。根拠のあるデータの区分に限る）。
7. 台本→統計表の選択（ROADMAP 3層目。人が OK/NG を返す形）。

## 未解決の確認事項（ユーザー待ち）

- （解消）離婚率の出典URLは e-Stat の統計表ページ（statdisp_id=0003411861）に差し替えた。元の NIPSSR 表12-32 の値と一致することは確認済み。
- ナレーションの聞こえ方（読み間違い・音量・間）。読み（kana）に誤読は見当たらないが、人の耳での確認は未了。ユーザーに動画を渡してあるので感想を聞く。
- 声・速さの好み（四国めたん／ずんだもん／男性声など）。
- TikTok のクリエイターリワード条件は変わりうる。量産前に公式ヘルプで再確認する。

## 未検証

- macOS でのフォント（`render.py` の候補）と VOICEVOX 配置（スクリプトは Linux x86_64 用）。
- 市区町村・業種などの地図なしテンプレは未実装。
