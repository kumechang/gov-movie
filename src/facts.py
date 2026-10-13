"""「人気の根拠」になる事実（世界遺産・無形文化遺産・映画のロケ地・写真）を Wikidata / ja.wikipedia / Wikimedia Commons から取得し、2系統で照合する。

  Wikidata（CC0）の主張  ×  ja.wikipedia の本文にその語が出てくること  → 一致した事実だけを動画に使う。
  写真は Commons のライセンスを API で確かめ、CC0 / パブリックドメイン / CC BY だけを使う（CC BY-SA・NC・ND は使わない）。
Wikimedia のAPIは回数制限が厳しい（429）ので、間隔をあけ、結果は build/facts_cache.json に残す。
"""
import html
import json
import os
import re
import time
import urllib.parse
import urllib.request

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
UA = 'gov-movie/0.1 (self-use research tool; https://github.com/kumechang/gov-movie)'
MIN_GAP = 1.5                      # 連続リクエストの最小間隔（秒）
WD_API = 'https://www.wikidata.org/w/api.php'
WP_API = 'https://ja.wikipedia.org/w/api.php'
COMMONS_API = 'https://commons.wikimedia.org/w/api.php'
WORLD_HERITAGE = 'Q9259'           # 世界遺産
ICH_LIST = 'Q1459900'              # 人類の無形文化遺産の代表的な一覧（Wikidata 上の指定先。ページの内容で別途確かめる）


class FactsError(RuntimeError):
    pass


_state = {'last': 0.0, 'cache': None, 'path': None}


def open_cache(path):
    _state['path'] = path
    _state['cache'] = {}
    if path and os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            _state['cache'] = json.load(f)


def _save():
    if _state['path']:
        os.makedirs(os.path.dirname(_state['path']), exist_ok=True)
        with open(_state['path'], 'w', encoding='utf-8') as f:
            json.dump(_state['cache'], f, ensure_ascii=False)


def _fetch(url, sleep=time.sleep, opener=urllib.request.urlopen, binary=False, tries=6, wait_429=True):
    last_err = None
    for i in range(tries):
        wait = _state['last'] + MIN_GAP - time.time()
        if wait > 0:
            sleep(wait)
        _state['last'] = time.time()
        try:
            with opener(urllib.request.Request(url, headers={'User-Agent': UA}), timeout=60) as r:
                data = r.read()
            return data if binary else json.loads(data.decode('utf-8'))
        except urllib.error.HTTPError as e:
            last_err = 'HTTP %s' % e.code
            if e.code not in (429, 503):
                break
            try:
                retry = int(e.headers.get('Retry-After', ''))       # サーバーが待つ秒数を教えてくれる
            except (TypeError, ValueError):
                retry = 0
            if not wait_429:                                   # API は待たずに、ブラウザ経由の予備ルートへ
                break
            wait = min(60, max(retry + 2, 10 * (i + 1)))
            print('  （Wikimedia の回数制限。%d秒待ちます）' % wait, flush=True)
            sleep(wait)
            continue
        except (urllib.error.URLError, TimeoutError) as e:
            last_err = str(e)[:80]
        sleep(25 * (i + 1))
    raise FactsError('取得に失敗しました（%s）: %s' % (last_err, url.split('?')[0]))


def _cached(key, fn):
    if _state['cache'] is None:
        open_cache(None)
    if key not in _state['cache']:
        _state['cache'][key] = fn()
        _save()
    return _state['cache'][key]


def _api(base, **params):
    """API は回数制限（429）が続くことがある。1回失敗したら、この実行ではAPIを諦めて、呼び出し側がブラウザ経由の予備ルートに切り替える"""
    if _state.get('api_blocked'):
        raise FactsError('API は回数制限のためこの実行では使いません')
    try:
        return _fetch(base + '?' + urllib.parse.urlencode(dict(params, format='json')), tries=2, wait_429=False)
    except FactsError:
        _state['api_blocked'] = True
        raise


def _web(fn, *a):
    """予備ルート: ヘッドレス Chromium で通常のページを読む（src/browser.py）"""
    import browser
    try:
        return fn(browser, *a)
    except browser.BrowserError as e:
        raise FactsError(str(e))


# ---------- Wikidata ----------
def _entity(e):
    return dict(label_ja=(e.get('labels', {}).get('ja') or {}).get('value', ''), label_en=(e.get('labels', {}).get('en') or {}).get('value', ''),
                jawiki=(e.get('sitelinks', {}).get('jawiki') or {}).get('title', ''), claims=e.get('claims', {}))


def wd_entity(qid):
    def get():
        try:
            e = _api(WD_API, action='wbgetentities', ids=qid, props='labels|claims|sitelinks', languages='ja|en')['entities'][qid]
        except FactsError:
            e = json.loads(_web(lambda b: b.fetch_text('https://www.wikidata.org/wiki/Special:EntityData/%s.json' % qid)))['entities'][qid]
        if 'missing' in e:
            raise FactsError('Wikidata に %s がありません' % qid)
        return _entity(e)
    return _cached('wd:' + qid, get)


def claim_ids(ent, prop):
    return [s['mainsnak']['datavalue']['value']['id'] for s in ent['claims'].get(prop, []) if s['mainsnak'].get('datavalue')]


def designation_years(ent, target):
    """P1435（文化遺産の指定）が target のとき、その開始年（P580）。無ければ空リスト"""
    out = []
    for s in ent['claims'].get('P1435', []):
        v = (s['mainsnak'].get('datavalue') or {}).get('value')
        if isinstance(v, dict) and v.get('id') == target:
            for q in s.get('qualifiers', {}).get('P580', []):
                m = re.match(r'\+?(\d{4})', q['datavalue']['value']['time'])
                if m:
                    out.append(int(m.group(1)))
    return out


# ---------- ja.wikipedia ----------
def wp_text(title, lang='ja'):
    def get():
        try:
            pages = _api('https://%s.wikipedia.org/w/api.php' % lang, action='query', titles=title, prop='extracts', explaintext=1, redirects=1)['query']['pages']
            return next(iter(pages.values())).get('extract', '')
        except FactsError:
            return _web(lambda b: b.fetch_text('https://%s.wikipedia.org/w/index.php?title=%s&action=raw' % (lang, urllib.parse.quote(title.replace(' ', '_')))))
    return _cached('wp:%s' % title if lang == 'ja' else 'wp:%s:%s' % (lang, title), get)


# ---------- Commons ----------
_OK_LICENSE = re.compile(r'^(CC0.*|Public domain|PD.*|CC BY \d\.\d)$', re.I)


def license_ok(short):
    return bool(_OK_LICENSE.match((short or '').strip())) and not re.search(r'\b(SA|NC|ND)\b', short or '', re.I)


def _strip(s):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', '', s or ''))).strip()


def _parse_commons_page(dom, title):
    """Commons のファイルページ（HTML）から、ライセンス・作者・カテゴリ・元画像の URL を取り出す"""
    def one(pat, flags=re.S):
        m = re.search(pat, dom, flags)
        return m.group(1) if m else ''
    lic = _strip(one(r'class="licensetpl_short"[^>]*>([^<]*)<'))
    aut = _strip(one(r'id="fileinfotpl_aut"[^>]*>.*?</td>\s*<td[^>]*>(.*?)</td>'))
    size = re.search(r'([\d,]+)\s*×\s*([\d,]+)\s*pixels', one(r'class="fileInfo">(.*?)</span>'))
    orig = html.unescape(one(r'class="fullMedia">.*?<a href="([^"]+)"'))
    cats = [_strip(c) for c in re.findall(r'<li><a href="/wiki/Category:[^"]*"[^>]*>([^<]*)</a></li>', one(r'id="mw-normal-catlinks"(.*?)id="mw-hidden-catlinks"') or dom)]
    if not orig or not size:
        raise FactsError('Commons のページから %s の情報を読み取れませんでした（ページの作りが変わった可能性）' % title)
    desc = _strip(one(r'id="fileinfotpl_desc".*?<td class="description">(.*?)</td>'))
    return dict(title=title, thumb=orig, page='https://commons.wikimedia.org/wiki/' + urllib.parse.quote(title.replace(' ', '_')),
                w=int(size.group(1).replace(',', '')), h=int(size.group(2).replace(',', '')), license=lic, artist=aut, credit='', desc=desc,
                categories=['Category:' + c for c in cats], attribution_required='')


def commons_file(title, width=3840):
    def get():
        try:
            pages = _api(COMMONS_API, action='query', titles=title, prop='imageinfo|categories', iiprop='url|size|extmetadata', iiurlwidth=width, cllimit=50)['query']['pages']
        except FactsError:
            return _web(lambda b: _parse_commons_page(b.dump_dom('https://commons.wikimedia.org/wiki/' + urllib.parse.quote(title.replace(' ', '_'))), title))
        p = next(iter(pages.values()))
        if 'imageinfo' not in p:
            raise FactsError('Commons に %s がありません' % title)
        ii, md = p['imageinfo'][0], p['imageinfo'][0].get('extmetadata', {})
        g = lambda k: _strip((md.get(k) or {}).get('value', ''))
        return dict(title=p['title'], thumb=ii.get('thumburl') or ii['url'], page=ii.get('descriptionurl', ''), w=ii['width'], h=ii['height'],
                    license=g('LicenseShortName'), artist=g('Artist'), credit=g('Credit'), desc=g('ImageDescription'),
                    categories=[c['title'] for c in p.get('categories', [])], attribution_required=g('AttributionRequired'))
    return _cached('cm:' + title, get)


def credit_line(info):
    who = info['artist'] or '（作者不詳）'
    return '%s／%s／Wikimedia Commons' % (who[:60], info['license'])


def _thumb_urls(info):
    """写真の取得先の候補。元画像（数MB〜数十MB）は回数制限にかかりやすいので、標準サイズのサムネイル（3840 → 1920 px）を先に試す"""
    u = info['thumb'].split('?')[0]
    m = re.match(r'(https://upload\.wikimedia\.org/wikipedia/commons)/(\w/\w\w)/([^/]+)$', u)
    if not m or info['w'] <= 1920:
        return [u]
    out = []
    for w in (3840, 1920):
        if info['w'] > w:
            out.append('%s/thumb/%s/%s/%dpx-%s' % (m.group(1), m.group(2), m.group(3), w, m.group(3)))
    return out + [u]


def download(info, out_dir, longest=3200):
    """写真を保存して、パスを返す（保存済みならそのまま）。長辺を longest 以内に縮めて JPEG にする"""
    import io
    from PIL import Image
    os.makedirs(out_dir, exist_ok=True)
    fp = os.path.join(out_dir, re.sub(r'[^\w.-]+', '_', info['title'].replace('File:', '')) + '.jpg')
    if os.path.exists(fp):
        return fp
    err = None
    for url in _thumb_urls(info):
        try:
            im = Image.open(io.BytesIO(_fetch(url, binary=True, tries=3))).convert('RGB')
            break
        except (FactsError, OSError) as e:
            err = e
    else:
        raise FactsError('写真を取得できませんでした（%s）: %s' % (err, info['title']))
    im.thumbnail((longest, longest), Image.LANCZOS)
    im.save(fp, 'JPEG', quality=92)
    return fp


# ---------- 検証 ----------
def check_scene(sc, place_qid):
    """scenes[] 1件の事実を2系統で照合する。(問題のリスト, 報告の行) を返す"""
    kind, problems, lines = sc['kind'], [], []
    name = sc.get('name', sc.get('title', kind))
    if kind == 'ich' and not sc.get('wikidata'):
        # Wikidata に該当の項目が無いとき（例: トルココーヒーの文化と伝統）は、ja / en の Wikipedia の2記事で照合する。
        # 同じ Wikipedia の別言語版なので、独立した2系統とは言えない（報告に残す。UNESCO の公式ページは自動取得できない）
        pages = sc.get('wikipedia') or []
        if len(pages) < 2:
            problems.append('%s: wikidata が無いときは wikipedia に2記事（ja と en）を書いてください' % name)
        for pg in pages:
            text = wp_text(pg['title'], pg.get('lang', 'ja'))
            miss = [w for w in pg['contains'] if w not in text]
            if not text:
                problems.append('%s: %s.wikipedia に記事「%s」がありません' % (name, pg.get('lang', 'ja'), pg['title']))
            elif miss:
                problems.append('%s: %s.wikipedia「%s」の本文に %s が出てきません' % (name, pg.get('lang', 'ja'), pg['title'], '、'.join(miss)))
            lines.append('  %s: %s.wikipedia「%s」（%s）' % (name, pg.get('lang', 'ja'), pg['title'], '、'.join(pg['contains'])))
    elif kind in ('heritage', 'ich'):
        ent = wd_entity(sc['wikidata'])
        years = designation_years(ent, sc['designation'])
        if sc['year'] not in years:
            problems.append('%s: Wikidata の指定年 %s が %s と一致しません' % (name, years or '（なし）', sc['year']))
        ref = '世界遺産' if kind == 'heritage' else '無形文化遺産'
        text = wp_text(ent['jawiki']) if ent['jawiki'] else ''
        need = [str(sc['year']), ref] + list(sc.get('wp_contains', []))
        miss = [w for w in need if w not in text]
        if not text:
            problems.append('%s: ja.wikipedia の記事がありません' % name)
        elif miss:
            problems.append('%s: ja.wikipedia の本文に %s が出てきません' % (name, '、'.join(miss)))
        lines.append('  %s: Wikidata %s（%s、%s年）× ja.wikipedia「%s」' % (name, sc['wikidata'], ref, years, ent['jawiki']))
    elif kind == 'film':
        for fm in sc['films']:
            ent = wd_entity(fm['wikidata'])
            places = claim_ids(ent, 'P915')
            if place_qid not in places and not any(p in places for p in sc.get('place_ids', [])):
                problems.append('%s: Wikidata の撮影場所に %s が含まれません' % (fm['name'], place_qid))
            for pq in fm.get('places', []):               # その映画の撮影場所に、写真の場所が含まれること
                if pq not in places:
                    problems.append('%s: Wikidata の撮影場所に %s が含まれません' % (fm['name'], pq))
            ys = [int(m.group(1)) for s_ in ent['claims'].get('P577', []) if (m := re.match(r'\+?(\d{4})', s_['mainsnak']['datavalue']['value']['time']))]
            if fm.get('year') not in ys:
                problems.append('%s: Wikidata の公開年 %s が %s と一致しません' % (fm['name'], ys or '（なし）', fm.get('year')))
            text = wp_text(ent['jawiki']) if ent['jawiki'] else ''
            miss = [w for w in sc.get('wp_contains', []) if w not in text]
            if not text:
                problems.append('%s: ja.wikipedia の記事がありません' % fm['name'])
            elif miss:
                problems.append('%s: ja.wikipedia の本文に %s が出てきません' % (fm['name'], '、'.join(miss)))
            lines.append('  %s（%s）: Wikidata %s（撮影場所に %s）× ja.wikipedia「%s」' % (fm['name'], fm.get('year'), fm['wikidata'], place_qid, ent['jawiki']))
    elif kind != 'night':
        problems.append('%s: 不明な kind です: %s' % (name, kind))
    ph = sc.get('photo')
    if ph:
        info = commons_file(ph['file'])
        if not license_ok(info['license']):
            problems.append('%s: 写真 %s のライセンス「%s」は使えません（CC0 / パブリックドメイン / CC BY のみ）' % (name, ph['file'], info['license']))
        if ph.get('must_mention'):                 # 例: night。ファイル名・説明・カテゴリのどれかに出てくること（夜景の写真かどうかの確認）
            hay = ' '.join([info['title'], info['desc']] + info['categories']).lower()
            if ph['must_mention'].lower() not in hay:
                problems.append('%s: 写真 %s のファイル名・説明・カテゴリに「%s」がありません' % (name, ph['file'], ph['must_mention']))
        lines.append('  写真 %s: %s ／ %s' % (ph['file'], info['license'], credit_line(info)))
    return problems, lines


def resolve(spec, cache_path, img_dir, log=print):
    """place_vs_risk のテーマ用。scenes[] の事実を照合し、写真を保存して、scenes[].image / image_credit を埋めた spec と報告を返す。
    1つでも照合できなければ止まる（検証できていない内容は動画に載せない）"""
    open_cache(cache_path)
    place_qid = spec['place']['wikidata']
    problems, lines = [], ['[人気の根拠の照合] Wikidata（CC0）× ja.wikipedia、写真は Commons のライセンスを確認']
    out = dict(spec)
    out['scenes'] = []
    for sc in spec['scenes']:
        p, l = check_scene(sc, place_qid)
        problems += p
        lines += l
        sc = dict(sc)
        if sc.get('photo') and not p:
            info = commons_file(sc['photo']['file'])
            sc['image'] = download(info, img_dir)
            sc['image_credit'] = credit_line(info)
        out['scenes'].append(sc)
    report = '\n'.join(lines)
    if problems:
        raise FactsError('人気の根拠の検証に失敗しました:\n' + '\n'.join('  ・' + x for x in problems) + '\n\n' + report)
    return out, report
