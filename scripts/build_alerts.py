"""Тревоги по областям из архива eTryvoga (датасет Vadimkin) -> data/alerts.json.

python scripts/build_alerts.py 2026-09-20
Формат: {"t0": unix-сек начала, "regions": {область: [[старт_мин, конец_мин, naive], ...]}}
минуты отсчитываются от t0. naive=1 — конец тревоги не объявлен, поставлен старт+30 мин.
"""
import csv, json, os, subprocess, sys
from datetime import datetime, timezone
from common import ROOT, TMP

URL = 'https://raw.githubusercontent.com/Vadimkin/ukrainian-air-raid-sirens-dataset/main/datasets/volunteer_data_uk.csv'
since = sys.argv[1] if len(sys.argv) > 1 else '2026-09-20'
src = os.path.join(TMP, 'vol_uk.csv')
subprocess.run(['curl', '-sL', '-o', src, URL], check=True)

# начало окна: 12:00 по Киеву (09:00 UTC) дня since — с него начинается «ночь на since+1»
t0 = int(datetime.fromisoformat(since + 'T09:00:00+00:00').timestamp())


def ts(s):
    return int(datetime.fromisoformat(s).timestamp())


regions, last = {}, 0
for r in csv.DictReader(open(src, encoding='utf-8')):
    s, e = ts(r['started_at']), ts(r['finished_at'])
    if e < t0:
        continue
    last = max(last, s, e if r['naive'] != 'True' else s)
    regions.setdefault(r['region'], []).append(
        [max(0, (s - t0) // 60), (e - t0) // 60, 1 if r['naive'] == 'True' else 0])
for v in regions.values():
    v.sort()
out = {'t0': t0, 'updated': datetime.fromtimestamp(last, timezone.utc).isoformat(), 'regions': regions,
       'source': 'eTryvoga via github.com/Vadimkin/ukrainian-air-raid-sirens-dataset'}
json.dump(out, open(os.path.join(ROOT, 'data', 'alerts.json'), 'w', encoding='utf-8'),
          ensure_ascii=False, separators=(',', ':'))
print('regions', len(regions), 'records', sum(len(v) for v in regions.values()), 'last', out['updated'])
