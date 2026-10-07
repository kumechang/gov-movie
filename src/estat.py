"""e-Stat API（政府統計の総合窓口）の最小クライアント。

appId は環境変数 ESTAT_APP_ID からだけ読む。e-Stat は appId を URL のクエリで送るため、
URL・例外メッセージ・ログに出さないよう、外へ出す文字列はすべて redact() を通す。
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request

BASE = 'https://api.e-stat.go.jp/rest/3.0/app/json/'
ENV_NAME = 'ESTAT_APP_ID'


class EstatError(RuntimeError):
    pass


def app_id():
    v = os.environ.get(ENV_NAME, '').strip()
    if not v:
        raise EstatError('環境変数 %s が未設定です（e-Stat の appId を登録してください）' % ENV_NAME)
    return v


def redact(text):
    """文字列中の appId を伏せる（URL エンコード済みの形も含む）。"""
    text = str(text)
    v = os.environ.get(ENV_NAME, '').strip()
    if v:
        for form in {v, urllib.parse.quote(v, safe=''), urllib.parse.quote_plus(v)}:
            text = text.replace(form, '***')
    return text


def call(endpoint, **params):
    """e-Stat の API を1回呼んで JSON を返す。失敗は EstatError（appId は伏せ済み）。"""
    q = {k: v for k, v in params.items() if v is not None}
    q['appId'] = app_id()
    url = BASE + endpoint + '?' + urllib.parse.urlencode(q)
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            body = r.read()
    except urllib.error.HTTPError as e:
        raise EstatError('e-Stat %s: HTTP %s' % (endpoint, e.code)) from None
    except (urllib.error.URLError, OSError) as e:
        raise EstatError('e-Stat %s: 通信エラー（%s）' % (endpoint, redact(getattr(e, 'reason', e)))) from None
    try:
        data = json.loads(body)
    except ValueError:
        raise EstatError('e-Stat %s: JSON ではない応答' % endpoint) from None
    root = next(iter(data.values()), {})
    res = root.get('RESULT', {}) if isinstance(root, dict) else {}
    if str(res.get('STATUS', '0')) not in ('0', '1'):  # 0=正常, 1=該当データなし
        raise EstatError('e-Stat %s: %s %s' % (endpoint, res.get('STATUS'), redact(res.get('ERROR_MSG', ''))))
    return data
