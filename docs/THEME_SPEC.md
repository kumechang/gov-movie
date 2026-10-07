# テーマ定義ファイル仕様

1本の動画 = `themes/<id>.yaml` 1ファイル。動画・音声・投稿文はすべてここから作られる。
実例: [themes/divorce_rate_2024.yaml](../themes/divorce_rate_2024.yaml)（コメントつき）

## 実行

```
python3 src/run.py themes/<id>.yaml              # 検証→地図→ナレーション→音声→映像→音量調整→投稿文
python3 src/run.py themes/<id>.yaml --no-voice   # VOICEVOXなしのプレビュー
python3 src/run.py themes/<id>.yaml --check      # 検証レポートだけ
python3 -m unittest discover -s tests            # テスト
```

成果物は `build/<id>/`（`final.mp4`, `post.md`, `report.txt`）。`build/` は git 管理外。

## 項目

| 項目 | 必須 | 内容 |
|---|---|---|
| `id` | ○ | 出力先名 |
| `metric` / `year` / `unit` | ○ | 指標名・年・正式な単位 |
| `decimals` | | 表示・読み上げ・同率判定の小数桁（既定2）。値はこの桁に丸めて順位づけする |
| `average` | ○（estat なら省略可） | 全国値。最小〜最大の範囲外なら読み込みエラー（年次・単位の取り違え検出） |
| `rank_order` | | `desc`（大きいほど1位、既定）/ `asc` |
| `source.name` / `note` / `table` / `url` / `fetch` | name○ | 出典。`url` が空だと警告が出る。`fetch` は `manual` / `estat` |
| `source.license` | estat なら推奨 | 利用条件の確認記録。`commercial: true` と `credit_lines`（概要欄に入る出典・加工の表記）が無いと警告 |
| `estat` | fetch: estat なら○ | e-Stat の取得定義（下の「e-Stat 取得」） |
| `verification` | ○ | 検証方法の記録。空だと読み込みエラー（検証できていない数字は載せない） |
| `values` | ○（estat なら省略可） | 47都道府県の値（`東京` でも `東京都` でも可。欠け・重複・数値以外はエラー） |
| `tiers.thresholds` / `colors` | | 色の境界値（昇順）。`auto` で5分位。colors は省略可 |
| `title` `title_small` `subtitle` `legend_title` | ○ | 画面の固定文言（長いタイトルは自動で縮む） |
| `card_sub` `card_sub_first` `card_sub_last` | ○ | カード下段の文言（通常 / 1位 / 最下位） |
| `voice.style_id` `speed` `credit` | | VOICEVOX の話者・速さ・クレジット（動画フッターと概要欄に入る） |
| `hooks[]` | ○ | 冒頭。`say`=読み上げ、`panel`=画面文字、`min`/`gap`=最短秒数/余白、`y`=位置、`fade`=出現秒数 |
| `intro_top10` | ○ | TOP10 の区切り |
| `item_say.last/first/top10` | ○ | 最下位 / 1位 / TOP10 の読み上げ文 |
| `focus` | | 最後に注目する県（省略可）。`name` `say` `panel` |
| `cta` | ○ | コメント誘導・注意書き |
| `post` | | 投稿用テキスト（タイトル・概要欄・固定コメント・ハッシュタグ） |

`panel` の各行は `[文字, サイズ, 色, 太さ]`。色は `white / yellow / red / muted`、太さは `Regular / Medium / Bold / Black`。

## e-Stat 取得（`source.fetch: estat`）

`values` / `average` を書かず `estat:` を書くと、`run.py` が e-Stat から47都道府県＋全国値を取って検証し、動画にする。
実例: [themes/tfr_2024.yaml](../themes/tfr_2024.yaml)（値なし）、[themes/divorce_rate_2024.yaml](../themes/divorce_rate_2024.yaml)（値あり＝検証済みの期待値と突き合わせ）

```yaml
estat:
  statsDataId: "0003411598"                      # 統計表ID（e-Stat の表のURLの statdisp_id）
  unit: ""                                       # 任意。e-Stat 側の単位表記が unit と違うとき（単位のない指標は ""）
  select: {cdTab: "10060", cdTime: "2024000000"} # 絞り込み。各都道府県が1値になるまで絞る
  cross:                                         # 2系統目の照合（任意・複数可）
    - {label: ..., statsDataId: ..., select: {...}}                                       # 別の表の同じ指標（丸めた値が全件一致）
    - {label: ..., numerator: {statsDataId: .., select: ..}, denominator: {...}, scale: 1000}  # 件数÷人口などの再計算（丸め誤差の範囲で一致）
```

- 取得時に確認すること: 時点が `year` と一致／単位が一致／47県＋全国が揃い、1地域1値／欠損記号（`-` `…`）なし／全国値が最小〜最大の範囲内／（あれば）YAML の `values` `average` と一致／`cross` と一致。1つでも外れると**止まる**（動画にしない）。
- 検証レポート（出典・表題・調査期間・公表日・取得日・単位・確定数/概数・最大/最小/全国値・照合結果）は画面に出て、`build/<id>/estat_report.txt` と `report.txt` に残る。
- 生の応答は `build/<id>/estat_cache.json` に保存（appId は含まない）。再取得は `--refetch`。取得だけ試す: `python3 src/fetch_estat.py themes/<id>.yaml`。
- 統計表の探し方: `getStatsList`（`searchWord`・`statsCode`）で表IDを探し、`getMetaInfo` で表章項目・地域・時間軸のコードを見る。
- 商用利用: e-Stat は「商用利用も可能」（政府標準利用規約2.0版準拠）。出典の記載と、加工した旨の記載が必要。API を使ったサービスにはクレジット表示（`source.license.credit_lines` に入れる）。確認日 2026-10-07、`https://www.e-stat.go.jp/terms-of-use` と `.../api/api-info/credit`。他の API（市区町村など）を使うときは、その都度規約を確認して記録する。

## 文言で使える変数 `{...}`

全体: `metric` `year` `unit` `avg` `first_name`（1位の県）`last_name`（最下位の県）
`gap_text`（最大÷最小。「約2倍」など）`last_vs_first`（「1位の約半分」など）

`item_say` / `card_sub*`: `rank` `name` `value` `ratio_avg`（値÷全国値）

`focus` 使用時: `focus` `focus_rank` `focus_value` `focus_tie`（同率の県）
`focus_say`（「ほぼ全国平均です」/「全国平均より高め・低めです」）`focus_cmp`

未定義の変数を書くと読み込み時にエラーになる。

## 注意

- 読み上げは VOICEVOX が数字を誤読することがある（「1.55」が「ごーごー」など）。聞いて確認し、文を言い換える。
- 読み上げ文を変えたら `run.py` を通しでやり直す（時間割が音声の長さに依存する）。
- 文言の中に指標固有の言い回し（「離婚の背景は人それぞれ」など）を入れるのはテーマ側の責任。差別・決めつけに見えないか確認する。
