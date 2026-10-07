"""都道府県のマスク画像を作る（Natural Earth: パブリックドメイン）。
出力: geo.pkl  {pref_name: dict(mask, edge, x0, y0, cx, cy)} と領域サイズ
"""
import json, math, pickle
from PIL import Image, ImageDraw, ImageFilter

W = 1080
MAP_H = 880            # 地図領域の高さ(px)
LAT_MAX, LAT_MIN = 45.6, 30.0
LON_MIN, LON_MAX = 128.5, 146.0
KY = MAP_H / (LAT_MAX - LAT_MIN)           # px / 緯度1度
KX = KY * math.cos(math.radians(37.5))     # px / 経度1度
X0 = (W - (LON_MAX - LON_MIN) * KX) / 2

# 沖縄インセット
INS = 0.65
INS_LEFT, INS_TOP = 340, 716               # 領域内の座標
OK_LON0, OK_LAT0 = 122.8, 28.1

SS = 3  # スーパーサンプリング

def proj_main(lon, lat):
    return X0 + (lon - LON_MIN) * KX, (LAT_MAX - lat) * KY

def proj_ok(lon, lat):
    return INS_LEFT + (lon - OK_LON0) * KX * INS, INS_TOP + (OK_LAT0 - lat) * KY * INS

def poly_polys(geom):
    if geom['type'] == 'Polygon':
        return [geom['coordinates']]
    return geom['coordinates']

def area(ring):
    a = 0
    for i in range(len(ring)):
        x1, y1 = ring[i]; x2, y2 = ring[(i + 1) % len(ring)]
        a += x1 * y2 - x2 * y1
    return abs(a) / 2

def simplify(pts, tol=0.6):
    out = [pts[0]]
    for p in pts[1:]:
        if abs(p[0] - out[-1][0]) + abs(p[1] - out[-1][1]) >= tol:
            out.append(p)
    return out

g = json.load(open('ne_admin1.geojson'))
jp = [f for f in g['features'] if f['properties'].get('iso_a2') == 'JP']
res = {}
for f in jp:
    name = f['properties']['name_ja']
    is_ok = name == '沖縄県'
    proj = proj_ok if is_ok else proj_main
    rings = []  # (outer_px, holes_px, area)
    for poly in poly_polys(f['geometry']):
        outer = poly[0]
        lons = [p[0] for p in outer]; lats = [p[1] for p in outer]
        clon, clat = sum(lons) / len(lons), sum(lats) / len(lats)
        if not is_ok:
            if clat < 30.0 or not (LON_MIN <= clon <= LON_MAX):
                continue
        o = [proj(*p) for p in outer]
        holes = [[proj(*p) for p in h] for h in poly[1:]]
        rings.append((o, holes, area(o)))
    if not rings:
        raise SystemExit('no polygons for ' + name)
    # 領域キャンバス全体にスーパーサンプリングで描く
    big = Image.new('L', (W * SS, MAP_H * SS), 0)
    d = ImageDraw.Draw(big)
    def dp(pts, fill):
        sp = simplify(pts, 0.6)
        if len(sp) >= 3:
            d.polygon([(x * SS, y * SS) for x, y in sp], fill=fill)
        elif len(pts) >= 3:
            d.polygon([(x * SS, y * SS) for x, y in pts], fill=fill)
    for o, holes, a in rings:
        dp(o, 255)
        for h in holes:
            dp(h, 0)
    m = big.resize((W, MAP_H), Image.LANCZOS)
    bbox = m.getbbox()
    if bbox is None:
        raise SystemExit('empty mask ' + name)
    pad = 6
    x0, y0 = max(0, bbox[0] - pad), max(0, bbox[1] - pad)
    x1, y1 = min(W, bbox[2] + pad), min(MAP_H, bbox[3] + pad)
    mask = m.crop((x0, y0, x1, y1))
    # 縁取り用（約1.5px）
    er = mask.point(lambda v: 255 if v > 200 else 0).filter(ImageFilter.MinFilter(3))
    edge = Image.composite(Image.new('L', mask.size, 255), Image.new('L', mask.size, 0), mask.point(lambda v: 255 if v > 40 else 0))
    edge = Image.eval(edge, lambda v: v)
    from PIL import ImageChops
    edge = ImageChops.subtract(mask.point(lambda v: 255 if v > 40 else 0), er)
    edge = edge.filter(ImageFilter.GaussianBlur(0.6))
    # 重心：最大ポリゴン
    o, _, _ = max(rings, key=lambda r: r[2])
    cx = sum(p[0] for p in o) / len(o); cy = sum(p[1] for p in o) / len(o)
    res[name] = dict(mask=mask, edge=edge, x0=x0, y0=y0, cx=cx, cy=cy)

pickle.dump(dict(prefs=res, W=W, MAP_H=MAP_H, INS=(INS_LEFT, INS_TOP, INS)), open('geo.pkl', 'wb'))
print('ok', len(res), 'prefs; X0=%.1f KX=%.2f KY=%.2f' % (X0, KX, KY))
