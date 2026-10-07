import pickle, math, subprocess, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops
from common import *

geo = pickle.load(open('geo.pkl', 'rb'))
P = geo['prefs']
W, H = 1080, 1920
MAP_H = geo['MAP_H']
MAP_TOP = 398
FPS = 30

FP = '/usr/share/fonts/opentype/noto/NotoSansCJK-%s.ttc'
_fc = {}
def F(size, w='Black'):
    k = (size, w)
    if k not in _fc:
        _fc[k] = ImageFont.truetype(FP % w, size, index=0)
    return _fc[k]

WHITE = (255, 255, 255)
YELLOW = (255, 213, 74)
RED = (255, 90, 95)
MUTED = (170, 180, 215)
GRAY = (46, 55, 100)
BG_TOP, BG_BOT = np.array([9, 14, 36]), np.array([20, 27, 58])

def ease(x):
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3

def lerp(a, b, k):
    return tuple(int(round(a[i] + (b[i] - a[i]) * k)) for i in range(3))

# ---------- 背景（静的） ----------
def build_bg():
    grad = np.linspace(0, 1, H)[:, None, None]
    arr = (BG_TOP * (1 - grad) + BG_BOT * grad).astype(np.uint8)
    arr = np.repeat(arr, W, axis=1)
    im = Image.fromarray(arr, 'RGB')
    d = ImageDraw.Draw(im, 'RGBA')
    # タイトル
    d.rounded_rectangle((330, 168, 750, 232), 32, fill=(255, 255, 255, 30), outline=(255, 255, 255, 70), width=2)
    d.text((540, 200), '2024年｜都道府県別', font=F(34, 'Bold'), fill=(235, 240, 255), anchor='mm')
    d.text((540, 282), '離婚率ランキング', font=F(100), fill=WHITE, anchor='mm', stroke_width=2, stroke_fill=(9, 14, 36))
    d.text((540, 366), '人口千人あたりの離婚数 ／ 全国平均 1.55', font=F(32, 'Bold'), fill=MUTED, anchor='mm')
    # 沖縄インセット枠
    o = P['沖縄県']
    x0, y0 = o['x0'], o['y0'] + MAP_TOP
    x1, y1 = x0 + o['mask'].size[0], y0 + o['mask'].size[1]
    d.rounded_rectangle((x0 - 14, y0 - 12, x1 + 14, y1 + 10), 14, outline=(90, 102, 160, 160), width=2)
    # 出典
    d.text((540, 1578), '出典：厚生労働省「人口動態統計」2024年', font=F(26, 'Medium'), fill=(150, 160, 200), anchor='mm')
    d.text((540, 1612), '（国立社会保障・人口問題研究所「人口統計資料集」より）', font=F(24, 'Medium'), fill=(130, 140, 180), anchor='mm')
    d.text((540, 1650), '音声：VOICEVOX:四国めたん', font=F(24, 'Medium'), fill=(130, 140, 180), anchor='mm')
    return im

BG = build_bg()

# ---------- 地図の永続レイヤ ----------
def paint(layer, name, color):
    p = P[name]
    layer.paste(Image.new('RGBA', p['mask'].size, color + (255,)), (p['x0'], p['y0']), p['mask'])
    layer.paste(Image.new('RGBA', p['edge'].size, tuple(BG_TOP.tolist()) + (255,)), (p['x0'], p['y0']), p['edge'])

def new_layer():
    layer = Image.new('RGBA', (W, MAP_H), (0, 0, 0, 0))
    for n in P:
        paint(layer, n, GRAY)
    return layer

_thick = {}
def thick_edge(name):
    if name not in _thick:
        m = P[name]['mask'].point(lambda v: 255 if v > 40 else 0)
        _thick[name] = ImageChops.subtract(m, m.filter(ImageFilter.MinFilter(7))).filter(ImageFilter.GaussianBlur(0.7))
    return _thick[name]

_glow = {}
def glow(name):
    if name not in _glow:
        m = P[name]['mask']
        pad = 40
        big = Image.new('L', (m.size[0] + 2 * pad, m.size[1] + 2 * pad), 0)
        big.paste(m, (pad, pad))
        _glow[name] = (big.filter(ImageFilter.GaussianBlur(16)), pad)
    return _glow[name]

def draw_active(frame, name, color, a_glow, outline=True):
    p = P[name]
    g, pad = glow(name)
    frame.paste(Image.new('RGB', g.size, (255, 255, 255)), (p['x0'] - pad, MAP_TOP + p['y0'] - pad), g.point(lambda v: int(v * a_glow)))
    frame.paste(Image.new('RGB', p['mask'].size, color), (p['x0'], MAP_TOP + p['y0']), p['mask'])
    if outline:
        te = thick_edge(name)
        frame.paste(Image.new('RGB', te.size, (255, 255, 255)), (p['x0'], MAP_TOP + p['y0']), te)

def ring(frame, name, a, strength=1.0):
    p = P[name]
    r = 14 + a * 170
    al = int(max(0, 1 - a / 0.6) * 230 * strength)
    if al <= 0:
        return
    d = ImageDraw.Draw(frame, 'RGBA')
    cx, cy = p['cx'], p['cy'] + MAP_TOP
    d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=(255, 255, 255, al), width=5)

# ---------- 部品 ----------
def text_center(d, xy, s, font, fill, stroke=0, sfill=(9, 14, 36)):
    d.text(xy, s, font=font, fill=fill, anchor='mm', stroke_width=stroke, stroke_fill=sfill)

def panel(frame, lines, cy, alpha=1.0, pad=44, gap=18):
    """lines: [(text,size,color,weight)]  中央寄せの半透明パネル"""
    if alpha <= 0:
        return
    dummy = ImageDraw.Draw(frame)
    metrics = []
    for s, size, col, wt in lines:
        f = F(size, wt)
        bb = dummy.textbbox((0, 0), s, font=f, anchor='ls')
        metrics.append((s, f, col, bb[2] - bb[0], size))
    total_h = sum(int(m[4] * 1.1) for m in metrics) + gap * (len(metrics) - 1)
    maxw = max(m[3] for m in metrics)
    w = min(1000, maxw + pad * 2)
    top = cy - total_h / 2 - pad * 0.8
    slide = (1 - ease(alpha * 1.0)) * 30
    layer = Image.new('RGBA', (W, int(total_h + pad * 1.6) + 6), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    ld.rounded_rectangle(((W - w) / 2, 3, (W + w) / 2, layer.size[1] - 3), 36, fill=(8, 12, 32, 222), outline=(255, 255, 255, 40), width=2)
    y = pad * 0.8 + 3
    for s, f, col, tw, size in metrics:
        h = int(size * 1.1)
        ld.text((W / 2, y + h / 2), s, font=f, fill=col + (255,), anchor='mm', stroke_width=2 if size > 80 else 0, stroke_fill=(9, 14, 36, 255))
        y += h + gap
    layer.putalpha(ImageChops.multiply(layer.getchannel('A'), Image.new('L', layer.size, int(255 * ease(alpha)))))
    frame.paste(layer, (0, int(top + slide)), layer)

def legend(frame, alpha, active_tier=None):
    if alpha <= 0:
        return
    layer = Image.new('RGBA', (440, 330), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.text((6, 8), '離婚率の色分け', font=F(28, 'Bold'), fill=MUTED + (255,))
    for i, (th, col, lab) in enumerate(TIERS):
        y = 56 + i * 52
        d.rounded_rectangle((6, y, 44, y + 36), 8, fill=col + (255,))
        if active_tier == i:
            d.rounded_rectangle((2, y - 4, 48, y + 40), 11, outline=(255, 255, 255, 255), width=3)
        d.text((62, y + 18), lab, font=F(32, 'Bold'), fill=(255, 255, 255, 255 if active_tier in (None, i) else 130), anchor='lm')
    layer.putalpha(ImageChops.multiply(layer.getchannel('A'), Image.new('L', layer.size, int(255 * alpha))))
    frame.paste(layer, (40, MAP_TOP + 40), layer)

def card(frame, item, a, dur):
    """カード：順位・県名・値"""
    k = ease(a / 0.22)
    name, v, rk = item['name'], item['val'], item['rank']
    col = TIERS[tier(v)][1]
    L = Image.new('RGBA', (W, 250), (0, 0, 0, 0))
    d = ImageDraw.Draw(L)
    d.rounded_rectangle((54, 12, 1026, 214), 34, fill=(12, 17, 42, 240), outline=col + (255,), width=5)
    # 順位
    num = str(rk)
    fn, fk = F(132), F(56)
    wn = d.textlength(num, font=fn); wk = d.textlength('位', font=fk)
    x = 178 - (wn + 6 + wk) / 2
    d.text((x, 160), num, font=fn, fill=WHITE + (255,), anchor='ls')
    d.text((x + wn + 6, 160), '位', font=fk, fill=WHITE + (255,), anchor='ls')
    if name in TIE:
        d.rounded_rectangle((126, 14, 230, 48), 15, fill=YELLOW + (255,))
        d.text((178, 31), '同率', font=F(25), fill=(30, 30, 40, 255), anchor='mm')
    # 県名
    d.text((590, 100), name, font=F(92), fill=WHITE + (255,), anchor='mm')
    if rk == 1:
        sub = '全国平均の約%.1f倍' % (v / AVG)
    elif rk == 47:
        sub = '最下位（1位の約半分）'
    else:
        sub = '人口千人あたり'
    d.text((590, 172), sub, font=F(32, 'Bold'), fill=(190, 198, 230, 255), anchor='mm')
    # 値
    d.text((900, 80), '離婚率', font=F(26, 'Bold'), fill=MUTED + (255,), anchor='mm')
    d.text((900, 140), '%.2f' % v, font=F(104), fill=col + (255,), anchor='mm')
    L.putalpha(ImageChops.multiply(L.getchannel('A'), Image.new('L', L.size, int(255 * k))))
    frame.paste(L, (0, 1282 + int((1 - k) * 26)), L)

def progress(frame, n, alpha=1.0):
    d = ImageDraw.Draw(frame, 'RGBA')
    d.rounded_rectangle((54, 1534, 1026, 1546), 6, fill=(40, 48, 90, int(255 * alpha)))
    if n > 0:
        wd = 54 + (1026 - 54) * n / 47
        d.rounded_rectangle((54, 1534, wd, 1546), 6, fill=(255, 255, 255, int(255 * alpha)))

# ---------- フレーム ----------
class Renderer:
    def __init__(self):
        self.layer = new_layer()
        self.done = 0

    def sync(self, t):
        while self.done < len(SEQ) and SEQ[self.done]['start'] + SEQ[self.done]['dur'] <= t:
            it = SEQ[self.done]
            paint(self.layer, it['name'], TIERS[tier(it['val'])][1])
            self.done += 1

    def frame(self, t):
        self.sync(t)
        f = BG.copy()
        if T_COUNT_END <= t < T_COUNT_END + T_TOKYO:
            lyr = self.layer.copy()
            lyr.putalpha(lyr.getchannel('A').point(lambda v: int(v * 0.32)))
            f.paste(lyr, (0, MAP_TOP), lyr)
        else:
            f.paste(self.layer, (0, MAP_TOP), self.layer)
        t_c = T_COUNT_END
        # ---- フック ----
        if t < T_HOOK:
            k = 0
            for i, sg in enumerate(HOOK_SEGS):
                if sg['start'] <= t:
                    k = i
            tl = t - HOOK_SEGS[k]['start']
            if k == 0:
                panel(f, [('あなたの県は', 68, WHITE, 'Bold'), ('何位？', 200, YELLOW, 'Black')], MAP_TOP + 380, ease(tl / 0.4))
            elif k == 1:
                panel(f, [('離婚率が一番高い県と', 54, WHITE, 'Bold'), ('一番低い県の差は', 54, WHITE, 'Bold'), ('約2倍', 190, RED, 'Black')], MAP_TOP + 400, ease(tl / 0.35))
            else:
                panel(f, [('47位から1位まで', 62, WHITE, 'Black'), ('一気に発表します', 62, YELLOW, 'Black')], MAP_TOP + 380, ease(tl / 0.35))
            legend(f, ease((t - (T_HOOK - 0.6)) / 0.6))
            progress(f, 0, 0.5)
            return f
        # ---- カウントダウン ----
        active = None
        for it in SEQ:
            if it['start'] <= t < it['start'] + it['dur']:
                active = it
                break
        n_done = self.done
        if active is not None:
            a = t - active['start']
            tr = tier(active['val'])
            col = lerp(WHITE, TIERS[tr][1], ease(a / 0.45))
            draw_active(f, active['name'], col, 0.85 - 0.4 * min(1, a / active['dur']))
            ring(f, active['name'], a)
            legend(f, 1.0, tr)
            card(f, active, a, active['dur'])
            progress(f, n_done + 1)
            return f
        # ---- 「ここからTOP10」 ----
        if t < T_COUNT_END and INTER and INTER['start'] <= t < INTER['start'] + INTER['dur']:
            legend(f, 1.0)
            panel(f, [('ここから', 72, WHITE, 'Bold'), ('TOP10', 200, YELLOW, 'Black')], MAP_TOP + 380, ease((t - INTER['start']) / 0.3))
            progress(f, n_done)
            return f
        # ---- アウトロ ----
        progress(f, 47)
        t0 = t - t_c
        if t0 < T_TOKYO:
            # 東京にスポットライト
            tk = '東京都'
            draw_active(f, tk, TIERS[tier(DATA[tk])][1], 0.8)
            ring(f, tk, t0 % 1.2 / 1.2 * 0.6)
            rk = RANK[tk]
            partners = [n for n in RANK if RANK[n] == rk and n != tk]
            sub = '離婚率 %.2f' % DATA[tk] + ('（%sと同率）' % partners[0] if partners else '')
            lines = [('東京都は', 52, WHITE, 'Bold'), ('%d位' % rk, 140, WHITE, 'Black'), (sub, 38, MUTED, 'Bold'),
                     ('全国平均 %.2f とほぼ同じ' % AVG, 44, YELLOW, 'Black')]
            panel(f, lines, 650, ease(t0 / 0.35), gap=16)
        else:
            t1 = t0 - T_TOKYO
            panel(f, [('離婚の背景は人それぞれ。', 38, MUTED, 'Bold'), ('数字だけで決めつけないでね', 38, MUTED, 'Bold'),
                      ('あなたの県は', 64, WHITE, 'Bold'), ('何位だった？', 124, YELLOW, 'Black'),
                      ('コメントで教えてね ↓', 54, WHITE, 'Black'), ('他の指標のランキングも → フォロー', 36, MUTED, 'Bold')],
                  MAP_TOP + 410, ease(t1 / 0.4), gap=14)
        return f

def main():
    r = Renderer()
    if len(sys.argv) > 1 and sys.argv[1] == 'still':
        ts = [float(x) for x in sys.argv[2].split(',')]
        for t in ts:
            r = Renderer()  # 毎回作り直し（時刻を飛ばすため）
            im = r.frame(t)
            im.save('still_%05.2f.png' % t)
        return
    out = sys.argv[1]
    audio = sys.argv[2]
    total = int(T_END * FPS)
    cmd = ['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', '%dx%d' % (W, H), '-r', str(FPS), '-i', '-',
           '-i', audio, '-c:v', 'libx264', '-preset', 'medium', '-crf', '19', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '160k',
           '-movflags', '+faststart', '-t', '%.3f' % T_END, out]
    ff = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for i in range(total):
        im = r.frame(i / FPS)
        ff.stdin.write(im.tobytes())
        if i % 300 == 0:
            print('frame', i, '/', total, flush=True)
    ff.stdin.close()
    ff.wait()
    print('done', out)

if __name__ == '__main__':
    main()
