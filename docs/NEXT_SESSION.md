# 次のセッションへの引き継ぎ（2026-10-07 時点）

まず [CLAUDE.md](../CLAUDE.md)（作業ルール・使い方）を読むこと。経緯は [HANDOFF.md](HANDOFF.md)、計画は [ROADMAP.md](ROADMAP.md)、テーマの書き方は [THEME_SPEC.md](THEME_SPEC.md)。

## 現状

- 1層目（テーマ YAML → 動画・投稿文まで1コマンド）: 完了。型は3つ: 地図ランキング（`prefecture_map`）、一覧型（`ranked_list`: grid / scroll / steps）、段階ボード（`tier_board`）。書き方は [THEME_SPEC.md](THEME_SPEC.md)。
- 2層目（データ取得）: e-Stat（離婚率・合計特殊出生率）、外務省 海外安全情報オープンデータ（危険レベル）。どちらも2系統照合つき。
- 動画の型の整理・国のデータの候補・作る順番・外務省データでの作り直しの経緯は [FORMATS.md](FORMATS.md)。**まずここを読む。**
- 最新の動画: `themes/g20_risk_levels.yaml`（G20の危険レベル。恐怖演出）。ユーザーに動画を渡してあり、感想待ち。長さは105.7秒（スポットライトの読み上げが各7〜9秒、CTAが13秒。短くするなら say を詰めるか speed を上げる）。
- 恐怖演出の素材: フォントは `bash scripts/setup_fonts.sh`、声は `EXTRA_VVM="1" bash scripts/setup_voicevox.sh`（冥鳴ひまり。「VOICEVOX:冥鳴ひまり」のクレジットが必要）。
- ブランチ: `claude/dreamy-bell-rwvipw`（PR #1 はマージ済み。続きの変更は新しい PR。ユーザーが頼むまで作らない）。

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

1. G20の動画へのユーザーの感想を聞き、直す（長さ・声・演出の強さ・理由の見せ方）。
2. 「何が危ないか」を軸にした別の動画（紛争・テロ・ギャング・感染症）。例: 「レベル4の地域を含む国」の理由別の分類、感染症（マラリアなど）。感染症は元データ（外務省の感染症危険情報／検疫所FORTH）の利用条件と取得方法を先に確認する。
3. 一覧型を都道府県以外の軸（役職別・学歴別の賃金など）に広げる（e-Stat の賃金構造基本統計調査は2023年まで）。
4. 国土地理院の年代別空中写真 →「同じ場所の変遷」。5. 推移の棒グラフ。6. EDINET（企業プロフィール）。
7. 台本→統計表の選択（ROADMAP 3層目）。

## 未解決の確認事項（ユーザー待ち）

- （解消）離婚率の出典URLは e-Stat の統計表ページ（statdisp_id=0003411861）に差し替えた。元の NIPSSR 表12-32 の値と一致することは確認済み。
- ナレーションの聞こえ方（読み間違い・音量・間）。読み（kana）に誤読は見当たらないが、人の耳での確認は未了。ユーザーに動画を渡してあるので感想を聞く。
- 声・速さの好み（四国めたん／ずんだもん／男性声など）。
- TikTok のクリエイターリワード条件は変わりうる。量産前に公式ヘルプで再確認する。

## 未検証

- macOS でのフォント（`render.py` の候補）と VOICEVOX 配置（スクリプトは Linux x86_64 用）。
- 市区町村・業種などの地図なしテンプレは未実装。
