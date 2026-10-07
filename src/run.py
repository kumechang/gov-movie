"""1テーマ = 1コマンドで、検証 → 地図 → ナレーション → 音声 → 映像 → 音量調整 → 投稿文 まで走らせる。

  python3 src/run.py themes/divorce_rate_2024.yaml              通常（VOICEVOX があれば音声付き）
  python3 src/run.py themes/divorce_rate_2024.yaml --no-voice   VOICEVOX なしのプレビュー（効果音のみ・読み上げ長は見積もり）
  python3 src/run.py themes/divorce_rate_2024.yaml --check      テーマの検証レポートだけ表示

成果物は build/<theme id>/ に出る（final.mp4, post.md, 検証レポート report.txt）。
"""
import os, subprocess, sys, urllib.request

import theme

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(HERE, '..', 'build')
GEOJSON_URL = 'https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_admin_1_states_provinces.geojson'


def step(msg):
    print('\n== ' + msg, flush=True)


def main(argv):
    args = [a for a in argv if not a.startswith('--')]
    if not args:
        raise SystemExit(__doc__)
    theme_path = args[0]
    no_voice, check_only = '--no-voice' in argv, '--check' in argv
    T0 = theme.load(theme_path)
    out_dir = os.path.join(BUILD, T0.id)
    os.makedirs(out_dir, exist_ok=True)

    step('テーマの検証')
    narration_json = os.path.join(out_dir, 'narration.json')
    voice_dir = os.environ.get('VOICEVOX_DIR', os.path.join(HERE, '..', 'tts', 'vv'))
    use_voice = not no_voice and not check_only
    if use_voice:
        if not os.path.isdir(voice_dir):
            raise SystemExit('VOICEVOX が %s にありません。--no-voice でプレビューするか、docs/HANDOFF.md 5.2 に従って配置してください' % voice_dir)
        step('ナレーション生成（VOICEVOX）')
        import narration
        narration.synthesize(T0, out_dir, voice_dir)
    T = theme.load(theme_path, narration_json)
    report = T.report()
    print(report)
    open(os.path.join(out_dir, 'report.txt'), 'w', encoding='utf-8').write(report + '\n')
    if check_only:
        return

    geojson, geo_pkl = os.path.join(BUILD, 'ne_admin1.geojson'), os.path.join(BUILD, 'geo.pkl')
    if not os.path.exists(geo_pkl):
        if not os.path.exists(geojson):
            step('地図データのダウンロード（Natural Earth、約40MB）')
            urllib.request.urlretrieve(GEOJSON_URL, geojson)
        step('地図マスクの生成')
        subprocess.run([sys.executable, os.path.join(HERE, 'geo.py'), geojson, geo_pkl], check=True)

    step('効果音＋音声')
    import audio
    wav = audio.build(T, out_dir, voice=use_voice)

    step('映像の書き出し')
    import render
    render.init(T, geo_pkl)
    raw, final = os.path.join(out_dir, 'out.mp4'), os.path.join(out_dir, 'final.mp4')
    render.render_video(raw, wav)

    step('音量調整（loudnorm）')
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', raw, '-c:v', 'copy', '-af', 'loudnorm=I=-16:TP=-1.5:LRA=11',
                    '-c:a', 'aac', '-b:a', '160k', final], check=True)

    open(os.path.join(out_dir, 'post.md'), 'w', encoding='utf-8').write(T.post_md())
    print('\n完成: %s\n投稿文: %s' % (os.path.relpath(final), os.path.relpath(os.path.join(out_dir, 'post.md'))))
    if T.estimated_keys or not use_voice:
        print('※ 音声は効果音のみ／読み上げ長は見積もりのプレビュー版です')


if __name__ == '__main__':
    main(sys.argv[1:])
