"""ヘッドレス Chromium でページを読む（API が回数制限（429）のときの予備ルート）。

Wikimedia の API は共有の出口 IP だと 429 が続くことがある。通常のページ（Wikidata の Special:EntityData、ja.wikipedia の記事、
Commons のファイルページ）は別の経路なので、ブラウザで開いて中身を取る。回数は増やさず、1ページずつ間隔を空けて読む。
TLS の検証は無効にしない（プロキシの CA はブラウザ側に設定済み）。
  html = dump_dom(url)        読み込み後の DOM（HTML 文字列）
  text = fetch_text(url)      JSON やテキストをそのまま返すページの本文（<pre> の中身）
Chrome の場所は環境変数 CHROME_PATH、無ければ /opt/pw-browsers/chromium-*/ や PATH から探す。
"""
import glob
import html as htmllib
import os
import re
import shutil
import subprocess
import time

_last = [0.0]


class BrowserError(RuntimeError):
    pass


def chrome_path():
    cands = [os.environ.get('CHROME_PATH', '')]
    cands += sorted(glob.glob('/opt/pw-browsers/chromium-*/chrome-linux/chrome'), reverse=True)
    cands += [shutil.which(n) or '' for n in ('chromium', 'chromium-browser', 'google-chrome', 'google-chrome-stable')]
    for c in cands:
        if c and os.path.exists(c):
            return c
    raise BrowserError('Chrome / Chromium が見つかりません（CHROME_PATH で指定できます）')


def dump_dom(url, timeout=90, gap=3.0, sleep=time.sleep):
    wait = _last[0] + gap - time.time()
    if wait > 0:
        sleep(wait)
    _last[0] = time.time()
    cmd = [chrome_path(), '--headless=new', '--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage', '--dump-dom', url]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise BrowserError('ブラウザの読み込みがタイムアウトしました: %s' % url.split('?')[0])
    out = r.stdout.decode('utf-8', 'replace')
    if r.returncode != 0 or not out.strip():
        raise BrowserError('ブラウザで読み込めませんでした（終了コード %s）: %s' % (r.returncode, url.split('?')[0]))
    return out


def fetch_text(url, **kw):
    """JSON やプレーンテキストを返すページの本文。<pre> の中身を取り出す（HTML のページには使わない）"""
    dom = dump_dom(url, **kw)
    m = re.search(r'<pre[^>]*>(.*?)</pre>', dom, re.S)
    if not m:
        raise BrowserError('テキストを取り出せませんでした: %s' % url.split('?')[0])
    text = htmllib.unescape(m.group(1))
    if text.startswith('You are making too many requests') or 'too many requests' in text[:200].lower():
        raise BrowserError('ブラウザ経由でも回数制限（429）でした: %s' % url.split('?')[0])
    return text


def screenshot_image(url, out_path, width, height, timeout=120, gap=3.0, sleep=time.sleep):
    """画像の URL をブラウザで開いて、画面を保存する（画像サーバーが直接の取得を 429 で断るとき用）。
    画像だけのページは、ウィンドウに合わせて表示されるので、元の縦横比のウィンドウで撮れば画像がほぼ全面に写る。"""
    wait = _last[0] + gap - time.time()
    if wait > 0:
        sleep(wait)
    _last[0] = time.time()
    cmd = [chrome_path(), '--headless=new', '--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage', '--hide-scrollbars',
           '--screenshot=%s' % out_path, '--window-size=%d,%d' % (width, height), url]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise BrowserError('ブラウザの画像の読み込みがタイムアウトしました: %s' % url.split('?')[0])
    if r.returncode != 0 or not os.path.exists(out_path):
        raise BrowserError('ブラウザで画像を保存できませんでした（終了コード %s）: %s' % (r.returncode, url.split('?')[0]))
    return out_path


def page_text(url, **kw):
    """通常の記事ページの本文テキスト（タグを除いたもの）。raw で取れない記事（リダイレクトなど）の予備"""
    dom = dump_dom(url, **kw)
    dom = re.sub(r'<(script|style)[^>]*>.*?</\1>', '', dom, flags=re.S)
    text = htmllib.unescape(re.sub(r'<[^>]+>', ' ', dom))
    return re.sub(r'[ \t\u3000]+', ' ', re.sub(r'\n\s*\n+', '\n', text)).strip()
