"""e-Stat 取得層のテスト。ネットワークには出ない（_get を差し替える）。
実行: python3 -m unittest discover -s tests   （リポジトリ直下から）
"""
import copy
import os
import sys
import unittest
import urllib.error
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'src'))
import estat  # noqa: E402
import fetch_estat  # noqa: E402
import theme  # noqa: E402

YAML = os.path.join(ROOT, 'themes', 'divorce_rate_2024.yaml')
FAKE_ID = 'FAKE-APP-ID-0123456789abcdef'


def fake_table(sid, values, national, unit='人口千対', time='2024000000', title='テスト表'):
    """_get の戻り値と同じ形の表を作る。values は {県名(フル): 値}。"""
    codes = {theme.full(p): fetch_estat.area_code(p) for p in theme.PREFS}
    rows = [{'@area': '00000', '@unit': unit, '@time': time, '$': str(national)}]
    rows += [{'@area': codes[n], '@unit': unit, '@time': time, '$': str(v)} for n, v in values.items()]
    area = {'00000': {'@code': '00000', '@name': '全国'}}
    area.update({c: {'@code': c, '@name': n} for n, c in codes.items()})
    return dict(sid=sid, select={}, classes={'area': area}, values=rows, total={}, fetched='2026-01-01',
                info={'STATISTICS_NAME': '人口動態調査 人口動態統計 確定数 離婚', 'TITLE': title,
                      'SURVEY_DATE': '202401-202412', 'OPEN_DATE': '2026-03-17', 'UPDATED_DATE': '2026-04-15'})


class FetchTest(unittest.TestCase):
    def setUp(self):
        self.spec = theme.load_spec(YAML)
        self.vals = {theme.full(k): v for k, v in self.spec['values'].items()}
        self.tables = {}

    def run_fetch(self, spec=None, refetch=True):
        spec = spec or self.spec

        def fake_get(sid, select):
            return copy.deepcopy(self.tables[sid])

        with mock.patch.object(fetch_estat, '_get', fake_get):
            return fetch_estat.fetch_values(spec)

    def test_ok_with_cross_checks(self):
        self.tables['0003411861'] = fake_table('0003411861', self.vals, 1.55)
        self.tables['0003411562'] = fake_table('0003411562', self.vals, 1.55)
        # 件数÷人口の再計算用: 人口 1,000,000 に対し 件数 = 率×1000（同じ表を分子・分母で共用するので別表にする）
        spec = copy.deepcopy(self.spec)
        spec['estat']['cross'] = [spec['estat']['cross'][0]]
        values, avg, report = self.run_fetch(spec)
        self.assertEqual(values, self.vals)
        self.assertEqual(avg, 1.55)
        self.assertIn('全件一致', report)

    def test_derived_cross_check(self):
        self.tables['0003411861'] = fake_table('0003411861', self.vals, 1.55)
        self.tables['num'] = fake_table('num', {n: v * 1000 for n, v in self.vals.items()}, 1550)
        self.tables['den'] = fake_table('den', {n: 1000000 for n in self.vals}, 1000000)
        spec = copy.deepcopy(self.spec)
        spec['estat']['cross'] = [{'label': '再計算', 'numerator': {'statsDataId': 'num'},
                                   'denominator': {'statsDataId': 'den'}, 'scale': 1000}]
        _, _, report = self.run_fetch(spec)
        self.assertIn('再計算', report)

    def test_mismatch_with_yaml_values_is_error(self):
        bad = dict(self.vals, 東京都=0.96)
        self.tables['0003411861'] = fake_table('0003411861', bad, 1.55)
        spec = copy.deepcopy(self.spec)
        spec['estat']['cross'] = []
        with self.assertRaises(fetch_estat.FetchError) as cm:
            self.run_fetch(spec)
        self.assertIn('東京都', str(cm.exception))

    def test_year_and_unit_mismatch_are_errors(self):
        spec = copy.deepcopy(self.spec)
        spec['estat']['cross'] = []
        self.tables['0003411861'] = fake_table('0003411861', self.vals, 1.55, time='2023000000')
        with self.assertRaises(fetch_estat.FetchError):
            self.run_fetch(spec)
        self.tables['0003411861'] = fake_table('0003411861', self.vals, 1.55, unit='件')
        with self.assertRaises(fetch_estat.FetchError):
            self.run_fetch(spec)

    def test_missing_symbol_and_duplicate_are_errors(self):
        spec = copy.deepcopy(self.spec)
        spec['estat']['cross'] = []
        t = fake_table('0003411861', self.vals, 1.55)
        t['values'][5]['$'] = '-'
        self.tables['0003411861'] = t
        with self.assertRaises(fetch_estat.FetchError):
            self.run_fetch(spec)
        t = fake_table('0003411861', self.vals, 1.55)
        t['values'].append(dict(t['values'][3]))
        self.tables['0003411861'] = t
        with self.assertRaises(fetch_estat.FetchError):
            self.run_fetch(spec)

    def test_without_expected_values_fills_from_estat(self):
        spec = copy.deepcopy(self.spec)
        spec.pop('values'), spec.pop('average')
        spec['estat']['cross'] = []
        self.tables['0003411861'] = fake_table('0003411861', self.vals, 1.55)
        with mock.patch.object(fetch_estat, '_get', lambda sid, select: copy.deepcopy(self.tables[sid])):
            out, _ = fetch_estat.resolve(spec)
        self.assertEqual(theme.Theme(out).RANK['沖縄県'], 1)


class AppIdTest(unittest.TestCase):
    def test_redact_hides_plain_and_encoded_forms(self):
        with mock.patch.dict(os.environ, {estat.ENV_NAME: 'a b+c/d'}):
            text = 'x a b+c/d y a%20b%2Bc%2Fd z a+b%2Bc%2Fd'
            self.assertNotIn('a b', estat.redact(text))
            self.assertNotIn('%2Bc', estat.redact(text))

    def test_errors_do_not_leak_app_id(self):
        with mock.patch.dict(os.environ, {estat.ENV_NAME: FAKE_ID}):
            err = urllib.error.URLError('failed for https://x/?appId=%s' % FAKE_ID)
            with mock.patch('urllib.request.urlopen', side_effect=err):
                with self.assertRaises(estat.EstatError) as cm:
                    estat.call('getStatsData', statsDataId='1')
            self.assertNotIn(FAKE_ID, str(cm.exception))
            http = urllib.error.HTTPError('https://x/?appId=%s' % FAKE_ID, 403, 'no', {}, None)
            with mock.patch('urllib.request.urlopen', side_effect=http):
                with self.assertRaises(estat.EstatError) as cm:
                    estat.call('getStatsData', statsDataId='1')
            self.assertNotIn(FAKE_ID, str(cm.exception))

    def test_missing_app_id_message(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(estat.EstatError):
                estat.app_id()


if __name__ == '__main__':
    unittest.main()
