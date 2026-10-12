"""一覧型テンプレート（template: ranked_list）のテーマ読み込み。

「項目＋値」の一覧を順位つきで見せる動画。見せ方は layout で選ぶ:
  grid    カード一覧（3列。最下位から順に埋まり、最後に1位）
  scroll  横スクロール（カードが右から流れ、順に発表）
  steps   階段（少数項目を棒の長さで比べる）

データの入れ方は2通り:
  values: 47都道府県の値（e-Stat 取得で埋まる）。show/n で上位・下位から n 件を使う。順位・色は47県全体で決める
  items:  [{name, value, note?}] を直接書く（都道府県以外の属性別など）

文言・色・数値はすべて YAML から読む（src/ にテーマ固有の文言は置かない）。書き方は docs/THEME_SPEC.md。
映像は render_list.py、音声は audio.build_list が、ここで作った ListTheme を読む。
"""
import json
import math
import os

import theme
from theme import ThemeError, _Vars, full

LAYOUTS = ('grid', 'scroll', 'steps')
DEFAULT_N = {'grid': 11, 'scroll': 47, 'steps': 5}
MAX_N = {'grid': 12, 'scroll': 47, 'steps': 6}
SEC_PER_CHAR = theme.SEC_PER_CHAR


class ListTheme:
    def __init__(self, spec, narration_json=None):
        self.spec = spec
        self.warnings = []
        self.estimated_keys = []
        self._load()
        self._vars()
        self._narration_cache(narration_json)
        self._panels()
        self._timeline()

    # ---------- データ ----------
    def _need(self, d, key, where=''):
        if d.get(key) in (None, ''):
            raise ThemeError('%s%s が未設定です' % (where, key))
        return d[key]

    def _load(self):
        s = self.spec
        self.id = self._need(s, 'id')
        if s.get('template') != 'ranked_list':
            raise ThemeError('template が ranked_list ではありません: %s' % s.get('template'))
        self.layout = s.get('layout', 'grid')
        if self.layout not in LAYOUTS:
            raise ThemeError('未対応の layout: %s（使えるもの: %s）' % (self.layout, '/'.join(LAYOUTS)))
        self.metric = self._need(s, 'metric')
        self.year = self._need(s, 'year')
        self.unit = self._need(s, 'unit')
        self.decimals = int(s.get('decimals', 2))
        self.suffix = s.get('value_suffix', '')
        self.higher_first = s.get('rank_order', 'desc') == 'desc'
        src = self._need(s, 'source')
        self._need(src, 'name', 'source.')
        if not src.get('url'):
            self.warnings.append('source.url が未記入です（出典URLを確認して記入してください）')
        lic = src.get('license') or {}
        if src.get('fetch') == 'estat' and not (lic.get('commercial') is True and lic.get('credit_lines')):
            self.warnings.append('source.license が未記入です（商用利用の可否と出典・加工の表記を確認して記入してください）')
        if not str(s.get('verification', '')).strip():
            raise ThemeError('verification（検証方法の記録）が未記入です。検証できていない数字は載せません')

        if s.get('values') and s.get('items'):
            raise ThemeError('values と items は同時に書けません')
        if s.get('values'):
            data = theme.normalize_pref_values(s['values'], self.decimals)
            pairs = [(n, data[theme.full(p)], True) for p in theme.PREFS for n in [theme.full(p)]]
        elif s.get('items'):
            pairs = []
            for it in s['items']:
                v = it.get('value')
                if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
                    raise ThemeError('%s の値が数値ではありません: %r' % (it.get('name'), v))
                if not it.get('name'):
                    raise ThemeError('items に name のない項目があります')
                pairs.append((str(it['name']), round(float(v), self.decimals), False))
            if len({p[0] for p in pairs}) != len(pairs):
                raise ThemeError('items の name が重複しています')
        elif s.get('source', {}).get('fetch') == 'estat':
            raise ThemeError('values がありません。source.fetch: estat のテーマは、先に e-Stat から取得してください'
                             '（run.py / fetch_estat.py 経由。ListTheme は取得しません）')
        else:
            raise ThemeError('values か items のどちらかが必要です')
        self.is_pref = bool(s.get('values'))
        self.notes = {it['name']: it.get('note', '') for it in s.get('items', [])}
        self.ALL = {n: v for n, v, _ in pairs}
        if len(self.ALL) < 2:
            raise ThemeError('項目が2件未満です')

        avg = s.get('average')
        self.AVG = float(avg) if avg is not None else None
        if self.AVG is not None and not min(self.ALL.values()) <= self.AVG <= max(self.ALL.values()):
            raise ThemeError('全国値 %s が最小〜最大の範囲外です。年次・単位の取り違えの可能性があります' % self.AVG)

        # 順位は全項目で決める（同率あり）。表示は show（top/bottom）の n 件
        order = sorted(self.ALL.items(), key=lambda kv: -kv[1] if self.higher_first else kv[1])
        self.RANK, prev, r = {}, None, 0
        for i, (n, v) in enumerate(order):
            if v != prev:
                r, prev = i + 1, v
            self.RANK[n] = r
        self.TIE = {n for n in self.RANK if sum(1 for m in self.RANK if self.RANK[m] == self.RANK[n]) > 1}
        self.n = int(s.get('n', DEFAULT_N[self.layout]))
        if not 1 <= self.n <= min(MAX_N[self.layout], len(order)):
            raise ThemeError('n=%d は %s レイアウトでは 1〜%d にしてください' % (self.n, self.layout, min(MAX_N[self.layout], len(order))))
        self.show = s.get('show', 'top')
        if self.show not in ('top', 'bottom'):
            raise ThemeError('show は top か bottom です: %s' % self.show)
        shown = order[:self.n] if self.show == 'top' else order[-self.n:]
        # 同率の途中で切らない（境界の同率グループは丸ごと外す。外した結果 n が減る）
        rest = order[self.n:] if self.show == 'top' else order[:-self.n]
        edge = shown[-1] if self.show == 'top' else shown[0]
        nb = rest[0] if self.show == 'top' and rest else (rest[-1] if rest else None)
        if nb and self.RANK[nb[0]] == self.RANK[edge[0]]:
            cut = self.RANK[edge[0]]
            shown = [kv for kv in shown if self.RANK[kv[0]] != cut]
            if not shown:
                raise ThemeError('n=%d では同率グループを丸ごと含められません。n を増やしてください' % self.n)
            self.warnings.append('境界の同率（%d位）を丸ごと除くため、表示は %d 件になりました' % (cut, len(shown)))
        self.n = len(shown)
        self.TIERS = theme.build_tiers(self.ALL.values(), s.get('tiers'), self.decimals)
        # ITEMS は発表順（画面の順位が小さい側が最後＝クライマックス）
        shown = list(reversed(shown)) if self.show == 'top' else shown
        self.ITEMS = [dict(name=n, val=v, rank=self.RANK[n], tie=n in self.TIE, tier=self.tier(v),
                           pref=self.is_pref, note=self.notes.get(n, '')) for n, v in shown]
        self.first, self.last = self.ITEMS[-1], self.ITEMS[0]
        self.top_name = min(order, key=lambda kv: self.RANK[kv[0]])[0]

    def tier(self, v):
        for i, (th, _, _) in enumerate(self.TIERS):
            if v < th:
                return i

    def fmt(self, v):
        return '%.*f' % (self.decimals, v)

    def value_text(self, v):
        return self.fmt(v) + self.suffix

    # ---------- 文言テンプレートの変数 ----------
    def _vars(self):
        vals = list(self.ALL.values())
        ratio = max(vals) / min(vals) if min(vals) > 0 else float('inf')
        if ratio < 1.5:
            gap = '約%.1f倍' % ratio
        else:
            r = round(ratio * 2) / 2
            gap = '約%s倍' % (int(r) if r == int(r) else r)
        v = _Vars(metric=self.metric, year=self.year, unit=self.unit, n=self.n,
                  first_name=self.ITEMS[-1]['name'], last_name=self.ITEMS[0]['name'], gap_text=gap)
        if self.AVG is not None:
            v['avg'] = self.fmt(self.AVG)
        self.V = v

    def say(self, template, **extra):
        v = _Vars(self.V)
        v.update(extra)
        try:
            return template.format_map(v)
        except (ValueError, IndexError) as e:
            raise ThemeError('文言テンプレートの書式エラー: %r (%s)' % (template, e))

    def item_vars(self, item):
        v = item['val']
        d = dict(rank=item['rank'], name=item['name'], value=self.value_text(v), note=item['note'],
                 ratio_last=('%.1f' % (v / self.last['val'])) if self.last['val'] else '',
                 ratio_first=('%.1f' % (v / self.first['val'])) if self.first['val'] else '')
        if self.AVG:
            d['ratio_avg'] = '%.1f' % (v / self.AVG)
        return d

    def item_sub(self, item):
        """カードの補足文。sub（共通）/ sub_first（1位）。item.note があればそれを優先。"""
        if item['note']:
            return item['note']
        key = 'sub_first' if item['rank'] == 1 and 'sub_first' in self.spec else 'sub'
        t = self.spec.get(key)
        return self.say(t, **self.item_vars(item)) if t else ''

    # ---------- 読み上げ ----------
    def narration_lines(self):
        s = self.spec
        L = {}
        for i, h in enumerate(s['hooks']):
            L['hook%d' % (i + 1)] = self.say(h['say'])
        tpl = s['item_say']
        for it in self.ITEMS:
            if it['rank'] == 1:
                t = tpl.get('first', tpl.get('top10'))
            elif it is self.ITEMS[0] and 'last' in tpl:
                t = tpl['last']
            elif it['rank'] <= 10 or self.layout != 'scroll':
                t = tpl.get('top10')
            else:
                t = tpl.get('rest')            # rest が無ければ読み上げなし
            if t:
                L['item:' + it['name']] = self.say(t, **self.item_vars(it))
        L['cta'] = self.say(s['cta']['say'])
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
                self.narration[k] = len(text) * SEC_PER_CHAR * 1.28 / speed
                self.estimated_keys.append(k)

    def nd(self, key):
        return self.narration.get(key, 0.0)

    # ---------- 画面のパネル ----------
    def _panels(self):
        s = self.spec
        self.hook_panels = [self._panel(h['panel']) for h in s['hooks']]
        self.cta_panel = self._panel(s['cta']['panel'])
        self.voice = s.get('voice', {})
        self.credit = self.voice.get('credit', '')
        self.note = s.get('grid_note')

    def _panel(self, rows):
        out = []
        for text, size, color, weight in rows:
            if color not in theme.NAMED_COLORS:
                raise ThemeError('不明な色名: %s（使える色: %s）' % (color, '/'.join(theme.NAMED_COLORS)))
            if weight not in theme.WEIGHTS:
                raise ThemeError('不明な太さ: %s（使える太さ: %s）' % (weight, '/'.join(theme.WEIGHTS)))
            out.append((self.say(text), int(size), theme.NAMED_COLORS[color], weight))
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
        base = {'grid': 1.1, 'scroll': 0.95, 'steps': 1.6}[self.layout]
        self.SEQ = []
        for it in self.ITEMS:
            key = 'item:' + it['name']
            dur = base
            if key in self.narration:
                dur = max(dur, self.nd(key) + (0.9 if it['rank'] == 1 else 0.3))
            elif self.layout == 'scroll':
                dur = 0.95
            self.SEQ.append(dict(it, start=t, dur=dur, key=key if key in self.narration else None))
            t += dur
        self.T_CTA = max(6.0, self.nd('cta') + 1.0)
        # 最短の長さ（既定60秒。クリエイターリワード条件）に満たなければ、各項目の表示時間を均等に延ばす
        min_total = float(s.get('min_total', 60))
        short = min_total - (t + self.T_CTA + 0.4)
        if short > 0:
            add = short / len(self.SEQ)
            t = self.T_HOOK
            for sg in self.SEQ:
                sg['start'] = t
                sg['dur'] += add
                t += sg['dur']
        self.T_COUNT_END = t
        self.T_FOCUS = 0.0
        self.T_END = self.T_COUNT_END + self.T_CTA + 0.4
        self.focus = None

    # ---------- 検証レポート・投稿文 ----------
    def report(self):
        vals = self.ALL.values()
        hi = max(self.ALL, key=self.ALL.get) if self.higher_first else min(self.ALL, key=self.ALL.get)
        lo = min(self.ALL, key=self.ALL.get) if self.higher_first else max(self.ALL, key=self.ALL.get)
        lines = [
            'テーマ %s: %s %s年（%s） 一覧型/%s %s %d件' % (self.id, self.metric, self.year, self.unit, self.layout,
                                                         '上位' if self.show == 'top' else '下位', self.n),
            '出典: %s  URL: %s' % (self.spec['source']['name'], self.spec['source'].get('url') or '（未記入）'),
            '最大 %s %s / 最小 %s %s / 全国 %s' % (hi, self.fmt(max(vals)), lo, self.fmt(min(vals)),
                                                   self.fmt(self.AVG) if self.AVG is not None else '（なし）'),
            '表示する項目（発表順）: ' + '、'.join('%d位%s%s' % (it['rank'], it['name'], '（同率）' if it['tie'] else '') for it in self.ITEMS),
            '動画長: フック %.1f秒 / 発表終了 %.1f秒 / 全体 %.1f秒%s' % (
                self.T_HOOK, self.T_COUNT_END, self.T_END,
                '' if self.T_END >= 60 else '  ★60秒未満（クリエイターリワードの対象外）'),
        ]
        if self.estimated_keys:
            lines.append('読み上げ長は見積もり（narration.json に一致する音声なし）: %d文' % len(self.estimated_keys))
        lines += ['警告: ' + w for w in self.warnings]
        return '\n'.join(lines)

    def post_md(self):
        return theme.post_md(self)
