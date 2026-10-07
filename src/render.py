"""映像の描画と書き出し。
使い方:
  python3 render.py <theme.yaml> still 1.0,4.5 [out_dir]   静止画で確認（still_XX.XX.png）
  python3 render.py <theme.yaml> video [out_dir]           out_dir/out.mp4 を書き出す（audio.wav が必要）
文言・色・数値はすべて Theme（themes/*.yaml）から読む。out_dir 既定: build/<theme id>
フォントは環境変数 FONT_PATH（例 '/path/NotoSansCJK-%s.ttc'、%s に Black/Bold/Medium/Regular が入る）で指定できる。
"""
import os, pickle, subprocess, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops

import theme

HERE = os.path.dirname(os.path.abspath(__file__))
W, H = 1080, 1920
MAP_TOP = 398
FPS = 30

# ---------- フォント ----------
_FALLBACK = {'Black': ('Black', 'Bold'), 'Medium': ('Medium', 'Regular'), 'Bold': ('Bold',), 'Regular': ('Regular',)}
# macOS のヒラギノは未検証（見つからなければ次の候補へ進む）
_HIRAGINO = {'Regular': 'W3', 'Medium': 'W3', 'Bold': 'W6', 'Black': 'W8'}


def _font_paths(w):
    if os.environ.get('FONT_PATH'):
        p = os.environ['FONT_PATH']
        for name in _FALLBACK[w]:
            yield p % name if '%s' in p else p
    for name in _FALLBACK[w]:
        yield '/usr/share/fonts/opentype/noto/NotoSansCJK-%s.ttc' % name
    yield '/System/Library/Fonts/ヒラギノ角ゴシック %s.ttc' % _HIRAGINO[w]
    yield '/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf'


_fc = {}
def F(size, w='Black'):
    k = (size, w)
    if k not in _fc:
        for p in _font_paths(w):
            if os.path.exists(p):
                _fc[k] = ImageFont.truetype(p, size, index=0)
                break
        else:
            raise SystemExit('日本語フォントが見つかりません。FONT_PATH を指定してください（docs/HANDOFF.md 5.1）')
    return _fc[k]


WHITE = (255, 255, 255)
YELLOW = (255, 213, 74)
MUTED = (170, 180, 215)
GRAY = (46, 55, 100)
BG_TOP, BG_BOT = np.array([9, 14, 36]), np.array([20, 27, 58])

# init() で設定する（テーマと地図データ）
T = None
P = None
MAP_H = None
BG = None


def ease(x):
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3

def lerp(a, b, k):
    return tuple(int(round(a[i] + (b[i] - a[i]) * k)) for i in range(3))

def fit_font(d, s, size, w, max_w):
    """max_w に収まるまで文字サイズを縮める"""
    while size > 40 and d.textlength(s, font=F(size, w)) > max_w:
        size -= 2
    return F(size, w)


# ---------- 背景（静的） ----------
def build_bg():
    grad = np.linspace(0, 1, H)[:, None, None]
    arr = (BG_TOP * (1 - grad) + BG_BOT * grad).astype(np.uint8)
    arr = np.repeat(arr, W, axis=1)
    im = Image.fromarray(arr, 'RGB')
    d = ImageDraw.Draw(im, 'RGBA')
    src = T.spec['source']
    # タイトル
    d.rounded_rectangle((330, 168, 750, 232), 32, fill=(255, 255, 255, 30), outline=(255, 255, 255, 70), width=2)
    d.text((540, 200), T.say(T.spec['title_small']), font=F(34, 'Bold'), fill=(235, 240, 255), anchor='mm')
    title = T.say(T.spec['title'])
    d.text((540, 282), title, font=fit_font(d, title, 100, 'Black', 960), fill=WHITE, anchor='mm', stroke_width=2, stroke_fill=(9, 14, 36))
    d.text((540, 366), T.say(T.spec['subtitle']), font=fit_font(d, T.say(T.spec['subtitle']), 32, 'Bold', 960), fill=MUTED, anchor='mm')
    # 沖縄インセット枠
    o = P['沖縄県']
    x0, y0 = o['x0'], o['y0'] + MAP_TOP
    x1, y1 = x0 + o['mask'].size[0], y0 + o['mask'].size[1]
    d.rounded_rectangle((x0 - 14, y0 - 12, x1 + 14, y1 + 10), 14, outline=(90, 102, 160, 160), width=2)
    # 出典・クレジット
    d.text((540, 1578), '出典：' + src['name'], font=fit_font(d, '出典：' + src['name'], 26, 'Medium', 1000), fill=(150, 160, 200), anchor='mm')
    if src.get('note'):
        d.text((540, 1612), src['note'], font=fit_font(d, src['note'], 24, 'Medium', 1000), fill=(130, 140, 180), anchor='mm')
    if T.credit:
        d.text((540, 1650), '音声：' + T.credit, font=F(24, 'Medium'), fill=(130, 140, 180), anchor='mm')
    return im


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
    d.text((6, 8), T.say(T.spec['legend_title']), font=F(28, 'Bold'), fill=MUTED + (255,))
    for i, (th, col, lab) in enumerate(T.TIERS):
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
    col = T.TIERS[T.tier(v)][1]
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
    if name in T.TIE:
        d.rounded_rectangle((126, 14, 230, 48), 15, fill=YELLOW + (255,))
        d.text((178, 31), '同率', font=F(25), fill=(30, 30, 40, 255), anchor='mm')
    # 県名
    d.text((590, 100), name, font=F(92), fill=WHITE + (255,), anchor='mm')
    if item['name'] == T.ORDER[-1]:
        sub = T.spec['card_sub_first']
    elif item['name'] == T.ORDER[0]:
        sub = T.spec['card_sub_last']
    else:
        sub = T.spec['card_sub']
    d.text((590, 172), T.say(sub, **T.item_vars(name)), font=F(32, 'Bold'), fill=(190, 198, 230, 255), anchor='mm')
    # 値
    d.text((900, 80), T.metric, font=F(26, 'Bold'), fill=MUTED + (255,), anchor='mm')
    d.text((900, 140), T.fmt(v), font=F(104), fill=col + (255,), anchor='mm')
    L.putalpha(ImageChops.multiply(L.getchannel('A'), Image.new('L', L.size, int(255 * k))))
    frame.paste(L, (0, 1282 + int((1 - k) * 26)), L)

def progress(frame, n, alpha=1.0):
    d = ImageDraw.Draw(frame, 'RGBA')
    d.rounded_rectangle((54, 1534, 1026, 1546), 6, fill=(40, 48, 90, int(255 * alpha)))
    if n > 0:
        wd = 54 + (1026 - 54) * n / T.N
        d.rounded_rectangle((54, 1534, wd, 1546), 6, fill=(255, 255, 255, int(255 * alpha)))


# ---------- フレーム ----------
class Renderer:
    def __init__(self):
        self.layer = new_layer()
        self.done = 0

    def sync(self, t):
        while self.done < len(T.SEQ) and T.SEQ[self.done]['start'] + T.SEQ[self.done]['dur'] <= t:
            it = T.SEQ[self.done]
            paint(self.layer, it['name'], T.TIERS[T.tier(it['val'])][1])
            self.done += 1

    def frame(self, t):
        self.sync(t)
        f = BG.copy()
        if T.T_COUNT_END <= t < T.T_COUNT_END + T.T_FOCUS:
            lyr = self.layer.copy()
            lyr.putalpha(lyr.getchannel('A').point(lambda v: int(v * 0.32)))
            f.paste(lyr, (0, MAP_TOP), lyr)
        else:
            f.paste(self.layer, (0, MAP_TOP), self.layer)
        t_c = T.T_COUNT_END
        # ---- フック ----
        if t < T.T_HOOK:
            k = 0
            for i, sg in enumerate(T.HOOK_SEGS):
                if sg['start'] <= t:
                    k = i
            sg = T.HOOK_SEGS[k]
            tl = t - sg['start']
            panel(f, T.hook_panels[k], MAP_TOP + sg['y'], ease(tl / sg['fade']))
            legend(f, ease((t - (T.T_HOOK - 0.6)) / 0.6))
            progress(f, 0, 0.5)
            return f
        # ---- カウントダウン ----
        active = None
        for it in T.SEQ:
            if it['start'] <= t < it['start'] + it['dur']:
                active = it
                break
        n_done = self.done
        if active is not None:
            a = t - active['start']
            tr = T.tier(active['val'])
            col = lerp(WHITE, T.TIERS[tr][1], ease(a / 0.45))
            draw_active(f, active['name'], col, 0.85 - 0.4 * min(1, a / active['dur']))
            ring(f, active['name'], a)
            legend(f, 1.0, tr)
            card(f, active, a, active['dur'])
            progress(f, n_done + 1)
            return f
        # ---- 「ここからTOP10」 ----
        if t < T.T_COUNT_END and T.INTER and T.INTER['start'] <= t < T.INTER['start'] + T.INTER['dur']:
            legend(f, 1.0)
            panel(f, T.intro_panel, MAP_TOP + 380, ease((t - T.INTER['start']) / 0.3))
            progress(f, n_done)
            return f
        # ---- アウトロ ----
        progress(f, T.N)
        t0 = t - t_c
        if t0 < T.T_FOCUS:
            # 指定した県にスポットライト
            fc = T.focus
            draw_active(f, fc, T.TIERS[T.tier(T.DATA[fc])][1], 0.8)
            ring(f, fc, t0 % 1.2 / 1.2 * 0.6)
            panel(f, T.focus_panel, 650, ease(t0 / 0.35), gap=16)
        else:
            t1 = t0 - T.T_FOCUS
            panel(f, T.cta_panel, MAP_TOP + 410, ease(t1 / 0.4), gap=14)
        return f


def init(theme_obj, geo_path):
    global T, P, MAP_H, BG
    T = theme_obj
    geo = pickle.load(open(geo_path, 'rb'))
    P = geo['prefs']
    MAP_H = geo['MAP_H']
    BG = build_bg()


def render_video(out, audio):
    r = Renderer()
    total = int(T.T_END * FPS)
    cmd = ['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', '%dx%d' % (W, H), '-r', str(FPS), '-i', '-',
           '-i', audio, '-c:v', 'libx264', '-preset', 'medium', '-crf', '19', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '160k',
           '-movflags', '+faststart', '-t', '%.3f' % T.T_END, out]
    ff = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for i in range(total):
        im = r.frame(i / FPS)
        ff.stdin.write(im.tobytes())
        if i % 300 == 0:
            print('frame', i, '/', total, flush=True)
    ff.stdin.close()
    if ff.wait() != 0:
        raise SystemExit('ffmpeg が失敗しました')
    print('done', out)


def render_stills(out_dir, times):
    for t in times:
        r = Renderer()  # 毎回作り直し（時刻を飛ばすため）
        r.frame(t).save(os.path.join(out_dir, 'still_%05.2f.png' % t))


if __name__ == '__main__':
    theme_path, mode = sys.argv[1], sys.argv[2]
    tid = theme.load(theme_path).id
    default_out = os.path.join(HERE, '..', 'build', tid)
    arg3 = sys.argv[3] if len(sys.argv) > 3 else None
    out_dir = (sys.argv[4] if mode == 'still' and len(sys.argv) > 4 else arg3 if mode == 'video' and arg3 else default_out)
    os.makedirs(out_dir, exist_ok=True)
    init(theme.load(theme_path, os.path.join(out_dir, 'narration.json')), os.path.join(HERE, '..', 'build', 'geo.pkl'))
    if mode == 'still':
        render_stills(out_dir, [float(x) for x in arg3.split(',')])
    else:
        render_video(os.path.join(out_dir, 'out.mp4'), os.path.join(out_dir, 'audio.wav'))
