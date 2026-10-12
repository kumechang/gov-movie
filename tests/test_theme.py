"""テンプレ化の回帰テスト: 離婚率テーマが、チャットで作った元の動画と同じ文・時間割を出すこと。
実行: python3 -m unittest discover -s tests   （リポジトリ直下から）
"""
import copy
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'src'))
import theme  # noqa: E402

YAML = os.path.join(ROOT, 'themes', 'divorce_rate_2024.yaml')
FIXTURE = os.path.join(ROOT, 'tests', 'fixtures', 'divorce_rate_2024_narration.json')
OLD = json.load(open(FIXTURE, encoding='utf-8'))


class DivorceThemeTest(unittest.TestCase):
    def setUp(self):
        self.T = theme.load(YAML, FIXTURE)

    def test_narration_text_matches_original(self):
        new = self.T.narration_lines()
        old = {k: v['text'] for k, v in OLD.items()}  # 元の 'tokyo' キーは 'focus' に改名済み
        self.assertEqual(new, old)

    def test_uses_recorded_durations(self):
        self.assertEqual(self.T.estimated_keys, [])

    def test_timeline_matches_original(self):
        # 元の common.py の出力（HANDOFF 記載の約91秒）
        self.assertAlmostEqual(self.T.T_HOOK, 9.57, places=2)
        self.assertAlmostEqual(self.T.T_COUNT_END, 79.76, places=2)
        self.assertAlmostEqual(self.T.T_END, 91.09, places=2)
        self.assertEqual((self.T.SEQ[0]['name'], self.T.SEQ[0]['rank']), ('富山県', 47))
        self.assertEqual((self.T.SEQ[-1]['name'], self.T.SEQ[-1]['rank']), ('沖縄県', 1))

    def test_ranking(self):
        self.assertEqual(self.T.RANK['東京都'], 20)
        self.assertIn('東京都', self.T.TIE)
        self.assertEqual(sorted((self.T.RANK[n], n) for n in self.T.TIE)[:2], [(2, '大阪府'), (2, '福岡県')])

    def test_tiers_match_original(self):
        self.assertEqual([t[2] for t in self.T.TIERS], ['〜1.29', '1.30〜1.44', '1.45〜1.54', '1.55〜1.69', '1.70〜'])
        counts = [sum(1 for v in self.T.DATA.values() if self.T.tier(v) == i) for i in range(5)]
        self.assertEqual(counts, [7, 7, 19, 8, 6])

    def test_derived_texts(self):
        self.assertEqual(self.T.V['gap_text'], '約2倍')
        self.assertEqual(self.T.V['last_vs_first'], '1位の約半分')
        self.assertEqual(self.T.V['focus_tie'], '（山梨県と同率）')

    def test_post_md_has_credits(self):
        md = self.T.post_md()
        for s in ('出典：厚生労働省', 'Natural Earth', 'VOICEVOX:四国めたん', '#離婚率'):
            self.assertIn(s, md)


class ValidationTest(unittest.TestCase):
    def spec(self):
        import yaml
        return yaml.safe_load(open(YAML, encoding='utf-8'))

    def test_missing_prefecture(self):
        s = self.spec()
        del s['values']['沖縄']
        with self.assertRaisesRegex(theme.ThemeError, '沖縄県'):
            theme.Theme(s)

    def test_average_out_of_range(self):
        s = self.spec()
        s['average'] = 9.9
        with self.assertRaisesRegex(theme.ThemeError, '範囲外'):
            theme.Theme(s)

    def test_verification_required(self):
        s = self.spec()
        s['verification'] = ''
        with self.assertRaisesRegex(theme.ThemeError, 'verification'):
            theme.Theme(s)

    def test_unknown_template_variable(self):
        s = self.spec()
        s['cta']['say'] = '{nonexistent}'
        with self.assertRaisesRegex(theme.ThemeError, 'nonexistent'):
            theme.Theme(s)

    def test_auto_thresholds_and_estimated_durations(self):
        s = self.spec()
        s['tiers'] = {'thresholds': 'auto'}
        T = theme.Theme(copy.deepcopy(s))
        self.assertEqual(len(T.TIERS), 5)
        self.assertTrue(T.estimated_keys)  # narration.json なし → 見積もり

    def test_missing_url_is_warning(self):
        s = self.spec()
        s['source']['url'] = None
        self.assertTrue(any('source.url' in w for w in theme.Theme(s).warnings))


if __name__ == '__main__':
    unittest.main()
