"""テーマ定義(YAML)を読み込み、検証し、順位・色・読み上げ文・動画の時間割を計算する。

映像(render.py)・音声(audio.py)・ナレーション(narration.py)は、すべてここで作った Theme を読む。
テーマ固有の文言や数値は themes/*.yaml にあり、このファイルには置かない。
"""
import json
import math
import os

import yaml

PREFS = ['北海道', '青森', '岩手', '宮城', '秋田', '山形', '福島', '茨城', '栃木', '群馬', '埼玉', '千葉', '東京', '神奈川',
         '新潟', '富山', '石川', '福井', '山梨', '長野', '岐阜', '静岡', '愛知', '三重', '滋賀', '京都', '大阪', '兵庫',
         '奈良', '和歌山', '鳥取', '島根', '岡山', '広島', '山口', '徳島', '香川', '愛媛', '高知', '福岡', '佐賀', '長崎',
         '熊本', '大分', '宮崎', '鹿児島', '沖縄']
assert len(PREFS) == 47

DEFAULT_COLORS = [(76, 124, 196), (63, 167, 160), (232, 201, 90), (242, 155, 75), (229, 72, 77)]
NAMED_COLORS = {
    'white': (255, 255, 255),
    'yellow': (255, 213, 74),
    'red': (255, 90, 95),
    'muted': (170, 180, 215),
}
WEIGHTS = ('Regular', 'Medium', 'Bold', 'Black')
SEC_PER_CHAR = 0.167  # 実測(speed 1.28)。VOICEVOXなしのプレビューで読み上げ長を見積もる


class ThemeError(ValueError):
    pass


def full(n):
    return {'北海道': '北海道', '東京': '東京都', '大阪': '大阪府', '京都': '京都府'}.get(n, n + '県')


FULL_NAMES = {full(n) for n in PREFS}


class _Vars(dict):
    def __missing__(self, key):
        raise ThemeError('文言テンプレートに未定義の変数 {%s} があります' % key)


class Theme:
    def __init__(self, spec, narration_json=None):
        self.spec = spec
        self.warnings = []
        self.estimated_keys = []
        self._load_data()
        self._rank()
        self._tiers()
        self._vars()
        self._narration_cache(narration_json)
        self._panels()
        self._timeline()

    # ---------- データ ----------
    def _need(self, d, key, where=''):
        if d.get(key) in (None, ''):
            raise ThemeError('%s%s が未設定です' % (where, key))
        return d[key]

    def _load_data(self):
        s = self.spec
        self.id = self._need(s, 'id')
        if s.get('template', 'prefecture_map') != 'prefecture_map':
            raise ThemeError('未対応の template: %s' % s['template'])
        self.metric = self._need(s, 'metric')
        self.year = self._need(s, 'year')
        self.unit = self._need(s, 'unit')
        self.decimals = int(s.get('decimals', 2))
        self.higher_first = s.get('rank_order', 'desc') == 'desc'
        src = self._need(s, 'source')
        self._need(src, 'name', 'source.')
        if not src.get('url'):
            self.warnings.append('source.url が未記入です（出典URLを確認して記入してください）')
        if not str(s.get('verification', '')).strip():
            raise ThemeError('verification（検証方法の記録）が未記入です。検証できていない数字は載せません')
        raw = self._need(s, 'values')
        data = {}
        for k, v in raw.items():
            k = str(k)
            n = k if k in FULL_NAMES else full(k)
            if n not in FULL_NAMES:
                raise ThemeError('不明な都道府県名: %s' % k)
            if n in data:
                raise ThemeError('都道府県が重複しています: %s' % n)
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
                raise ThemeError('%s の値が数値ではありません: %r' % (n, v))
            data[n] = round(float(v), self.decimals)
        missing = FULL_NAMES - set(data)
        if missing:
            raise ThemeError('値のない都道府県: %s' % '、'.join(sorted(missing)))
        # 地図の描画順（北→南）に並べ直す
        self.DATA = {full(n): data[full(n)] for n in PREFS}
        self.AVG = float(self._need(s, 'average'))
        lo, hi = min(self.DATA.values()), max(self.DATA.values())
        if not lo <= self.AVG <= hi:
            raise ThemeError('全国値 %s が最小 %s〜最大 %s の範囲外です。年次・単位の取り違えの可能性があります' % (self.AVG, lo, hi))

    def fmt(self, v):
        return '%.*f' % (self.decimals, v)

    def _rank(self):
        self.ITEMS = sorted(self.DATA.items(), key=lambda kv: -kv[1] if self.higher_first else kv[1])
        self.RANK = {}
        prev, r = None, 0
        for i, (n, v) in enumerate(self.ITEMS):
            if v != prev:
                r, prev = i + 1, v
            self.RANK[n] = r
        self.TIE = {n for n in self.RANK if sum(1 for m in self.RANK if self.RANK[m] == self.RANK[n]) > 1}
        self.ORDER = [n for n, _ in reversed(self.ITEMS)]  # 発表順（最下位→1位）
        self.N = len(self.ORDER)

    # ---------- 色の区分 ----------
    def _tiers(self):
        t = self.spec.get('tiers') or {}
        colors = [tuple(c) for c in t.get('colors', DEFAULT_COLORS)]
        th = t.get('thresholds', 'auto')
        vals = sorted(self.DATA.values())
        if th == 'auto':
            k = len(colors)
            th = [round(vals[min(len(vals) - 1, int(len(vals) * i / k))], self.decimals) for i in range(1, k)]
        th = [float(x) for x in th]
        if len(th) != len(colors) - 1:
            raise ThemeError('tiers: thresholds は colors より1つ少なくしてください')
        if any(b <= a for a, b in zip(th, th[1:])):
            raise ThemeError('tiers.thresholds が昇順になっていません: %s' % th)
        step = 10 ** -self.decimals
        labels = ['〜' + self.fmt(th[0] - step)]
        labels += ['%s〜%s' % (self.fmt(a), self.fmt(b - step)) for a, b in zip(th, th[1:])]
        labels.append(self.fmt(th[-1]) + '〜')
        self.TIERS = [(h, c, lb) for h, c, lb in zip(th + [float('inf')], colors, labels)]

    def tier(self, v):
        for i, (th, _, _) in enumerate(self.TIERS):
            if v < th:
                return i

    # ---------- 文言テンプレートの変数 ----------
    def _gap_text(self):
        ratio = max(self.DATA.values()) / min(self.DATA.values())
        if ratio < 1.5:
            return '約%.1f倍' % ratio
        r = round(ratio * 2) / 2
        return '約%s倍' % (int(r) if r == int(r) else r)

    def _last_vs_first(self):
        r = min(self.DATA.values()) / max(self.DATA.values())
        return '1位の約半分' if 0.45 <= r < 0.55 else '1位の約%d%%' % round(r * 100)

    def _vars(self):
        s = self.spec
        v = _Vars(metric=self.metric, year=self.year, unit=self.unit, avg=self.fmt(self.AVG),
                  first_name=self.ITEMS[0][0], last_name=self.ITEMS[-1][0],
                  gap_text=self._gap_text(), last_vs_first=self._last_vs_first())
        self.focus = None
        f = s.get('focus')
        if f:
            n = f['name']
            if n not in self.DATA:
                raise ThemeError('focus.name が都道府県にありません: %s' % n)
            self.focus = n
            fv = self.DATA[n]
            partners = [m for m, _ in self.ITEMS if self.RANK[m] == self.RANK[n] and m != n]
            rel = (fv - self.AVG) / self.AVG
            if abs(rel) <= 0.05:
                say, cmp_ = 'ほぼ全国平均です', '全国平均 %s とほぼ同じ' % self.fmt(self.AVG)
            elif rel > 0:
                say, cmp_ = '全国平均より高めです', '全国平均 %s より高め' % self.fmt(self.AVG)
            else:
                say, cmp_ = '全国平均より低めです', '全国平均 %s より低め' % self.fmt(self.AVG)
            v.update(focus=n, focus_rank=self.RANK[n], focus_value=self.fmt(fv),
                     focus_tie='（%sと同率）' % partners[0] if partners else '',
                     focus_say=say, focus_cmp=cmp_)
        self.V = v

    def say(self, template, **extra):
        v = _Vars(self.V)
        v.update(extra)
        try:
            return template.format_map(v)
        except (ValueError, IndexError) as e:
            raise ThemeError('文言テンプレートの書式エラー: %r (%s)' % (template, e))

    def item_vars(self, name):
        v = self.DATA[name]
        return dict(rank=self.RANK[name], name=name, value=self.fmt(v), ratio_avg='%.1f' % (v / self.AVG))

    # ---------- 読み上げ ----------
    def narration_lines(self):
        s = self.spec
        L = {}
        for i, h in enumerate(s['hooks']):
            L['hook%d' % (i + 1)] = self.say(h['say'])
        L['intro10'] = self.say(s['intro_top10']['say'])
        tpl = s['item_say']
        for idx, n in enumerate(self.ORDER):
            r = self.RANK[n]
            if idx == 0:
                t = tpl['last']
            elif r == 1:
                t = tpl['first']
            elif r <= 10:
                t = tpl['top10']
            else:
                continue
            L['item:' + n] = self.say(t, **self.item_vars(n))
        if self.focus:
            L['focus'] = self.say(s['focus']['say'])
        L['cta'] = self.say(s['cta']['say'])
        return L

    def _narration_cache(self, path):
        """narration.json の長さを使う。文が変わっていたら（古い）見積もりに切り替える。"""
        cache = {}
        if path and os.path.exists(path):
            cache = json.load(open(path, encoding='utf-8'))
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
    def _panel(self, rows):
        out = []
        for text, size, color, weight in rows:
            if color not in NAMED_COLORS:
                raise ThemeError('不明な色名: %s（使える色: %s）' % (color, '/'.join(NAMED_COLORS)))
            if weight not in WEIGHTS:
                raise ThemeError('不明な太さ: %s（使える太さ: %s）' % (weight, '/'.join(WEIGHTS)))
            out.append((self.say(text), int(size), NAMED_COLORS[color], weight))
        return out

    def _panels(self):
        s = self.spec
        self.hook_panels = [self._panel(h['panel']) for h in s['hooks']]
        self.intro_panel = self._panel(s['intro_top10']['panel'])
        self.focus_panel = self._panel(s['focus']['panel']) if self.focus else None
        self.cta_panel = self._panel(s['cta']['panel'])
        self.voice = s.get('voice', {})
        self.credit = self.voice.get('credit', '')

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
        self.INTER = None
        for idx, n in enumerate(self.ORDER):
            from_end = self.N - 1 - idx
            if from_end == 0:
                dur = 4.2
            elif from_end <= 2:
                dur = 2.2
            elif from_end <= 9:
                dur = 1.5
            else:
                dur = 0.95
            key = None
            if idx == 0 or self.RANK[n] <= 10:
                key = 'item:' + n
                dur = max(dur, self.nd(key) + (0.8 if self.RANK[n] == 1 else 0.3))
            if self.RANK[n] <= 10 and self.INTER is None:
                self.INTER = dict(start=t, dur=max(1.6, self.nd('intro10') + 0.4), key='intro10')
                t += self.INTER['dur']
            self.SEQ.append(dict(name=n, val=self.DATA[n], rank=self.RANK[n], start=t, dur=dur, key=key))
            t += dur
        self.T_COUNT_END = t
        self.T_FOCUS = max(4.0, self.nd('focus') + 0.7) if self.focus else 0.0
        self.T_CTA = max(6.6, self.nd('cta') + 1.0)
        self.T_END = self.T_COUNT_END + self.T_FOCUS + self.T_CTA + 0.4

    # ---------- 検証レポート・投稿文 ----------
    def report(self):
        d = self.DATA.values()
        lines = [
            'テーマ %s: %s %s年（%s）' % (self.id, self.metric, self.year, self.unit),
            '出典: %s  URL: %s' % (self.spec['source']['name'], self.spec['source'].get('url') or '（未記入）'),
            '最大 %s %s / 最小 %s %s / 全国 %s  最大÷最小 %.3f  最大÷全国 %.3f' % (
                self.ITEMS[0][0], self.fmt(max(d)), self.ITEMS[-1][0], self.fmt(min(d)), self.fmt(self.AVG),
                max(d) / min(d), max(d) / self.AVG),
            '同率: %s' % ('、'.join('%d位%s' % (self.RANK[n], n) for n in sorted(self.TIE, key=lambda x: self.RANK[x])) or 'なし'),
            '色区分の件数: %s' % [sum(1 for v in d if self.tier(v) == i) for i in range(len(self.TIERS))],
            '動画長: フック %.1f秒 / カウントダウン終了 %.1f秒 / 全体 %.1f秒%s' % (
                self.T_HOOK, self.T_COUNT_END, self.T_END,
                '' if self.T_END >= 60 else '  ★60秒未満（クリエイターリワードの対象外）'),
        ]
        if self.estimated_keys:
            lines.append('読み上げ長は見積もり（narration.json に一致する音声なし）: %d文' % len(self.estimated_keys))
        lines += ['警告: ' + w for w in self.warnings]
        return '\n'.join(lines)

    def post_md(self):
        p = self.spec.get('post')
        if not p:
            return ''
        src = self.spec['source']
        desc = ' '.join(self.say(p['description']).split())
        credits = ['出典：%s%s' % (src['name'], src.get('note', '')),
                   '地図：Natural Earth（パブリックドメイン）']
        if self.credit:
            credits.append('音声：' + self.credit)
        return '\n'.join([
            '# 投稿用テキスト（自動生成）', '',
            '## タイトル', self.say(p['title']), '',
            '## 概要欄', desc, '', *credits, '', ' '.join(self.say(h) for h in p.get('hashtags', [])), '',
            '## 固定コメント案', self.say(p.get('pinned_comment', '')), '',
        ])


def load(path, narration_json=None):
    with open(path, encoding='utf-8') as f:
        spec = yaml.safe_load(f)
    return Theme(spec, narration_json)


if __name__ == '__main__':
    import sys
    print(load(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None).report())
