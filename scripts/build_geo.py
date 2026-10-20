"""Границы областей: geoBoundaries ADM1 -> data/oblasts.geojson (укр. имена, округление координат)."""
import json, os, subprocess
from common import ROOT, TMP, GB_NAMES

src = os.path.join(TMP, 'adm1.geojson')
if not os.path.exists(src):
    subprocess.run(['curl', '-sL', '-o', src,
                    'https://github.com/wmgeolab/geoBoundaries/raw/main/releaseData/gbOpen/UKR/ADM1/'
                    'geoBoundaries-UKR-ADM1_simplified.geojson'], check=True)
d = json.load(open(src, encoding='utf-8'))


def rnd(c):
    if isinstance(c[0], (int, float)):
        return [round(c[0], 3), round(c[1], 3)]
    out = [rnd(x) for x in c]
    if out and isinstance(out[0][0], float):  # кольцо: убрать повторы после округления
        ded = [out[0]] + [p for i, p in enumerate(out[1:], 1) if p != out[i - 1]]
        return ded if len(ded) >= 4 else out
    return out


feats = []
for f in d['features']:
    g = f['geometry']
    feats.append({'type': 'Feature', 'properties': {'name': GB_NAMES[f['properties']['shapeName']]},
                  'geometry': {'type': g['type'], 'coordinates': rnd(g['coordinates'])}})
out = os.path.join(ROOT, 'data', 'oblasts.geojson')
json.dump({'type': 'FeatureCollection', 'features': feats}, open(out, 'w', encoding='utf-8'),
          ensure_ascii=False, separators=(',', ':'))
print(len(feats), os.path.getsize(out))
