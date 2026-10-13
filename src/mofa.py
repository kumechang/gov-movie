"""外務省 海外安全情報オープンデータ（国別の危険レベル）の取得。

  python3 src/mofa.py [--refetch]    全207か国の危険レベルを取得して一覧を表示（キャッシュは build/mofa_cache.json）

データ: https://www.ezairyu.mofa.go.jp/html/opendata/index.html
利用条件（確認日 2026-10-13）: 商用利用可。出典の記載と、加工した旨の記載が必要（政府標準利用規約2.0版準拠、CC BY 互換）。
  規約: https://www.ezairyu.mofa.go.jp/html/opendata/support/terms.html
フラグの意味（公式のファイルフォーマットより）: riskLevelN は「危険レベルNの地域を含む／含まない」。
  国全体のレベルではなく、**国内に含まれるレベル**の集合。この値から言えるのは「国内で最も高いレベル」まで。
  「全土がレベルN」とは言えない（一部地域だけのことがある）ので、動画の文言は「〜の地域を含む」にする。
運用の注意: 更新は5分ごと。「短時間における大量のアクセス」は禁止なので、1か国ずつ間隔を空け、
  各国のファイルの先頭（危険レベルのフラグが載っている部分）だけを読んで切る。キャッシュは既定で24時間使う。
"""
import csv
import datetime
import html
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..')
URL = 'https://www.ezairyu.mofa.go.jp/opendata/country/%s.xml'
COUNTRIES_CSV = os.path.join(ROOT, 'data', 'mofa_countries.csv')
HEAD_BYTES = 24000          # フラグ・危険情報の件名は先頭の数KBに入っている
PAUSE = 0.35                # 国ごとの待ち（秒）
AREAS = {'10': 'アジア', '20': '大洋州', '30': '北米', '33': '中南米', '42': 'ヨーロッパ', '50': '中東', '60': 'アフリカ'}
LEVEL_NAMES = {4: '退避してください', 3: '渡航は止めてください', 2: '不要不急の渡航は止めてください', 1: '十分注意してください'}
LEVEL_OFFICIAL = {4: '退避勧告', 3: '渡航中止勧告', 2: '不要不急の渡航中止', 1: '十分注意'}


class MofaError(RuntimeError):
    pass


def now_jst():
    """日本時間の現在時刻（タイムゾーンなし）。取得日の表示とキャッシュの期限に使う"""
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).replace(tzinfo=None)


def countries():
    """公式の国コード一覧（data/mofa_countries.csv）: [(コード, 名称, 地域コード)]"""
    with open(COUNTRIES_CSV, encoding='utf-8', newline='') as f:
        return [(r['country_code'], r['name'], r['area_code']) for r in csv.DictReader(f)]


def _tag(b, name):
    m = re.search(r'<%s[^>]*>(.*?)</%s>' % (name, name), b, re.S)
    return m.group(1).strip() if m else None


def parse_country(xml_head):
    """国別XMLの先頭部分から、危険レベル・感染症危険レベル・件名・日時・最終更新を取り出す"""
    def flag(tag):
        v = _tag(xml_head, tag)
        return None if v is None else v.upper() in ('1', 'Y')
    risk = {n: flag('riskLevel%d' % n) for n in (4, 3, 2, 1)}
    infection = {n: flag('infectionLevel%d' % n) for n in (4, 3, 2, 1)}
    m = re.search(r'<opendata[^>]*lastModified="([^"]+)"', xml_head)
    country = re.search(r'<country\b[^>]*>(.*?)</country>', xml_head, re.S)
    return dict(
        has_risk_block=all(v is not None for v in risk.values()),
        risk=[n for n in (4, 3, 2, 1) if risk[n]],            # 含まれるレベル（高い順）
        infection=[n for n in (4, 3, 2, 1) if infection[n]],
        risk_title=_tag(xml_head, 'riskTitle'),
        risk_date=_tag(xml_head, 'riskLeaveDate'),
        risk_url=_tag(xml_head, 'riskUrl'),
        last_modified=m.group(1) if m else None,
        name_live=_tag(country.group(1), 'name') if country else None,
    )


def fetch_country(code, opener=urllib.request.urlopen):
    req = urllib.request.Request(URL % code, headers={'User-Agent': 'gov-movie (personal research; polite; reads file head only)'})
    last = None
    for attempt in range(3):
        try:
            with opener(req, timeout=60) as r:
                head = r.read(HEAD_BYTES).decode('utf-8', 'ignore')
            return parse_country(head)
        except (urllib.error.URLError, OSError) as e:
            last = e
            time.sleep(2 * (attempt + 1))
    raise MofaError('国コード %s の取得に失敗: %s' % (code, last))


def fetch_all(cache_path=None, refetch=False, max_age_hours=24, log=print, sleep=time.sleep):
    """全国の危険レベルを取得して {'fetched': ISO日時, 'countries': {コード: {...}}} を返す（失敗は MofaError）"""
    if cache_path and os.path.exists(cache_path) and not refetch:
        with open(cache_path, encoding='utf-8') as f:
            c = json.load(f)
        age = now_jst() - datetime.datetime.fromisoformat(c['fetched'])
        if age < datetime.timedelta(hours=max_age_hours):
            return c
        log('キャッシュが%d時間以上前のため取り直します' % max_age_hours)
    out = {}
    rows = countries()
    for i, (code, name, area) in enumerate(rows):
        d = fetch_country(code)
        d.update(name=name, area=area)
        out[code] = d
        if i % 40 == 0:
            log('取得 %d/%d' % (i + 1, len(rows)))
        sleep(PAUSE)
    c = dict(fetched=now_jst().isoformat(timespec='seconds'), countries=out)
    if cache_path:
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(c, f, ensure_ascii=False)
    return c


def max_level(d):
    return d['risk'][0] if d['risk'] else 0


def display_name(name):
    """画面・読み上げ用の短い名前（「／」以降と（）の補足を落とす）"""
    n = re.sub(r'[（(].*?[）)]', '', name).split('／')[0].strip()
    return n or name


# ---------- 2系統目の照合: 公式の危険情報ページ（HTML）の本文 ----------
_ZEN = str.maketrans('１２３４', '1234')
PAGE_UA = {'User-Agent': 'gov-movie (personal research; polite)'}


def page_info(url, opener=urllib.request.urlopen):
    """危険情報ページを読み、本文に出てくる「レベルN」の集合 と、「【危険レベル】」の節の本文（地域ごとのレベル）を返す。
    集合には隣国のレベルへの言及も含まれうる。"""
    req = urllib.request.Request(url, headers=PAGE_UA)
    with opener(req, timeout=60) as r:
        t = r.read().decode('utf-8', 'ignore')
    body = re.sub(r'<(script|style)[^>]*>.*?</\1>', '', t, flags=re.S)
    txt = html.unescape(re.sub(r'<[^>]+>', '\n', body)).translate(_ZEN)
    txt = re.sub(r'[ \t\u3000]+', ' ', txt)
    levels = sorted({int(x) for x in re.findall(r'レベル\s*([1-4])', txt)})
    i = txt.find('【危険レベル】')
    j = txt.find('【ポイント】', i) if i >= 0 else -1
    section = re.sub(r'\n\s*\n+', '\n', txt[i:j if j > i else i + 4000]).strip() if i >= 0 else ''
    return dict(levels=levels, section=section[:6000], body=re.sub(r'\n\s*\n+', '\n', txt).strip()[:20000])


def verify_pages(c, cache_path=None, log=print, sleep=time.sleep):
    """危険レベルのある国の危険情報ページを読み、c['pages'][コード] = {levels, section} を埋める（取得済みは飛ばす）"""
    pages = c.setdefault('pages', {})
    todo = [code for code, d in c['countries'].items()
            if d['risk'] and d['risk_url'] and not (isinstance(pages.get(code), dict) and 'body' in pages[code])]
    for i, code in enumerate(todo):
        try:
            pages[code] = page_info(c['countries'][code]['risk_url'])
        except (urllib.error.URLError, OSError):
            pages[code] = None
        if i % 40 == 0:
            log('危険情報ページの照合 %d/%d' % (i + 1, len(todo)))
        sleep(PAUSE)
    if cache_path and todo:
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(c, f, ensure_ascii=False)
    return c


def _squash(x):
    """空白を除き、全角・半角の違い（６と6、（と(）をそろえて比べる"""
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', x))


def where_is_faithful(section, level, where):
    """画面に出す「地域の文言」が、公式ページの「危険レベル」の節にそのまま出てきて、その直後のレベル表示が level であること"""
    sec, w = _squash(section), _squash(where)
    if not w:
        return False
    start = 0
    while True:
        i = sec.find(w, start)
        if i < 0:
            return False
        m = re.search(r'レベル([1-4])', sec[i + len(w):])
        if m and int(m.group(1)) == level:
            return True
        start = i + 1


def classify(c):
    """照合結果で国を分ける。XMLの最大レベルが公式ページ本文に出てくれば verified、出なければ（古いデータの疑い）excluded"""
    verified, excluded = [], []
    for code, d in c['countries'].items():
        lv = max_level(d)
        if lv == 0:
            verified.append(dict(code=code, name=d['name'], short=display_name(d['name']), area=d['area'], level=0, flags=[],
                                 page_levels=None, risk_date=None, title=None))
            continue
        info = (c.get('pages') or {}).get(code)
        pg = info['levels'] if isinstance(info, dict) else None
        row = dict(code=code, name=d['name'], short=display_name(d['name']), area=d['area'], level=lv, flags=d['risk'],
                   page_levels=pg, risk_date=d['risk_date'], title=d['risk_title'])
        if pg is None:
            row['reason'] = '危険情報ページを取得できなかった'
            excluded.append(row)
        elif lv in pg:
            verified.append(row)
        else:
            row['reason'] = 'XMLの最大レベル%d が、危険情報ページ本文（%s）に出てこない' % (lv, '、'.join('レベル%d' % x for x in pg) or 'レベルの記載なし')
            excluded.append(row)
    key = lambda r: (r['area'], r['code'])
    return sorted(verified, key=key), sorted(excluded, key=key)


def summary_report(c, verified, excluded):
    n_all = len(c['countries'])
    by = {n: sum(1 for r in verified if r['level'] == n) for n in (4, 3, 2, 1)}
    none = sum(1 for r in verified if r['level'] == 0)
    lines = [
        '[取得] 外務省 海外安全情報オープンデータ（国別 %d か国）  取得日時 %s' % (n_all, c['fetched']),
        '  国別XMLの最終更新: %s' % max(d['last_modified'] for d in c['countries'].values() if d['last_modified']),
        '  最大レベル別（照合できた国）: ' + ' / '.join('レベル%d %d か国' % (n, by[n]) for n in (4, 3, 2, 1)) + ' / 危険情報なし %d か国' % none,
        '[照合] 公式の危険情報ページ本文との照合: %d か国中 %d か国が一致' % (len(excluded) + sum(by.values()), sum(by.values())),
    ]
    for r in excluded:
        lines.append('  ×除外 %s（XML最大レベル%d）: %s' % (r['name'], r['level'], r['reason']))
    inf = [(d['name'], d['infection']) for d in c['countries'].values() if d['infection']]
    if inf:
        lines.append('  （感染症危険レベルは使わない。参考: %s）' % '、'.join('%s%s' % (n, v) for n, v in inf))
    return '\n'.join(lines)


def check_members(spec, c, verified, excluded, problems):
    """spec['members']（対象の絞り込み）を検証する。
    - 国コードが取得データにあり、照合で除外されていないこと
    - where（最も高いレベルの地域の文言）が、公式の危険情報ページの「危険レベル」の節にそのまま出てきて、直後のレベル表示が一致すること
    - why[].evidence（危険の理由の根拠の文言）が、公式の危険情報ページの本文にそのまま出てくること
    """
    members = spec.get('members')
    if not members:
        return []
    lv = {r['code']: r for r in verified}
    bad = {r['code']: r for r in excluded}
    lines = ['[対象の検証] 指定した %d か国' % len(members)]
    for m in members:
        code = str(m['code'])
        if code in bad:
            problems.append('%s: 公式ページとの照合で除外された国です（%s）。画面に出せません' % (m.get('label', code), bad[code]['reason']))
            continue
        r = lv.get(code)
        if r is None:
            problems.append('%s: 国コード %s が取得データにありません' % (m.get('label', code), code))
            continue
        info = (c.get('pages') or {}).get(code) or {}
        if m.get('where'):
            if not where_is_faithful(info.get('section', ''), r['level'], m['where']):
                problems.append('%s: where「%s」が、公式ページの「危険レベル」の節にレベル%d の地域として出てきません（ページが更新された可能性。文言を確かめてください）'
                                % (m['label'], m['where'], r['level']))
        for rg in m.get('regions', []):             # 地図に出す地域ごとのレベル（place_vs_risk）
            if not where_is_faithful(info.get('section', ''), rg['level'], rg['where']):
                problems.append('%s: 地域「%s」が、公式ページの「危険レベル」の節にレベル%d として出てきません（ページが更新された可能性）'
                                % (m['label'], rg['where'], rg['level']))
            if rg.get('note') and _squash(rg['note']) not in _squash(info.get('body', '')):
                problems.append('%s: 地域「%s」の note「%s」が、公式ページの本文にそのまま出てきません' % (m['label'], rg['where'], rg['note']))
        for ab in m.get('absent_places', []):        # 「危険レベルの節に載っていない場所」: 地名が節に出てこないこと
            hit = [n for n in ab['names'] if _squash(n) in _squash(info.get('section', ''))]
            if hit:
                problems.append('%s: %s は「危険レベル」の節に載っていません、と言えません（%s が出てきます）' % (m['label'], ab['place'], '、'.join(hit)))
        for w in m.get('why', []):
            ev = w.get('evidence', '')
            if not ev or _squash(ev) not in _squash(info.get('body', '')):
                problems.append('%s: why「%s」の根拠の文言「%s」が、公式ページの本文に出てきません' % (m['label'], w.get('text'), ev))
        lines.append('  %s: レベル%d%s' % (m['label'], r['level'], '（地域・理由の文言を公式ページ本文と照合済み）' if m.get('where') or m.get('why') or m.get('regions') else ''))
    return lines


def resolve(spec, cache_path=None, refetch=False, log=print):
    """source.fetch: mofa_risk のテーマ用。取得・照合して spec['tier_data'] を埋め、(spec, レポート) を返す"""
    conf = spec.get('mofa') or {}
    c = fetch_all(cache_path, refetch, int(conf.get('max_age_hours', 24)), log)
    problems = []
    if len(c['countries']) < 200:
        problems.append('国の数が少なすぎます: %d' % len(c['countries']))
    odd = [(d['name'], d['name_live']) for d in c['countries'].values() if d['name_live'] and display_name(d['name_live']) != display_name(d['name'])]
    if odd:
        problems.append('国コードに対応する名称が公式一覧と違います（コードの付け替えの疑い）: %s' % odd)
    fetched = datetime.datetime.fromisoformat(c['fetched'])
    lm = [datetime.datetime.strptime(d['last_modified'], '%Y/%m/%d %H:%M:%S') for d in c['countries'].values() if d['last_modified']]
    if not lm or fetched - max(lm) > datetime.timedelta(days=3):
        problems.append('国別XMLの最終更新が古い（%s）' % (max(lm) if lm else 'なし'))
    verify_pages(c, cache_path, log)
    verified, excluded = classify(c)
    if sum(1 for r in verified if r['level'] >= 3) < 10:
        problems.append('レベル3以上の国が極端に少ないです（取得の失敗の疑い）')
    lines_extra = check_members(spec, c, verified, excluded, problems)
    report = summary_report(c, verified, excluded)
    if lines_extra:
        report += '\n' + '\n'.join(lines_extra)
    if problems:
        raise MofaError('外務省データの検証に失敗しました:\n' + '\n'.join('  ・' + p for p in problems) + '\n\n' + report)
    out = dict(spec)
    out['tier_data'] = dict(fetched=c['fetched'], asof=fetched.strftime('%Y年%-m月%-d日'), countries=verified, excluded=excluded)
    return out, report


def main(argv):
    cache = os.path.join(ROOT, 'build', 'mofa_cache.json')
    c = fetch_all(cache, '--refetch' in argv)
    by = {n: [] for n in (4, 3, 2, 1, 0)}
    for code, d in c['countries'].items():
        by[max_level(d)].append(d['name'])
    print('取得日時 %s' % c['fetched'])
    for n in (4, 3, 2, 1, 0):
        print('最大レベル%d: %d か国' % (n, len(by[n])), '' if n < 2 and by[n] else '', ('、'.join(by[n]) if n >= 2 else ''))
    odd = [(code, d['name'], d['name_live']) for code, d in c['countries'].items() if d['name_live'] and d['name_live'] != d['name']]
    print('名称の不一致:', odd)
    print('危険情報のブロックが無い国:', [d['name'] for d in c['countries'].values() if not d['has_risk_block']])
    print('感染症レベルあり:', [(d['name'], d['infection']) for d in c['countries'].values() if d['infection']])


if __name__ == '__main__':
    main(sys.argv[1:])
