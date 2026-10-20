"""Тревоги за всю войну -> data/history.json, агрегаты для фильтра по годам.

Источник — архив eTryvoga, очищенный сверкой с официальным (см. alerts_clean.py).
Для каждой области:
  m — по месяцам [эпизоды тревоги, минут под тревогой] (эпизод — объединение пересекающихся тревог)
  y — по годам {h: 24 значения минут по часу суток (киевское время), max: [минут, начало самого долгого эпизода]}
days — сумма «областе-минут» тревоги по суткам по всей стране.
"""
import json, os
from collections import defaultdict
from datetime import timedelta
from common import ROOT
from split_nights import kyiv
from alerts_clean import load

rows, stats, (off_start, off_end) = load()
raw = defaultdict(list)
for reg, s, e, _ in rows:
    raw[reg].append((s, e))

first = min(s for v in raw.values() for s, _ in v)
last = max(e for v in raw.values() for _, e in v)
k0, k1 = kyiv(first), kyiv(last)
months = []
y, m = k0.year, k0.month
while (y, m) <= (k1.year, k1.month):
    months.append(f'{y}-{m:02d}')
    y, m = (y + 1, 1) if m == 12 else (y, m + 1)
mi = {k: i for i, k in enumerate(months)}
day0 = k0.date()
days = [0.0] * ((k1.date() - day0).days + 1)


def pieces(s, e):
    """Режет интервал UTC по часам киевского времени: (киевское время начала куска, минуты)."""
    t = s
    while t < e:
        k = kyiv(t)
        step = min(e, t + (k.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1) - k))
        yield k, (step - t).total_seconds() / 60
        t = step


regions = {}
for reg, iv in raw.items():
    merged = []
    for s, e in sorted(iv):
        if merged and s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    mon = [[0, 0.0] for _ in months]
    years = {}
    for s, e in merged:
        ks = kyiv(s)
        mon[mi[ks.strftime('%Y-%m')]][0] += 1
        dur = (e - s).total_seconds() / 60
        yr = years.setdefault(str(ks.year), {'h': [0.0] * 24, 'max': [0, None]})
        if dur > yr['max'][0]:
            yr['max'] = [round(dur), ks.strftime('%Y-%m-%dT%H:%M')]
        for k, mins in pieces(s, e):
            mon[mi[k.strftime('%Y-%m')]][1] += mins
            years.setdefault(str(k.year), {'h': [0.0] * 24, 'max': [0, None]})['h'][k.hour] += mins
            days[(k.date() - day0).days] += mins
    regions[reg] = {
        'm': [[c, round(v)] for c, v in mon],
        'y': {yy: {'h': [round(v) for v in d['h']], 'max': d['max']} for yy, d in sorted(years.items())},
    }

out = {
    'from': kyiv(first).strftime('%Y-%m-%d'), 'to': kyiv(last).strftime('%Y-%m-%dT%H:%M'),
    'official': [kyiv(off_start).strftime('%Y-%m-%d'), kyiv(off_end).strftime('%Y-%m-%d')],
    'months': months, 'regions': regions,
    'days': {'start': day0.isoformat(), 'v': [round(v) for v in days]},
    # постоянные тревоги, которых нет в архиве (киевское время начала)
    'permanent': {'Луганська область': '2022-04-04T19:45', 'Автономна Республіка Крим': '2022-12-11T00:22',
                  'Севастополь': '2022-12-11T00:22'},
}
path = os.path.join(ROOT, 'data', 'history.json')
json.dump(out, open(path, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
print('regions', len(regions), 'months', len(months), 'clean', stats, 'size', os.path.getsize(path))
