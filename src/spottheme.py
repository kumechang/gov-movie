"""1か国の「人気の場所」と「外務省の危険情報」を見比べる型（template: place_vs_risk）のテーマ読み込み。

流れ: フック → 人気の根拠（世界遺産・映画のロケ地・無形文化遺産・写真）を数枚 → 「ところが」→ 危険情報の地域を地図に出す
      → その人気の街のレベル → 結び（地域ごとにレベルが違う）→ CTA
実例: themes/turkey_place_risk.yaml（トルコ × イスタンブール）。

データの検証:
  ・危険レベルと地域・理由の文言は mofa.resolve が、公式の危険情報ページの本文と照合する（regions[] の where もここで照合）
  ・人気の根拠は facts.resolve が、Wikidata × ja.wikipedia で照合し、写真のライセンスを Commons の API で確かめる
  どちらも通ったものだけを使う。文言・色・順番はすべて YAML から読む。書き方は docs/THEME_SPEC.md「場所と危険情報」。
"""
import math

import theme
import world
from theme import ThemeError, _Vars
from tiertheme import TierTheme

LEVEL_COLORS = {4: (214, 20, 40), 3: (226, 70, 36), 2: (232, 150, 40), 1: (216, 188, 64), 0: (96, 160, 130)}   # 地図とバッジの色
LEVEL_SUB = {4: '退避してください（退避勧告）', 3: '渡航は止めてください（渡航中止勧告）', 2: '不要不急の渡航は止めてください',
             1: '十分注意してください', 0: '危険情報は出ていません'}


def _km(a, b):
    """2点 [経度, 緯度] の大圏距離（km）"""
    la1, lo1, la2, lo2 = map(math.radians, (a[1], a[0], b[1], b[0]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(h))


def _in_ring(pt, ring):
    """点 [経度, 緯度] が多角形（リング）の内側か（光線法）"""
    x, y = pt
    inside = False
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i][0], ring[i][1]
        x2, y2 = ring[(i + 1) % n][0], ring[(i + 1) % n][1]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def _seg_km(pt, a, b):
    """点から線分 a-b までの距離（km。局所の平面近似）"""
    k = math.cos(math.radians(pt[1]))
    px, py = pt[0] * k * 111.32, pt[1] * 110.57
    ax, ay = a[0] * k * 111.32, a[1] * 110.57
    bx, by = b[0] * k * 111.32, b[1] * 110.57
    dx, dy = bx - ax, by - ay
    t = 0.0 if dx == dy == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _in_region(pt, r):
    """人気の場所の座標が、地図に描く地域の中か。州・県で塗る地域は、州の中で、かつ例外の円の外。帯・円の地域は、その幅・半径の中。国境で決まる地域は None（別に確かめる）"""
    if r.get('border'):
        return None
    if r.get('polys'):
        if any(_km(pt, h[:2]) <= h[2] for h in r.get('holes', [])):
            return False
        if any(_in_ring(pt, ring) for ring in r['polys']):
            return True
    for run in r.get('bands', []):
        if len(run) == 1:
            if _km(pt, run[0]) <= float(r.get('radius_km', 0)):
                return True
        elif any(_seg_km(pt, a, b) <= float(r.get('width_km', 0)) / 2 for a, b in zip(run, run[1:])):
            return True
    return False


def _dense(band, step_km=10.0):
    """折れ線を、約 step_km ごとの点に刻む（最も近い点を探すため）"""
    if len(band) == 1:
        return [tuple(band[0])]
    out = []
    for p, q in zip(band, band[1:]):
        n = max(1, int(_km(p, q) / step_km))
        out += [(p[0] + (q[0] - p[0]) * i / n, p[1] + (q[1] - p[1]) * i / n) for i in range(n)]
    return out + [tuple(band[-1])]


class SpotTheme(TierTheme):
    layout = 'place'
    is_pref = False

    def __init__(self, spec, narration_json=None):
        self.spec = spec
        self.style = spec.get('style') or {}
        self.warnings = []
        self.estimated_keys = []
        self._load()
        self._vars()
        self._narration_cache(narration_json)
        self._panels()
        self._timeline()

    # ---------- データ ----------
    def _load(self):
        s = self.spec
        self.id = self._need(s, 'id')
        if s.get('template') != 'place_vs_risk':
            raise ThemeError('template が place_vs_risk ではありません: %s' % s.get('template'))
        self.metric, self.year, self.unit = s.get('metric', ''), s.get('year', ''), s.get('unit', '')
        src = self._need(s, 'source')
        self._need(src, 'name', 'source.')
        lic = src.get('license') or {}
        if not (lic.get('commercial') is True and lic.get('credit_lines')):
            self.warnings.append('source.license が未記入です（商用利用の可否と出典・加工の表記を確認して記入してください）')
        if not str(s.get('verification', '')).strip():
            raise ThemeError('verification（検証方法の記録）が未記入です。検証できていない内容は載せません')
        td = s.get('tier_data')
        if not td:
            raise ThemeError('tier_data がありません。source.fetch: mofa_risk のテーマは、先に取得・照合してください（run.py 経由）')
        self.asof, self.fetched = td['asof'], td['fetched']
        mem = (s.get('members') or [None])[0]
        if not mem:
            raise ThemeError('members に対象の国を1つ書いてください')
        row = next((c for c in td['countries'] if c['code'] == str(mem['code'])), None)
        if row is None:
            raise ThemeError('国コード %s が取得データにありません' % mem['code'])
        self.country = dict(row, short=mem.get('label', row['short']), iso=mem.get('iso'), marker=mem.get('marker'),
                            why=list(mem.get('why', [])))
        self.level = row['level']
        # 危険情報の地域。bands があるものは地図に描く危険地域、無いものは「人気の場所が属する地域のレベル」（places から参照する）
        self.regions = []
        for r in mem.get('regions', []):
            for k in ('level', 'where'):
                self._need(r, k, 'regions[].')
            self.regions.append(dict(r, color=LEVEL_COLORS[r['level']], sub=LEVEL_SUB[r['level']]))
        for r in self.regions:                         # 国境からの距離で決まる地域（例: タイ国境から30km以内）は、国境線のデータから帯を作る
            b = r.get('border')
            if b:
                runs = world.border_runs(self.country['iso'], b['with'])
                if not runs:
                    raise ThemeError('地域「%s」: %s との国境線が見つかりません' % (r['where'], b['with']))
                r.update(bands=[[list(p) for p in run] for run in runs], width_km=2 * float(b['km']), clip=True, edge_km=float(b['km']))
        for r in self.regions:                         # 州・県の単位で決まる地域は、Natural Earth の州の境界から塗る（provinces: 英語名）
            if r.get('provinces'):
                try:
                    r['polys'] = world.admin1_rings(self.country['iso'], r['provinces'], r.get('lat_max'), r.get('lat_min'))
                except KeyError as e:
                    raise ThemeError('地域「%s」: %s' % (r['where'], e.args[0]))
        for r in self.regions:                         # rings: 州の境界データが無い地域（未承認の地域など）を、座標の多角形で書く（概算。位置の目安）
            if r.get('rings'):
                r['polys'] = list(r.get('polys', [])) + [[tuple(pt) for pt in ring] for ring in r['rings']]
        self.danger = [r for r in self.regions if r.get('bands') or r.get('polys')]
        for r in self.danger:
            if not r.get('say'):
                raise ThemeError('地域 %s に say（読み上げ文）がありません' % r['where'])
        by_where = {r['where']: r for r in self.regions}
        absent = {a['place']: a['names'] for a in mem.get('absent_places', [])}
        # 人気の場所。status は3種類: region（その場所のレベルがある地域）／in_region（危険地域の中）／absent（危険レベルの地域に載っていない）
        self.places = []
        for i, p in enumerate(self._need(s, 'places')):
            for k in ('name', 'marker'):
                self._need(p, k, 'places[%d].' % i)
            q = dict(p, side=p.get('side', 'above-right'))
            if p.get('region'):
                r = by_where.get(p['region'])
                if r is None or r.get('bands'):
                    raise ThemeError('places[%d] %s: region「%s」が members[0].regions にありません（bands の無い地域を指定）' % (i, p['name'], p['region']))
                q.update(status='region', rg=r)
            elif p.get('in_region'):
                r = by_where.get(p['in_region'])
                if r is None or not (r.get('bands') or r.get('polys')):
                    raise ThemeError('places[%d] %s: in_region「%s」が危険地域（bands あり）にありません' % (i, p['name'], p['in_region']))
                q.update(status='in_region', rg=r)
            elif p.get('absent') is True:
                if p['name'] not in absent:
                    raise ThemeError('places[%d] %s: members[0].absent_places に載っていない場所は absent にできません（公式ページに載っていないことを検証するため）' % (i, p['name']))
                q.update(status='absent', rg=None)
            else:
                raise ThemeError('places[%d] %s に region / in_region / absent のどれかを書いてください' % (i, p['name']))
            self.places.append(q)
        border_pts = [tuple(pt) for r in self.regions if r.get('border') for run in r['bands'] for pt in run]
        for p in self.places:                          # 国境までの距離（地図上の概算）。in_region の主張が、距離と食い違わないことも確かめる
            p['border_km'] = min((_km(p['marker'], pt) for pt in border_pts), default=None)
            if p['status'] == 'in_region' and _in_region(p['marker'], p['rg']) is False:
                raise ThemeError('places %s: 座標が、地図に描く地域「%s」の中にありません（州・帯・円の範囲を確かめてください）' % (p['name'], p['rg']['where']))
            if p['status'] == 'in_region' and p['rg'].get('border') and p['border_km'] > p['rg']['edge_km']:
                raise ThemeError('places %s: 国境まで約%dkm あり、「%s」（国境から%skm以内）の中とは言えません（座標か地域を確かめてください）'
                                 % (p['name'], p['border_km'], p['rg']['where'], p['rg']['border']['km']))
        names = [p['name'] for p in self.places]
        if len(set(names)) != len(names):
            raise ThemeError('places の name が重複しています: %s' % names)
        self.level_places = [p for p in self.places if p['status'] == 'region']
        self.place_groups = []                         # 同じ地域に属する場所は、1つの説明にまとめる（出てくる順）
        for p in self.level_places:
            g = next((g for g in self.place_groups if g['region'] is p['rg']), None)
            if g is None:
                if not p['rg'].get('say'):
                    raise ThemeError('地域「%s」に say（読み上げ文）がありません（places から参照している地域）' % p['rg']['where'])
                g = dict(region=p['rg'], places=[])
                self.place_groups.append(g)
            g['places'].append(p)
        self.absent_places = [p for p in self.places if p['status'] == 'absent']
        if self.absent_places:
            self._need(s, 'others')
            self._need(s['others'], 'say', 'others.')
        # 距離（地図上のおおよその位置から計算する概算）
        self.dist = None
        if s.get('distance'):
            d = s['distance']
            self._need(d, 'say', 'distance.')
            src = next((p for p in self.places if p['name'] == d.get('from')), None)
            if src is None:
                raise ThemeError('distance.from「%s」が places にありません' % d.get('from'))
            targets = [r for r in self.danger if r['level'] == int(d['level'])]
            if not targets:
                raise ThemeError('distance.level=%s の危険地域がありません' % d['level'])
            cand = []
            for r in targets:
                for b in list(r.get('bands', [])) + [list(ring) + [ring[0]] for ring in r.get('polys', [])]:      # 帯・円と、州の外周（閉じた折れ線）
                    for pt in _dense(b):
                        cand.append((_km(src['marker'], pt) - r.get('edge_km', 0.0), pt, r))
            d_edge, pt, r = min(cand, key=lambda x: x[0])
            d_edge = max(0.0, d_edge)
            d_all = d_edge + r.get('edge_km', 0.0)
            k = (d_edge / d_all) if d_all else 0.0                # 国境線の点ではなく、地域の縁（国境から edge_km の手前）まで線を引く
            end = (src['marker'][0] + (pt[0] - src['marker'][0]) * (1 - (r.get('edge_km', 0.0) / d_all if d_all else 0)),
                   src['marker'][1] + (pt[1] - src['marker'][1]) * (1 - (r.get('edge_km', 0.0) / d_all if d_all else 0)))
            step = float(d.get('round', 50))
            self.dist = dict(src=src, level=int(d['level']), km=d_edge, point=end, km_round=int(round(d_edge / step)) * int(step))

        self.scenes = list(self._need(s, 'scenes'))
        for i, sc in enumerate(self.scenes):
            for k in ('kind', 'tag', 'name', 'say'):
                self._need(sc, k, 'scenes[%d].' % i)
            if sc.get('photo') and not sc.get('image'):
                raise ThemeError('scenes[%d]: 写真は facts.resolve で取得・検証してから使います（run.py 経由）' % i)
        for k in ('turn', 'closing') + (('caution',) if s.get('caution') else ()):
            self._need(s, k)
            self._need(s[k], 'say', k + '.')
        self.footnote = s.get('footnote', '')
        self.uses_map = True
        self.extra_credits = list(s.get('extra_credits', []))
        for sc in self.scenes:
            if sc.get('image_credit'):
                self.extra_credits.append('写真：%s（%s）' % (sc['image_credit'], sc['name']))
            if sc.get('source_line'):
                self.extra_credits.append(sc['source_line'])
        self.TIERS = []                                # TierTheme の部品（_vars など）が参照する
        self.subset = True

    def _vars(self):
        self._vars0()
        v = self.V
        for i, p in enumerate(self.places):
            if p.get('border_km') is not None:
                v['border_km_%d' % i] = int(round(p['border_km'] / 5.0)) * 5
        for sc in self.scenes:                         # 場面の文言でも、{border_km_0} のような変数が使える
            for k in ('lines', 'photo_note', 'source_line'):
                if sc.get(k):
                    sc[k] = [self.say(x) for x in sc[k]] if isinstance(sc[k], list) else self.say(sc[k])

    def _vars0(self):
        rd = self.country.get('risk_date') or ''
        v = _Vars(asof=self.asof, risk_date=('%s年%d月%d日' % (rd[:4], int(rd[5:7]), int(rd[8:10]))) if rd else '不明', country=self.country['short'], level=self.level,
                  n_scenes=len(self.scenes), dist_km=('{:,}'.format(self.dist['km_round']) if self.dist else ''))
        self.V = v

    # ---------- 読み上げ ----------
    def narration_lines(self):
        s = self.spec
        L = {}
        for i, h in enumerate(s['hooks']):
            L['hook%d' % (i + 1)] = self.say(h['say'])
        for i, sc in enumerate(self.scenes):
            L['scene:%d' % i] = self.say(sc['say'])
        L['turn'] = self.say(s['turn']['say'])
        for i, r in enumerate(self.danger):
            L['region:%d' % i] = self.say(r['say'])
        if self.dist:
            L['distance'] = self.say(s['distance']['say'])
        for i, g in enumerate(self.place_groups):
            L['place:%d' % i] = self.say(g['region']['say'])
        if self.absent_places:
            L['others'] = self.say(s['others']['say'])
        if s.get('caution'):
            L['caution'] = self.say(s['caution']['say'])
        L['closing'] = self.say(s['closing']['say'])
        L['cta'] = self.say(s['cta']['say'])
        return L

    # ---------- 時間割 ----------
    def _timeline(self):
        s = self.spec
        self.HOOK_SEGS = []
        t = 0.0
        for i, h in enumerate(s['hooks']):
            key = 'hook%d' % (i + 1)
            d = max(float(h['min']), self.nd(key) + float(h['gap']))
            self.HOOK_SEGS.append(dict(key=key, start=t, dur=d, y=h['y'], fade=h['fade']))
            t += d
        self.T_HOOK = t
        self.SCENE_SEGS = []
        for i, sc in enumerate(self.scenes):
            key = 'scene:%d' % i
            d = max(float(sc.get('min', 6.0)), self.nd(key) + 0.9)
            self.SCENE_SEGS.append(dict(key=key, start=t, dur=d, scene=sc, index=i))
            t += d
        self.T_TURN = t                                # ここから恐怖演出（背景・音が切り替わる）
        self.MAP_SEGS = []

        def add(kind, key, minimum, pad, **kw):
            nonlocal t
            d = max(minimum, self.nd(key) + pad)
            self.MAP_SEGS.append(dict(kind=kind, key=key, start=t, dur=d, **kw))
            t += d

        add('turn', 'turn', 3.4, 0.7)
        for i, r in enumerate(self.danger):
            add('region', 'region:%d' % i, 4.2, 0.9, region=r, index=i)
        for i, g in enumerate(self.place_groups):
            if self.dist and any(p['name'] == self.dist['src']['name'] for p in g['places']):
                add('distance', 'distance', 4.0, 0.9, dist=self.dist)
            add('place', 'place:%d' % i, 4.6, 1.0, region=g['region'], places=g['places'], index=i)
        if self.absent_places:
            add('others', 'others', 4.0, 1.0, places=self.absent_places)
            if self.dist and self.dist['src']['status'] == 'absent':          # 載っていない場所から、レベル3の地域までの距離
                add('distance', 'distance', 4.0, 0.9, dist=self.dist)
        if s.get('caution'):
            add('caution', 'caution', 5.0, 0.9)
        add('closing', 'closing', 5.0, 1.0)
        # 地図の場所の印が、いつ色づくか（その場所の説明が始まる時刻）
        for p in self.places:
            p['t_reveal'] = next((sg['start'] for sg in self.MAP_SEGS
                                  if (sg['kind'] == 'place' and p in sg['places']) or (sg['kind'] == 'others' and p in sg['places'])
                                  or (sg['kind'] == 'region' and p['status'] == 'in_region' and sg['region'] is p['rg'])), None)
        self.T_COUNT_END = t
        self.T_CTA = max(6.5, self.nd('cta') + 1.0)
        self.T_END = t + self.T_CTA + 0.4
        self.focus = None
        self.T_FOCUS = 0.0

    # ---------- 検証レポート ----------
    def report(self):
        lines = [
            'テーマ %s: %s（%s 時点）場所×危険情報' % (self.id, self.country['short'], self.asof),
            '国の最大レベル: %d' % self.level,
            '危険情報の地域: ' + ' / '.join('レベル%d %s' % (r['level'], r['where']) for r in self.danger),
            '人気の場所: ' + ' / '.join('%s（%s）' % (p['name'], {'region': 'レベル%s' % (p['rg']['level'] if p['rg'] else ''), 'in_region': 'レベル%s の地域内' % (p['rg']['level'] if p['rg'] else ''), 'absent': '危険情報の地域に載っていない'}[p['status']]) for p in self.places),
            ('距離: %s から レベル%d の地域まで 約%d km（地図上の概算）' % (self.dist['src']['name'], self.dist['level'], self.dist['km_round'])) if self.dist else '距離: なし',
            '人気の根拠: ' + ' / '.join('%s（%s）' % (sc['name'], sc['kind']) for sc in self.scenes),
            '動画長: フック %.1f秒 / 人気の場面 %.1f〜%.1f秒 / 発表終了 %.1f秒 / 全体 %.1f秒%s' % (
                self.T_HOOK, self.T_HOOK, self.T_TURN, self.T_COUNT_END, self.T_END,
                '' if self.T_END >= 60 else '  ★60秒未満（クリエイターリワードの対象外）'),
        ]
        if self.estimated_keys:
            lines.append('読み上げ長は見積もり（narration.json に一致する音声なし）: %d文' % len(self.estimated_keys))
        lines += ['警告: ' + w for w in self.warnings]
        return '\n'.join(lines)
