"""Извлечение треков/прилётов по ночам: отдельный процесс `claude -p` на каждую ночь.

python scripts/run_extract.py [параллельно=5] [ночь ...]
Без списка ночей берёт все _tmp/nights/*.txt, для которых ещё нет валидного data/extract/<ночь>.json.
Логи: _tmp/extract/<ночь>.log, сводный — _tmp/extract/run.log.
"""
import json, os, sys, subprocess, time, glob, shutil
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from common import ROOT, TMP

MONTHS = ['січня', 'лютого', 'березня', 'квітня', 'травня', 'червня', 'липня', 'серпня',
          'вересня', 'жовтня', 'листопада', 'грудня']
OUT_DIR = os.path.join(ROOT, 'data', 'extract')
WORK = os.path.join(TMP, 'extract')
CLAUDE = shutil.which('claude') or 'claude'


def log(msg):
    line = time.strftime('%H:%M:%S ') + msg
    print(line, flush=True)
    open(os.path.join(WORK, 'run.log'), 'a', encoding='utf-8').write(line + '\n')


def valid(path):
    try:
        d = json.load(open(path, encoding='utf-8'))
        return isinstance(d.get('tracks'), list) and isinstance(d.get('impacts'), list)
    except Exception:
        return False


def run(night):
    out = os.path.join(OUT_DIR, night + '.json')
    if valid(out):
        return night, 'skip'
    d = date.fromisoformat(night)
    tpl = open(os.path.join(ROOT, 'scripts', 'extract_prompt.md'), encoding='utf-8').read()
    prompt = (tpl.replace('{NIGHT}', night)
              .replace('{PREV}', (d - timedelta(days=1)).isoformat())
              .replace('{NIGHT_UA}', f'{d.day} {MONTHS[d.month - 1]}')
              .replace('{INPUT}', os.path.join(TMP, 'nights', night + '.txt'))
              .replace('{OUTPUT}', out))
    for attempt in (1, 2):
        t = time.time()
        with open(os.path.join(WORK, f'{night}.log'), 'w', encoding='utf-8') as lf:
            try:
                subprocess.run([CLAUDE, '-p', '--allowedTools', 'Read', 'Write', 'WebSearch', 'WebFetch',
                                '--output-format', 'text'],
                               input=prompt.encode('utf-8'), stdout=lf, stderr=subprocess.STDOUT,
                               cwd=ROOT, timeout=45 * 60)
            except subprocess.TimeoutExpired:
                lf.write('\nTIMEOUT\n')
        ok = valid(out)
        log(f'{night} attempt {attempt} {"ok" if ok else "FAIL"} {int(time.time() - t)}s')
        if ok:
            return night, 'ok'
    return night, 'fail'


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    os.makedirs(WORK, exist_ok=True)
    par = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    nights = sys.argv[2:] or sorted(os.path.basename(p)[:-4] for p in glob.glob(os.path.join(TMP, 'nights', '*.txt')))
    log(f'start {len(nights)} nights, par={par}')
    with ThreadPoolExecutor(par) as ex:
        res = list(ex.map(run, nights))
    log('ALLDONE ' + ' '.join(f'{n}:{s}' for n, s in res))


if __name__ == '__main__':
    main()
