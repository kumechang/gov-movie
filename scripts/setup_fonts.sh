#!/usr/bin/env bash
# 演出用の日本語フォント（Google Fonts・SIL Open Font License。商用利用可・クレジット不要）を assets/fonts/ に置く。
# テーマの style.fonts から参照する。無いときは標準の Noto Sans CJK に戻る。
#   KaiseiTokumin-ExtraBold … 太い筆文字風の明朝（恐怖演出の見出し）
#   YujiBoku-Regular        … かすれた手書き風（「？」などの見せ場）
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p assets/fonts
BASE=https://raw.githubusercontent.com/google/fonts/main/ofl
curl -fsSL -o assets/fonts/KaiseiTokumin-ExtraBold.ttf "$BASE/kaiseitokumin/KaiseiTokumin-ExtraBold.ttf"
curl -fsSL -o assets/fonts/YujiBoku-Regular.ttf "$BASE/yujiboku/YujiBoku-Regular.ttf"
echo "配置完了: assets/fonts/"
