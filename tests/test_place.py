"""場所と危険情報の型（place_vs_risk）: 事実の照合（facts.py）、テーマ（spottheme.py）、描画のテスト。ネットワークには出ない。
実行: python3 -m unittest discover -s tests   （リポジトリ直下から）
"""
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(ROOT), 'src'))
sys.path.insert(0, ROOT)
import facts  # noqa: E402
import mofa  # noqa: E402
import spottheme  # noqa: E402
from test_mofa import fake_cache  # noqa: E402
from theme import ThemeError  # noqa: E402


def claim(pid, qid, start=None):
    s = {'mainsnak': {'datavalue': {'value': {'id': qid}}}}
    if start:
        s['qualifiers'] = {'P580': [{'datavalue': {'value': {'time': '+%d-01-01T00:00:00Z' % start}}}]}
    return s


def entity(label, jawiki, claims):
    return dict(label_ja=label, label_en='', jawiki=jawiki, claims=claims)


def preload(**cache):
    facts.open_cache(None)
    facts._state['cache'].update(cache)


FILM = entity('映画A', '映画A', {'P915': [claim('P915', 'Q406')], 'P577': [{'mainsnak': {'datavalue': {'value': {'time': '+2012-10-26T00:00:00Z'}}}}]})
HERITAGE = entity('歴史地域', '歴史地域', {'P1435': [claim('P1435', 'Q9259', 1985)]})


class FactsTest(unittest.TestCase):
    def test_license_ok(self):
        for ok in ('CC BY 4.0', 'CC BY 2.0', 'CC0', 'Public domain', 'CC0 1.0'):
            self.assertTrue(facts.license_ok(ok), ok)
        for ng in ('CC BY-SA 4.0', 'CC BY-NC 2.0', 'CC BY-ND 3.0', 'All rights reserved', ''):
            self.assertFalse(facts.license_ok(ng), ng)

    def test_designation_years(self):
        self.assertEqual(facts.designation_years(HERITAGE, 'Q9259'), [1985])
        self.assertEqual(facts.designation_years(HERITAGE, 'Q1'), [])

    def test_heritage_needs_both_systems(self):
        preload(**{'wd:Q1': HERITAGE, 'wp:歴史地域': '1985年に世界遺産に登録された。'})
        sc = dict(kind='heritage', name='歴史地域', wikidata='Q1', designation='Q9259', year=1985)
        self.assertEqual(facts.check_scene(sc, 'Q406')[0], [])
        self.assertTrue(facts.check_scene(dict(sc, year=1990), 'Q406')[0])             # Wikidata の年が違う
        preload(**{'wd:Q1': HERITAGE, 'wp:歴史地域': '何も書かれていない'})
        self.assertTrue(facts.check_scene(sc, 'Q406')[0])                              # ja.wikipedia に出てこない

    def test_film_place_and_year(self):
        preload(**{'wd:Q2': FILM, 'wp:映画A': 'イスタンブールで撮影された。'})
        sc = dict(kind='film', name='映画', films=[dict(wikidata='Q2', name='映画A', year=2012)], wp_contains=['イスタンブール'])
        self.assertEqual(facts.check_scene(sc, 'Q406')[0], [])
        self.assertTrue(facts.check_scene(sc, 'Q999')[0])                              # 撮影場所に含まれない
        bad = dict(sc, films=[dict(wikidata='Q2', name='映画A', year=2010)])
        self.assertTrue(facts.check_scene(bad, 'Q406')[0])                             # 公開年が違う

    def test_photo_license_blocks(self):
        preload(**{'cm:File:a.jpg': dict(title='File:a.jpg', thumb='x', page='', w=1, h=1, license='CC BY-SA 4.0', artist='A', credit='', desc='', categories=[], attribution_required='true')})
        p, _ = facts.check_scene(dict(kind='night', name='夜', photo=dict(file='File:a.jpg')), 'Q406')
        self.assertTrue(p)


def place_spec(image_path, **kw):
    c = fake_cache()
    c['pages']['0004'] = dict(levels=[1, 4], section='【危険レベル】\n●北の国境地帯\nレベル4：退避してください。\n●首都県\nレベル1：十分注意してください。',
                              body='国境地帯で衝突が散発的に発生しています。首都ではデモが突発的に行われることがあります。')
    v, ex = mofa.classify(c)
    spec = {
        'id': 'p', 'template': 'place_vs_risk', 'metric': 'm', 'year': 2026, 'unit': 'u',
        'source': {'name': 'n', 'url': 'https://example.com'}, 'verification': 'v',
        'title': 'T', 'title_small': 's', 'subtitle': '{asof}', 'footnote': '更新 {risk_date}',
        'tier_data': dict(asof='2026年10月13日', fetched=c['fetched'], countries=v, excluded=ex),
        'members': [{'code': '0004', 'label': 'デルタ', 'iso': 'TUR', 'regions': [
            {'level': 4, 'where': '北の国境地帯', 'note': '衝突が散発的に発生しています', 'bands': [[[36.0, 36.3], [40.0, 36.9]]], 'label_at': [38.0, 35.5], 'say': '北がレベル4'},
            {'level': 1, 'where': '首都県', 'say': '首都はレベル1'}], 'absent_places': [{'place': '田舎', 'names': ['存在しない県']}],
            'why': [{'tag': 'デモ', 'text': 'デモがある', 'evidence': 'デモが突発的に行われることがあります'}]}],
        'places': [{'name': '首都', 'marker': [28.98, 41.01], 'region': '首都県'}, {'name': '田舎', 'marker': [34.0, 39.0], 'absent': True}],
        'others': {'say': '田舎は載っていません'},
        'distance': {'from': '首都', 'level': 4, 'say': '約{dist_km}キロ'},
        'scenes': [{'kind': 'night', 'tag': '夜景', 'name': '夜', 'say': '夜景です', 'place': '首都', 'image': image_path, 'photo': {'file': 'x'}, 'image_credit': '作者／CC BY 4.0／Wikimedia Commons'},
                   {'kind': 'heritage', 'tag': '世界遺産', 'name': '歴史地域', 'say': '世界遺産です', 'lines': ['1985年に登録'], 'image': image_path, 'photo': {'file': 'y'}}],
        'turn': {'say': 'ところが', 'lines': [['ところが', 100, 'red']]},
        'caution': {'say': '注意'}, 'closing': {'say': '結び', 'lines': [['地域ごと', 60, 'white']]},
        'hooks': [{'say': 'フック', 'min': 2.0, 'gap': 0.4, 'y': 380, 'fade': 0.4, 'panel': [['t', 60, 'white', 'Bold']]}],
        'cta': {'say': 'CTA', 'panel': [['t', 50, 'white', 'Bold']]},
    }
    spec.update(kw)
    return spec


class MofaRegionsTest(unittest.TestCase):
    def test_regions_are_checked_against_the_page(self):
        spec = place_spec('x')
        c = fake_cache()
        c['pages']['0004'] = dict(levels=[1, 4], section='【危険レベル】\n●北の国境地帯\nレベル4：x\n●首都県\nレベル1：y', body='衝突が散発的に発生しています。デモが突発的に行われることがあります。')
        v, ex = mofa.classify(c)
        problems = []
        mofa.check_members({'members': spec['members']}, c, v, ex, problems)
        self.assertEqual(problems, [])
        c['pages']['0004']['section'] += '\n●存在しない県\nレベル1：y'
        problems = []
        mofa.check_members({'members': spec['members']}, c, v, ex, problems)
        self.assertEqual(len(problems), 1)             # 載っていないはずの場所の名前が、節に出てきた
        bad = [dict(spec['members'][0], absent_places=[], regions=[{'level': 3, 'where': '北の国境地帯'}, {'level': 4, 'where': '存在しない県', 'note': '書かれていない'}])]
        problems = []
        mofa.check_members({'members': bad}, c, v, ex, problems)
        self.assertEqual(len(problems), 3)             # レベル違い・存在しない地域・note


class SpotThemeTest(unittest.TestCase):
    def setUp(self):
        from PIL import Image
        self.tmp = tempfile.TemporaryDirectory()
        self.img = os.path.join(self.tmp.name, 'p.jpg')
        Image.new('RGB', (1600, 1000), (40, 60, 90)).save(self.img)

    def tearDown(self):
        self.tmp.cleanup()

    def test_distance_from_absent_place_follows_others(self):
        spec = place_spec(self.img, distance={'from': '田舎', 'level': 4, 'say': '約{dist_km}キロ'})
        T = spottheme.SpotTheme(spec)
        self.assertEqual([sg['kind'] for sg in T.MAP_SEGS], ['turn', 'region', 'place', 'others', 'distance', 'caution', 'closing'])
        self.assertEqual(T.dist['src']['name'], '田舎')

    def test_structure_and_timeline(self):
        T = spottheme.SpotTheme(place_spec(self.img))
        self.assertEqual(T.level, 4)
        self.assertEqual(T.place_groups[0]['region']['level'], 1)
        self.assertEqual([r['level'] for r in T.danger], [4])
        self.assertEqual([p['status'] for p in T.places], ['region', 'absent'])
        self.assertTrue(T.dist['km_round'] > 0 and T.dist['km_round'] % 50 == 0)
        self.assertEqual([sg['kind'] for sg in T.MAP_SEGS], ['turn', 'region', 'distance', 'place', 'others', 'caution', 'closing'])
        self.assertTrue(all(p['t_reveal'] is not None for p in T.places))
        self.assertEqual(T.nd('hook1') > 0, True)
        starts = [s['start'] for s in T.HOOK_SEGS + T.SCENE_SEGS + T.MAP_SEGS]
        self.assertEqual(starts, sorted(starts))
        seg = T.MAP_SEGS[-1]
        self.assertAlmostEqual(seg['start'] + seg['dur'], T.T_COUNT_END)
        self.assertAlmostEqual(T.SCENE_SEGS[-1]['start'] + T.SCENE_SEGS[-1]['dur'], T.T_TURN)
        self.assertIn('更新 2026年1月1日', T.say(T.spec['footnote']))
        self.assertIn('scene:1', T.narration_lines())

    def test_errors(self):
        with self.assertRaises(ThemeError):
            spottheme.SpotTheme(place_spec(self.img, verification=''))
        s = place_spec(self.img)
        s['places'][0]['region'] = '存在しない地域'
        with self.assertRaises(ThemeError):
            spottheme.SpotTheme(s)                      # 場所が参照する地域がない
        s = place_spec(self.img)
        s['members'][0]['absent_places'] = []
        with self.assertRaises(ThemeError):
            spottheme.SpotTheme(s)                      # 「載っていない」ことを検証していない場所
        s = place_spec(self.img)
        s['scenes'][0].pop('image')
        with self.assertRaises(ThemeError):
            spottheme.SpotTheme(s)                      # 写真が facts.resolve を通っていない

    def test_render_smoke(self):
        import render
        import render_list
        import render_spot  # noqa: F401
        try:
            render.F(40)
        except SystemExit:
            self.skipTest('日本語フォントがありません')
        T = spottheme.SpotTheme(place_spec(self.img, style={'look': 'horror', 'fx': {'shake': 14, 'flash': [170, 0, 10], 'flash_alpha': 0.35}},
                                           calm_style={'title_color': [244, 236, 224]}))
        lay = render_list.init(T)
        times = [1.0, T.SCENE_SEGS[0]['start'] + 1.5, T.SCENE_SEGS[1]['start'] + 2.0, T.T_TURN + 0.3]
        times += [sg['start'] + 1.2 for sg in T.MAP_SEGS] + [T.T_COUNT_END + 1.0]
        for t in times:
            self.assertEqual(lay.frame(t).size, (1080, 1920), t)
        render_list.apply_style(None)


if __name__ == '__main__':
    unittest.main()


class AdminRingsTest(unittest.TestCase):
    """州・県の外周（world.admin1_rings）と、緯度での切り取り。地図データは合成して、ネットワークには出ない。"""

    def setUp(self):
        import world
        self.world = world
        sq = lambda x0, y0, x1, y1: [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]]
        feats = [
            {'properties': {'adm0_a3': 'AAA', 'name': 'Alpha'}, 'geometry': {'type': 'Polygon', 'coordinates': sq(0, 0, 2, 4)}},
            {'properties': {'adm0_a3': 'AAA', 'name': 'Alpha'}, 'geometry': {'type': 'Polygon', 'coordinates': sq(5, 5, 6, 6)}},
            {'properties': {'adm0_a3': 'BBB', 'name': 'Alpha'}, 'geometry': {'type': 'Polygon', 'coordinates': sq(9, 9, 10, 10)}},
        ]
        self._orig = world._load_admin1
        world._load_admin1 = lambda: feats

    def tearDown(self):
        self.world._load_admin1 = self._orig

    def test_same_name_all_included_and_other_country_excluded(self):
        rings = self.world.admin1_rings('AAA', ['Alpha'])
        self.assertEqual(len(rings), 2)

    def test_missing_name_raises(self):
        with self.assertRaises(KeyError):
            self.world.admin1_rings('AAA', ['Alpha', 'Nowhere'])

    def test_clip_lat(self):
        rings = self.world.admin1_rings('AAA', ['Alpha'], lat_max=2)
        ys = [p[1] for r in rings for p in r]
        self.assertTrue(max(ys) <= 2 + 1e-9)


class InRegionTest(unittest.TestCase):
    """人気の場所の座標が、地図に描く地域の中か（州・帯・円・例外の円）"""

    def test_polys_with_holes(self):
        sq = [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]
        r = {'polys': [sq], 'holes': [[5, 5, 50]]}
        self.assertFalse(spottheme._in_region([5, 5.1], r))      # 例外の円の中
        self.assertTrue(spottheme._in_region([1, 1], r))
        self.assertFalse(spottheme._in_region([20, 20], r))      # 州の外

    def test_distance_from_inside_hole_is_to_hole_edge(self):
        sq = [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]
        r = {'polys': [sq], 'holes': [[5, 5, 50]]}
        self.assertAlmostEqual(spottheme._region_km([5, 5], r), 50.0, places=3)        # 穴の中心から、穴の縁まで
        self.assertEqual(spottheme._region_km([1, 1], r), 0.0)

    def test_band_width(self):
        r = {'bands': [[[0, 0], [0, 1]]], 'width_km': 20}
        self.assertTrue(spottheme._in_region([0.05, 0.5], r))    # 約5km
        self.assertFalse(spottheme._in_region([0.3, 0.5], r))    # 約33km

    def test_circle_and_border(self):
        self.assertTrue(spottheme._in_region([0, 0.05], {'bands': [[[0, 0]]], 'radius_km': 10}))
        self.assertIsNone(spottheme._in_region([0, 0], {'border': {'km': 30}, 'bands': [[[0, 0]]]}))
