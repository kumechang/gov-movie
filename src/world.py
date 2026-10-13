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


def country_silhouette(iso, box_w, box_h, margin=0, ss=2):
    """国の形を box_w×box_h に収めた RGBA 画像（白＋不透明度）と、(lon, lat) → 画像内の座標 の関数を返す"""
    feats = _load()
    if iso not in feats:
        raise KeyError('国 %s が地図データにありません' % iso)
    polys = _polys(feats[iso])
    pts = [pt for poly in polys for ring in poly for pt in ring]
    lat0 = (min(y for _, y in pts) + max(y for _, y in pts)) / 2
    kx = math.cos(math.radians(lat0))
    minx, maxx = min(x for x, _ in pts) * kx, max(x for x, _ in pts) * kx
    miny, maxy = -max(y for _, y in pts), -min(y for _, y in pts)
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
