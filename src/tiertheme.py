"""段階ボード（template: tier_board）のテーマ読み込み。

項目を「段階（レベル）」ごとにまとめ、段階を順に発表して、その段階に入る項目の名前を1つずつ並べていく型。
実例: 外務省の危険レベル（レベル1→4の順に、そのレベルの地域を含む国を読み上げる）。
  themes/world_risk_levels.yaml

データは source.fetch: mofa_risk なら src/mofa.py が取得・照合して spec['tier_data'] に入れる（このクラスは取得しない）。
tier_data = {asof, fetched, countries: [{code, short, level, area, ...}], excluded: [...]}

文言・色・段階の定義はすべて YAML から読む。書き方は docs/THEME_SPEC.md。
映像は render_list.Tiers、音声は audio.build_tiers が、ここで作った TierTheme を読む。
"""
import json
import os

import theme
from theme import ThemeError, _Vars

SEC_PER_CHAR = theme.SEC_PER_CHAR


class TierTheme:
    layout = 'tiers'
    is_pref = False
    uses_map = False

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

    def _need(self, d, key, where=''):
        if d.get(key) in (None, ''):
            raise ThemeError('%s%s が未設定です' % (where, key))
        return d[key]

    # ---------- データ ----------
    def _load(self):
        s = self.spec
        self.id = self._need(s, 'id')
        if s.get('template') != 'tier_board':
            raise ThemeError('template が tier_board ではありません: %s' % s.get('template'))
        self.metric = self._need(s, 'metric')
        self.year = self._need(s, 'year')
        self.unit = s.get('unit', '')
        src = self._need(s, 'source')
        self._need(src, 'name', 'source.')
        if not src.get('url'):
            self.warnings.append('source.url が未記入です（出典URLを確認して記入してください）')
        lic = src.get('license') or {}
        if src.get('fetch') in ('estat', 'mofa_risk') and not (lic.get('commercial') is True and lic.get('credit_lines')):
            self.warnings.append('source.license が未記入です（商用利用の可否と出典・加工の表記を確認して記入してください）')
        if not str(s.get('verification', '')).strip():
            raise ThemeError('verification（検証方法の記録）が未記入です。検証できていない数字は載せません')
        td = s.get('tier_data')
        if not td:
            raise ThemeError('tier_data がありません。source.fetch: mofa_risk のテーマは、先に取得・照合してください'
                             '（run.py 経由。TierTheme は取得しません）')
        self.asof = td['asof']
        self.fetched = td['fetched']
        self.excluded = td.get('excluded', [])
        tiers = self._need(s, 'tiers')
        if not isinstance(tiers, list) or not tiers:
            raise ThemeError('tiers が空です')
        # 対象の国: members で指定（省略すると、取得できた国すべて）
        if s.get('members'):
            by_code = {c['code']: c for c in td['countries']}
            universe = []
            for m in s['members']:
                code = str(self._need(m, 'code', 'members[].'))
                r = by_code.get(code)
                if r is None:
                    raise ThemeError('members の国コード %s が取得データにありません' % code)
                universe.append(dict(r, short=m.get('label', r['short']), where=m.get('where', ''), why=list(m.get('why', [])),
                                     also=list(m.get('also', [])), say=m.get('say')))
            self.subset = True
        else:
            universe = [dict(c, where='', why=[], also=[], say=None) for c in td['countries']]
            self.subset = False
        self.TIERS = []
        for t in tiers:
            for k in ('level', 'title', 'sub', 'color', 'say'):
                if k not in t or t[k] in (None, ''):
                    raise ThemeError('tiers[].%s が未設定です' % k)
            if len(t['color']) != 3:
                raise ThemeError('tiers[].color は [R,G,B] です: %r' % (t['color'],))
            members = [dict(m) for m in universe if m['level'] == t['level']]
            if not members:
                raise ThemeError('レベル%s に該当する国がありません' % t['level'])
            spot = bool(t.get('spotlight', False))
            if spot:
                for m in members:
                    if not m.get('say'):
                        raise ThemeError('スポットライトの国 %s に say（読み上げ文）がありません' % m['short'])
                    if not (m['where'] or m['why']):
                        self.warnings.append('スポットライトの国 %s に where / why がありません（画面が国名とレベルだけになります）' % m['short'])
            self.TIERS.append(dict(level=t['level'], title=t['title'], sub=t['sub'], color=tuple(t['color']),
                                   names=bool(t.get('names', True)) or spot, spotlight=spot, say=t['say'], members=members,
                                   count=len(members)))
        levels = [t['level'] for t in self.TIERS]
        if len(set(levels)) != len(levels):
            raise ThemeError('tiers の level が重複しています: %s' % levels)
        listed = {t['level'] for t in self.TIERS}
        missed = sorted({c['level'] for c in universe if c['level'] > 0} - listed)
        if missed:
            self.warnings.append('tiers に書かれていないレベルの国があります（画面に出ません）: %s' % missed)
        for t in self.TIERS:
            if t['names']:
                shorts = [m['short'] for m in t['members']]
                if len(set(shorts)) != len(shorts):
                    raise ThemeError('レベル%s に同じ表示名があります: %s' % (t['level'], shorts))
        self.universe = universe
        self.footnote = s.get('footnote', '')

    # ---------- 文言テンプレートの変数 ----------
    def _vars(self):
        v = _Vars(metric=self.metric, year=self.year, asof=self.asof, total=len(self.universe))
        for t in self.TIERS:
            v['n%s' % t['level']] = t['count']
        v['n_high'] = sum(t['count'] for t in self.TIERS if t['level'] >= 3)
        v['n_any'] = sum(t['count'] for t in self.TIERS if t['level'] >= 1)
        ex = '' if self.subset else '・'.join(r['short'] for r in self.excluded)   # 国を指定したときは、除外は問題にならない（指定した国が除外されたら取得時に止まる）
        v['excluded'] = ex
        v['excluded_note'] = ('公式ページとの照合で食い違いがあった国（%s）は除いています。' % ex) if ex else ''
        self.V = v

    def say(self, template, **extra):
        v = _Vars(self.V)
        v.update(extra)
        try:
            return template.format_map(v)
        except (ValueError, IndexError) as e:
            raise ThemeError('文言テンプレートの書式エラー: %r (%s)' % (template, e))

    # ---------- 読み上げ ----------
    def narration_lines(self):
        L = {}
        for i, h in enumerate(self.spec['hooks']):
            L['hook%d' % (i + 1)] = self.say(h['say'])
        for t in self.TIERS:
            L['tier:%s' % t['level']] = self.say(t['say'], level=t['level'], title=t['title'], sub=t['sub'], count=t['count'])
            if t['names']:
                for m in t['members']:
                    L['item:' + m['code']] = self.say(m['say']) if t['spotlight'] else m['short']
        L['cta'] = self.say(self.spec['cta']['say'])
        return L

    def _narration_cache(self, path):
        cache = {}
        if path and os.path.exists(path):
            with open(path, encoding='utf-8') as f:
                cache = json.load(f)
        self.narration = {}
        speed = float(self.spec.get('voice', {}).get('speed', 1.28))
        for k, text in self.narration_lines().items():
            c = cache.get(k)
            if c and c.get('text') == text:
                self.narration[k] = c['dur']
            else:
                self.narration[k] = len(text) * SEC_PER_CHAR * 1.28 / speed + 0.15
                self.estimated_keys.append(k)

    def nd(self, key):
        return self.narration.get(key, 0.0)

    def _panels(self):
        s = self.spec
        self.hook_panels = [self._panel(h['panel']) for h in s['hooks']]
        self.cta_panel = self._panel(s['cta']['panel'])
        self.voice = s.get('voice', {})
        self.credit = self.voice.get('credit', '')

    def _panel(self, rows):
        out = []
        for text, size, color, weight in rows:
            named = dict(theme.NAMED_COLORS)
            named.update({k: tuple(v) for k, v in (self.style.get('named_colors') or {}).items()})
            if color not in named:
                raise ThemeError('不明な色名: %s（使える色: %s）' % (color, '/'.join(named)))
            if weight not in theme.WEIGHTS:
                raise ThemeError('不明な太さ: %s（使える太さ: %s）' % (weight, '/'.join(theme.WEIGHTS)))
            out.append((self.say(text), int(size), named[color], weight))
        return out

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
        self.SEQ = []
        for ti, tier in enumerate(self.TIERS):
            key = 'tier:%s' % tier['level']
            start = t
            intro = max(2.0, self.nd(key) + 0.5)
            t += intro
            items = []
            if tier['names']:
                for m in tier['members']:
                    k = 'item:' + m['code']
                    d = max(4.2, self.nd(k) + 1.0) if tier['spotlight'] else max(0.5, self.nd(k) + 0.12)
                    items.append(dict(name=m['short'], code=m['code'], start=t, dur=d, key=k, member=m))
                    t += d
                t += 0.6                                   # 段階の最後の間
            else:
                t += 1.2
            self.SEQ.append(dict(level=tier['level'], tier=tier, start=start, dur=t - start, intro=intro, key=key,
                                 items=items, last=ti == len(self.TIERS) - 1))
        self.T_COUNT_END = t
        self.T_FOCUS = 0.0
        self.T_CTA = max(7.0, self.nd('cta') + 1.0)
        self.T_END = self.T_COUNT_END + self.T_CTA + 0.4
        self.focus = None

    # ---------- 検証レポート・投稿文 ----------
    def report(self):
        lines = [
            'テーマ %s: %s（%s 時点）段階ボード %d 段階%s' % (self.id, self.metric, self.asof, len(self.TIERS),
                                                           '（対象 %d か国を指定）' % len(self.universe) if self.subset else ''),
            '出典: %s  URL: %s' % (self.spec['source']['name'], self.spec['source'].get('url') or '（未記入）'),
            '段階ごとの件数: ' + ' / '.join('%s %d' % (t['title'], t['count']) for t in self.TIERS),
            '名前を並べる段階: ' + '、'.join('%s（%d件%s）' % (t['title'], t['count'], '・詳しく見せる' if t['spotlight'] else '') for t in self.TIERS if t['names']),
            '動画長: フック %.1f秒 / 発表終了 %.1f秒 / 全体 %.1f秒%s' % (
                self.T_HOOK, self.T_COUNT_END, self.T_END,
                '' if self.T_END >= 60 else '  ★60秒未満（クリエイターリワードの対象外）'),
        ]
        if self.excluded and not self.subset:
            lines.append('照合で除外: ' + '、'.join(r['name'] for r in self.excluded))
        if self.estimated_keys:
            lines.append('読み上げ長は見積もり（narration.json に一致する音声なし）: %d文' % len(self.estimated_keys))
        lines += ['警告: ' + w for w in self.warnings]
        return '\n'.join(lines)

    def post_md(self):
        return theme.post_md(self)
