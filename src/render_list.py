"""一覧型テンプレート（ranked_list）の描画と書き出し。layout: grid / scroll / steps。
使い方:
  python3 render_list.py <theme.yaml> still 1.0,4.5 [out_dir]   静止画で確認（still_XX.XX.png）
  python3 render_list.py <theme.yaml> video [out_dir]           out_dir/out.mp4 を書き出す（audio.wav が必要）
文字・色・数値はすべて ListTheme（themes/*.yaml）から読む。フォント・文字の部品は render.py と共通。
"""
import math
import os
import pickle
import subprocess
import sys

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

import loader
import render
from render import BG_BOT, BG_TOP, FPS, H, MAP_TOP, MUTED, W, WHITE, YELLOW, F, ease, fit_font, panel

HERE = os.path.dirname(os.path.abspath(__file__))
AREA_TOP, AREA_BOTTOM = 440, 1510       # 一覧を置く領域
NAVY = tuple(BG_TOP.tolist())

T = None
P = None
BG = None
_cards = {}


# ---------- 背景 ----------
def build_bg():
    grad = np.linspace(0, 1, H)[:, None, None]
    arr = (BG_TOP * (1 - grad) + BG_BOT * grad).astype(np.uint8)
    im = Image.fromarray(np.repeat(arr, W, axis=1), 'RGB')
    d = ImageDraw.Draw(im, 'RGBA')
    src = T.spec['source']
    d.rounded_rectangle((330, 168, 750, 232), 32, fill=(255, 255, 255, 30), outline=(255, 255, 255, 70), width=2)
    d.text((540, 200), T.say(T.spec['title_small']), font=F(34, 'Bold'), fill=(235, 240, 255), anchor='mm')
    title = T.say(T.spec['title'])
    d.text((540, 282), title, font=fit_font(d, title, 100, 'Black', 960), fill=WHITE, anchor='mm', stroke_width=2, stroke_fill=NAVY)
    sub = T.say(T.spec['subtitle'])
    d.text((540, 366), sub, font=fit_font(d, sub, 32, 'Bold', 960), fill=MUTED, anchor='mm')
    d.text((540, 1578), '出典：' + src['name'], font=fit_font(d, '出典：' + src['name'], 26, 'Medium', 1000), fill=(150, 160, 200), anchor='mm')
    if src.get('note'):
        d.text((540, 1612), src['note'], font=fit_font(d, src['note'], 24, 'Medium', 1000), fill=(130, 140, 180), anchor='mm')
    if T.credit:
        d.text((540, 1650), '音声：' + T.credit, font=F(24, 'Medium'), fill=(130, 140, 180), anchor='mm')
    return im


# ---------- 部品 ----------
def tier_color(it):
    return T.TIERS[it['tier']][1]


def silhouette(name, bw, bh, color):
    """都道府県の形（地図データのマスク）を bw×bh に収めて色をつける"""
    m = P[name]['mask']
    k = min(bw / m.size[0], bh / m.size[1])
    sz = (max(1, int(m.size[0] * k)), max(1, int(m.size[1] * k)))
    mask = m.resize(sz, Image.LANCZOS)
    filled = float((np.asarray(mask) > 100).mean())
    if filled < 0.12:                      # 沖縄のように島が散らばる形は、点にしか見えないので太らせる
        mask = mask.filter(ImageFilter.MaxFilter(7))
    out = Image.new('RGBA', sz, color + (255,))
    out.putalpha(mask)
    return out


def draw_value(d, cx, cy, it, size, color, max_w, left=False):
    """値（大）＋単位（小）を描く（既定は cx を中心に、left=True なら cx を左端に）。幅に収まるまで縮める"""
    num, suf = T.fmt(it['val']), T.suffix
    while size > 24:
        fn, fs = F(size, 'Black'), F(int(size * 0.5), 'Bold')
        w = d.textlength(num, font=fn) + (d.textlength(suf, font=fs) + 4 if suf else 0)
        if w <= max_w:
            break
        size -= 2
    x = cx if left else cx - w / 2
    d.text((x, cy), num, font=fn, fill=color + (255,), anchor='lm')
    if suf:
        d.text((x + d.textlength(num, font=fn) + 4, cy + size * 0.12), suf, font=fs, fill=color + (255,), anchor='lm')


def text_fit(d, xy, s, size, weight, fill, max_w, anchor='mm', **kw):
    d.text(xy, s, font=fit_font(d, s, size, weight, max_w), fill=fill, anchor=anchor, **kw)


def rank_label(d, x, y, it, size, color=WHITE, anchor='lm'):
    """「12位」の数字を大きく、「位」を小さく"""
    num = str(it['rank'])
    fn, fk = F(size), F(int(size * 0.42), 'Bold')
    wn = d.textlength(num, font=fn)
    d.text((x, y), num, font=fn, fill=color + (255,), anchor=anchor)
    d.text((x + wn + 4, y + size * 0.22), '位', font=fk, fill=color + (255,), anchor=anchor)
    return wn + 4 + d.textlength('位', font=fk)


def pop(frame, img, cx, cy, k):
    """出現アニメ（拡大しながら現れる）"""
    if k <= 0:
        return
    k = ease(k)
    s = 0.86 + 0.14 * k
    im = img.resize((max(1, int(img.size[0] * s)), max(1, int(img.size[1] * s))), Image.LANCZOS)
    im.putalpha(ImageChops.multiply(im.getchannel('A'), Image.new('L', im.size, int(255 * k))))
    frame.paste(im, (int(cx - im.size[0] / 2), int(cy - im.size[1] / 2)), im)


def dimmed(frame, k=0.35):
    """CTA 用に画面を暗くする（背景との合成）"""
    return Image.blend(frame, BG, 1 - k)


def progress(frame, n, alpha=1.0):
    d = ImageDraw.Draw(frame, 'RGBA')
    d.rounded_rectangle((54, 1534, 1026, 1546), 6, fill=(40, 48, 90, int(255 * alpha)))
    if n > 0:
        d.rounded_rectangle((54, 1534, 54 + (1026 - 54) * n / len(T.SEQ), 1546), 6, fill=(255, 255, 255, int(255 * alpha)))


def hook_panel(f, t):
    k = 0
    for i, sg in enumerate(T.HOOK_SEGS):
        if sg['start'] <= t:
            k = i
    sg = T.HOOK_SEGS[k]
    panel(f, T.hook_panels[k], MAP_TOP + sg['y'], ease((t - sg['start']) / sg['fade']))


def current(t):
    """発表中の項目 (index, seg, 経過秒)。まだ・もう発表中でなければ None"""
    for i, sg in enumerate(T.SEQ):
        if sg['start'] <= t < sg['start'] + sg['dur']:
            return i, sg, t - sg['start']
    return None


def revealed(t):
    return sum(1 for sg in T.SEQ if sg['start'] <= t)


# ---------- grid ----------
class Grid:
    COLS, GAP = 3, 14

    def __init__(self):
        cells = len(T.SEQ) + (1 if T.note else 0)
        self.rows = math.ceil(cells / self.COLS)
        self.cw = (1000 - self.GAP * (self.COLS - 1)) // self.COLS
        self.ch = min(330, (AREA_BOTTOM - AREA_TOP - self.GAP * (self.rows - 1)) // self.rows)
        # 縦に余ったら中央に寄せる
        used = self.rows * self.ch + (self.rows - 1) * self.GAP
        self.top = AREA_TOP + (AREA_BOTTOM - AREA_TOP - used) // 2

    def center(self, cell):
        r, c = divmod(cell, self.COLS)
        return 40 + c * (self.cw + self.GAP) + self.cw / 2, self.top + r * (self.ch + self.GAP) + self.ch / 2

    def cell_of(self, idx):
        return len(T.SEQ) - 1 - idx          # 発表の最後（1位）が左上

    def card(self, it):
        key = ('grid', it['name'])
        if key in _cards:
            return _cards[key]
        w, h = self.cw, self.ch
        col = tier_color(it)
        top = it['rank'] == 1
        L = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(L)
        d.rounded_rectangle((3, 3, w - 3, h - 3), 26, fill=(12, 17, 42, 242), outline=(YELLOW if top else col) + (255,), width=6 if top else 4)
        # 順位バッジ
        bw = 150
        d.rounded_rectangle((12, 12, 12 + bw, 12 + 62), 20, fill=col + (255,))
        rank_label(d, 12 + 14, 12 + 33, it, 46, color=(15, 20, 40) if sum(col) > 520 else WHITE)
        if it['tie']:
            d.rounded_rectangle((12 + bw + 8, 22, 12 + bw + 8 + 70, 22 + 38), 14, fill=YELLOW + (255,))
            d.text((12 + bw + 43, 41), '同率', font=F(24), fill=(30, 30, 40, 255), anchor='mm')
        # 形と文字
        sil_w = 118
        body_top = 84
        if it['pref']:
            sil = silhouette(it['name'], sil_w, h - body_top - 16, col)
            L.paste(sil, (14 + (sil_w - sil.size[0]) // 2, body_top + (h - body_top - 16 - sil.size[1]) // 2), sil)
            tx, tw = 14 + sil_w + 8 + (w - 14 - sil_w - 8 - 12) / 2, w - 14 - sil_w - 8 - 12
        else:
            tx, tw = w / 2, w - 28
        text_fit(d, (tx, body_top + (h - body_top) * 0.20), it['name'], 50, 'Black', WHITE + (255,), tw)
        draw_value(d, tx, body_top + (h - body_top) * 0.50, it, 76, col, tw)
        sub = T.item_sub(it)
        if sub:
            text_fit(d, (tx, body_top + (h - body_top) * 0.80), sub, 25, 'Medium', (190, 198, 230, 255), tw)
        _cards[key] = L
        return L

    def slot(self, rank_text):
        key = ('slot', rank_text)
        if key not in _cards:
            L = Image.new('RGBA', (self.cw, self.ch), (0, 0, 0, 0))
            d = ImageDraw.Draw(L)
            d.rounded_rectangle((3, 3, self.cw - 3, self.ch - 3), 26, fill=(16, 22, 52, 150), outline=(70, 82, 140, 170), width=2)
            d.text((self.cw / 2, self.ch / 2), rank_text, font=F(70, 'Bold'), fill=(80, 92, 150, 200), anchor='mm')
            _cards[key] = L
        return _cards[key]

    def note_card(self):
        key = ('note',)
        if key not in _cards:
            n = T.note
            L = Image.new('RGBA', (self.cw, self.ch), (0, 0, 0, 0))
            d = ImageDraw.Draw(L)
            d.rounded_rectangle((3, 3, self.cw - 3, self.ch - 3), 26, fill=(12, 17, 42, 242), outline=(110, 124, 190, 255), width=3)
            y = 34
            if n.get('title'):
                text_fit(d, (self.cw / 2, y), n['title'], 34, 'Black', YELLOW + (255,), self.cw - 30)
                y += 52
            for line in n.get('lines', []):
                text_fit(d, (self.cw / 2, y), line, 26, 'Medium', (220, 226, 245, 255), self.cw - 30)
                y += 40
            _cards[key] = L
        return _cards[key]

    def frame(self, t):
        f = BG.copy()
        cur = current(t)
        n_rev = revealed(t)
        for idx, sg in enumerate(T.SEQ):
            cx, cy = self.center(self.cell_of(idx))
            if idx < n_rev:
                a = t - sg['start']
                pop(f, self.card(sg), cx, cy, a / 0.3)
                if cur and cur[0] == idx:
                    d = ImageDraw.Draw(f, 'RGBA')
                    al = int(255 * (0.55 + 0.45 * math.sin(a * 9)) * 0.9)
                    d.rounded_rectangle((cx - self.cw / 2 - 2, cy - self.ch / 2 - 2, cx + self.cw / 2 + 2, cy + self.ch / 2 + 2), 28, outline=(255, 255, 255, al), width=5)
            else:
                f.paste(self.slot('%d位' % sg['rank']), (int(cx - self.cw / 2), int(cy - self.ch / 2)), self.slot('%d位' % sg['rank']))
        if T.note:
            cx, cy = self.center(len(T.SEQ))
            if n_rev >= len(T.SEQ):
                pop(f, self.note_card(), cx, cy, min(1.0, (t - T.SEQ[-1]['start'] - 0.6) / 0.4))
        if t < T.T_HOOK:
            hook_panel(f, t)
            progress(f, 0, 0.5)
            return f
        progress(f, n_rev)
        if t >= T.T_COUNT_END:
            f = dimmed(f, 0.32)
            panel(f, T.cta_panel, MAP_TOP + 410, ease((t - T.T_COUNT_END) / 0.4), gap=14)
            progress(f, len(T.SEQ))
        return f


# ---------- scroll ----------
class Scroll:
    CW, CH, PITCH = 420, 900, 444
    TOP = (AREA_TOP + AREA_BOTTOM - CH) // 2

    def card(self, it):
        key = ('scroll', it['name'])
        if key in _cards:
            return _cards[key]
        w, h = self.CW, self.CH
        col = tier_color(it)
        top = it['rank'] == 1
        L = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(L)
        d.rounded_rectangle((4, 4, w - 4, h - 4), 36, fill=(12, 17, 42, 244), outline=(YELLOW if top else col) + (255,), width=8 if top else 6)
        d.rounded_rectangle((26, 24, w - 26, 150), 28, fill=col + (255,))
        # 順位（中央寄せ）
        size = 120
        num, fk = str(it['rank']), F(52, 'Bold')
        wn = d.textlength(num, font=F(size))
        x = w / 2 - (wn + 6 + d.textlength('位', font=fk)) / 2
        dark = sum(col) > 520
        rc = (15, 20, 40) if dark else WHITE
        d.text((x, 92), num, font=F(size), fill=rc + (255,), anchor='lm')
        d.text((x + wn + 6, 112), '位', font=fk, fill=rc + (255,), anchor='lm')
        if it['tie']:
            d.rounded_rectangle((w - 120, 160, w - 30, 204), 16, fill=YELLOW + (255,))
            d.text((w - 75, 182), '同率', font=F(28), fill=(30, 30, 40, 255), anchor='mm')
        y = 230
        if it['pref']:
            sil = silhouette(it['name'], 340, 300, col)
            L.paste(sil, ((w - sil.size[0]) // 2, y + (300 - sil.size[1]) // 2), sil)
            y += 316
        else:
            y += 40
        text_fit(d, (w / 2, y + 46), it['name'], 84, 'Black', WHITE + (255,), w - 50)
        d.text((w / 2, y + 112), T.metric, font=fit_font(d, T.metric, 30, 'Bold', w - 50), fill=MUTED + (255,), anchor='mm')
        draw_value(d, w / 2, y + 184, it, 128, col, w - 50)
        sub = T.item_sub(it)
        if sub:
            text_fit(d, (w / 2, y + 262), sub, 34, 'Bold', (190, 198, 230, 255), w - 50)
        _cards[key] = L
        return L

    def back(self):
        key = ('back',)
        if key not in _cards:
            w, h = self.CW, self.CH
            L = Image.new('RGBA', (w, h), (0, 0, 0, 0))
            d = ImageDraw.Draw(L)
            d.rounded_rectangle((4, 4, w - 4, h - 4), 36, fill=(16, 22, 52, 190), outline=(70, 82, 140, 190), width=3)
            d.text((w / 2, h / 2), '?', font=F(260, 'Black'), fill=(80, 92, 150, 210), anchor='mm')
            _cards[key] = L
        return _cards[key]

    def pos(self, t):
        """画面中央に来ている項目番号（小数）。項目が切り替わる最初の 0.5 秒でイージングする"""
        f = 0.0
        for i, sg in enumerate(T.SEQ):
            if t >= sg['start']:
                f = i - 1 + ease((t - sg['start']) / 0.5) if i >= 1 else 0.0
        return max(0.0, f)

    def frame(self, t):
        f = BG.copy()
        n_rev = revealed(t)
        fpos = self.pos(t)
        for idx in range(len(T.SEQ)):
            cx = 540 + (idx - fpos) * self.PITCH
            if cx < -self.CW or cx > W + self.CW:
                continue
            img = self.card(T.SEQ[idx]) if idx < n_rev else self.back()
            f.paste(img, (int(cx - self.CW / 2), self.TOP), img)
        if t < T.T_HOOK:
            hook_panel(f, t)
            progress(f, 0, 0.5)
            return f
        progress(f, n_rev)
        if t >= T.T_COUNT_END:
            f = dimmed(f, 0.32)
            panel(f, T.cta_panel, MAP_TOP + 410, ease((t - T.T_COUNT_END) / 0.4), gap=14)
            progress(f, len(T.SEQ))
        return f


# ---------- steps ----------
class Steps:
    X_BAR, BAR_MAX = 215, 540

    def frame(self, t):
        f = BG.copy()
        n = len(T.SEQ)
        pitch = min(172, (AREA_BOTTOM - AREA_TOP) // n)
        vmax = max(sg['val'] for sg in T.SEQ)
        d = ImageDraw.Draw(f, 'RGBA')
        n_rev = revealed(t)
        for idx, sg in enumerate(T.SEQ):
            y = AREA_TOP + (n - 1 - idx) * pitch            # 1位が一番上
            col = tier_color(sg)
            d.rounded_rectangle((40, y, 1040, y + pitch - 14), 26, fill=(14, 20, 48, 120), outline=(60, 72, 130, 120), width=2)
            if idx >= n_rev:
                rank_label(d, 70, y + (pitch - 14) / 2, sg, 64, color=(80, 92, 150))
                continue
            a = t - sg['start']
            k = ease(a / 0.6)
            rank_label(d, 70, y + (pitch - 14) / 2, sg, 64, color=WHITE if sg['rank'] > 1 else YELLOW)
            text_fit(d, (self.X_BAR, y + 27), sg['name'], 46, 'Black', WHITE + (255,), 600, anchor='lm')
            blen = max(8, self.BAR_MAX * sg['val'] / vmax * k)
            by0, by1 = y + 62, y + 62 + 50
            d.rounded_rectangle((self.X_BAR, by0, self.X_BAR + blen, by1), 14, fill=col + (255,))
            if k > 0.6:
                vimg = Image.new('RGBA', (320, 90), (0, 0, 0, 0))
                draw_value(ImageDraw.Draw(vimg), 4, 45, sg, 64, col, 300, left=True)
                vimg.putalpha(ImageChops.multiply(vimg.getchannel('A'), Image.new('L', vimg.size, int(255 * min(1, (k - 0.6) / 0.4)))))
                f.paste(vimg, (int(self.X_BAR + blen + 14), by0 - 19), vimg)
            sub = T.item_sub(sg)
            if sub:
                text_fit(d, (self.X_BAR, y + pitch - 14 - 16), sub, 26, 'Medium', (190, 198, 230, 255), 760, anchor='lm')
        if t < T.T_HOOK:
            hook_panel(f, t)
            progress(f, 0, 0.5)
            return f
        progress(f, n_rev)
        if t >= T.T_COUNT_END:
            f = dimmed(f, 0.32)
            panel(f, T.cta_panel, MAP_TOP + 410, ease((t - T.T_COUNT_END) / 0.4), gap=14)
            progress(f, n)
        return f


LAYOUT_CLASSES = {'grid': Grid, 'scroll': Scroll, 'steps': Steps}


def init(theme_obj, geo_path=None):
    global T, P, BG
    T = theme_obj
    _cards.clear()
    P = None
    if T.is_pref:
        P = pickle.load(open(geo_path, 'rb'))['prefs']
    BG = build_bg()
    return LAYOUT_CLASSES[T.layout]()


def render_video(out, audio, layout):
    total = int(T.T_END * FPS)
    cmd = ['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', '%dx%d' % (W, H), '-r', str(FPS), '-i', '-',
           '-i', audio, '-c:v', 'libx264', '-preset', 'medium', '-crf', '19', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '160k',
           '-movflags', '+faststart', '-t', '%.3f' % T.T_END, out]
    ff = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for i in range(total):
        ff.stdin.write(layout.frame(i / FPS).tobytes())
        if i % 300 == 0:
            print('frame', i, '/', total, flush=True)
    ff.stdin.close()
    if ff.wait() != 0:
        raise SystemExit('ffmpeg が失敗しました')
    print('done', out)


def render_stills(out_dir, times, layout):
    for t in times:
        layout.frame(t).save(os.path.join(out_dir, 'still_%05.2f.png' % t))


if __name__ == '__main__':
    theme_path, mode = sys.argv[1], sys.argv[2]
    arg3 = sys.argv[3] if len(sys.argv) > 3 else None
    spec0 = loader.theme.load_spec(theme_path)
    default_out = os.path.join(HERE, '..', 'build', spec0['id'])
    out_dir = (sys.argv[4] if mode == 'still' and len(sys.argv) > 4 else arg3 if mode == 'video' and arg3 else default_out)
    os.makedirs(out_dir, exist_ok=True)
    spec, _ = loader.load_resolved(theme_path, out_dir)
    layout = init(loader.make_theme(spec, os.path.join(out_dir, 'narration.json')), os.path.join(HERE, '..', 'build', 'geo.pkl'))
    if mode == 'still':
        render_stills(out_dir, [float(x) for x in arg3.split(',')], layout)
    else:
        render_video(os.path.join(out_dir, 'out.mp4'), os.path.join(out_dir, 'audio.wav'), layout)
