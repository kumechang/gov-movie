"""テーマ YAML を読み、必要なら e-Stat から取得・検証し、template に合うテーマオブジェクトを返す。

run.py / render*.py / narration.py が共通で使う入口。
  spec, fetch_report = load_resolved(path, out_dir)   YAML を読み、source.fetch: estat なら取得して values を埋める
  T = make_theme(spec, narration_json)                template に応じて Theme（地図）か ListTheme（一覧型）を作る
"""
import os

import estat
import fetch_estat
import listtheme
import theme


def load_resolved(path, out_dir, refetch=False):
    spec = theme.load_spec(path)
    report = ''
    if spec.get('source', {}).get('fetch') == 'estat':
        try:
            spec, report = fetch_estat.resolve(spec, os.path.join(out_dir, 'estat_cache.json'), refetch)
        except (fetch_estat.FetchError, estat.EstatError) as err:
            raise SystemExit(estat.redact(err))
    return spec, report


def make_theme(spec, narration_json=None):
    t = spec.get('template', 'prefecture_map')
    if t == 'ranked_list':
        return listtheme.ListTheme(spec, narration_json)
    return theme.Theme(spec, narration_json)
