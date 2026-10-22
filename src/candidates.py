"""「危険と隣り合わせの観光地帯」シリーズの、国の候補を並べる。

  python3 src/candidates.py              候補の一覧（スコア順）
  python3 src/candidates.py --fetch-views  ja.wikipedia の閲覧数（知名度の目安）を取得して build/pageviews_ja.json に残す（1件ずつ間隔を空ける）

使う値:
  距離      東京から、国の中心（最大の陸地の重心）までの直線距離。Natural Earth 50m（パブリックドメイン）から計算
  知名度    ja.wikipedia の国の記事の、直近12か月の閲覧数（Wikimedia のデータ。日本語で読まれている量の目安。ニュースで急に増えた国は高く出る）
  人気      日本人旅行者の多さ（1〜3）。**暫定**。JNTO「日本人訪問者数ランキング」で置き換える（data/series_candidates.csv の pop）
  隣り合わせ度  危険地域と有名な観光地・名物の近さ（1〜3）。**暫定**。作る前に、公式ページの文言と世界遺産などの情報で検証する（story）
どれも、動画には出さない。候補の優先順を決めるための内部の指標。
"""
import csv
import json
import math
import os
import sys
import time
import urllib.parse
import urllib.request

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
TOKYO = (139.6917, 35.6895)
W = dict(story=0.35, pop=0.25, aware=0.20, near=0.20)       # 重み（合計1）
VIEWS_PATH = os.path.join(ROOT, 'build', 'pageviews_ja.json')
UA = 'gov-movie/0.1 (self-use research tool; https://github.com/kumechang/gov-movie)'
TITLE_FIX = {'GEO': 'ジョージア_(国)', 'COG': 'コンゴ共和国', 'PAK': 'パキスタン'}


def km(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[1], a[0], b[1], b[0]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(h))


def centroid(feature):
    g = feature['geometry']
    polys = g['coordinates'] if g['type'] == 'MultiPolygon' else [g['coordinates']]
    best, best_area = None, -1
    for poly in polys:
        ring = poly[0]
        a = cx = cy = 0.0
        for (x0, y0), (x1, y1) in zip(ring, ring[1:] + ring[:1]):
            c = x0 * y1 - x1 * y0
            a += c
            cx += (x0 + x1) * c
            cy += (y0 + y1) * c
        if abs(a) > best_area and a:
            best_area, best = abs(a), (cx / (3 * a), cy / (3 * a))
    return best


def load_world():
    import world
    feats = world._load()
    return {iso: (centroid(f), f['properties'].get('NAME_JA')) for iso, f in feats.items()}


def load_views():
    return json.load(open(VIEWS_PATH, encoding='utf-8')) if os.path.exists(VIEWS_PATH) else {}


def fetch_views(isos, titles, months=('2025100100', '2026093000'), sleep=time.sleep, log=print):
    """ja.wikipedia の閲覧数（月別の合計）を1件ずつ取得して残す。回数制限（429）のときは、教えられた秒数だけ待つ"""
    views = load_views()
    for iso in isos:
        if iso in views:
            continue
        url = 'https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/ja.wikipedia/all-access/user/%s/monthly/%s/%s' % (
            urllib.parse.quote(titles[iso].replace(' ', '_'), safe=''), months[0], months[1])
        for attempt in range(6):
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': UA}), timeout=60) as r:
                    items = json.loads(r.read().decode('utf-8')).get('items', [])
                views[iso] = sum(i['views'] for i in items)
                log('  %s %s: %d' % (iso, titles[iso], views[iso]))
                break
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    log('  %s %s: 記事が見つかりません' % (iso, titles[iso]))
                    break
                wait = min(120, max(int(e.headers.get('Retry-After') or 0) + 2, 20 * (attempt + 1)))
                log('  （回数制限。%d秒待ちます）' % wait)
                sleep(wait)
        else:
            log('  %s: 取得できませんでした' % iso)
        json.dump(views, open(VIEWS_PATH, 'w', encoding='utf-8'), ensure_ascii=False)
        sleep(15)
    return views


def rows():
    with open(os.path.join(ROOT, 'data', 'series_candidates.csv'), encoding='utf-8') as f:
        return list(csv.DictReader(f))


def ranking(views=None):
    world = load_world()
    views = views if views is not None else load_views()
    out = []
    for r in rows():
        c, ja = world[r['iso']]
        d = km(TOKYO, c)
        out.append(dict(r, dist=d, views=views.get(r['iso']), title=TITLE_FIX.get(r['iso'], ja)))
    vmax = max((x['views'] for x in out if x['views']), default=0)
    for x in out:
        s = int(x['story']) / 3
        p = int(x['pop']) / 3
        a = (math.log10(x['views'] + 1) / math.log10(vmax + 1)) if x['views'] and vmax else None
        n = 1 - min(x['dist'], 18000) / 18000
        parts = dict(story=s, pop=p, aware=a, near=n)
        w = {k: v for k, v in W.items() if parts[k] is not None}          # 知名度が取れていない国は、残りの重みで計算する
        x['score'] = sum(parts[k] * w[k] for k in w) / sum(w.values())
        x['aware'] = a
    return sorted(out, key=lambda x: -x['score'])


def main(argv):
    if '--fetch-views' in argv:
        rs = rows()
        world = load_world()
        titles = {r['iso']: TITLE_FIX.get(r['iso'], world[r['iso']][1]) for r in rs}
        fetch_views([r['iso'] for r in rs], titles)
    lines = ['| # | 国 | 点 | 隣り合わせ度 | 日本人の人気 | 距離(km) | 知名度(閲覧数/年) | 観光地・名物 | 危険地域 |', '|---|---|---|---|---|---|---|---|---|']
    for i, x in enumerate(ranking(), 1):
        lines.append('| %d | %s | %.2f | %s | %s | %s | %s | %s | %s |' % (
            i, x['name'], x['score'], x['story'], x['pop'], '{:,}'.format(int(round(x['dist'], -2))),
            '{:,}'.format(x['views']) if x['views'] else '—', x['spot'], x['danger']))
    print('\n'.join(lines))


if __name__ == '__main__':
    main(sys.argv[1:])
