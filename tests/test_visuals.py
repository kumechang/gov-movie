"""背景の演出部品のテスト: 危険の種類のアイコン、国の形（Natural Earth）、画像の出典チェック。
国の形のテストは、地図データ（build/ne_admin0_50m.geojson）が無く、ダウンロードもできない環境ではスキップする。
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'src'))
import render_list  # noqa: E402
import tiertheme  # noqa: E402
from theme import ThemeError  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_mofa import tier_spec  # noqa: E402


class IconTest(unittest.TestCase):
    def test_why_kind(self):
        k = render_list.why_kind
        self.assertEqual(k('紛争・武力衝突'), 'blast')
        self.assertEqual(k('テロ'), 'bomb')
        self.assertEqual(k('テロ警戒'), 'bomb')
        self.assertEqual(k('ギャング・凶悪犯罪'), 'skull')
        self.assertEqual(k('事件率'), 'skull')
        self.assertEqual(k('感染症'), 'virus')
        self.assertEqual(k('誘拐'), 'warn')
        self.assertEqual(k('その他'), 'warn')

    def test_icons_draw(self):
        for kind in ('blast', 'bomb', 'skull', 'virus', 'warn'):
            im = render_list.draw_icon(kind, 64, (200, 20, 30))
            self.assertEqual(im.size, (64, 64))
            self.assertGreater(im.getchannel('A').getbbox()[2], 10)         # 何かが描かれている


class WorldTest(unittest.TestCase):
    def test_silhouettes(self):
        import world
        try:
            world._load()
        except Exception as e:                                   # オフラインで地図データが無い
            self.skipTest('地図データを取得できません: %s' % e)
        for iso in ('MEX', 'SAU', 'TUR', 'IND', 'RUS'):
            mask, proj = world.country_silhouette(iso, 600, 300)
            bb = mask.getbbox()
            self.assertIsNotNone(bb)
            self.assertGreater(bb[2] - bb[0], 100)
        # ロシア（日付変更線をまたぐ）は、つなげて1つの形になる（幅が箱いっぱい）
        mask, proj = world.country_silhouette('RUS', 600, 300)
        self.assertGreaterEqual(mask.getbbox()[2] - mask.getbbox()[0], 560)
        x, y = proj(36.6, 50.6)                                  # ベルゴロド付近は、国の形の左（西）の端に近い
        self.assertLess(x, 200)
        with self.assertRaises(KeyError):
            world.country_silhouette('ZZZ', 100, 100)


class ImageCreditTest(unittest.TestCase):
    def test_image_requires_credit_and_adds_to_post(self):
        s = tier_spec()
        s['members'][2]['image'] = 'assets/x.jpg'
        with self.assertRaises(ThemeError):
            tiertheme.TierTheme(s)
        s['members'][2]['image_credit'] = '撮影者（CC BY 4.0）'
        s['post'] = {'title': 't', 'description': 'd', 'hashtags': []}
        self.assertIn('画像：撮影者（CC BY 4.0）', tiertheme.TierTheme(s).post_md())

    def test_map_credit_only_when_iso_used(self):
        s = tier_spec(post={'title': 't', 'description': 'd', 'hashtags': []})
        self.assertNotIn('Natural Earth', tiertheme.TierTheme(s).post_md())
        s['members'][2]['iso'] = 'MEX'
        self.assertIn('Natural Earth', tiertheme.TierTheme(s).post_md())

    def test_fast_tier(self):
        s = tier_spec()
        s['tiers'][0]['fast'] = True
        T = tiertheme.TierTheme(s)
        self.assertNotIn('item:0001', T.narration_lines())          # 名前は読み上げない
        seg = T.SEQ[0]
        self.assertEqual(len(seg['items']), 1)
        s['tiers'][2]['fast'] = True                                  # spotlight との併用は不可
        with self.assertRaises(ThemeError):
            tiertheme.TierTheme(s)


class AudioSmokeTest(unittest.TestCase):
    """段階ボードの音声（fast の段階・スポットライトを含む）が、短い偽の読み上げ音声で最後まで組み立てられる"""

    def test_build_tiers_with_voice(self):
        import json
        import tempfile
        import wave
        import audio
        s = tier_spec(style={'look': 'horror'})
        s['tiers'][0]['fast'] = True
        T0 = tiertheme.TierTheme(s)
        with tempfile.TemporaryDirectory() as d:
            nj = {}
            for i, (k, text) in enumerate(T0.narration_lines().items()):
                fn = 'n%d.wav' % i
                with wave.open(os.path.join(d, fn), 'wb') as w:
                    w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000)
                    w.writeframes((b'\x10\x00\xf0\xff') * 2400)
                nj[k] = dict(file=fn, dur=0.2, text=text, kana='')
            json.dump(nj, open(os.path.join(d, 'narration.json'), 'w', encoding='utf-8'), ensure_ascii=False)
            T = tiertheme.TierTheme(s, os.path.join(d, 'narration.json'))
            path = audio.build_tiers(T, d, voice=True)
            self.assertTrue(os.path.getsize(path) > 10000)


if __name__ == '__main__':
    unittest.main()
