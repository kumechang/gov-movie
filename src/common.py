"""データと時間割（映像と音声で共通）
データ出典：厚生労働省「人口動態統計」2024年（国立社会保障・人口問題研究所「人口統計資料集」表12-32より）
離婚率＝人口千対。全国 1.55。2回の読み取りが一致、別動画の表示値20件以上とも一致を確認済み。
"""
SHORT = {
    '北海道': 1.76, '青森': 1.51, '岩手': 1.28, '宮城': 1.43, '秋田': 1.17, '山形': 1.18, '福島': 1.51,
    '茨城': 1.54, '栃木': 1.50, '群馬': 1.54, '埼玉': 1.49, '千葉': 1.50, '東京': 1.52, '神奈川': 1.48,
    '新潟': 1.19, '富山': 1.13, '石川': 1.26, '福井': 1.27, '山梨': 1.52, '長野': 1.35, '岐阜': 1.42,
    '静岡': 1.44, '愛知': 1.55, '三重': 1.54, '滋賀': 1.40, '京都': 1.50, '大阪': 1.79, '兵庫': 1.59,
    '奈良': 1.47, '和歌山': 1.70, '鳥取': 1.49, '島根': 1.32, '岡山': 1.62, '広島': 1.54, '山口': 1.44,
    '徳島': 1.47, '香川': 1.60, '愛媛': 1.50, '高知': 1.65, '福岡': 1.79, '佐賀': 1.49, '長崎': 1.54,
    '熊本': 1.67, '大分': 1.63, '宮崎': 1.74, '鹿児島': 1.65, '沖縄': 2.24,
}
AVG = 1.55
assert len(SHORT) == 47

def full(n):
    return {'北海道': '北海道', '東京': '東京都', '大阪': '大阪府', '京都': '京都府'}.get(n, n + '県')

DATA = {full(n): v for n, v in SHORT.items()}

# 順位（同率は同順位）
ITEMS = sorted(DATA.items(), key=lambda kv: -kv[1])
RANK = {}
_prev = None; _r = 0
for _i, (_n, _v) in enumerate(ITEMS):
    if _v != _prev:
        _r = _i + 1; _prev = _v
    RANK[_n] = _r
TIE = {n for n in RANK if sum(1 for m in RANK if RANK[m] == RANK[n]) > 1}

# 色の区分
TIERS = [
    (1.30, (76, 124, 196), '〜1.29'),
    (1.45, (63, 167, 160), '1.30〜1.44'),
    (1.55, (232, 201, 90), '1.45〜1.54'),
    (1.70, (242, 155, 75), '1.55〜1.69'),
    (99.0, (229, 72, 77), '1.70〜'),
]
def tier(v):
    for i, (th, _, _) in enumerate(TIERS):
        if v < th:
            return i

# ---------- 読み上げ文（narration.py が音声化し narration.json に長さを書く） ----------
import json, os
_N = json.load(open('narration.json')) if os.path.exists('narration.json') else {}
def nd(key, default=0.0):
    return _N.get(key, {}).get('dur', default)

def _val_txt(v):
    return '%.2f' % v

def narration_lines():
    L = {
        'hook1': '都道府県別、離婚率ランキング。あなたの県は、何位？',
        'hook2': '一番高い県と低い県で、差は約2倍。',
        'hook3': '47位から、いきます。',
        'intro10': 'ここからトップ10です。',
    }
    for n, v in DATA.items():
        r = RANK[n]
        tie = ''
        if r == 47:
            L['item:' + n] = '47位、%s、%s。ここが最下位です。' % (n, _val_txt(v))
        elif r == 1:
            L['item:' + n] = 'そして1位は、%s。%s。全国平均の約%.1f倍です。' % (n, _val_txt(v), v / AVG)
        elif r <= 10:
            L['item:' + n] = '%s%d位、%s、%s。' % (tie, r, n, _val_txt(v))
    tk = '東京都'
    L['tokyo'] = 'ちなみに東京都は、%d位。ほぼ全国平均です。' % RANK[tk]
    L['cta'] = '離婚の背景は、人それぞれ。決めつけないでね。あなたの県は、何位だった？コメントで教えてね。'
    return L

# ---------- 時間割 ----------
HOOK_KEYS = [('hook1', 2.6, 0.5), ('hook2', 2.2, 0.45), ('hook3', 1.6, 0.45)]
HOOK_SEGS = []
t = 0.0
for k, mn, mg in HOOK_KEYS:
    d = max(mn, nd(k) + mg)
    HOOK_SEGS.append(dict(key=k, start=t, dur=d))
    t += d
T_HOOK = t

ORDER = [n for n, v in reversed(ITEMS)]  # 低い順（47位→1位）
SEQ = []
INTER = None
N = len(ORDER)
for idx, n in enumerate(ORDER):
    from_end = N - 1 - idx
    if from_end == 0:
        dur = 4.2
    elif from_end <= 2:
        dur = 2.2
    elif from_end <= 9:
        dur = 1.5
    else:
        dur = 0.95
    key = None
    if RANK[n] == 47 or RANK[n] <= 10:
        key = 'item:' + n
        dur = max(dur, nd(key) + (0.8 if RANK[n] == 1 else 0.3))
    if RANK[n] <= 10 and INTER is None:
        INTER = dict(start=t, dur=max(1.6, nd('intro10') + 0.4), key='intro10')
        t += INTER['dur']
    SEQ.append(dict(name=n, val=DATA[n], rank=RANK[n], start=t, dur=dur, key=key))
    t += dur
T_COUNT_END = t
T_TOKYO = max(4.0, nd('tokyo') + 0.7)
T_CTA = max(6.6, nd('cta') + 1.0)
T_END = T_COUNT_END + T_TOKYO + T_CTA + 0.4

if __name__ == '__main__':
    import json
    print('hook %.2f countdown end %.2f  total %.2f' % (T_HOOK, T_COUNT_END, T_END))
    print('tokyo rank', RANK['東京都'], 'tie' if '東京都' in TIE else '')
    print('first', SEQ[0]['name'], SEQ[0]['rank'], 'last', SEQ[-1]['name'], SEQ[-1]['rank'])
    print('ties', sorted((RANK[n], n) for n in TIE))
    from collections import Counter
    print('tier counts', Counter(tier(v) for v in DATA.values()))
    print('max/min ratio %.3f  max/avg %.3f  min/max %.3f' % (max(DATA.values()) / min(DATA.values()), max(DATA.values()) / AVG, min(DATA.values()) / max(DATA.values())))
    json.dump(SEQ, open('timeline.json', 'w'), ensure_ascii=False)
