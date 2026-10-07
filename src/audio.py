import numpy as np, wave
from common import *
SR = 44100
n = int((T_END + 0.5) * SR)
L = np.zeros(n); R = np.zeros(n)
def add(sig, t0, pan=0.0, gain=1.0):
    i = int(t0 * SR)
    if i >= n: return
    sig = sig[: n - i]
    L[i:i+len(sig)] += sig * gain * (1 - max(0, pan))
    R[i:i+len(sig)] += sig * gain * (1 + min(0, pan))
def tone(f, dur, decay, amp=1.0, harm=(1.0, 0.3, 0.1)):
    t = np.arange(int(dur * SR)) / SR
    s = sum(h * np.sin(2 * np.pi * f * (k + 1) * t) for k, h in enumerate(harm))
    return s * np.exp(-t * decay) * amp * np.minimum(1, t * 400)
def noise_sweep(dur, f0, f1, amp):
    t = np.arange(int(dur * SR)) / SR
    rng = np.random.default_rng(1)
    x = rng.standard_normal(len(t))
    # 簡易ローパス（移動平均を周波数で変える代わりに複数帯域をクロスフェード）
    k = max(2, int(SR / f1)); y = np.convolve(x, np.ones(k) / k, 'same')
    env = np.sin(np.pi * np.clip(t / dur, 0, 1)) ** 2
    return y * env * amp * 6
# 背景パッド
t = np.arange(n) / SR
pad = sum(a * np.sin(2 * np.pi * f * t + p) for f, a, p in [(110, 0.5, 0), (164.8, 0.35, 1), (220, 0.3, 2), (277.2, 0.15, 3)])
pad *= (0.8 + 0.2 * np.sin(2 * np.pi * 0.12 * t)) * 0.045
pad *= np.minimum(1, t / 1.5) * np.minimum(1, (T_END + 0.5 - t) / 1.5)
L += pad; R += pad
# フック
add(noise_sweep(0.9, 300, 3000, 0.25), 0.0, 0, 1)
add(tone(220, 0.6, 5, 0.3), 0.2); add(tone(330, 0.5, 6, 0.2), 0.45)
add(tone(98, 0.9, 4, 0.5, (1, 0.2)), HOOK_SEGS[1]['start']); add(noise_sweep(0.5, 500, 4000, 0.2), HOOK_SEGS[1]['start'] - 0.3)
add(tone(98, 0.9, 4, 0.5, (1, 0.2)), HOOK_SEGS[2]['start'])
add(noise_sweep(1.0, 300, 5000, 0.28), HOOK_SEGS[2]['start'] + 0.1)
# カウントダウン
for i, it in enumerate(SEQ):
    prog = i / (len(SEQ) - 1)
    f = 300 * 2 ** (prog * 1.4)
    pan = ((i % 2) * 2 - 1) * 0.25
    add(tone(f, 0.16, 22, 0.42, (1, 0.35, 0.12)), it['start'], pan)
    add(tone(f / 2, 0.22, 18, 0.18, (1, 0.2)), it['start'], pan)
    if it['rank'] <= 10:
        add(tone(70, 0.5, 7, 0.55, (1, 0.15)), it['start'])
        add(tone(f * 1.5, 0.3, 12, 0.18), it['start'] + 0.05, -pan)
    if it['rank'] == 1:
        add(tone(55, 2.2, 1.6, 0.9, (1, 0.2)), it['start'])
        for fx in (261.6, 329.6, 392.0, 523.3):
            add(tone(fx, 2.8, 1.5, 0.28, (1, 0.4, 0.15)), it['start'] + 0.02)
        add(noise_sweep(0.8, 800, 6000, 0.3), it['start'] - 0.2)
# 東京
t1 = T_COUNT_END
add(tone(440, 0.4, 8, 0.3), t1 + 0.05); add(tone(554, 0.5, 8, 0.3), t1 + 0.18)
# CTA
t2 = T_COUNT_END + T_TOKYO
for k, fx in enumerate((523.3, 659.3, 784.0, 1046.5)):
    add(tone(fx, 1.0, 4, 0.3), t2 + 0.1 + k * 0.12, ((k % 2) * 2 - 1) * 0.3)
add(tone(130.8, 2.5, 1.3, 0.5, (1, 0.2)), t2 + 0.1)
# ---- 効果音を控えめにし、読み上げを重ねる ----
import json
NJ = json.load(open('narration.json'))
V = np.zeros(n)
def load_narr(key):
    w = wave.open(NJ[key]['file']); sr = w.getframerate(); ch = w.getnchannels(); raw = w.readframes(w.getnframes()); w.close()
    x = np.frombuffer(raw, dtype=np.int16).astype(np.float64) / 32768
    if ch == 2: x = x.reshape(-1, 2).mean(1)
    n2 = int(len(x) * SR / sr)
    y = np.interp(np.linspace(0, len(x) - 1, n2), np.arange(len(x)), x)
    return y / (np.abs(y).max() + 1e-9) * 0.9
def voice(key, t0):
    y = load_narr(key); i = int(t0 * SR); y = y[: n - i]; V[i:i + len(y)] += y
for sg in HOOK_SEGS: voice(sg['key'], sg['start'] + 0.12)
if INTER: voice('intro10', INTER['start'] + 0.1)
for it in SEQ:
    if it.get('key'): voice(it['key'], it['start'] + 0.08)
voice('tokyo', T_COUNT_END + 0.15)
voice('cta', T_COUNT_END + T_TOKYO + 0.25)
sfx_peak = max(np.abs(L).max(), np.abs(R).max())
k = 0.38 / sfx_peak
L = L * k + V; R = R * k + V
m = max(np.abs(L).max(), np.abs(R).max())
g = 0.85 / m
st = (np.stack([L, R], 1) * g * 32767).astype(np.int16)
with wave.open('audio.wav', 'wb') as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(st.tobytes())
print('audio ok', n / SR, 's peak gain', g)
