"""一覧型テンプレート（ranked_list）のテスト。実データではなくテスト用の架空の値を使う（動画には出さない）。
実行: python3 -m unittest discover -s tests   （リポジトリ直下から）
"""
import copy
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'src'))
import listtheme  # noqa: E402
import theme  # noqa: E402
from theme import ThemeError  # noqa: E402

BASE = {
    'id': 'test_list', 'template': 'ranked_list', 'layout': 'steps', 'metric': 'テスト指標', 'year': 2024, 'unit': 'テスト単位',
    'decimals': 1, 'value_suffix': '万円',
    'source': {'name': 'テスト出典', 'url': 'https://example.com', 'fetch': 'manual'},
    'verification': 'テスト用の架空データ',
    'items': [{'name': '部長', 'value': 60.0}, {'name': '課長', 'value': 50.0}, {'name': '係長', 'value': 40.0},
              {'name': '主任', 'value': 40.0}, {'name': '一般', 'value': 30.0}],
    'title': 'テスト', 'title_small': '{year}年', 'subtitle': '{metric}',
    'sub': '最下位の{ratio_last}倍',
    'hooks': [{'say': '{metric}の{n}件です。', 'min': 2.0, 'gap': 0.4, 'y': 380, 'fade': 0.4,
               'panel': [['{metric}', 60, 'white', 'Bold']]}],
    'item_say': {'top10': '{rank}位、{name}、{value}。', 'first': '1位は{name}、{value}。'},
    'cta': {'say': 'コメントしてね。', 'panel': [['コメントしてね', 50, 'white', 'Bold']]},
}


def spec(**kw):
    s = copy.deepcopy(BASE)
    s.update(kw)
    return s


class ListThemeTest(unittest.TestCase):
    def test_items_mode_ranks_and_order(self):
        T = listtheme.ListTheme(spec())
        self.assertEqual([it['name'] for it in T.ITEMS], ['一般', '主任', '係長', '課長', '部長'])   # 発表順: 最下位から
        self.assertEqual((T.RANK['係長'], T.RANK['主任'], T.RANK['一般']), (3, 3, 5))
        self.assertEqual(T.ITEMS[-1]['rank'], 1)
        self.assertIn('1位は部長、60.0万円。', T.narration_lines().values())

    def test_tie_group_at_cut_is_dropped(self):
        T = listtheme.ListTheme(spec(n=3))      # 3位が2件（係長・主任）のうち1件で切れる → 3位ごと外す
        self.assertEqual([it['name'] for it in T.ITEMS], ['課長', '部長'])
        self.assertEqual(T.n, 2)
        self.assertTrue(any('同率' in w for w in T.warnings))

    def test_show_bottom_ends_with_the_extreme(self):
        T = listtheme.ListTheme(spec(show='bottom', n=3))
        self.assertEqual([it['name'] for it in T.ITEMS], ['係長', '主任', '一般'])
        self.assertEqual(T.ITEMS[-1]['name'], '一般')       # 最下位が最後（クライマックス）
        T2 = listtheme.ListTheme(spec(show='bottom', n=2))   # 3位（係長・主任）の途中で切れる → 3位ごと外す
        self.assertEqual([it['name'] for it in T2.ITEMS], ['一般'])

    def test_auto_tiers_survive_ties(self):
        T = listtheme.ListTheme(spec())     # 値 60/50/40/40/30（同率あり）で自動の色区分
        ths = [t for t, _, _ in T.TIERS[:-1]]
        self.assertEqual(ths, sorted(set(ths)))
        self.assertEqual(len(T.TIERS), len(ths) + 1)

    def test_stretches_to_minimum_length(self):
        T = listtheme.ListTheme(spec())
        self.assertGreaterEqual(T.T_END, 60.0 - 1e-6)
        T0 = listtheme.ListTheme(spec(min_total=0))
        self.assertLess(T0.T_END, T.T_END)
        # 時間割は連続している
        for a, b in zip(T.SEQ, T.SEQ[1:]):
            self.assertAlmostEqual(a['start'] + a['dur'], b['start'], places=6)
        self.assertAlmostEqual(T.SEQ[-1]['start'] + T.SEQ[-1]['dur'], T.T_COUNT_END, places=6)

    def test_validation_errors(self):
        with self.assertRaises(ThemeError):
            listtheme.ListTheme(spec(layout='bogus'))
        with self.assertRaises(ThemeError):
            listtheme.ListTheme(spec(n=99))
        with self.assertRaises(ThemeError):
            listtheme.ListTheme(spec(verification=''))
        with self.assertRaises(ThemeError):
            listtheme.ListTheme(spec(values={'東京': 1.0}))        # values と items は同時に書けない
        bad = spec(items=[{'name': 'a', 'value': 'x'}, {'name': 'b', 'value': 1}])
        with self.assertRaises(ThemeError):
            listtheme.ListTheme(bad)
        dup = spec(items=[{'name': 'a', 'value': 1}, {'name': 'a', 'value': 2}])
        with self.assertRaises(ThemeError):
            listtheme.ListTheme(dup)

    def test_pref_mode_uses_47_value_validation(self):
        vals = {p: 1.0 + i / 100 for i, p in enumerate(theme.PREFS)}
        s = spec(items=None, values=vals, layout='grid', n=10, decimals=2, value_suffix='', average=1.2)
        s.pop('items')
        T = listtheme.ListTheme(s)
        self.assertTrue(T.is_pref)
        self.assertEqual(T.ITEMS[-1]['name'], '沖縄県')
        del s['values']['東京']
        with self.assertRaises(ThemeError):
            listtheme.ListTheme(s)

    def test_post_md_has_license_credits(self):
        s = spec(post={'title': '{metric}', 'description': 'd', 'hashtags': ['#a']})
        s['source']['license'] = {'commercial': True, 'credit_lines': ['クレジット行']}
        self.assertIn('クレジット行', listtheme.ListTheme(s).post_md())


class RenderSmokeTest(unittest.TestCase):
    """3つの layout が、実際にフレームを描けること（フォントが無い環境ではスキップ）"""

    def test_each_layout_renders(self):
        import render_list
        try:
            import render
            render.F(40)
        except SystemExit:
            self.skipTest('日本語フォントがありません')
        for layout in listtheme.LAYOUTS:
            s = spec(layout=layout, n=3 if layout == 'steps' else 5)
            s['items'] = BASE['items'] + [{'name': '新人', 'value': 20.0}] if layout != 'steps' else BASE['items']
            T = listtheme.ListTheme(s)
            lay = render_list.init(T)
            for t in (1.0, T.SEQ[0]['start'] + 0.5, T.SEQ[-1]['start'] + 1.0, T.T_COUNT_END + 1.0):
                im = lay.frame(t)
                self.assertEqual(im.size, (1080, 1920))


if __name__ == '__main__':
    unittest.main()
