"""Чистка архива тревог eTryvoga (по областям) сверкой с официальным архивом.

eTryvoga (volunteer_data_uk.csv) — единственный архив с одинаковым определением «тревога в области»
на всю войну и до сегодняшнего дня, но он теряет отбои: в тылу встречаются «тревоги» по 20–180 ч,
которые по официальному архиву (official_data_uk.csv, канал «Повітряна тривога», 15.03.2022–07.09.2026)
длились минуты. Официальный как основу не берём: до 2025 часть районных объявлений там записана как
областные, и, например, Харьковщина-2024 набирает до 39 ч тревоги в сутки из перекрывающихся записей.

Правило:
  - тревога eTryvoga длиннее 6 ч, если на её время есть официальный архив: оставить только те куски,
    где официальный архив подтверждает тревогу в этой области (любой уровень, кроме громад), — если
    подтверждено меньше половины; иначе оставить как есть;
  - без официального архива (25.02–15.03.2022 и после его конца): тревога длиннее 20 ч -> 30 минут;
    после конца официального в тыловой области — уже длиннее 8 ч (в сверяемые годы такие в тылу
    почти всегда оказывались потерянным отбоем).
"""
import csv, os, subprocess
from collections import defaultdict
from datetime import datetime, timedelta
from common import TMP

BASE = 'https://raw.githubusercontent.com/Vadimkin/ukrainian-air-raid-sirens-dataset/main/datasets/'
FRONT = {'Донецька область', 'Запорізька область', 'Херсонська область', 'Харківська область',
         'Сумська область', 'Дніпропетровська область', 'Чернігівська область'}
LONG = timedelta(hours=6)
MAX_LEN = timedelta(hours=20)
REAR_MAX = timedelta(hours=8)
F = datetime.fromisoformat


def fetch(name, max_age_h=6):
    path = os.path.join(TMP, name)
    if not os.path.exists(path) or os.path.getmtime(path) < datetime.now().timestamp() - max_age_h * 3600:
        subprocess.run(['curl', '-sL', '-o', path, BASE + name], check=True)
    return path


def _merge(iv):
    out = []
    for s, e in sorted(iv):
        if out and s <= out[-1][1]:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return out


def load():
    """[(область, старт, конец, naive)] — очищенный архив eTryvoga, время UTC."""
    official = defaultdict(list)
    off_start = off_end = None
    for r in csv.DictReader(open(fetch('official_data_uk.csv', 24), encoding='utf-8')):
        if r['level'] not in ('oblast', 'raion'):
            continue
        s, e = F(r['started_at']), F(r['finished_at'])
        official['Київ' if r['oblast'] == 'м. Київ' else r['oblast']].append((s, e))
        off_start = s if off_start is None or s < off_start else off_start
        off_end = s if off_end is None or s > off_end else off_end
    official = {k: _merge(v) for k, v in official.items()}

    def confirmed(reg, s, e):
        return [(max(a, s), min(b, e)) for a, b in official.get(reg, []) if b > s and a < e]

    out, stats = [], defaultdict(int)
    for r in csv.DictReader(open(fetch('volunteer_data_uk.csv'), encoding='utf-8')):
        reg, s, e = r['region'], F(r['started_at']), F(r['finished_at'])
        naive = r['naive'] == 'True'
        if e <= s:
            continue
        if e - s > LONG and off_start <= s and e <= off_end:
            parts = confirmed(reg, s, e)
            got = sum(((b - a) for a, b in parts), timedelta())
            if got < (e - s) / 2:
                stats['trimmed'] += 1
                for a, b in parts:
                    out.append((reg, a, b, naive))
                if not parts:
                    out.append((reg, s, s + timedelta(minutes=30), True))
                continue
        elif e - s > (REAR_MAX if s > off_end and reg not in FRONT else MAX_LEN):
            stats['capped'] += 1
            e, naive = s + timedelta(minutes=30), True
        out.append((reg, s, e, naive))
    return out, dict(stats), (off_start, off_end)
