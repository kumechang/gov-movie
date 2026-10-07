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
| `average` | ○ | 全国値。最小〜最大の範囲外なら読み込みエラー（年次・単位の取り違え検出） |
| `rank_order` | | `desc`（大きいほど1位、既定）/ `asc` |
| `source.name` / `note` / `table` / `url` / `fetch` | name○ | 出典。`url` が空だと警告が出る |
| `verification` | ○ | 検証方法の記録。空だと読み込みエラー（検証できていない数字は載せない） |
| `values` | ○ | 47都道府県の値（`東京` でも `東京都` でも可。欠け・重複・数値以外はエラー） |
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
