#!/usr/bin/env bash
# VOICEVOX Core 0.17.0 一式を tts/vv/ に配置し、Python ラッパーを入れる（Linux x86_64）。
# 公式の download ツールは GitHub API を使うため、API が使えない環境ではこのスクリプトでリリース配布物を直接取る。
# 利用規約: tts/vv/TERMS.txt（商用可・クレジット表記必須。話者ごとの規約は各話者の配布元を確認）
set -euo pipefail
cd "$(dirname "$0")/.."
VV=tts/vv
mkdir -p "$VV/ort" "$VV/dic" tts/dl

CORE=https://github.com/VOICEVOX/voicevox_core/releases/download/0.17.0
ORT=https://github.com/VOICEVOX/onnxruntime-builder/releases/download/voicevox_onnxruntime-1.23.2
DIC=https://github.com/r9y9/open_jtalk/releases/download/v1.11.1
VVM=https://github.com/VOICEVOX/voicevox_vvm/releases/download/0.17.0

WHL=voicevox_core-0.17.0-cp310-abi3-manylinux_2_34_x86_64.whl
curl -fsSL -o "tts/dl/$WHL" "$CORE/$WHL"
curl -fsSL -o tts/dl/ort.tgz "$ORT/voicevox_onnxruntime-linux-x64-1.23.2.tgz"
curl -fsSL -o tts/dl/dic.tar.gz "$DIC/open_jtalk_dic_utf_8-1.11.tar.gz"
curl -fsSL -o "$VV/0.vvm" "$VVM/0.vvm"
curl -fsSL -o "$VV/TERMS.txt" "$VVM/TERMS.txt"
tar xzf tts/dl/ort.tgz -C "$VV/ort"
tar xzf tts/dl/dic.tar.gz -C "$VV/dic"
python3 -m pip install -q "tts/dl/$WHL"
python3 -c "import voicevox_core; print('voicevox_core OK')"
echo "配置完了: $VV （規約: $VV/TERMS.txt）"
