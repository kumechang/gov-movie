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
STYLE = {}
FX = None                                 # 揺れ・フラッシュの設定（恐怖演出のとき）
TITLE_COLOR = None
BAR_BG, BAR_FILL = (40, 48, 90), (255, 255, 255)
SRC_COLOR, SRC_COLOR2 = (150, 160, 200), (130, 140, 180)


# ---------- 背景 ----------
def _rgb(v, default):
    return tuple(v) if v else default


def build_bg():
    st = STYLE
    bg = st.get('bg') or {}
    top = np.array(_rgb(bg.get('top'), tuple(BG_TOP.tolist())), dtype=float)
    bot = np.array(_rgb(bg.get('bottom'), tuple(BG_BOT.tolist())), dtype=float)
    grad = np.linspace(0, 1, H)[:, None, None]
    arr = (top * (1 - grad) + bot * grad)
    arr = np.repeat(arr, W, axis=1)
    if bg.get('fog'):                                  # 下から立ちのぼる赤い霧
        fog = np.array(bg['fog'], dtype=float)
        k = np.clip((np.linspace(0, 1, H) - (1 - float(bg.get('fog_height', 0.4)))) / float(bg.get('fog_height', 0.4)), 0, 1)[:, None, None] ** 1.6
        arr = arr * (1 - 0.55 * k) + fog * 0.55 * k
    if bg.get('vignette'):                             # 四隅を暗くする
        yy, xx = np.mgrid[0:H, 0:W]
        r = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2) / 1.41
        v = 1 - float(bg['vignette']) * np.clip(r, 0, 1)[:, :, None] ** 2.2
        arr = arr * v
    if bg.get('grain'):                                # フィルムのざらつき（静止）
        rng = np.random.default_rng(7)
        arr = arr + rng.normal(0, float(bg['grain']) * 255, (H, W, 1))
    im = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), 'RGB')
    d = ImageDraw.Draw(im, 'RGBA')
    src = T.spec['source']
    pill = st.get('pill') or {}
    d.rounded_rectangle((330, 168, 750, 232), 32, fill=_rgb(pill.get('fill'), (255, 255, 255, 30)),
                        outline=_rgb(pill.get('outline'), (255, 255, 255, 70)), width=2)
    d.text((540, 200), T.say(T.spec['title_small']), font=F(34, 'Bold'), fill=_rgb(pill.get('text'), (235, 240, 255)), anchor='mm')
    title = T.say(T.spec['title'])
    tfont = fit_font(d, title, 100, 'Black', 960)
    tcol = TITLE_COLOR or WHITE
    if st.get('title_glow'):                           # タイトルの赤い光
        glow = Image.new('RGB', im.size, (0, 0, 0))
        ImageDraw.Draw(glow).text((540, 282), title, font=tfont, fill=tuple(st['title_glow']), anchor='mm', stroke_width=6)
        glow = glow.filter(ImageFilter.GaussianBlur(18))
        im = Image.fromarray(np.clip(np.asarray(im, dtype=float) + np.asarray(glow, dtype=float), 0, 255).astype(np.uint8), 'RGB')
        d = ImageDraw.Draw(im, 'RGBA')
    d.text((540, 282), title, font=tfont, fill=tcol, anchor='mm', stroke_width=3, stroke_fill=STROKE_COLOR())
    if st.get('drips'):                                # 文字から血が滴る
        bb = d.textbbox((540, 282), title, font=tfont, anchor='mm')
        rng = np.random.default_rng(11)
        base_y = bb[3] - 14
        for x in sorted(rng.integers(bb[0] + 20, bb[2] - 20, 9)):
            ln = int(rng.integers(16, 52))
            wd = int(rng.integers(5, 9))
            col = tuple(st['drips']) if isinstance(st['drips'], (list, tuple)) else tcol
            d.rounded_rectangle((x - wd // 2, base_y, x + wd // 2, base_y + ln), wd // 2, fill=col + (235,))
            d.ellipse((x - wd, base_y + ln - wd // 2, x + wd, base_y + ln + wd * 1.4), fill=col + (235,))
    sub = T.say(T.spec['subtitle'])
    d.text((540, 366), sub, font=fit_font(d, sub, 32, 'Bold', 960), fill=MUTED, anchor='mm')
    d.text((540, 1578), '出典：' + src['name'], font=fit_font(d, '出典：' + src['name'], 26, 'Medium', 1000), fill=SRC_COLOR, anchor='mm')
    if src.get('note'):
        note = T.say(src['note']) if '{' in src['note'] else src['note']
        d.text((540, 1612), note, font=fit_font(d, note, 24, 'Medium', 1000), fill=SRC_COLOR2, anchor='mm')
    if T.credit:
        d.text((540, 1650), '音声：' + T.credit, font=F(24, 'Medium'), fill=SRC_COLOR2, anchor='mm')
    return im


def STROKE_COLOR():
    return tuple(render.STROKE[:3])


def apply_style(st):
    """テーマの style を反映する（フォント・配色・パネル・揺れ）。style が無ければ標準の見た目"""
    global STYLE, FX, TITLE_COLOR, BAR_BG, BAR_FILL, SRC_COLOR, SRC_COLOR2, WHITE, MUTED, YELLOW, NAVY
    STYLE = st or {}
    # 既定に戻す（テーマを続けて処理しても前のスタイルが残らないように）
    WHITE, MUTED, YELLOW = (255, 255, 255), (170, 180, 215), (255, 213, 74)
    NAVY = tuple(BG_TOP.tolist())
    render.FONT_OVERRIDE.clear()
    render._fc.clear()
    render.PANEL_FILL, render.PANEL_OUTLINE, render.STROKE = (8, 12, 32, 222), (255, 255, 255, 40), (9, 14, 36, 255)
    BAR_BG, BAR_FILL, SRC_COLOR, SRC_COLOR2, TITLE_COLOR, FX = (40, 48, 90), (255, 255, 255), (150, 160, 200), (130, 140, 180), None, None
    if not STYLE:
        return
    root = os.path.join(HERE, '..')
    for w, path in (STYLE.get('fonts') or {}).items():
        fp = path if os.path.isabs(path) else os.path.join(root, path)
        if os.path.exists(fp):
            render.FONT_OVERRIDE[w] = fp
        else:
            print('注意: フォント %s が見つかりません。標準のフォントで書き出します（scripts/setup_fonts.sh で配置できます）' % path)
    if STYLE.get('text'):
        WHITE = tuple(STYLE['text'])
    if STYLE.get('muted'):
        MUTED = tuple(STYLE['muted'])
        SRC_COLOR, SRC_COLOR2 = tuple(int(x * 0.9) for x in MUTED), tuple(int(x * 0.75) for x in MUTED)
    if STYLE.get('accent'):
        YELLOW = tuple(STYLE['accent'])
    if STYLE.get('title_color'):
        TITLE_COLOR = tuple(STYLE['title_color'])
    pn = STYLE.get('panel') or {}
    if pn.get('fill'):
        render.PANEL_FILL = tuple(pn['fill'])
    if pn.get('outline'):
        render.PANEL_OUTLINE = tuple(pn['outline'])
    if pn.get('stroke'):
        render.STROKE = tuple(pn['stroke'])
        NAVY = tuple(pn['stroke'][:3])
    bar = STYLE.get('bar') or {}
    BAR_BG, BAR_FILL = _rgb(bar.get('bg'), BAR_BG), _rgb(bar.get('fill'), BAR_FILL)
    FX = STYLE.get('fx') or None


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
    d.rounded_rectangle((54, 1534, 1026, 1546), 6, fill=BAR_BG + (int(255 * alpha),))
    if n > 0:
        d.rounded_rectangle((54, 1534, 54 + (1026 - 54) * n / len(T.SEQ), 1546), 6, fill=BAR_FILL + (int(255 * alpha),))


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


def wrap_text(d, text, font, max_w):
    """文字単位で折り返す（日本語向け）"""
    lines, cur = [], ''
    for ch in text:
        if cur and d.textlength(cur + ch, font=font) > max_w:
            lines.append(cur)
            cur = ch
        else:
            cur += ch
    if cur:
        lines.append(cur)
    return lines


def why_color(tag):
    """危険の種類ごとの色（紛争・テロ・犯罪・感染症…）"""
    for keys, col in ((('紛争', '武力', '戦'), (205, 70, 70)), (('テロ',), (230, 125, 45)), (('誘拐',), (205, 70, 150)),
                      (('ギャング', '犯罪', '凶悪', '麻薬'), (140, 80, 205)), (('感染', 'マラリア', '疫'), (50, 160, 120))):
        if any(k in tag for k in keys):
            return col
    return (90, 110, 170)


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


# ---------- tiers（段階ボード） ----------
class Tiers:
    """段階（レベル）ごとに、その段階の項目名をチップとして1つずつ並べる。最後は段階ごとの件数の一覧"""
    HEAD_TOP, HEAD_H = AREA_TOP, 150
    BOARD_TOP, BOARD_BOTTOM = AREA_TOP + 170, AREA_BOTTOM - 40
    FOOT_Y = AREA_BOTTOM - 10

    def __init__(self):
        self._lay = {}

    @staticmethod
    def _on(col):
        return (15, 20, 40) if sum(col) > 420 else WHITE

    def header(self, tier, k=1.0):
        key = ('head', tier['level'])
        if key not in _cards:
            col = tier['color']
            on = self._on(col)
            L = Image.new('RGBA', (1000, self.HEAD_H), (0, 0, 0, 0))
            d = ImageDraw.Draw(L)
            d.rounded_rectangle((0, 0, 999, self.HEAD_H - 1), 30, fill=col + (255,), outline=(255, 255, 255, 140), width=3)
            d.text((34, 58), tier['title'], font=F(88), fill=on + (255,), anchor='lm')
            text_fit(d, (36, 118), tier['sub'], 34, 'Bold', on + (235,), 620, anchor='lm')
            cnt = str(tier['count'])
            fn, fs = F(120), F(42, 'Bold')
            w = d.textlength(cnt, font=fn) + 8 + d.textlength('か国', font=fs)
            x = 966 - w
            d.text((x, 70), cnt, font=fn, fill=on + (255,), anchor='lm')
            d.text((x + d.textlength(cnt, font=fn) + 8, 96), 'か国', font=fs, fill=on + (255,), anchor='lm')
            _cards[key] = L
        L = _cards[key]
        if k >= 1:
            return L
        im = L.copy()
        im.putalpha(ImageChops.multiply(im.getchannel('A'), Image.new('L', im.size, int(255 * max(0.0, k)))))
        return im

    def layout(self, tier):
        """チップの位置を最初に決める（文字サイズは、全部が領域に収まる最大にする）"""
        if tier['level'] in self._lay:
            return self._lay[tier['level']]
        probe = ImageDraw.Draw(Image.new('RGB', (10, 10)))
        avail_h = self.BOARD_BOTTOM - self.BOARD_TOP
        names = [m['short'] for m in tier['members']]
        for size in range(48, 27, -2):
            pad, gap = int(size * 0.55), 12
            h = int(size * 1.7)
            ws = [int(probe.textlength(n, font=F(size, 'Bold'))) + 2 * pad for n in names]
            rows, cur, curw = [], [], 0
            for i, w in enumerate(ws):
                add = w + (gap if cur else 0)
                if cur and curw + add > 1000:
                    rows.append(cur)
                    cur, curw = [], 0
                    add = w
                cur.append(i)
                curw += add
            rows.append(cur)
            if len(rows) * (h + gap) - gap <= avail_h:
                break
        pos = {}
        total_h = len(rows) * (h + gap) - gap
        y = self.BOARD_TOP + max(0, (avail_h - total_h) // 2)
        for r in rows:
            rw = sum(ws[i] for i in r) + gap * (len(r) - 1)
            x = 40 + (1000 - rw) // 2
            for i in r:
                pos[i] = (x, y, ws[i], h)
                x += ws[i] + gap
            y += h + gap
        self._lay[tier['level']] = (size, pos)
        return self._lay[tier['level']]

    def chip(self, tier, i, size, box):
        key = ('chip', tier['level'], i)
        if key not in _cards:
            x, y, w, h = box
            col = tier['color']
            L = Image.new('RGBA', (w, h), (0, 0, 0, 0))
            d = ImageDraw.Draw(L)
            d.rounded_rectangle((0, 0, w - 1, h - 1), h // 2, fill=col + (240,), outline=(255, 255, 255, 120), width=2)
            d.text((w / 2, h / 2 + 1), tier['members'][i]['short'], font=F(size, 'Bold'), fill=self._on(col) + (255,), anchor='mm')
            _cards[key] = L
        return _cards[key]

    def legend(self, f, alpha):
        """フック中に出す、段階の凡例（レベルの高い順）"""
        if alpha <= 0:
            return
        d = ImageDraw.Draw(f, 'RGBA')
        n = len(T.TIERS)
        rh = min(118, (AREA_BOTTOM - AREA_TOP - 30) // n - 14)
        top = AREA_TOP + 20
        for i, tier in enumerate(reversed(T.TIERS)):
            y = top + i * (rh + 14)
            col = tier['color']
            d.rounded_rectangle((40, y, 1040, y + rh), 26, fill=col + (int(200 * alpha),))
            on = self._on(col)
            tf = F(min(60, rh - 40))
            d.text((74, y + rh / 2), tier['title'], font=tf, fill=on + (int(255 * alpha),), anchor='lm')
            sx = 74 + int(d.textlength(tier['title'], font=tf)) + 28
            text_fit(d, (sx, y + rh / 2), tier['sub'], 36, 'Bold', on + (int(255 * alpha),), 1010 - sx, anchor='lm')

    def summary(self, f, alpha=1.0):
        if T.subset:
            return self.summary_chips(f)
        d = ImageDraw.Draw(f, 'RGBA')
        mx = max(t['count'] for t in T.TIERS)
        n = len(T.TIERS)
        rh = min(118, (AREA_BOTTOM - AREA_TOP - 30) // n - 14)
        top = AREA_TOP + 20
        for i, tier in enumerate(reversed(T.TIERS)):
            y = top + i * (rh + 14)
            col = tier['color']
            on = self._on(col)
            d.rounded_rectangle((40, y, 1040, y + rh), 26, fill=(14, 20, 48, 200), outline=(70, 82, 140, 200), width=2)
            d.rounded_rectangle((52, y + 14, 330, y + rh - 14), 18, fill=col + (255,))
            d.text((191, y + rh / 2), tier['title'], font=F(52), fill=on + (255,), anchor='mm')
            blen = 40 + 520 * tier['count'] / mx
            d.rounded_rectangle((350, y + 30, 350 + blen, y + rh - 30), 14, fill=col + (255,))
            d.text((350 + blen + 16, y + rh / 2), '%dか国' % tier['count'], font=F(48), fill=WHITE + (255,), anchor='lm')

    def summary_chips(self, f):
        """指定した国すべてを、レベル別の行にして並べる（結果の一覧）"""
        d = ImageDraw.Draw(f, 'RGBA')
        probe = d
        fs, pad, gap, ch = 34, 18, 10, 56
        y = AREA_TOP + 4
        for tier in reversed(T.TIERS):
            col = tier['color']
            on = self._on(col)
            names = [m['short'] for m in tier['members']]
            rows, cur, curw = [], [], 0
            for n in names:
                w = int(probe.textlength(n, font=F(fs, 'Bold'))) + 2 * pad
                add = w + (gap if cur else 0)
                if cur and curw + add > 790:
                    rows.append(cur)
                    cur, curw, add = [], 0, w
                cur.append((n, w))
                curw += add
            rows.append(cur)
            h = len(rows) * (ch + gap) - gap
            d.rounded_rectangle((40, y, 1040, y + h + 24), 24, fill=(14, 20, 48, 190), outline=col + (200,), width=3)
            d.rounded_rectangle((52, y + 12, 250, y + 12 + h), 18, fill=col + (255,))
            size = 44
            while size > 22 and d.textlength(tier['title'], font=F(size)) > 180:     # 長い見出しは枠に収まるまで縮める
                size -= 2
            d.text((151, y + 12 + h / 2), tier['title'], font=F(size), fill=on + (255,), anchor='mm')
            yy = y + 12
            for r in rows:
                x = 270
                for n, w in r:
                    d.rounded_rectangle((x, yy, x + w, yy + ch), ch // 2, fill=col + (235,))
                    d.text((x + w / 2, yy + ch / 2 + 1), n, font=F(fs, 'Bold'), fill=on + (255,), anchor='mm')
                    x += w + gap
                yy += ch + gap
            y += h + 24 + 14

    def footnote(self, f):
        if T.footnote:
            d = ImageDraw.Draw(f, 'RGBA')
            text_fit(d, (540, self.FOOT_Y), T.footnote, 28, 'Medium', (170, 180, 215, 255), 1000)

    def unknown_chip(self, tier, i, box):
        key = ('unk', tier['level'], i)
        if key not in _cards:
            x, y, w, h = box
            L = Image.new('RGBA', (w, h), (0, 0, 0, 0))
            d = ImageDraw.Draw(L)
            d.rounded_rectangle((0, 0, w - 1, h - 1), h // 2, fill=(16, 22, 52, 170), outline=(80, 92, 150, 200), width=2)
            d.text((w / 2, h / 2 + 1), '？', font=F(int(h * 0.6), 'Bold'), fill=(90, 102, 160, 230), anchor='mm')
            _cards[key] = L
        return _cards[key]

    def spotlight(self, f, sg, it, a):
        """1か国をじっくり見せる: 国名 →「？」→ レベル・地域・危険の理由 を順に出す"""
        tier, m = sg['tier'], it['member']
        col = tier['color']
        on = self._on(col)
        d = ImageDraw.Draw(f, 'RGBA')
        k0 = ease(a / 0.3)
        # 国名
        name_font = fit_font(d, m['short'], 170, 'Black', 960)
        d.text((540, self.BOARD_TOP + 110 - (1 - k0) * 30), m['short'], font=name_font, fill=WHITE + (int(255 * k0),), anchor='mm',
               stroke_width=3, stroke_fill=NAVY + (255,))
        reveal = 1.0
        if a < reveal:
            blink = 0.65 + 0.35 * math.sin(a * 10)
            d.text((540, self.BOARD_TOP + 330), 'レベルは？', font=F(130, 'Accent'), fill=YELLOW + (int(255 * k0 * blink),), anchor='mm')
            return
        r = a - reveal
        kb = ease(r / 0.35)
        by = self.BOARD_TOP + 255
        bw = 880
        d.rounded_rectangle((540 - bw / 2, by - 55, 540 + bw / 2, by + 55), 30, fill=col + (int(255 * kb),), outline=(255, 255, 255, int(180 * kb)), width=3)
        d.text((540, by + 2), '%s の地域を含む' % tier['title'], font=F(64), fill=on + (int(255 * kb),), anchor='mm')
        y = by + 100
        # どこ？
        if m.get('where'):
            kw = ease((r - 0.35) / 0.35)
            d.text((60, y), 'どこ？', font=F(34, 'Bold'), fill=(170, 180, 215, int(255 * kw)), anchor='lm')
            wf = F(46, 'Bold')
            lines = wrap_text(d, m['where'], wf, 940)[:3]
            for i, ln in enumerate(lines):
                d.text((60, y + 50 + i * 58), ln, font=wf, fill=WHITE + (int(255 * kw),), anchor='lm')
            y += 50 + len(lines) * 58 + 22
        # 何が危ない？
        if m.get('why'):
            d.text((60, y), '何が危ない？', font=F(34, 'Bold'), fill=(170, 180, 215, int(255 * ease((r - 0.7) / 0.3))), anchor='lm')
            y += 56
            for i, w in enumerate(m['why'][:3]):
                kw = ease((r - 0.9 - i * 0.4) / 0.35)
                if kw <= 0:
                    continue
                tc = why_color(w.get('tag', ''))
                tag = w.get('tag', '')
                tf = F(34, 'Bold')
                tw = int(d.textlength(tag, font=tf)) + 36
                avail = 1020 - (60 + tw + 18)
                for size in (40, 36, 32):
                    bf = F(size, 'Bold')
                    lines = wrap_text(d, w['text'], bf, avail)
                    if len(lines) <= 2:
                        break
                rh = max(62, 46 * len(lines) + 16)
                d.rounded_rectangle((60, y, 60 + tw, y + 58), 29, fill=tc + (int(255 * kw),))
                d.text((60 + tw / 2, y + 30), tag, font=tf, fill=WHITE + (int(255 * kw),), anchor='mm')
                for j, ln in enumerate(lines[:2]):
                    d.text((60 + tw + 18, y + 24 + j * 46), ln, font=bf, fill=WHITE + (int(255 * kw),), anchor='lm')
                y += rh + 14
        # ほかの地域のレベル
        for i, al in enumerate(m.get('also', [])[:2]):
            kw = ease((r - 2.2 - i * 0.3) / 0.35)
            if kw <= 0:
                continue
            lc = next((t['color'] for t in T.TIERS if t['level'] == al['level']), (170, 180, 215))
            txt = 'レベル%d：%s' % (al['level'], al['where'])
            lf = F(34, 'Bold')
            for j, ln in enumerate(wrap_text(d, txt, lf, 940)[:2]):
                d.text((60, y + 10 + j * 44), ln, font=lf, fill=lc + (int(255 * kw),), anchor='lm')
            y += 12 + 44 * min(2, len(wrap_text(d, txt, lf, 940)))

    def events(self):
        """揺れ・フラッシュが入る時刻 [(開始, 長さ, 揺れの強さ, フラッシュの強さ)]。レベル3以上の発表と、レベルが明かされる瞬間"""
        if not hasattr(self, '_events'):
            ev = []
            for sg in T.SEQ:
                if sg['level'] >= 3:
                    ev.append((sg['start'], 0.6, 0.5, 0.5))
                for it in sg['items']:
                    if sg['tier']['spotlight']:
                        ev.append((it['start'] + 1.0, 0.55, 1.3 if sg['level'] >= 4 else 1.0, 1.0))
            self._events = ev
        return self._events

    def post(self, f, t):
        """恐怖演出: レベルが明かされる瞬間に、画面を揺らし、赤くフラッシュさせる（点滅の繰り返しはしない）"""
        if not FX:
            return f
        amp = flash = 0.0
        for t0, dur, a, fl in self.events():
            if t0 <= t < t0 + dur:
                k = 1 - (t - t0) / dur
                amp, flash = max(amp, a * k), max(flash, fl * k)
        if amp > 0:
            sh = float(FX.get('shake', 14)) * amp
            dx, dy = int(round(sh * math.sin(t * 97))), int(round(sh * math.cos(t * 83)))
            g = Image.new('RGB', f.size, NAVY)
            g.paste(f, (dx, dy))
            f = g
        if flash > 0:
            f = Image.blend(f, Image.new('RGB', f.size, tuple(FX.get('flash', (170, 0, 10)))), flash * float(FX.get('flash_alpha', 0.35)))
        return f

    def frame(self, t):
        return self.post(self._frame(t), t)

    def _frame(self, t):
        f = BG.copy()
        if t < T.T_HOOK:
            self.legend(f, 0.55)
            hook_panel(f, t)
            progress(f, 0, 0.5)
            self.footnote(f)
            return f
        cur = current(t)
        if cur is None and t < T.T_COUNT_END:                # 段階の間（通常は起きないが念のため）
            cur = (len(T.SEQ) - 1, T.SEQ[-1], 0.0)
        if cur is not None:
            idx, sg, a = cur
            tier = sg['tier']
            hd = self.header(tier, a / 0.3)
            f.paste(hd, (40, self.HEAD_TOP), hd)
            active = None
            if tier['spotlight']:
                active = next((it for it in sg['items'] if it['start'] <= t < it['start'] + it['dur']), None)
            if active is not None:
                self.spotlight(f, sg, active, t - active['start'])
            elif tier['names']:
                size, pos = self.layout(tier)
                for i, it in enumerate(sg['items']):
                    box = pos[i]
                    if it['start'] > t:
                        if tier['spotlight']:
                            ch = self.unknown_chip(tier, i, box)
                            f.paste(ch, (box[0], box[1]), ch)
                        continue
                    ch = self.chip(tier, i, size, box)
                    k = (t - it['start']) / 0.22
                    pop(f, ch, box[0] + box[2] / 2, box[1] + box[3] / 2, k)
                    if t - it['start'] < 0.5 and not tier['spotlight']:
                        d = ImageDraw.Draw(f, 'RGBA')
                        d.rounded_rectangle((box[0] - 3, box[1] - 3, box[0] + box[2] + 3, box[1] + box[3] + 3), box[3] // 2 + 3,
                                            outline=(255, 255, 255, int(255 * (1 - (t - it['start']) / 0.5))), width=4)
            else:
                d = ImageDraw.Draw(f, 'RGBA')
                k = ease((a - sg['intro'] + 0.6) / 0.5)
                cnt = '%d' % tier['count']
                d.text((540, self.BOARD_TOP + 300), cnt, font=F(360), fill=tier['color'] + (int(255 * k),), anchor='mm')
                d.text((540, self.BOARD_TOP + 560), 'か国', font=F(100, 'Bold'), fill=WHITE + (int(255 * k),), anchor='mm')
                note = T.spec.get('names_note')
                if note:
                    text_fit(d, (540, self.BOARD_TOP + 700), note, 34, 'Medium', (170, 180, 215, int(255 * k)), 960)
            progress(f, revealed(t))
            self.footnote(f)
            return f
        # アウトロ: 結果の一覧 ＋ CTA
        self.summary(f)
        if not T.subset:
            f = dimmed(f, 0.38)
        panel(f, T.cta_panel, 1225 if T.subset else MAP_TOP + 410, ease((t - T.T_COUNT_END) / 0.4), gap=14)
        progress(f, len(T.SEQ))
        self.footnote(f)
        return f


LAYOUT_CLASSES = {'grid': Grid, 'scroll': Scroll, 'steps': Steps, 'tiers': Tiers}


def init(theme_obj, geo_path=None):
    global T, P, BG
    T = theme_obj
    _cards.clear()
    apply_style(getattr(T, 'style', None))
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
