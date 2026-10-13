"""世界地図（Natural Earth 50m の国境・パブリックドメイン）から、国の形（シルエット）を作る。

  mask = country_silhouette('MEX', 1000, 860)     -> (RGBA 画像, 座標変換 f(lon, lat)->(x, y))
データは初回に build/ne_admin0_50m.geojson へ自動でダウンロードする（約3MB。raw.githubusercontent.com）。
注意: 国境線は Natural Earth の描き方に従った目安。画面には「おおよその位置」と添える。
"""
import json
import math
import os
import urllib.request

from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, '..', 'build', 'ne_admin0_50m.geojson')
URL = 'https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_admin_0_countries.geojson'
_data = {}


def _load():
    if 'f' not in _data:
        if not os.path.exists(PATH):
            os.makedirs(os.path.dirname(PATH), exist_ok=True)
            urllib.request.urlretrieve(URL, PATH)
        with open(PATH, encoding='utf-8') as f:
            _data['f'] = {ft['properties'].get('ADM0_A3'): ft for ft in json.load(f)['features']}
    return _data['f']


def _polys(feature):
    g = feature['geometry']
    polys = g['coordinates'] if g['type'] == 'MultiPolygon' else [g['coordinates']]
    lons = [pt[0] for poly in polys for pt in poly[0]]
    wrap = max(lons) - min(lons) > 180                 # ロシアのように日付変更線をまたぐ国は、西側の経度に 360 を足してつなげる
    return [[[((x + 360 if wrap and x < 0 else x), y) for x, y in ring] for ring in poly] for poly in polys]


def country_silhouette(iso, box_w, box_h, margin=0, ss=2, bbox=None):
    """国の形を box_w×box_h に収めた画像（マスク）と、(lon, lat) → 画像内の座標 の関数を返す。
    bbox=[経度の最小, 緯度の最小, 経度の最大, 緯度の最大] を渡すと、国全体ではなく、その範囲だけを拡大して収める（国の一部の地域を見せたいとき）"""
    feats = _load()
    if iso not in feats:
        raise KeyError('国 %s が地図データにありません' % iso)
    polys = _polys(feats[iso])
    pts = [pt for poly in polys for ring in poly for pt in ring]
    ex = pts if bbox is None else [(bbox[0], bbox[1]), (bbox[2], bbox[3])]      # 範囲の計算に使う点（bbox があれば、その2隅）
    lat0 = (min(y for _, y in ex) + max(y for _, y in ex)) / 2
    kx = math.cos(math.radians(lat0))
    minx, maxx = min(x for x, _ in ex) * kx, max(x for x, _ in ex) * kx
    miny, maxy = -max(y for _, y in ex), -min(y for _, y in ex)
    k = min((box_w - 2 * margin) / (maxx - minx), (box_h - 2 * margin) / (maxy - miny))
    ox = (box_w - (maxx - minx) * k) / 2 - minx * k
    oy = (box_h - (maxy - miny) * k) / 2 - miny * k

    def proj(lon, lat, wrap=False):
        if lon < 0 and (max(x for x, _ in pts) > 180):
            lon += 360
        return lon * kx * k + ox, -lat * k + oy

    big = Image.new('L', (box_w * ss, box_h * ss), 0)
    d = ImageDraw.Draw(big)
    for poly in polys:
        for i, ring in enumerate(poly):
            xy = [(proj(x, y)[0] * ss, proj(x, y)[1] * ss) for x, y in ring]
            if len(xy) >= 3:
                d.polygon(xy, fill=255 if i == 0 else 0)
    mask = big.resize((box_w, box_h), Image.LANCZOS)
    return mask, proj


def _rings(iso):
    feats = _load()
    g = feats[iso]['geometry']
    polys = g['coordinates'] if g['type'] == 'MultiPolygon' else [g['coordinates']]
    return [ring for poly in polys for ring in poly[:1]]


def _densify(ring, step_km):
    out = []
    for (x0, y0), (x1, y1) in zip(ring, ring[1:]):
        d = math.hypot((x1 - x0) * math.cos(math.radians((y0 + y1) / 2)) * 111.32, (y1 - y0) * 110.57)
        n = max(1, int(d / step_km))
        out += [(x0 + (x1 - x0) * i / n, y0 + (y1 - y0) * i / n) for i in range(n)]
    return out


def border_runs(iso_a, iso_b, near_km=4.0, step_km=3.0):
    """2つの国の国境線（iso_a の国境線のうち、iso_b の国境線から near_km 以内の部分）を、[経度, 緯度] の折れ線のリストで返す。
    「国境から30km以内」のような、距離で決まる危険地域を、国境線のデータから描くために使う（Natural Earth 50m。国境線は目安）"""
    import numpy as np
    b_pts = np.array([p for ring in _rings(iso_b) for p in _densify(ring, step_km * 2)])
    runs = []
    for ring in _rings(iso_a):
        pts = _densify(ring, step_km)
        arr = np.array(pts)
        near = np.zeros(len(arr), dtype=bool)
        for i in range(0, len(arr), 400):
            chunk = arr[i:i + 400]
            dx = (chunk[:, None, 0] - b_pts[None, :, 0]) * math.cos(math.radians(chunk[:, 1].mean())) * 111.32
            dy = (chunk[:, None, 1] - b_pts[None, :, 1]) * 110.57
            near[i:i + 400] = (np.sqrt(dx ** 2 + dy ** 2).min(axis=1) <= near_km)
        cur = []
        for pt, n in zip(pts, near):
            if n:
                cur.append((float(pt[0]), float(pt[1])))
            else:
                if len(cur) > 1:
                    runs.append(cur)
                cur = []
        if len(cur) > 1:
            runs.append(cur)
    return runs
