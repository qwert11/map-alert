"""Сверка треков build_paths.py с треками, которые восстановила модель (data/nights/*.json, 30 ночей).

- склейки: пара соседних точек трека, обе точки которой есть у модели (тот же пост, ≤20 км), — модель
  держит их в одном треке (верно) или в разных (ошибка склейки);
- геометрия: доля длины наших треков в пределах 15 км от трека модели той же ночи (сколько наших линий
  модель подтверждает) и обратное (сколько линий модели мы нашли).
python scripts/check_paths.py [--show N]  — N худших склеек с текстом
"""
import glob, json, os, sys
from collections import defaultdict
from common import ROOT, TMP
from build_paths import km

G = {'shahed': 'd', 'jet_drone': 'j', 'loitering': 'l', 'cruise': 'm', 'unknown_missile': 'm', 'supersonic': 'm',
     'ballistic': 'b', 'aeroballistic': 'b'}


def sample(pts, step=5):
    out = []
    for a, b in zip(pts, pts[1:]):
        d = km(a[0], a[1], b[0], b[1])
        n = max(1, int(d / step))
        out += [(a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n) for i in range(n)]
    return out + [pts[-1]]


def near_any(p, lines, r=15):
    return any(km(p[0], p[1], q[0], q[1]) <= r for q in lines)


def main():
    ref = {}
    for path in glob.glob(os.path.join(ROOT, 'data', 'nights', '*.json')):
        d = json.load(open(path, encoding='utf-8'))
        ref[d['night']] = d['tracks']
    ours = [t for t in json.load(open(os.path.join(TMP, 'paths_tracks.json'), encoding='utf-8')) if t['night'] in ref]
    st = defaultdict(lambda: defaultdict(float))
    bad = []
    for t in ours:
        g = t['g']
        rt = ref[t['night']]
        # склейки
        for a, b in zip(t['pts'], t['pts'][1:]):
            def owners(p):
                return {i for i, r in enumerate(rt) for q in r['pts']
                        if q.get('src') == p['src'] and km(q['lat'], q['lon'], p['lat'], p['lon']) <= 20}
            oa, ob = owners(a), owners(b)
            if oa and ob:
                if oa & ob:
                    st[g]['link_ok'] += 1
                else:
                    st[g]['link_bad'] += 1
                    bad.append((t['night'], a, b, [rt[i]['id'] for i in oa], [rt[i]['id'] for i in ob]))
            else:
                st[g]['link_unk'] += 1
        # геометрия
        refpts = [q for r in rt for q in sample([(p['lat'], p['lon']) for p in r['pts']] or [(0, 0)])]
        s = sample([(p['lat'], p['lon']) for p in t['pts']])
        ok = sum(near_any(p, refpts) for p in s)
        st[g]['len'] += len(s) * 5
        st[g]['len_ok'] += ok * 5
        st[g]['n'] += 1
    # обратное: сколько линий модели покрыто нашими
    by_night = defaultdict(list)
    for t in ours:
        by_night[t['night']] += sample([(p['lat'], p['lon']) for p in t['pts']])
    for night, rt in ref.items():
        for r in rt:
            if len(r['pts']) < 2:
                continue
            g = G.get(r['type'], 'm')
            s = sample([(p['lat'], p['lon']) for p in r['pts']])
            st[g]['ref_len'] += len(s) * 5
            st[g]['ref_ok'] += sum(near_any(p, by_night[night]) for p in s) * 5
    print('группа  треков  склейки ок/ошибка/не с чем сверить   наша длина подтверждена   длина модели найдена')
    for g in 'djlmb':
        s = st[g]
        lk = s['link_ok'] + s['link_bad']
        print(f"{g:6} {int(s['n']):6}   {int(s['link_ok'])}/{int(s['link_bad'])}/{int(s['link_unk'])} "
              f"({100 * s['link_ok'] / lk if lk else 0:.0f}% верных)   "
              f"{100 * s['len_ok'] / s['len'] if s['len'] else 0:.0f}% из {int(s['len'])} км   "
              f"{100 * s['ref_ok'] / s['ref_len'] if s['ref_len'] else 0:.0f}% из {int(s['ref_len'])} км")
    if '--show' in sys.argv:
        n = int(sys.argv[sys.argv.index('--show') + 1])
        for night, a, b, ia, ib in bad[:n]:
            print(night, a['n'], a['src'], ia, '->', b['n'], b['src'], ib, f"{b['t'] - a['t']:.0f} мин")


if __name__ == '__main__':
    main()
