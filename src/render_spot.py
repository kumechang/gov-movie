"""場所と危険情報（template: place_vs_risk）の描画。render_list.init() が layout 'place' でこのクラスを使う。

フック → 人気の根拠の場面（写真・落ち着いた配色）→ ターン（背景が赤黒に切り替わる）→ 地図に危険情報の地域を出す
→ 人気の街のレベル → 注意点 → 結び → CTA。文言・色・位置はすべて PlaceTheme（YAML）から読む。
"""
import math

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps

import render
import render_list as rl
import world
from render import H, MAP_TOP, W, F, ease, fit_font, panel

MAP_RECT = (40, 478, 1000, 520)         # 地図を置く枠 (x, y, w, h)
INFO_TOP = 1040                         # 地図の下の説明欄の上端
GOLD = (236, 196, 92)


class PlaceRisk(rl.Tiers):
    def __init__(self):
        self.cache = {}
        T = rl.T
        calm = dict(T.style)
        calm.update(T.spec.get('calm_style') or {})        # ターンの前の、落ち着いた背景（タイトルなどの色）
        rl.apply_style(calm)
        self.bg_calm = rl.build_bg()
        rl.apply_style(T.style)                             # 描画中の文字・パネルは本編（恐怖演出）のスタイルで描く
        self.bg_hot = rl.BG

    # ---------- 共通 ----------
    def _gold(self):
        return tuple((rl.T.style.get('named_colors') or {}).get('yellow', GOLD))

    def _blend_bg(self, t):
        k = ease((t - rl.T.T_TURN) / 0.45)
        if k <= 0:
            return self.bg_calm.copy()
        if k >= 1:
            return self.bg_hot.copy()
        return Image.blend(self.bg_calm, self.bg_hot, k)

    def events(self):
        if not hasattr(self, '_events'):
            ev = [(rl.T.T_TURN, 0.5, 0.6, 0.6)]
            for sg in rl.T.MAP_SEGS:
                if sg['kind'] == 'region' and sg['region']['level'] >= 3:
                    ev.append((sg['start'] + 0.05, 0.6, 1.3 if sg['region']['level'] >= 4 else 1.0, 1.0))
            self._events = ev
        return self._events

    # ---------- 人気の根拠の場面 ----------
    def photo(self, sc):
        key = ('photo', sc['image'])
        if key not in self.cache:
            self.cache[key] = ImageOps.fit(Image.open(sc['image']).convert('RGB'), (W, H), method=Image.LANCZOS)
        return self.cache[key]

    def shade(self):
        if 'shade' not in self.cache:
            y = np.linspace(0, 1, H)[:, None]
            dark = np.clip((y - 0.50) / 0.30, 0, 1) * 0.80 + 0.10          # 下ほど暗く（文字を読みやすく）
            self.cache['shade'] = np.repeat(1 - dark, W, axis=1)[:, :, None]
            top = Image.new('L', (W, H), 0)                                  # 上（タイトル）は隠さない
            ImageDraw.Draw(top).rectangle((0, 600, W, H), fill=255)
            self.cache['top'] = top.filter(ImageFilter.GaussianBlur(40))
        return self.cache['shade'], self.cache['top']

    def scene(self, f, seg, a):
        sc = seg['scene']
        k0 = ease(a / 0.5)
        zoom = 1.0 + 0.07 * min(1.0, a / max(seg['dur'], 1.0))
        im = self.photo(sc)
        cw, ch = int(W / zoom), int(H / zoom)
        im = im.crop(((W - cw) // 2, (H - ch) // 2, (W + cw) // 2, (H + ch) // 2)).resize((W, H), Image.BILINEAR)
        shade, top = self.shade()
        im = Image.fromarray((np.asarray(im, dtype=float) * shade).astype(np.uint8), 'RGB')
        f.paste(im, (0, 0), top.point(lambda v: int(v * k0)))
        d = ImageDraw.Draw(f, 'RGBA')
        gold = self._gold()
        kt = ease((a - 0.3) / 0.35)
        tag = sc['tag']
        tf = F(40, 'Bold')
        tw = int(d.textlength(tag, font=tf)) + 56
        d.rounded_rectangle((60, 1010, 60 + tw, 1070), 30, fill=gold + (int(235 * kt),))
        d.text((60 + tw / 2, 1041), tag, font=tf, fill=(24, 12, 6, int(255 * kt)), anchor='mm')
        kn = ease((a - 0.5) / 0.4)
        head = sc.get('headline', sc['name'])
        d.text((60, 1150 - (1 - kn) * 18), head, font=fit_font(d, head, 96, 'Black', 960), fill=rl.WHITE + (int(255 * kn),), anchor='lm',
               stroke_width=4, stroke_fill=rl.NAVY + (255,))
        y = 1236
        for i, ln in enumerate(sc.get('lines', [])):
            kl = ease((a - 0.9 - i * 0.35) / 0.35)
            if kl <= 0:
                continue
            for j, piece in enumerate(rl.wrap_text(d, ln, F(44, 'Bold'), 960)[:2]):
                d.text((60, y + j * 54), piece, font=F(44, 'Bold'), fill=rl.WHITE + (int(255 * kl),), anchor='lm',
                       stroke_width=3, stroke_fill=rl.NAVY + (255,))
            y += 62 + 54 * (min(2, len(rl.wrap_text(d, ln, F(44, 'Bold'), 960))) - 1)
        if sc.get('photo_note'):
            rl.text_fit(d, (60, 1432), sc['photo_note'], 26, 'Medium', (216, 208, 200, int(235 * kt)), 960, anchor='lm')
        if sc.get('source_line'):
            rl.text_fit(d, (60, 1466), sc['source_line'], 26, 'Medium', (216, 208, 200, int(235 * kt)), 960, anchor='lm')
        if sc.get('image_credit'):
            rl.text_fit(d, (540, 1508), '写真：' + sc['image_credit'], 22, 'Medium', (200, 190, 180, 220), 1000)

    def hook_bg(self, f, t):
        """フックの背景: 最初の場面の写真を暗くして敷く（ゆっくり寄る）"""
        sc = rl.T.scenes[0]
        zoom = 1.0 + 0.05 * min(1.0, t / max(rl.T.T_HOOK, 1.0))
        im = self.photo(sc)
        cw, ch = int(W / zoom), int(H / zoom)
        im = im.crop(((W - cw) // 2, (H - ch) // 2, (W + cw) // 2, (H + ch) // 2)).resize((W, H), Image.BILINEAR)
        im = Image.fromarray((np.asarray(im, dtype=float) * 0.42).astype(np.uint8), 'RGB')
        _, top = self.shade()
        f.paste(im, (0, 0), top.point(lambda v: int(v * ease(t / 0.5))))

    # ---------- 地図 ----------
    def map_base(self):
        if 'map' not in self.cache:
            T = rl.T
            x0, y0, w, h = MAP_RECT
            mask, proj = world.country_silhouette(T.country['iso'], w, h, margin=26)
            edge = ImageChops.subtract(mask, mask.filter(ImageFilter.MinFilter(7)))
            layer = Image.new('RGBA', mask.size, (0, 0, 0, 0))
            layer.paste(Image.new('RGBA', mask.size, (92, 16, 24, 255)), (0, 0), mask.point(lambda v: int(v * 0.86)))
            layer.paste(Image.new('RGBA', mask.size, (214, 40, 52, 255)), (0, 0), edge.filter(ImageFilter.GaussianBlur(7)).point(lambda v: min(255, int(v * 1.6))))
            layer.paste(Image.new('RGBA', mask.size, (255, 96, 104, 255)), (0, 0), edge.point(lambda v: int(v * 0.8)))
            self.cache['map'] = (layer, proj)
        return self.cache['map']

    def to_px(self, lonlat):
        _, proj = self.map_base()
        x, y = proj(lonlat[0], lonlat[1])
        return MAP_RECT[0] + x, MAP_RECT[1] + y

    def km_px(self, km):
        _, proj = self.map_base()
        return abs(proj(0, 1)[1] - proj(0, 0)[1]) * km / 111.0

    def region_layer(self, r, k, t):
        """地域の帯（折れ線）と円を、光らせて描く（RGBA 全画面）"""
        col = r['color']
        lay = Image.new('RGBA', (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(lay)
        for band in r['bands']:
            pts = [self.to_px(p) for p in band]
            wd = max(6, int(self.km_px(float(r.get('width_km', 46))) * ease(k)))
            if len(pts) == 1:
                rr = self.km_px(float(r.get('radius_km', 60))) * ease(k)
                d.ellipse((pts[0][0] - rr, pts[0][1] - rr, pts[0][0] + rr, pts[0][1] + rr), fill=col + (190,), outline=col + (255,), width=3)
                continue
            d.line(pts, fill=col + (190,), width=wd, joint='curve')
            for p in (pts[0], pts[-1]):
                d.ellipse((p[0] - wd / 2, p[1] - wd / 2, p[0] + wd / 2, p[1] + wd / 2), fill=col + (190,))
        glow = lay.filter(ImageFilter.GaussianBlur(16))
        pulse = 0.75 + 0.25 * math.sin(t * 5)
        glow.putalpha(glow.getchannel('A').point(lambda v: min(255, int(v * 1.5 * pulse))))
        return Image.alpha_composite(glow, lay)

    def chip(self, d, cx, cy, text, col, size=34):
        font = F(size, 'Bold')
        w = int(d.textlength(text, font=font)) + 34
        d.rounded_rectangle((cx - w / 2, cy - 27, cx + w / 2, cy + 27), 27, fill=col + (255,), outline=(255, 255, 255, 210), width=2)
        d.text((cx, cy + 1), text, font=font, fill=(255, 255, 255, 255), anchor='mm')

    def map_frame(self, f, t, upto):
        """upto: ここまでに出ている MAP_SEGS の番号（-1 でまだ地図だけ）"""
        T = rl.T
        sg0 = T.MAP_SEGS[0]
        layer, _ = self.map_base()
        km = ease((t - sg0['start']) / 0.6)
        lay = layer.copy()
        lay.putalpha(ImageChops.multiply(lay.getchannel('A'), Image.new('L', lay.size, int(255 * km))))
        f.paste(lay, (MAP_RECT[0], MAP_RECT[1]), lay)
        shown = [(i, sg) for i, sg in enumerate(T.MAP_SEGS) if sg['kind'] in ('region', 'place') and sg['start'] <= t]
        for i, sg in shown:
            r = sg['region']
            if sg['kind'] == 'place':
                continue
            rl_img = self.region_layer(r, (t - sg['start']) / 0.5, t)
            f.paste(rl_img, (0, 0), rl_img)
        d = ImageDraw.Draw(f, 'RGBA')
        for i, sg in shown:
            r = sg['region']
            if sg['kind'] == 'region' and r.get('label_at'):
                x, y = self.to_px(r['label_at'])
                self.chip(d, x, y, 'レベル%d' % r['level'], r['color'])
        # 人気の街（いつも出ている。レベルが明かされたら色が付く）
        px, py = self.to_px(T.place['marker'])
        seg_place = next(sg for sg in T.MAP_SEGS if sg['kind'] == 'place')
        known = t >= seg_place['start']
        col = T.place_region['color'] if known else (255, 255, 255)
        ph = (t * 0.9) % 1.0
        rr = 12 + 46 * ph
        d.ellipse((px - rr, py - rr, px + rr, py + rr), outline=col + (int(230 * (1 - ph)),), width=4)
        d.ellipse((px - 13, py - 13, px + 13, py + 13), fill=col + (255,), outline=(20, 8, 8, 255), width=3)
        label = T.place['name'] + ('  レベル%d' % T.place_region['level'] if known else '')
        d.text((px + 6, py - 44), label, font=F(36, 'Bold'), fill=rl.WHITE + (255,), anchor='lm', stroke_width=4, stroke_fill=(20, 0, 4, 255))

    # ---------- 説明欄 ----------
    def badge(self, d, y, r, a):
        k = ease(a / 0.35)
        d.rounded_rectangle((60, y - 46, 60 + 300, y + 46), 28, fill=r['color'] + (int(255 * k),), outline=(255, 255, 255, int(190 * k)), width=3)
        d.text((210, y + 2), 'レベル%d' % r['level'], font=F(64), fill=(255, 255, 255, int(255 * k)), anchor='mm')
        d.text((390, y), r['sub'], font=fit_font(d, r['sub'], 42, 'Bold', 620), fill=rl.WHITE + (int(255 * k),), anchor='lm',
               stroke_width=3, stroke_fill=rl.NAVY + (255,))

    def info_region(self, f, sg, a):
        d = ImageDraw.Draw(f, 'RGBA')
        r = sg['region']
        self.badge(d, INFO_TOP + 60, r, a)
        kw = ease((a - 0.35) / 0.4)
        d.text((60, INFO_TOP + 150), 'どこ？', font=F(34, 'Bold'), fill=rl.MUTED + (int(255 * kw),), anchor='lm')
        wf = F(58, 'Bold')
        for i, ln in enumerate(rl.wrap_text(d, r['where'], wf, 960)[:3]):
            d.text((60, INFO_TOP + 220 + i * 70), ln, font=wf, fill=rl.WHITE + (int(255 * kw),), anchor='lm', stroke_width=3, stroke_fill=rl.NAVY + (255,))
        if r.get('note'):
            kn = ease((a - 1.2) / 0.4)
            nf = F(40, 'Bold')
            for i, ln in enumerate(rl.wrap_text(d, r['note'], nf, 960)[:3]):
                d.text((60, INFO_TOP + 220 + 70 * 2 + 50 + i * 54), ln, font=nf, fill=rl.MUTED + (int(255 * kn),), anchor='lm')

    info_place = info_region                      # 人気の街のレベルも、地域と同じ見せ方

    def info_turn(self, f, sg, a):
        d = ImageDraw.Draw(f, 'RGBA')
        for i, (text, size, col) in enumerate(rl.T.spec['turn'].get('lines', [])):
            k = ease((a - 0.2 - i * 0.5) / 0.4)
            c = rl.T._panel([[text, size, col, 'Black']])[0]
            d.text((540, INFO_TOP + 100 + i * 120), c[0], font=F(c[1], 'Black'), fill=c[2] + (int(255 * k),), anchor='mm',
                   stroke_width=4, stroke_fill=rl.NAVY + (255,))

    def info_caution(self, f, sg, a):
        d = ImageDraw.Draw(f, 'RGBA')
        T = rl.T
        d.text((60, INFO_TOP + 30), T.spec['caution'].get('head', 'ただし'), font=F(40, 'Bold'), fill=rl.MUTED + (int(255 * ease(a / 0.3)),), anchor='lm')
        y = INFO_TOP + 86
        for i, w in enumerate(T.country['why'][:3]):
            if not w.get('show', True):
                continue
            kw = ease((a - 0.3 - i * 0.5) / 0.35)
            if kw <= 0:
                continue
            tag = w.get('tag', '')
            tc = rl.why_color(tag)
            ico = rl.draw_icon(rl.why_kind(tag), 56, tc)
            f.paste(ico, (60, y + 4), ImageChops.multiply(ico.getchannel('A'), Image.new('L', ico.size, int(255 * kw))))
            tf = F(34, 'Bold')
            tw = int(d.textlength(tag, font=tf)) + 36
            d.rounded_rectangle((132, y, 132 + tw, y + 58), 29, fill=tc + (int(255 * kw),))
            d.text((132 + tw / 2, y + 30), tag, font=tf, fill=(255, 255, 255, int(255 * kw)), anchor='mm')
            bf = F(42, 'Bold')
            lines = rl.wrap_text(d, w['text'], bf, 1020 - (132 + tw + 18))[:3]
            for j, ln in enumerate(lines):
                d.text((132 + tw + 18, y + 26 + j * 50), ln, font=bf, fill=rl.WHITE + (int(255 * kw),), anchor='lm', stroke_width=2, stroke_fill=rl.NAVY + (255,))
            y += max(80, 50 * len(lines) + 34)

    def info_closing(self, f, sg, a):
        d = ImageDraw.Draw(f, 'RGBA')
        T = rl.T
        rows = sorted(T.regions, key=lambda r: -r['level'])
        y = INFO_TOP + 40
        for i, r in enumerate(rows):
            k = ease((a - 0.15 - i * 0.3) / 0.35)
            if k <= 0:
                continue
            font = F(36, 'Bold')
            self.chip(d, 168, y + 30, 'レベル%d' % r['level'], r['color'], 34)
            for j, ln in enumerate(rl.wrap_text(d, r['where'], font, 740)[:2]):
                d.text((300, y + 26 + (j - (len(rl.wrap_text(d, r['where'], font, 740)[:2]) - 1) / 2) * 42), ln, font=font,
                       fill=rl.WHITE + (int(255 * k),), anchor='lm', stroke_width=2, stroke_fill=rl.NAVY + (255,))
            y += 70 + 42 * (len(rl.wrap_text(d, r['where'], font, 740)[:2]) - 1)
        kt = ease((a - 0.3 - len(rows) * 0.3) / 0.4)
        for i, (text, size, col) in enumerate(T.spec['closing'].get('lines', [])):
            c = T._panel([[text, size, col, 'Black']])[0]
            d.text((540, y + 56 + i * 76), c[0], font=F(c[1], 'Black'), fill=c[2] + (int(255 * kt),), anchor='mm', stroke_width=3, stroke_fill=rl.NAVY + (255,))

    # ---------- フレーム ----------
    def frame(self, t):
        return self.post(self._frame(t), t)

    def _frame(self, t):
        T = rl.T
        f = self._blend_bg(t)
        if t >= T.T_TURN:
            self.embers(f, t)
        if t < T.T_HOOK:
            self.hook_bg(f, t)
            rl.hook_panel(f, t)
            return f
        if t < T.T_TURN:
            seg = next((s for s in T.SCENE_SEGS if s['start'] <= t < s['start'] + s['dur']), T.SCENE_SEGS[-1])
            self.scene(f, seg, t - seg['start'])
            return f
        if t >= T.T_COUNT_END:
            self.map_frame(f, T.T_COUNT_END - 0.01, len(T.MAP_SEGS) - 1)
            f = rl.dimmed(f, 0.4)
            panel(f, T.cta_panel, 1060, ease((t - T.T_COUNT_END) / 0.4), gap=14)
            return f
        idx = max(i for i, s in enumerate(T.MAP_SEGS) if s['start'] <= t)
        sg = T.MAP_SEGS[idx]
        a = t - sg['start']
        self.map_frame(f, t, idx)
        getattr(self, 'info_' + sg['kind'])(f, sg, a)
        if T.footnote:
            d = ImageDraw.Draw(f, 'RGBA')
            rl.text_fit(d, (540, 1508), T.say(T.footnote), 24, 'Medium', rl.MUTED + (210,), 1000)
        return f


rl.LAYOUT_CLASSES['place'] = PlaceRisk
