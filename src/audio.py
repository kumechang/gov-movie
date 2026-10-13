"""効果音の合成＋ナレーション配置 → audio.wav
使い方: python3 audio.py <theme.yaml> [out_dir] [--no-voice]
"""
import json, os, sys, wave

import numpy as np

import theme

HERE = os.path.dirname(os.path.abspath(__file__))
SR = 44100


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


def _pad(T, n):
    """背景パッド（両チャンネル共通）"""
    t = np.arange(n) / SR
    pad = sum(a * np.sin(2 * np.pi * f * t + p) for f, a, p in [(110, 0.5, 0), (164.8, 0.35, 1), (220, 0.3, 2), (277.2, 0.15, 3)])
    pad *= (0.8 + 0.2 * np.sin(2 * np.pi * 0.12 * t)) * 0.045
    pad *= np.minimum(1, t / 1.5) * np.minimum(1, (T.T_END + 0.5 - t) / 1.5)
    return pad


def _horror_bed(T, n):
    """不穏な背景: 半音でぶつかる低いうなり ＋ 次第に速くなる心音。左右同じ音を返す"""
    t = np.arange(n) / SR
    drone = sum(a * np.sin(2 * np.pi * f * t + p) for f, a, p in [(55.0, 0.6, 0), (58.27, 0.55, 1.3), (110.0, 0.25, 2), (116.54, 0.22, 0.7), (164.8, 0.08, 2.1)])
    drone *= (0.75 + 0.25 * np.sin(2 * np.pi * 0.07 * t)) * 0.08
    drone *= np.minimum(1, t / 1.5) * np.minimum(1, (T.T_END + 0.5 - t) / 2.0)
    beat = np.zeros(n)
    tt, i = 0.4, 0
    while tt < T.T_END:
        prog = tt / T.T_END
        g = 0.5 + 0.5 * prog                                   # 後半ほど強く
        for off, amp in ((0.0, 1.0), (0.2, 0.7)):             # 「ドクッ、ドッ」
            x = tone(58, 0.35, 11, 0.55 * g * amp, (1, 0.5))
            k = int((tt + off) * SR)
            if k < n:
                beat[k:k + len(x)] += x[: n - k]
        tt += 1.15 - 0.45 * prog                              # 1.15秒 → 0.7秒間隔へ
        i += 1
    return drone + beat


def _voice(T, out_dir, n, cues):
    """cues: [(キー, 開始秒)] の読み上げを narration.json の音声から重ねる"""
    V = np.zeros(n)
    NJ = json.load(open(os.path.join(out_dir, 'narration.json'), encoding='utf-8'))

    def load_narr(key):
        w = wave.open(os.path.join(out_dir, NJ[key]['file'])); sr = w.getframerate(); ch = w.getnchannels(); raw = w.readframes(w.getnframes()); w.close()
        x = np.frombuffer(raw, dtype=np.int16).astype(np.float64) / 32768
        if ch == 2: x = x.reshape(-1, 2).mean(1)
        n2 = int(len(x) * SR / sr)
        y = np.interp(np.linspace(0, len(x) - 1, n2), np.arange(len(x)), x)
        return y / (np.abs(y).max() + 1e-9) * 0.9

    for key, t0 in cues:
        y = load_narr(key); i = int(t0 * SR); y = y[: n - i]; V[i:i + len(y)] += y
    return V


def _finish(L, R, V, out_dir, n):
    """効果音を控えめにし、読み上げを重ねて audio.wav に書き出す"""
    sfx_peak = max(np.abs(L).max(), np.abs(R).max())
    k = 0.38 / sfx_peak
    L = L * k + V; R = R * k + V
    m = max(np.abs(L).max(), np.abs(R).max())
    g = 0.85 / m
    st = (np.stack([L, R], 1) * g * 32767).astype(np.int16)
    path = os.path.join(out_dir, 'audio.wav')
    with wave.open(path, 'wb') as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(st.tobytes())
    print('audio ok', n / SR, 's peak gain', g)
    return path


def _adder(L, R, n):
    def add(sig, t0, pan=0.0, gain=1.0):
        i = int(t0 * SR)
        if i >= n: return
        sig = sig[: n - i]
        L[i:i+len(sig)] += sig * gain * (1 - max(0, pan))
        R[i:i+len(sig)] += sig * gain * (1 + min(0, pan))
    return add


def build(T, out_dir, voice=True):
    n = int((T.T_END + 0.5) * SR)
    L = np.zeros(n); R = np.zeros(n)
    add = _adder(L, R, n)

    pad = _pad(T, n)
    L += pad; R += pad
    # フック（先頭3つの区間に効果音を合わせる）
    hs = T.HOOK_SEGS
    add(noise_sweep(0.9, 300, 3000, 0.25), 0.0, 0, 1)
    add(tone(220, 0.6, 5, 0.3), 0.2); add(tone(330, 0.5, 6, 0.2), 0.45)
    if len(hs) > 1:
        add(tone(98, 0.9, 4, 0.5, (1, 0.2)), hs[1]['start']); add(noise_sweep(0.5, 500, 4000, 0.2), hs[1]['start'] - 0.3)
    if len(hs) > 2:
        add(tone(98, 0.9, 4, 0.5, (1, 0.2)), hs[2]['start'])
        add(noise_sweep(1.0, 300, 5000, 0.28), hs[2]['start'] + 0.1)
    # カウントダウン
    for i, it in enumerate(T.SEQ):
        prog = i / (len(T.SEQ) - 1)
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
    # スポットを当てる県
    if T.focus:
        t1 = T.T_COUNT_END
        add(tone(440, 0.4, 8, 0.3), t1 + 0.05); add(tone(554, 0.5, 8, 0.3), t1 + 0.18)
    # CTA
    t2 = T.T_COUNT_END + T.T_FOCUS
    for k, fx in enumerate((523.3, 659.3, 784.0, 1046.5)):
        add(tone(fx, 1.0, 4, 0.3), t2 + 0.1 + k * 0.12, ((k % 2) * 2 - 1) * 0.3)
    add(tone(130.8, 2.5, 1.3, 0.5, (1, 0.2)), t2 + 0.1)

    V = np.zeros(n)
    if voice:
        cues = [(sg['key'], sg['start'] + 0.12) for sg in hs]
        if T.INTER: cues.append(('intro10', T.INTER['start'] + 0.1))
        cues += [(it['key'], it['start'] + 0.08) for it in T.SEQ if it.get('key')]
        if T.focus: cues.append(('focus', T.T_COUNT_END + 0.15))
        cues.append(('cta', T.T_COUNT_END + T.T_FOCUS + 0.25))
        V = _voice(T, out_dir, n, cues)
    return _finish(L, R, V, out_dir, n)


def build_list(T, out_dir, voice=True):
    """一覧型（ListTheme）用の効果音＋ナレーション。順位が上がるほど音が高くなる。"""
    n = int((T.T_END + 0.5) * SR)
    L = np.zeros(n); R = np.zeros(n)
    add = _adder(L, R, n)
    pad = _pad(T, n)
    L += pad; R += pad
    hs = T.HOOK_SEGS
    add(noise_sweep(0.9, 300, 3000, 0.25), 0.0, 0, 1)
    add(tone(220, 0.6, 5, 0.3), 0.2); add(tone(330, 0.5, 6, 0.2), 0.45)
    for sg in hs[1:]:
        add(tone(98, 0.9, 4, 0.5, (1, 0.2)), sg['start'])
        add(noise_sweep(0.5, 500, 4000, 0.2), sg['start'] - 0.3)
    for i, it in enumerate(T.SEQ):
        prog = i / max(1, len(T.SEQ) - 1)
        f = 300 * 2 ** (prog * 1.4)
        pan = ((i % 2) * 2 - 1) * 0.25
        add(tone(f, 0.16, 22, 0.42, (1, 0.35, 0.12)), it['start'], pan)
        add(tone(f / 2, 0.22, 18, 0.18, (1, 0.2)), it['start'], pan)
        if i >= len(T.SEQ) - 3:
            add(tone(70, 0.5, 7, 0.55, (1, 0.15)), it['start'])
            add(tone(f * 1.5, 0.3, 12, 0.18), it['start'] + 0.05, -pan)
    last = T.SEQ[-1]['start']
    add(tone(55, 2.2, 1.6, 0.9, (1, 0.2)), last)
    for fx in (261.6, 329.6, 392.0, 523.3):
        add(tone(fx, 2.8, 1.5, 0.28, (1, 0.4, 0.15)), last + 0.02)
    add(noise_sweep(0.8, 800, 6000, 0.3), last - 0.2)
    t2 = T.T_COUNT_END
    for k, fx in enumerate((523.3, 659.3, 784.0, 1046.5)):
        add(tone(fx, 1.0, 4, 0.3), t2 + 0.1 + k * 0.12, ((k % 2) * 2 - 1) * 0.3)
    add(tone(130.8, 2.5, 1.3, 0.5, (1, 0.2)), t2 + 0.1)
    V = np.zeros(n)
    if voice:
        cues = [(sg['key'], sg['start'] + 0.12) for sg in hs]
        cues += [(it['key'], it['start'] + 0.08) for it in T.SEQ if it.get('key')]
        cues.append(('cta', T.T_COUNT_END + 0.25))
        V = _voice(T, out_dir, n, cues)
    return _finish(L, R, V, out_dir, n)


def build_tiers(T, out_dir, voice=True):
    """段階ボード（TierTheme）用の効果音＋ナレーション。段階が上がるほど低く重い音になり、名前ごとに小さな音が鳴る。
    style.look が horror なら、明るい和音をやめて、不協和なうなりと心音にする"""
    n = int((T.T_END + 0.5) * SR)
    L = np.zeros(n); R = np.zeros(n)
    add = _adder(L, R, n)
    horror = (getattr(T, 'style', {}) or {}).get('look') == 'horror'
    pad = _horror_bed(T, n) if horror else _pad(T, n)
    L += pad; R += pad
    hs = T.HOOK_SEGS
    add(noise_sweep(0.9, 300, 3000, 0.25), 0.0, 0, 1)
    add(tone(220, 0.6, 5, 0.3), 0.2); add(tone(330, 0.5, 6, 0.2), 0.45)
    for sg in hs[1:]:
        add(tone(98, 0.9, 4, 0.5, (1, 0.2)), sg['start'])
        add(noise_sweep(0.5, 500, 4000, 0.2), sg['start'] - 0.3)
    k = len(T.SEQ)
    for ti, sg in enumerate(T.SEQ):
        heavy = (ti + 1) / k                                   # 0〜1: 最後の段階ほど重く
        add(noise_sweep(0.7, 300, 3000, 0.22 + 0.1 * heavy), sg['start'] - 0.15)
        add(tone(110 - 40 * heavy, 0.9, 4, 0.45 + 0.35 * heavy, (1, 0.2)), sg['start'])
        if sg['last']:
            for fx in ((110.0, 116.5, 155.6) if horror else (110.0, 130.8, 164.8)):
                add(tone(fx, 2.0, 1.8, 0.3, (1, 0.5, 0.2)), sg['start'] + 0.02)
        for j, it in enumerate(sg['items']):
            if sg['tier']['spotlight']:
                add(tone(330, 0.25, 9, 0.3), it['start'])                       # 国名が出る
                add(noise_sweep(0.5, 400, 3000, 0.2), it['start'] + 0.6)        # 「？」からの盛り上がり
                add(tone(55, 1.4, 3, 0.9, (1, 0.2)), it['start'] + 1.0)          # レベルが明かされる
                add(tone(110 + 40 * j, 0.8, 5, 0.4, (1, 0.5, 0.2)), it['start'] + 1.0)
                continue
            f = 520 + 380 * heavy - 160 * (j % 4) / 3
            add(tone(f, 0.12, 26, 0.3, (1, 0.3, 0.1)), it['start'], ((j % 2) * 2 - 1) * 0.2)
    t2 = T.T_COUNT_END
    chord = (220.0, 261.6, 311.1, 370.0) if horror else (523.3, 659.3, 784.0, 1046.5)   # 減七の和音（暗い）／明るい和音
    for j, fx in enumerate(chord):
        add(tone(fx, 1.6 if horror else 1.0, 3 if horror else 4, 0.3), t2 + 0.1 + j * 0.12, ((j % 2) * 2 - 1) * 0.3)
    add(tone(130.8 if not horror else 55.0, 2.5, 1.3, 0.5, (1, 0.2)), t2 + 0.1)
    V = np.zeros(n)
    if voice:
        cues = [(sg['key'], sg['start'] + 0.12) for sg in hs]
        for sg in T.SEQ:
            cues.append((sg['key'], sg['start'] + 0.15))
            cues += [(it['key'], it['start'] + 0.04) for it in sg['items']]
        cues.append(('cta', T.T_COUNT_END + 0.25))
        V = _voice(T, out_dir, n, cues)
    return _finish(L, R, V, out_dir, n)


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    T = theme.load(args[0])
    out_dir = args[1] if len(args) > 1 else os.path.join(HERE, '..', 'build', T.id)
    nj = os.path.join(out_dir, 'narration.json')
    T = theme.load(args[0], nj)
    build(T, out_dir, voice='--no-voice' not in sys.argv)
