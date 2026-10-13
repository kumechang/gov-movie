"""1か国の「人気の場所」と「外務省の危険情報」を見比べる型（template: place_vs_risk）のテーマ読み込み。

流れ: フック → 人気の根拠（世界遺産・映画のロケ地・無形文化遺産・写真）を数枚 → 「ところが」→ 危険情報の地域を地図に出す
      → その人気の街のレベル → 結び（地域ごとにレベルが違う）→ CTA
実例: themes/turkey_place_risk.yaml（トルコ × イスタンブール）。

データの検証:
  ・危険レベルと地域・理由の文言は mofa.resolve が、公式の危険情報ページの本文と照合する（regions[] の where もここで照合）
  ・人気の根拠は facts.resolve が、Wikidata × ja.wikipedia で照合し、写真のライセンスを Commons の API で確かめる
  どちらも通ったものだけを使う。文言・色・順番はすべて YAML から読む。書き方は docs/THEME_SPEC.md「場所と危険情報」。
"""
import theme
from theme import ThemeError, _Vars
from tiertheme import TierTheme

LEVEL_COLORS = {4: (214, 20, 40), 3: (226, 70, 36), 2: (232, 150, 40), 1: (216, 188, 64), 0: (96, 160, 130)}   # 地図とバッジの色
LEVEL_SUB = {4: '退避してください（退避勧告）', 3: '渡航は止めてください（渡航中止勧告）', 2: '不要不急の渡航は止めてください',
             1: '十分注意してください', 0: '危険情報は出ていません'}


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
        pl = self._need(s, 'place')
        for k in ('name', 'marker'):
            self._need(pl, k, 'place.')
        self.place = dict(pl)
        # 危険情報の地域（地図に出す）。place: true の1件が、人気の街のレベル
        self.regions = []
        for r in mem.get('regions', []):
            for k in ('level', 'where'):
                self._need(r, k, 'regions[].')
            self.regions.append(dict(r, color=LEVEL_COLORS[r['level']], sub=LEVEL_SUB[r['level']], place=bool(r.get('place'))))
        pr = [r for r in self.regions if r['place']]
        if len(pr) != 1:
            raise ThemeError('regions に place: true の地域をちょうど1つ書いてください（人気の街が属する地域）')
        self.place_region = pr[0]
        self.danger = sorted((r for r in self.regions if not r['place']), key=lambda r: -r['level'])
        for r in self.danger:
            if not r.get('say'):
                raise ThemeError('地域 %s に say（読み上げ文）がありません' % r['where'])
            if not r.get("bands"):
                raise ThemeError('地域 %s に bands（地図上の位置 [[[経度,緯度],...],...]）がありません' % r['where'])
        if not self.place_region.get('say'):
            raise ThemeError('place: true の地域に say がありません')
        self.scenes = list(self._need(s, 'scenes'))
        for i, sc in enumerate(self.scenes):
            for k in ('kind', 'tag', 'name', 'say'):
                self._need(sc, k, 'scenes[%d].' % i)
            if sc.get('photo') and not sc.get('image'):
                raise ThemeError('scenes[%d]: 写真は facts.resolve で取得・検証してから使います（run.py 経由）' % i)
        for k in ('turn', 'caution', 'closing'):
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
        rd = self.country.get('risk_date') or ''
        v = _Vars(asof=self.asof, risk_date=('%s年%d月%d日' % (rd[:4], int(rd[5:7]), int(rd[8:10]))) if rd else '不明', country=self.country['short'], place=self.place['name'], level=self.level,
                  place_level=self.place_region['level'], n_scenes=len(self.scenes))
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
        L['place'] = self.say(self.place_region['say'])
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
        add('place', 'place', 5.0, 1.0, region=self.place_region)
        add('caution', 'caution', 5.0, 0.9)
        add('closing', 'closing', 5.0, 1.0)
        self.T_COUNT_END = t
        self.T_CTA = max(6.5, self.nd('cta') + 1.0)
        self.T_END = t + self.T_CTA + 0.4
        self.focus = None
        self.T_FOCUS = 0.0

    # ---------- 検証レポート ----------
    def report(self):
        lines = [
            'テーマ %s: %s と %s（%s 時点）場所×危険情報' % (self.id, self.country['short'], self.place['name'], self.asof),
            '国の最大レベル: %d  人気の街 %s の属する地域: %s（レベル%d）' % (self.level, self.place['name'], self.place_region['where'], self.place_region['level']),
            '危険情報の地域: ' + ' / '.join('レベル%d %s' % (r['level'], r['where']) for r in self.danger),
            '人気の根拠: ' + ' / '.join('%s（%s）' % (sc['name'], sc['kind']) for sc in self.scenes),
            '動画長: フック %.1f秒 / 人気の場面 %.1f〜%.1f秒 / 発表終了 %.1f秒 / 全体 %.1f秒%s' % (
                self.T_HOOK, self.T_HOOK, self.T_TURN, self.T_COUNT_END, self.T_END,
                '' if self.T_END >= 60 else '  ★60秒未満（クリエイターリワードの対象外）'),
        ]
        if self.estimated_keys:
            lines.append('読み上げ長は見積もり（narration.json に一致する音声なし）: %d文' % len(self.estimated_keys))
        lines += ['警告: ' + w for w in self.warnings]
        return '\n'.join(lines)
