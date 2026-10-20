"""Тревоги по областям за период карты атак -> data/alerts.json.

python scripts/build_alerts.py 2026-09-20
Источник — архив eTryvoga, очищенный сверкой с официальным (alerts_clean.py).
Формат: {"t0": unix-сек начала, "regions": {область: [[старт_мин, конец_мин, naive], ...]}}
минуты отсчитываются от t0. naive=1 — отбой не объявлен или потерян, поставлен старт+30 мин.
"""
import json, os, sys
from datetime import datetime, timezone
from common import ROOT
from alerts_clean import load

since = sys.argv[1] if len(sys.argv) > 1 else '2026-09-20'
# начало окна: 12:00 по Киеву (09:00 UTC летом) дня since — с него начинается «ночь на since+1»
t0 = int(datetime.fromisoformat(since + 'T09:00:00+00:00').timestamp())

rows, stats, _ = load()
regions, last = {}, 0
for reg, s, e, naive in rows:
    s, e = int(s.timestamp()), int(e.timestamp())
    if e < t0:
        continue
    last = max(last, s, e if not naive else s)
    regions.setdefault(reg, []).append([max(0, (s - t0) // 60), (e - t0) // 60, 1 if naive else 0])
for v in regions.values():
    v.sort()
out = {'t0': t0, 'updated': datetime.fromtimestamp(last, timezone.utc).isoformat(), 'regions': regions,
       'source': 'eTryvoga via github.com/Vadimkin/ukrainian-air-raid-sirens-dataset'}
json.dump(out, open(os.path.join(ROOT, 'data', 'alerts.json'), 'w', encoding='utf-8'),
          ensure_ascii=False, separators=(',', ':'))
print('regions', len(regions), 'records', sum(len(v) for v in regions.values()), 'last', out['updated'], stats)
