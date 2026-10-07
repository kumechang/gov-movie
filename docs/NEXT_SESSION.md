# 次のセッションへの引き継ぎ（2026-10-07 時点）

まず [CLAUDE.md](../CLAUDE.md)（作業ルール・使い方）を読むこと。経緯は [HANDOFF.md](HANDOFF.md)、計画は [ROADMAP.md](ROADMAP.md)、テーマの書き方は [THEME_SPEC.md](THEME_SPEC.md)。

## 現状

- 1層目（テーマ定義 YAML → 動画・投稿文まで1コマンド）は完了。
- 2層目（e-Stat からのデータ取得）は**完了**（2026-10-07）。`src/estat.py`（appId を伏せるクライアント）、`src/fetch_estat.py`（取得・検証・照合）。使い方は [THEME_SPEC.md](THEME_SPEC.md) の「e-Stat 取得」。
  - 離婚率2024: e-Stat の値が、手で読み取った検証済みの47件・全国値と**全件一致**。別表（人口動態総覧）の離婚率とも一致、離婚件数÷人口の再計算とも整合。
  - 2本目 `themes/tfr_2024.yaml`（合計特殊出生率2024、`values` なし＝e-Stat から取得）。別表と全件一致。`--no-voice` のプレビュー動画（88秒）まで確認。音声つきの通し（VOICEVOX）と読み（kana）の確認は未了。
  - 商用利用: e-Stat は商用可・出典記載と加工した旨の記載が必要・API利用のクレジット表示あり。`source.license.credit_lines` として概要欄（post.md）に自動で入る。
- 3層目（台本→統計の選択。人が OK/NG を返す形）と、地図なしテンプレが次。
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

## 次にやること（ROADMAP 3層目ほか）

1. `tfr_2024` を VOICEVOX 付きで通し実行し、`narration.json` の kana で誤読を確認（「0.96」「1.54」の読み、「合計特殊出生率」）。必要なら文を言い換える。
2. 3本目以降のテーマ候補（e-Stat で47都道府県の値が取れ、最新年があるもの）。賃金構造基本統計調査は e-Stat 上で2023年までのため最新年の動画には不向き（年を明記して使うなら可）。「社会・人口統計体系」（statsCode 00200502）など、最新年のある指標を探す。ペルソナ別（35歳主婦／32歳営業職／35歳建築職人）に「みんな気になる」もの（地域差・職業・お金・暮らし）。
3. 台本→統計表の選択（`getStatsList` で候補を探し、取得定義と文言案を作って、人が OK/NG を返す）。統計表の取り違えが数字の事故になるため、取得後の検証レポートを必ず見せる。
4. 地図なしテンプレ（市区町村・業種など）。

## 未解決の確認事項（ユーザー待ち）

- （解消）離婚率の出典URLは e-Stat の統計表ページ（statdisp_id=0003411861）に差し替えた。元の NIPSSR 表12-32 の値と一致することは確認済み。
- ナレーションの聞こえ方（読み間違い・音量・間）。読み（kana）に誤読は見当たらないが、人の耳での確認は未了。ユーザーに動画を渡してあるので感想を聞く。
- 声・速さの好み（四国めたん／ずんだもん／男性声など）。
- TikTok のクリエイターリワード条件は変わりうる。量産前に公式ヘルプで再確認する。

## 未検証

- macOS でのフォント（`render.py` の候補）と VOICEVOX 配置（スクリプトは Linux x86_64 用）。
- 市区町村・業種などの地図なしテンプレは未実装。
