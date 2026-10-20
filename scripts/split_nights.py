"""Раскладывает посты каналов по «ночам» -> _tmp/nights/<дата>.txt (вход для извлечения).

Ночь D = окно [D-1 12:00, D 12:00) по Киеву: вечер, ночь и утро до полудня,
плюс утренняя сводка Повітряних сил «у ніч на D».
python scripts/split_nights.py [с YYYY-MM-DD] [по YYYY-MM-DD]
"""
import json, os, sys, glob
from datetime import datetime, timedelta, timezone
from common import TMP

CHANNELS = {'kpszsu': 'ПС ЗСУ', 'monitorwarr': 'Монітор', 'war_monitor': 'war_monitor',
            'vanek_nikolaev': 'Ванёк'}


def last_sunday(y, m):
    d = datetime(y, m + 1, 1) - timedelta(days=1) if m < 12 else datetime(y, 12, 31)
    return d - timedelta(days=(d.weekday() + 1) % 7)


def kyiv(dt_utc):
    """UTC -> Киев (EET/EEST по правилу ЕС, без tzdata)."""
    y = dt_utc.year
    start = last_sunday(y, 3).replace(hour=1, tzinfo=timezone.utc)
    end = last_sunday(y, 10).replace(hour=1, tzinfo=timezone.utc)
    off = 3 if start <= dt_utc < end else 2
    return (dt_utc + timedelta(hours=off)).replace(tzinfo=timezone(timedelta(hours=off)))


def main():
    frm = sys.argv[1] if len(sys.argv) > 1 else '2026-09-21'
    to = sys.argv[2] if len(sys.argv) > 2 else '2099-01-01'
    nights = {}
    for path in glob.glob(os.path.join(TMP, 'tg', '*.jsonl')):
        ch = os.path.basename(path)[:-6]
        if ch not in CHANNELS:
            continue
        for line in open(path, encoding='utf-8'):
            p = json.loads(line)
            if not p['text']:
                continue
            k = kyiv(datetime.fromisoformat(p['dt']))
            night = (k + timedelta(hours=12)).date().isoformat()
            if not (frm <= night <= to):
                continue
            txt = p['text'] if len(p['text']) < 1800 else p['text'][:1800] + ' …'
            nights.setdefault(night, []).append((k, ch, p['id'], txt))
    os.makedirs(os.path.join(TMP, 'nights'), exist_ok=True)
    now = kyiv(datetime.now(timezone.utc))
    for night, posts in sorted(nights.items()):
        if night + 'T12:00' > now.strftime('%Y-%m-%dT%H:%M'):
            print(night, 'ещё не закончилась — пропуск')
            continue
        posts.sort()
        out = [f'# Ночь на {night}: посты {len(posts)}, время киевское (UTC{posts[0][0].strftime("%z")[:3]})']
        seen = set()
        for k, ch, pid, txt in posts:
            key = (ch, txt)
            if key in seen:  # каналы часто дублируют пост через минуту
                continue
            seen.add(key)
            out.append(f'[{k.strftime("%d.%m %H:%M")}] {ch}/{pid}: ' + txt.replace('\n', ' / '))
        open(os.path.join(TMP, 'nights', night + '.txt'), 'w', encoding='utf-8').write('\n'.join(out) + '\n')
        print(night, len(posts), len(out) - 1)


if __name__ == '__main__':
    main()
