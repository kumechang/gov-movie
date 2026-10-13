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

## 一覧型（`template: ranked_list`）

「項目＋値」の一覧を順位つきで見せる。実例: [tfr_2024_grid.yaml](../themes/tfr_2024_grid.yaml)（カード一覧）、[tfr_2024_scroll.yaml](../themes/tfr_2024_scroll.yaml)（横スクロール・全47県）、[tfr_2024_steps.yaml](../themes/tfr_2024_steps.yaml)（階段）。
地図テンプレートと同じ項目（`metric` `year` `unit` `source` `verification` `title*` `subtitle` `voice` `hooks` `cta` `post` など）に加えて、次の項目を使う。`focus` `intro_top10` `card_sub*` `legend_title` は不要。

| 項目 | 内容 |
|---|---|
| `layout` | `grid`（3列のカード一覧。最下位から埋まり1位が左上、最大12マス）／`scroll`（カードが右から流れる。最大47件）／`steps`（棒で比べる。最大6件） |
| `n` / `show` | 表示する件数（既定 grid 11 / scroll 47 / steps 5）と、`top`（上位）か `bottom`（下位）か。**同率の途中では切らない**（境界の同率グループは丸ごと外すので、表示件数 `{n}` は減ることがある。警告が出る） |
| `values` / `items` | `values`: 47都道府県の値（e-Stat 取得で埋まる。順位・色は47県全体で決め、カードには都道府県の形が出る）。`items`: `[{name, value, note?}]` を直接書く（都道府県以外。形は出ない）。同時には書けない |
| `value_suffix` | 値のあとに付ける単位の表示（`万円` `人` など。読み上げにも入る） |
| `sub` / `sub_first` | カードの補足文（1位だけ `sub_first`）。`items[].note` があればそれを優先 |
| `grid_note` | grid の余ったマスに出す一言 `{title, lines: [...]}`（省略可） |
| `item_say` | `last`（最初に発表）／`first`（1位）／`top10`（10位以内。grid・steps は全件）／`rest`（scroll の11位以下。無ければ無言で短く流す） |
| `min_total` | 最短の動画長（秒、既定60）。足りなければ各項目の表示時間を均等に延ばす。0で無効 |

文言で使える変数: 全体 `metric` `year` `unit` `n` `first_name`（クライマックスの項目）`last_name`（最初に発表する項目）`gap_text` `avg`（`average` があるとき）／ `sub` `item_say`: `rank` `name` `value`（単位つき）`note` `ratio_last`（最初に発表する項目に対する倍率）`ratio_first` `ratio_avg`。

映像は `src/render_list.py`、音声は `audio.build_list`。プレビュー: `python3 src/render_list.py themes/<id>.yaml still 5,30,50`。

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
- 検証レポート（出典・表題・調査期間・公表日・取得日・単位・確定数/概数・最大/最小/全国値・照合結果）は画面に出て、`build/<id>/fetch_report.txt` と `report.txt` に残る。
- 生の応答は `build/<id>/estat_cache.json` に保存（appId は含まない）。再取得は `--refetch`。取得だけ試す: `python3 src/fetch_estat.py themes/<id>.yaml`。
- 統計表の探し方: `getStatsList`（`searchWord`・`statsCode`）で表IDを探し、`getMetaInfo` で表章項目・地域・時間軸のコードを見る。
- 商用利用: e-Stat は「商用利用も可能」（政府標準利用規約2.0版準拠）。出典の記載と、加工した旨の記載が必要。API を使ったサービスにはクレジット表示（`source.license.credit_lines` に入れる）。確認日 2026-10-07、`https://www.e-stat.go.jp/terms-of-use` と `.../api/api-info/credit`。他の API（市区町村など）を使うときは、その都度規約を確認して記録する。

## 段階ボード（`template: tier_board`）

項目を「段階（レベル）」ごとにまとめて、段階を順に発表する型。レベルの高い段階ほど後ろに置き、最後がクライマックス。
実例: [g20_risk_levels.yaml](../themes/g20_risk_levels.yaml)（G20の18か国の、外務省の危険レベル。恐怖演出つき）

データは `source.fetch: mofa_risk`（外務省 海外安全情報オープンデータ）。`run.py` が取得して検証し、`tier_data` に入れる（`src/mofa.py`）。
- **取得**: 国別XML（全207か国）の `riskLevel1〜4`（＝「そのレベルの**地域を含む**」）から、国ごとの最大レベルを使う。国全体のレベルではないので、画面に「国全体ではなく、その国に含まれる地域のレベルです」と明記する（`footnote`）。
- **2系統目の照合**: 各国の公式の危険情報ページ（HTML）の本文に、その最大レベルが出てくるか。一致した国だけを使い、食い違った国は除外してレポートに残す（実際に、XMLのフラグが古い国が見つかった）。
- キャッシュ `build/mofa_cache.json` は全テーマで共有（既定24時間。古ければ取り直す）。アクセスは1国ずつ間隔を空け、先頭だけ読む（規約の「大量アクセスの禁止」への配慮）。
- 商用可・出典と加工した旨の記載が必要（`source.license` に記録。確認日 2026-10-13）。

| 項目 | 内容 |
|---|---|
| `tiers[]` | `level` `title` `sub` `color` `say`（`{count}` `{level}` `{title}` `{sub}` が使える）。先に出す順に並べる。`names: false` で件数だけ見せる。`spotlight: true` で1か国ずつじっくり見せる |
| `members[]` | 対象の国を絞る（省略すると取得できた全国）。`code`（外務省の国コード。`data/mofa_countries.csv`）`label`（画面の名前）。スポットライトの国は `say`（読み上げ文）が必須 |
| `members[].where` | 最も高いレベルの地域の文言。**公式の「危険レベル」の節にそのまま出てきて、直後のレベル表示が一致すること**を毎回自動で検証する（外れると止まる） |
| `members[].also` | ほかの地域のレベル `[{level, where}]`（同じく検証）。「ロシアはそれ以外も全域レベル3」のような、誤解を防ぐ情報に使う |
| `members[].why` | 何が危ないか `[{tag, text, evidence}]`。`tag` は種類（紛争・武力衝突／テロ／ギャング・凶悪犯罪／誘拐／感染症…）、`evidence` は**公式ページ本文にそのまま出てくる文言**（毎回検証。出てこなければ止まる） |
| `names_note` `footnote` | 件数だけの段階に出す注記／画面下の常設の注記 |

文言の変数: `metric` `year` `asof`（取得日）`total` `n<レベル>`（例 `{n4}`）`n_high`（レベル3以上）`n_any` `excluded_note`。

## 見た目の設定（`style`）と声

一覧型・段階ボードで使える。無ければ標準の見た目（紺色）。恐怖演出の実例は [g20_risk_levels.yaml](../themes/g20_risk_levels.yaml)。

| 項目 | 内容 |
|---|---|
| `look: horror` | 音が、明るい和音ではなく、半音でぶつかる低いうなりと心音になる |
| `fonts` | `Black` `Bold` `Accent`（見せ場用）にフォントファイルを指定。`scripts/setup_fonts.sh` で `assets/fonts/` に置く（Kaisei Tokumin＝筆文字風の明朝、Yuji Boku＝かすれた手書き風。どちらも OFL で商用可）。無ければ標準のフォント |
| `bg` | `top` `bottom`（背景のグラデーション）`fog`（下から立ちのぼる霧の色）`fog_height` `vignette`（四隅の暗さ）`grain`（ざらつき） |
| `text` `muted` `accent` `title_color` `title_glow` `drips` | 文字色・補助色・強調色・タイトルの色・タイトルの光・血の滴り（色） |
| `pill` `panel` `bar` | 上部の丸い枠・フックのパネル・進行バーの配色 |
| `fx` | `shake`（揺れの大きさ）`flash`（色）`flash_alpha`。レベルが明かされる瞬間に1回だけ。点滅の繰り返しはしない |
| `named_colors` | hooks / cta の panel で使う色名（white / yellow / red / muted）の差し替え |

声（`voice`）: `vvm: [n]`（`tts/vv/<n>.vvm` の追加モデル。`scripts/setup_voicevox.sh` の `EXTRA_VVM="1"` で配置）`style_id` `speed` `pitch`（低いほど不穏）`intonation`（小さいほど平坦）`credit`。
1=冥鳴ひまり（style 14・落ち着いた低めの声）、2=九州そら、3=波音リツ・中国うさぎ。話者を変えたら `credit` も必ず変える（冥鳴ひまりは「VOICEVOX:冥鳴ひまり」。商用可・クレジット必須・公序良俗に反しないこと）。

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
