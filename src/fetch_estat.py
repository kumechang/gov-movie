"""テーマの `source.fetch: estat` に従い、e-Stat から47都道府県の値と全国値を取って検証する。

  python3 src/fetch_estat.py themes/<id>.yaml [--refetch]   取得して検証レポートだけ表示

テーマ YAML の書き方（docs/THEME_SPEC.md「e-Stat 取得」）:

  source: {fetch: estat, ...}
  estat:
    statsDataId: "0003411861"            # 統計表ID
    select: {cdTab: "10320", cdTime: "2024000000"}   # 絞り込み。各都道府県1値になるまで絞る
    cross:                               # 照合（2系統目）。任意・複数可
      - {label: ..., statsDataId: ..., select: {...}}                       # 別の表の同じ指標
      - {label: ..., numerator: {statsDataId, select}, denominator: {...}, scale: 1000}  # 件数÷人口などの再計算

YAML に `values` / `average` があれば「検証済みの期待値」として、取得値と一致することを確認する。
なければ取得値で埋める。取得結果（生の応答）は build/<id>/estat_cache.json に保存し、--refetch で取り直す。
appId はキャッシュにもレポートにも入らない。
"""
import datetime
import json
import math
import os
import sys

import estat
import theme

TIME_AXIS = 'time'


class FetchError(RuntimeError):
    pass


def area_code(pref):
    return '%02d000' % (theme.PREFS.index(pref) + 1)


def _as_list(x):
    return x if isinstance(x, list) else [x]


def _get(sid, select):
    """getStatsData を呼び、表の情報と {地域コード: 文字列の値} を返す。"""
    params = {k: v for k, v in select.items()}
    data = estat.call('getStatsData', statsDataId=sid, metaGetFlg='Y', annotationFlg='Y', **params)
    sd = data['GET_STATS_DATA']['STATISTICAL_DATA']
    info = sd['TABLE_INF']
    classes = {o['@id']: {c['@code']: c for c in _as_list(o['CLASS'])} for o in _as_list(sd['CLASS_INF']['CLASS_OBJ'])}
    values = _as_list(sd.get('DATA_INF', {}).get('VALUE', []))
    return dict(sid=sid, select=select, info=info, classes=classes, values=values, total=sd['RESULT_INF'])


def _title(info):
    t = info.get('TITLE')
    return t.get('$') if isinstance(t, dict) else t


def _what(raw):
    """select で選んだ項目名（例: 離婚件数）。表題だけでは同じ表の別項目を区別できないため。"""
    names = []
    for k, code in raw['select'].items():
        c = raw['classes'].get(k[2:].lower(), {}).get(code)
        if k.startswith('cd') and c and k != 'cdTime':
            names.append(c['@name'])
    return '・'.join(names) or _title(raw['info'])


def _rows(raw, area_id='area'):
    """1地域1値に絞れているか確認して {地域コード: (値の文字列, 単位, 時点コード)} にする。"""
    rows = {}
    for v in raw['values']:
        code = v.get('@' + area_id)
        if code is None:
            raise FetchError('表 %s に地域軸 "%s" がありません' % (raw['sid'], area_id))
        if code in rows:
            raise FetchError('表 %s: 地域 %s に複数の値があります。select をもっと絞ってください' % (raw['sid'], code))
        rows[code] = (v['$'], v.get('@unit', ''), v.get('@time', ''))
    return rows


def _number(s, where):
    try:
        x = float(s.replace(',', ''))
    except (ValueError, AttributeError):
        raise FetchError('%s: 数値でない値 %r（"-" "…" などの欠損記号の可能性）' % (where, s)) from None
    if not math.isfinite(x):
        raise FetchError('%s: 数値でない値 %r' % (where, s))
    return x


def _series(raw, spec, area_id):
    """表から47都道府県＋全国の数値を取り出す。"""
    rows = _rows(raw, area_id)
    need = [area_code(p) for p in theme.PREFS] + ['00000']
    missing = [c for c in need if c not in rows]
    if missing:
        raise FetchError('表 %s: 地域コードが足りません: %s' % (raw['sid'], missing))
    units = {rows[c][1] for c in need}
    times = {rows[c][2] for c in need}
    if len(units) != 1 or len(times) != 1:
        raise FetchError('表 %s: 単位または時点が地域によって異なります: %s %s' % (raw['sid'], units, times))
    area_names = raw['classes'].get(area_id, {})
    pref_vals = {}
    for p in theme.PREFS:
        c = area_code(p)
        name = area_names.get(c, {}).get('@name')
        if name and name != theme.full(p):
            raise FetchError('表 %s: 地域コード %s の名前が想定（%s）と違います: %s' % (raw['sid'], c, theme.full(p), name))
        pref_vals[theme.full(p)] = _number(rows[c][0], '%s %s' % (raw['sid'], theme.full(p)))
    return pref_vals, _number(rows['00000'][0], '%s 全国' % raw['sid']), units.pop(), times.pop()


def _cached(path, key, loader, refetch):
    cache = {}
    if path and os.path.exists(path) and not refetch:
        cache = json.load(open(path, encoding='utf-8'))
    if key not in cache:
        cache[key] = loader()
        if path:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            json.dump(cache, open(path, 'w', encoding='utf-8'), ensure_ascii=False)
    return cache[key]


def _fetch(cache_path, sid, select, refetch):
    key = json.dumps([sid, select], sort_keys=True, ensure_ascii=False)
    got = _cached(cache_path, key, lambda: dict(_get(sid, select), fetched=datetime.date.today().isoformat()), refetch)
    return got


def fetch_values(spec, cache_path=None, refetch=False):
    """取得・検証して (values, average, report 文字列) を返す。失敗は FetchError。"""
    e = spec.get('estat')
    if not e:
        raise FetchError('source.fetch が estat ですが、estat: の定義がありません')
    area_id = e.get('area', 'area')
    decimals = int(spec.get('decimals', 2))
    lines, problems = [], []
    sid, select = str(e['statsDataId']), e.get('select', {})
    raw = _fetch(cache_path, sid, select, refetch)
    vals, national, unit, tcode = _series(raw, e, area_id)
    info = raw['info']

    # --- 取り違え検出: 年・単位 ---
    if not str(tcode).startswith(str(spec['year'])):
        problems.append('時点 %s が year=%s と一致しません' % (tcode, spec['year']))
    if unit != spec['unit']:
        problems.append('単位 %r が unit=%r と一致しません' % (unit, spec['unit']))
    stat_name = (info.get('STATISTICS_NAME') or '')
    kind = '確定数' if '確定数' in stat_name else ('概数' if '概数' in stat_name else '（表の名称から確定数/概数を判別できません）')

    lines += [
        '[取得] e-Stat 統計表ID %s' % sid,
        '  統計: %s ／ 表: %s' % (stat_name, _title(info)),
        '  調査期間: %s ／ 公表: %s ／ 更新: %s ／ 取得日: %s' % (
            info.get('SURVEY_DATE'), info.get('OPEN_DATE'), info.get('UPDATED_DATE'), raw.get('fetched')),
        '  単位: %s ／ %s ／ 絞り込み: %s' % (unit, kind, json.dumps(select, ensure_ascii=False)),
    ]
    rounded = {n: round(v, decimals) for n, v in vals.items()}
    hi = max(rounded, key=rounded.get)
    lo = min(rounded, key=rounded.get)
    lines.append('  最大 %s %s ／ 最小 %s %s ／ 全国 %s' % (hi, rounded[hi], lo, rounded[lo], national))
    if not min(rounded.values()) <= national <= max(rounded.values()):
        problems.append('全国値 %s が最小〜最大の範囲外です' % national)

    # --- 期待値（YAML に書かれた検証済みの値）との突き合わせ ---
    exp = spec.get('values')
    if exp:
        exp_full = {(k if k in theme.FULL_NAMES else theme.full(k)): v for k, v in exp.items()}
        diff = [(n, exp_full.get(n), rounded[n]) for n in rounded if exp_full.get(n) != rounded[n]]
        lines.append('[突き合わせ] YAML の検証済みの値 %d件と取得値: %s' % (
            len(exp_full), '全件一致' if not diff else '不一致 %d件 %s' % (len(diff), diff)))
        if diff:
            problems.append('YAML の値と e-Stat の取得値が一致しません: %s' % diff)
        if spec.get('average') is not None and round(float(spec['average']), decimals) != round(national, decimals):
            problems.append('YAML の average=%s と e-Stat 全国値 %s が一致しません' % (spec['average'], national))
        else:
            lines.append('  全国値: YAML %s ＝ e-Stat %s' % (spec.get('average'), national))

    # --- 2系統目の照合 ---
    for c in e.get('cross', []):
        label = c.get('label', '照合')
        exact = 'numerator' not in c
        try:
            if not exact:
                n_raw = _fetch(cache_path, str(c['numerator']['statsDataId']), c['numerator'].get('select', {}), refetch)
                d_raw = _fetch(cache_path, str(c['denominator']['statsDataId']), c['denominator'].get('select', {}), refetch)
                nv, nn, _, nt = _series(n_raw, c, area_id)
                dv, dn, _, dt = _series(d_raw, c, area_id)
                scale = float(c.get('scale', 1))
                other = {k: nv[k] / dv[k] * scale for k in nv}
                other_nat = nn / dn * scale
                tol = 0.5 * 10 ** -decimals + 1e-9
                how = '再計算（統計表ID %s の %s ÷ %s × %g）' % (c['numerator']['statsDataId'], _what(n_raw), _what(d_raw), scale)
                if not (str(nt).startswith(str(spec['year'])) and str(dt).startswith(str(spec['year']))):
                    problems.append('%s: 時点が year=%s と一致しません' % (label, spec['year']))
            else:
                o_raw = _fetch(cache_path, str(c['statsDataId']), c.get('select', {}), refetch)
                other, other_nat, ounit, ot = _series(o_raw, c, area_id)
                how = '別の表（統計表ID %s: %s）' % (c['statsDataId'], _title(o_raw['info']))
                if not str(ot).startswith(str(spec['year'])):
                    problems.append('%s: 時点 %s が year=%s と一致しません' % (label, ot, spec['year']))
                if ounit != unit:
                    problems.append('%s: 単位 %r が主系統 %r と違います' % (label, ounit, unit))
        except FetchError as err:
            problems.append('%s: %s' % (label, err))
            continue
        if exact:   # 別の表: 丸めた値が完全一致すること
            diffs = {n: abs(round(other[n], decimals) - rounded[n]) for n in vals}
            nat_ok = round(other_nat, decimals) == round(national, decimals)
        else:       # 再計算: 丸めの分（最終桁の半分）までのずれは許す
            diffs = {n: abs(other[n] - vals[n]) for n in vals}
            nat_ok = abs(other_nat - national) <= tol
        bad = [n for n in vals if diffs[n] > (1e-9 if exact else tol)]
        worst = max(diffs.values())
        lines.append('[照合: %s] %s' % (label, how))
        lines.append('  47都道府県 %s（最大差 %.4f）／ 全国値 %s（%s vs %s）' % (
            '全件一致' if not bad else '不一致 %d件 %s' % (len(bad), bad), worst,
            '一致' if nat_ok else '不一致', round(other_nat, decimals + 1), national))
        if bad:
            problems.append('%s: 主系統と一致しない県があります: %s' % (label, bad))
        if not nat_ok:
            problems.append('%s: 全国値が一致しません' % label)

    if not e.get('cross'):
        lines.append('[照合] 2系統目の定義なし（cross 未設定）')
    if problems:
        raise FetchError('\n'.join(['e-Stat データの検証に失敗しました:'] + ['  ・' + p for p in problems]) + '\n\n' + '\n'.join(lines))
    return rounded, round(national, decimals), '\n'.join(lines)


def resolve(spec, cache_path=None, refetch=False):
    """spec の values / average を e-Stat の値で確定させ、(spec, レポート) を返す（元の spec は変えない）。"""
    values, national, report = fetch_values(spec, cache_path, refetch)
    out = dict(spec)
    out['values'] = values
    out['average'] = national
    return out, report


def main(argv):
    args = [a for a in argv if not a.startswith('--')]
    if not args:
        raise SystemExit(__doc__)
    spec = theme.load_spec(args[0])
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'build', spec['id'])
    try:
        _, report = resolve(spec, os.path.join(out_dir, 'estat_cache.json'), '--refetch' in argv)
    except (FetchError, estat.EstatError) as err:
        raise SystemExit(estat.redact(err))
    print(report)


if __name__ == '__main__':
    main(sys.argv[1:])
