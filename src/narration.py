"""テーマの読み上げ文を VOICEVOX で音声化し、narration.json に長さ・読みを書き出す。
使い方: python3 narration.py <theme.yaml> [out_dir]    （out_dir 既定: build/<theme id>）
VOICEVOX 一式の置き場所: 環境変数 VOICEVOX_DIR（既定 ../tts/vv）に ort/, dic/, 0.vvm を置く（docs/HANDOFF.md 5.2）。
"""
import glob, hashlib, json, os, sys, wave

import theme

HERE = os.path.dirname(os.path.abspath(__file__))


def find_onnxruntime(vv):
    from voicevox_core.blocking import Onnxruntime
    want = getattr(Onnxruntime, 'LIB_VERSIONED_FILENAME', None)
    files = sorted(glob.glob(vv + '/ort/**/libvoicevox_onnxruntime*', recursive=True))
    for f in files:
        if want and os.path.basename(f) == want:
            return f
    if not files:
        raise SystemExit('onnxruntime が見つかりません: %s/ort/ 以下に配置してください' % vv)
    return files[0]


def synthesize(T, out_dir, vv):
    from voicevox_core.blocking import Onnxruntime, OpenJtalk, Synthesizer, VoiceModelFile
    style = int(T.voice.get('style_id', 2))
    speed = float(T.voice.get('speed', 1.28))
    ort = Onnxruntime.load_once(filename=find_onnxruntime(vv))
    syn = Synthesizer(ort, OpenJtalk(glob.glob(vv + '/dic/open_jtalk_dic_utf_8-*')[0]))
    with VoiceModelFile.open(vv + '/0.vvm') as m:
        syn.load_voice_model(m)
    os.makedirs(os.path.join(out_dir, 'narr'), exist_ok=True)
    out = {}
    for key, text in T.narration_lines().items():
        q = syn.create_audio_query(text, style)
        q.speed_scale = speed
        q.pre_phoneme_length = 0.05
        q.post_phoneme_length = 0.12
        wav = syn.synthesis(q, style)
        fn = 'narr/%s.wav' % hashlib.md5(key.encode()).hexdigest()[:10]   # out_dir からの相対パス
        open(os.path.join(out_dir, fn), 'wb').write(wav)
        with wave.open(os.path.join(out_dir, fn)) as w:
            dur = w.getnframes() / w.getframerate()
        out[key] = dict(file=fn, dur=round(dur, 3), text=text, kana=q.kana)
        print('%-14s %5.2fs  %s' % (key, dur, q.kana))
    json.dump(out, open(os.path.join(out_dir, 'narration.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)


if __name__ == '__main__':
    T = theme.load(sys.argv[1])
    out_dir = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, '..', 'build', T.id)
    os.makedirs(out_dir, exist_ok=True)
    synthesize(T, out_dir, os.environ.get('VOICEVOX_DIR', os.path.join(HERE, '..', 'tts', 'vv')))
