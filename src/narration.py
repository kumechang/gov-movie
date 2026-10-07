import glob, json, os, wave, hashlib
from voicevox_core.blocking import Onnxruntime, OpenJtalk, Synthesizer, VoiceModelFile
import common

VV = '../tts/vv'  # VOICEVOX一式の置き場所（HANDOFF.md 参照）
STYLE = 2          # 四国めたん ノーマル
SPEED = 1.28
ort = Onnxruntime.load_once(filename=glob.glob(VV + '/ort/*/lib/libvoicevox_onnxruntime.so.1.23.2')[0])
syn = Synthesizer(ort, OpenJtalk(glob.glob(VV + '/dic/open_jtalk_dic_utf_8-*')[0]))
with VoiceModelFile.open(VV + '/0.vvm') as m:
    syn.load_voice_model(m)
os.makedirs('narr', exist_ok=True)
out = {}
for key, text in common.narration_lines().items():
    q = syn.create_audio_query(text, STYLE)
    q.speed_scale = SPEED
    q.pre_phoneme_length = 0.05
    q.post_phoneme_length = 0.12
    wav = syn.synthesis(q, STYLE)
    fn = 'narr/%s.wav' % hashlib.md5(key.encode()).hexdigest()[:10]
    open(fn, 'wb').write(wav)
    with wave.open(fn) as w:
        dur = w.getnframes() / w.getframerate()
    out[key] = dict(file=fn, dur=round(dur, 3), text=text, kana=q.kana)
    print('%-14s %5.2fs  %s' % (key, dur, q.kana))
json.dump(out, open('narration.json', 'w'), ensure_ascii=False, indent=1)
