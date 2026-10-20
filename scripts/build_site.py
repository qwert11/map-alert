"""data/extract/*.json (сырой результат извлечения) -> data/nights/*.json + data/index.json.

Чистит типы, сверяет координаты точек с GeoNames (LLM мог ошибиться в координатах,
но название обычно верное), считает сводные цифры по ночам.
"""
import glob, json, math, os
from common import ROOT, load_gazetteer, geocode, ob_key

TYPES = {'ballistic', 'aeroballistic', 'cruise', 'supersonic', 'loitering', 'shahed', 'jet_drone', 'unknown_missile'}
MISSILES = {'ballistic', 'aeroballistic', 'cruise', 'supersonic', 'unknown_missile'}
DRONES = {'shahed', 'jet_drone', 'loitering'}
TYPE_ALIAS = {'kinzhal': 'aeroballistic', 'kalibr': 'cruise', 'x101': 'cruise', 'iskander': 'ballistic',
              'drone': 'shahed', 'uav': 'shahed', 'missile': 'unknown_missile', 'x22': 'supersonic',
              'x32': 'supersonic', 'zircon': 'supersonic', 'onyx': 'supersonic', 'banderol': 'loitering',
              'guided_bomb': None, 'kab': None}
KINDS = {'hit', 'debris', 'explosions'}
# Украина + запад РФ + акватории: всё, что вне, — явная ошибка координат
BOX = (40.0, 20.0, 60.0, 52.0)

gaz = load_gazetteer()
stats = {'pts': 0, 'fixed': 0, 'gaz': 0, 'dropped': 0}


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def in_box(lat, lon):
    return lat is not None and lon is not None and BOX[0] <= lat <= BOX[2] and BOX[1] <= lon <= BOX[3]


def fix_place(p, near=None):
    """Возвращает (lat, lon) с поправкой по газетиру или None."""
    stats['pts'] += 1
    lat, lon = num(p.get('lat')), num(p.get('lon'))
    name = (p.get('name') or '').strip()
    oblast = p.get('oblast')
    hit = None
    if name:
        base = name.split('(')[0].split(',')[0].strip()
        hit = geocode(gaz, base, oblast, near=(lat, lon) if in_box(lat, lon) else near)
        ob = ob_key(oblast)
        if hit and ob and hit[2] and hit[2] != ob:
            hit = None  # одноимённый пункт в другой области — не трогаем
    if hit:
        if not in_box(lat, lon):
            stats['gaz'] += 1
            return hit[0], hit[1]
        d = math.hypot(hit[0] - lat, (hit[1] - lon) * math.cos(math.radians(lat)))
        area = not hit[4].startswith('PPL')  # район, водохранилище: у них центроид, точка LLM точнее
        district = hit[3] >= 100000 and d < 0.25  # крупный город: LLM указал район внутри него
        if 0.05 < d < 2.5 and not area and not district:  # LLM поставил точку не туда, название узнаваемое
            stats['fixed'] += 1
            return hit[0], hit[1]
    if in_box(lat, lon):
        return lat, lon
    stats['dropped'] += 1
    return None


def clean_type(t):
    t = (t or '').strip().lower()
    t = TYPE_ALIAS.get(t, t)
    return t if t in TYPES else None


def clean_night(d):
    tracks = []
    for i, t in enumerate(d.get('tracks') or []):
        typ = clean_type(t.get('type'))
        if not typ:
            continue
        pts = []
        prev = None
        for p in t.get('points') or []:
            ll = fix_place(p, near=prev)
            if not ll:
                continue
            prev = ll
            pts.append({'t': p.get('time'), 'n': p.get('name'), 'o': ob_key(p.get('oblast')) or p.get('oblast'),
                        'lat': ll[0], 'lon': ll[1], 'note': p.get('note'), 'src': p.get('src')})
        launch = None
        L = t.get('launch')
        if isinstance(L, dict):
            ll = fix_place({'name': L.get('name'), 'lat': L.get('lat'), 'lon': L.get('lon')})
            if ll:
                launch = {'n': L.get('name'), 'lat': ll[0], 'lon': ll[1]}
        if not pts and not launch:
            continue
        cnt = t.get('count')
        tracks.append({'id': t.get('id') or f'T{i + 1}', 'type': typ, 'label': t.get('label'),
                       'count': cnt if isinstance(cnt, int) and cnt > 0 else None,
                       'launch': launch, 'pts': pts, 'end': t.get('end') or 'unknown', 'note': t.get('note')})
    impacts = []
    for m in d.get('impacts') or []:
        ll = fix_place(m)
        if not ll:
            continue
        kind = m.get('kind') if m.get('kind') in KINDS else 'explosions'
        impacts.append({'t': m.get('time'), 'n': m.get('name'), 'dist': m.get('district'),
                        'o': ob_key(m.get('oblast')) or m.get('oblast'), 'lat': ll[0], 'lon': ll[1],
                        'kind': kind, 'weapon': clean_type(m.get('weapon')), 'tk': m.get('target_kind'),
                        'what': m.get('what'), 'cas': m.get('casualties'), 'src': m.get('src')})
    af = d.get('af_report') if isinstance(d.get('af_report'), dict) else None
    if af:
        for k in ('launched', 'downed'):
            af[k] = [dict(x, type=clean_type(x.get('type')) or x.get('type')) for x in af.get(k) or []
                     if isinstance(x, dict)]
    return {'night': d['night'], 'headline': d.get('headline'), 'summary': d.get('summary'),
            'intensity': d.get('intensity') if isinstance(d.get('intensity'), int) else None,
            'af': af, 'tracks': tracks, 'impacts': impacts, 'notes': d.get('notes')}


def amount(x):
    """Число из сводки, а если там «ракетами» без числа — оценка по мониторам."""
    for k in ('count', 'count_est'):
        if isinstance(x.get(k), int) and x[k] > 0:
            return x[k]
    return None


def counts(n):
    """Сколько чего запущено: из сводки ПС, иначе по трекам."""
    c = {'missiles': 0, 'drones': 0, 'downed': 0}
    af = n['af']
    if af and af.get('launched'):
        for x in af['launched']:
            k = 'missiles' if x.get('type') in MISSILES else 'drones' if x.get('type') in DRONES else None
            v = amount(x)
            if k and v:
                c[k] += v
                c['est'] = c.get('est') or not isinstance(x.get('count'), int)
        c['downed'] = sum(amount(x) or 0 for x in af.get('downed') or [])
        c['from_af'] = True
    else:
        for t in n['tracks']:
            k = 'missiles' if t['type'] in MISSILES else 'drones'
            c[k] += t['count'] or 1
        c['from_af'] = False
    c['hits'] = (af or {}).get('hits_locations') if isinstance((af or {}).get('hits_locations'), int) else None
    return c


def main():
    os.makedirs(os.path.join(ROOT, 'data', 'nights'), exist_ok=True)
    index = []
    for path in sorted(glob.glob(os.path.join(ROOT, 'data', 'extract', '*.json'))):
        try:
            raw = json.load(open(path, encoding='utf-8'))
        except Exception as e:
            print('BAD', path, e)
            continue
        raw.setdefault('night', os.path.basename(path)[:-5])
        n = clean_night(raw)
        json.dump(n, open(os.path.join(ROOT, 'data', 'nights', n['night'] + '.json'), 'w', encoding='utf-8'),
                  ensure_ascii=False, separators=(',', ':'))
        types = sorted({t['type'] for t in n['tracks']})
        index.append({
            'night': n['night'], 'headline': n['headline'], 'intensity': n['intensity'], 'types': types,
            'c': counts(n), 'nImpacts': len(n['impacts']),
            # для обзора «весь период»: прилёты и ракетные треки в сжатом виде
            'imp': [[round(m['lat'], 3), round(m['lon'], 3), m['kind'], m['weapon'], m['n']] for m in n['impacts']],
            'mt': [[t['type'], [[round(p['lat'], 2), round(p['lon'], 2)] for p in
                                ([t['launch']] if t['launch'] else []) + t['pts']]]
                   for t in n['tracks'] if t['type'] in MISSILES],
        })
    json.dump({'nights': index}, open(os.path.join(ROOT, 'data', 'index.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, separators=(',', ':'))
    print('nights', len(index), stats)


if __name__ == '__main__':
    main()
