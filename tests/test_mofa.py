"""外務省データの取得層（mofa.py）と、段階ボード（tiertheme.py）のテスト。ネットワークには出ない。
実行: python3 -m unittest discover -s tests   （リポジトリ直下から）
"""
import copy
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'src'))
import mofa  # noqa: E402
import theme  # noqa: E402
import tiertheme  # noqa: E402
from theme import ThemeError  # noqa: E402

XML = """<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<opendata dataType="L" lastModified="2026/10/13 08:55:46" mailCount="114" odType="04">
  <area><cd>10</cd></area>
  <country areaCd="10" countryCd="1"><cd>0091</cd><name>インド</name></country>
  <riskLevel4>1</riskLevel4><riskLevel3>1</riskLevel3><riskLevel2>0</riskLevel2><riskLevel1>1</riskLevel1>
  <infectionLevel4>0</infectionLevel4><infectionLevel3>0</infectionLevel3><infectionLevel2>0</infectionLevel2><infectionLevel1>1</infectionLevel1>
  <riskLeaveDate keyCd="2025T030">2025/03/25 00:00:00</riskLeaveDate>
  <riskTitle>インドの危険情報</riskTitle><riskUrl>https://example.com/x.html</riskUrl>
</opendata>"""

SECTION = """【危険レベル】
●シリアとの国境地帯
レベル4：
退避してください。
●ディヤルバクル県及びイラクとの国境地帯
レベル3：渡航は止めてください。
●上記以外の地域
 レベル1：十分注意してください。"""


class ParseTest(unittest.TestCase):
    def test_parse_country(self):
        d = mofa.parse_country(XML)
        self.assertEqual(d['risk'], [4, 3, 1])           # 含まれるレベル（高い順）
        self.assertEqual(d['infection'], [1])
        self.assertEqual(d['name_live'], 'インド')
        self.assertEqual(d['last_modified'], '2026/10/13 08:55:46')
        self.assertTrue(d['has_risk_block'])

    def test_display_name(self):
        self.assertEqual(mofa.display_name('英国／イギリス／グレートブリテン及び北部アイルランド連合王国'), '英国')
        self.assertEqual(mofa.display_name('ジョージア（旧グルジア）'), 'ジョージア')

    def test_where_is_faithful(self):
        f = mofa.where_is_faithful
        self.assertTrue(f(SECTION, 4, 'シリアとの国境地帯'))
        self.assertTrue(f(SECTION, 3, 'ディヤルバクル県及びイラクとの国境地帯'))
        self.assertFalse(f(SECTION, 3, 'シリアとの国境地帯'))        # 直後のレベルが違う
        self.assertFalse(f(SECTION, 4, 'どこにもない地域'))
        self.assertTrue(f(SECTION, 1, '上記以外の地域'))
        self.assertFalse(f(SECTION, 4, ''))

    def test_section_with_alternative_heading(self):
        txt = '前置き\n【危険度】\n●ミンダナオ地方\nレベル3：渡航は止めてください。\n【ポイント】\n本文'
        sec = mofa.extract_section(txt)
        self.assertTrue(sec.startswith('【危険度】'))
        self.assertNotIn('本文', sec)
        self.assertTrue(mofa.where_is_faithful(sec, 3, 'ミンダナオ地方'))
        self.assertEqual(mofa.section_of({'section': '', 'body': txt}), sec)       # 節が空の古いキャッシュは、本文から取り直す
        self.assertEqual(mofa.extract_section('見出しなし'), '')

    def test_where_with_repeated_phrase_checks_each_occurrence(self):
        sec = '●A州のイエメンとの国境地帯を除く地域\nレベル2：x\n●イエメンとの国境地帯\nレベル3：y'
        self.assertTrue(mofa.where_is_faithful(sec, 3, 'イエメンとの国境地帯'))


def fake_cache(pages=None):
    def c(code, name, risk, area='10'):
        return dict(name=name, area=area, risk=risk, infection=[], risk_title='t', risk_date='2026/01/01 00:00:00',
                    risk_url='https://example.com/' + code, last_modified='2026/10/13 08:55:46', name_live=name, has_risk_block=True)
    countries = {'0001': c('0001', 'アルファ', []), '0002': c('0002', 'ベータ', [1]), '0003': c('0003', 'ガンマ', [3, 2]),
                 '0004': c('0004', 'デルタ', [4, 1]), '0005': c('0005', 'イプシロン', [2])}
    pages = pages or {'0002': dict(levels=[1], section='', body=''),
                      '0003': dict(levels=[2, 3], section='【危険レベル】\n●北部\nレベル3：x', body='北部で衝突が発生している'),
                      '0004': dict(levels=[1, 4], section='', body=''),
                      '0005': dict(levels=[1], section='', body='')}       # 最大レベル2 が本文に出てこない → 除外
    return dict(fetched='2026-10-13T09:00:00', countries=countries, pages=pages)


class ClassifyTest(unittest.TestCase):
    def test_classify_excludes_mismatch_and_keeps_level_zero(self):
        v, ex = mofa.classify(fake_cache())
        self.assertEqual({r['code'] for r in v}, {'0001', '0002', '0003', '0004'})
        self.assertEqual([r['code'] for r in ex], ['0005'])
        self.assertEqual(next(r for r in v if r['code'] == '0001')['level'], 0)
        self.assertIn('レベル2', ex[0]['reason'])

    def test_check_members(self):
        c = fake_cache()
        v, ex = mofa.classify(c)
        spec = {'members': [{'code': '0003', 'label': 'ガンマ', 'where': '北部', 'why': [{'text': 't', 'evidence': '北部で衝突が発生している'}]}]}
        problems = []
        mofa.check_members(spec, c, v, ex, problems)
        self.assertEqual(problems, [])
        bad = {'members': [{'code': '0003', 'label': 'ガンマ', 'where': '南部', 'why': [{'text': 't', 'evidence': '書かれていない文言'}]},
                           {'code': '0005', 'label': 'イプシロン'}, {'code': '9999', 'label': 'なし'}]}
        problems = []
        mofa.check_members(bad, c, v, ex, problems)
        self.assertEqual(len(problems), 4)           # where・evidence・除外された国・存在しない国


def tier_spec(**kw):
    c = fake_cache()
    v, ex = mofa.classify(c)
    spec = {
        'id': 't', 'template': 'tier_board', 'metric': 'm', 'year': 2026, 'unit': 'u',
        'source': {'name': 'n', 'url': 'https://example.com'}, 'verification': 'v',
        'title': 'T', 'title_small': 's', 'subtitle': '{asof}',
        'tier_data': dict(asof='2026年10月13日', fetched=c['fetched'], countries=v, excluded=ex),
        'tiers': [
            {'level': 0, 'title': 'なし', 'sub': 's', 'color': [60, 100, 90], 'say': '{count}か国'},
            {'level': 1, 'title': 'L1', 'sub': 's', 'color': [190, 160, 45], 'say': '{count}か国'},
            {'level': 3, 'title': 'L3', 'sub': 's', 'color': [200, 20, 30], 'say': '{count}か国', 'spotlight': True},
            {'level': 4, 'title': 'L4', 'sub': 's', 'color': [120, 0, 14], 'say': '{count}か国'},
        ],
        'members': [{'code': '0001', 'label': 'アルファ'}, {'code': '0002', 'label': 'ベータ'},
                    {'code': '0003', 'label': 'ガンマ', 'where': '北部', 'say': 'ガンマ。北部がレベル3です。'},
                    {'code': '0004', 'label': 'デルタ'}],
        'hooks': [{'say': 'フック', 'min': 2.0, 'gap': 0.4, 'y': 380, 'fade': 0.4, 'panel': [['t', 60, 'white', 'Bold']]}],
        'cta': {'say': '{n_high}か国', 'panel': [['t', 50, 'white', 'Bold']]},
    }
    spec.update(kw)
    return spec


class TierThemeTest(unittest.TestCase):
    def test_members_and_levels(self):
        T = tiertheme.TierTheme(tier_spec())
        self.assertTrue(T.subset)
        self.assertEqual([t['level'] for t in T.TIERS], [0, 1, 3, 4])
        self.assertEqual(T.V['n_high'], 2)               # レベル3以上: ガンマ(3)とデルタ(4)
        self.assertEqual(T.V['excluded_note'], '')       # 国を指定したときは除外の注記なし

    def test_spotlight_needs_say_and_uses_it(self):
        s = tier_spec()
        T = tiertheme.TierTheme(s)
        self.assertEqual(T.narration_lines()['item:0003'], 'ガンマ。北部がレベル3です。')
        del s['members'][2]['say']
        with self.assertRaises(ThemeError):
            tiertheme.TierTheme(s)

    def test_timeline_is_continuous(self):
        T = tiertheme.TierTheme(tier_spec())
        t = T.T_HOOK
        for sg in T.SEQ:
            self.assertAlmostEqual(sg['start'], t, places=6)
            t = sg['start'] + sg['dur']
        self.assertAlmostEqual(t, T.T_COUNT_END, places=6)
        spot = next(sg for sg in T.SEQ if sg['tier']['spotlight'])
        self.assertGreaterEqual(spot['items'][0]['dur'], 4.2)

    def test_errors(self):
        s = tier_spec()
        s['tier_data'] = None
        with self.assertRaises(ThemeError):
            tiertheme.TierTheme(s)
        s = tier_spec()
        s['members'].append({'code': '9999', 'label': 'x'})
        with self.assertRaises(ThemeError):
            tiertheme.TierTheme(s)
        s = tier_spec()
        s['tiers'].append(dict(s['tiers'][0]))            # level の重複
        with self.assertRaises(ThemeError):
            tiertheme.TierTheme(s)

    def test_post_md_has_no_map_credit(self):
        s = tier_spec(post={'title': '{asof}', 'description': 'd {excluded_note}', 'hashtags': ['#a']})
        md = tiertheme.TierTheme(s).post_md()
        self.assertNotIn('Natural Earth', md)
        self.assertIn('2026年10月13日', md)


class RenderSmokeTest(unittest.TestCase):
    def test_tiers_render_with_and_without_style(self):
        import render_list
        import render
        try:
            render.F(40)
        except SystemExit:
            self.skipTest('日本語フォントがありません')
        for style in ({}, {'look': 'horror', 'bg': {'top': [3, 0, 1], 'bottom': [28, 2, 5], 'fog': [120, 0, 12], 'vignette': 0.7, 'grain': 0.03},
                           'title_color': [206, 18, 30], 'title_glow': [150, 0, 8], 'drips': [150, 0, 10],
                           'fx': {'shake': 14, 'flash': [170, 0, 10], 'flash_alpha': 0.35}}):
            T = tiertheme.TierTheme(tier_spec(style=style))
            lay = render_list.init(T)
            spot = next(sg for sg in T.SEQ if sg['tier']['spotlight'])['items'][0]
            for t in (1.0, T.SEQ[0]['start'] + 1.0, spot['start'] + 0.5, spot['start'] + 1.1, spot['start'] + 3.0, T.T_COUNT_END + 1.0):
                self.assertEqual(lay.frame(t).size, (1080, 1920))
        render_list.apply_style(None)                      # 後続のテストに影響を残さない


if __name__ == '__main__':
    unittest.main()
