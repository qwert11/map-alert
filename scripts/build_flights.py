"""«Куда летело»: упоминания населённых пунктов в мониторинговых каналах с 24.02.2022 -> data/flights.json.

Посты @kpszsu, @monitorwarr, @war_monitor, @vanek_nikolaev («ракета на Бурштин», «БпЛА повз Калуш»,
«КАБи на Куп'янськ») -> места через textgeo -> по каждому месту и году число дней, когда туда/мимо летело,
отдельно ракеты, дроны и КАБы. История качается scripts/collect_range.py в _tmp/hist/, свежие посты — _tmp/tg/.

Формат: {years, to, oblasts, p: [[lat, lon, имя, обл_индекс, [дни всего по годам], [ракеты], [дроны], [КАБ]], ...]}
"""
import glob, json, os, re
from collections import defaultdict
from datetime import datetime
from common import ROOT, TMP, OBLASTS
from split_nights import kyiv
from textgeo import TextGeo

YEARS = ['2022', '2023', '2024', '2025', '2026']
THREAT = re.compile(r'ракет|\bкр\b|балісти|баллисти|кинджал|кинжал|циркон|онікс|оникс|калібр|калибр|іскандер|искандер|'
                    r'х-\d|бпла|шахед|дрон|мопед|реактив|бандерол|\bкаб|каби\b|кабы|авіабомб|авиабомб|умпк|'
                    r'🚀|🛵|🏍|☄|вибух|взрыв|загроз|угроз|курс|напрям|направлени|летят|летять|повз|мимо|'
                    r'мінус|збит|сбит|уламк|обломк|приліт|прилет', re.I)
MISSILE = re.compile(r'ракет|\bкр\b|балісти|баллисти|кинджал|кинжал|циркон|онікс|оникс|калібр|калибр|іскандер|искандер|х-\d|☄', re.I)
KAB = re.compile(r'\bкаб|каби\b|кабы|авіабомб|авиабомб|умпк', re.I)
DRONE = re.compile(r'бпла|шахед|дрон|мопед|реактив|бандерол|герань|🛵|🏍', re.I)
SKIP_CH_WORDS = re.compile(r'відбій|отбой|reklama|реклама|розіграш|донат|збір на|сбор на', re.I)

posts = {}
for path in glob.glob(os.path.join(TMP, 'hist', '*.jsonl')) + glob.glob(os.path.join(TMP, 'tg', '*.jsonl')):
    ch = os.path.basename(path).rsplit('_', 1)[0] if 'hist' in path else os.path.basename(path)[:-6]
    for line in open(path, encoding='utf-8'):
        if not line.strip():
            continue
        p = json.loads(line)
        if p['dt'] >= '2022-02-24' and p['text']:
            posts[(ch, p['id'])] = p
print('posts', len(posts))

tg = TextGeo()
texts = [p['text'] for p in posts.values()]
tg.learn_common(texts)

days = defaultdict(lambda: [[set() for _ in YEARS] for _ in range(4)])  # [всего, ракеты, дроны, КАБ]
used = 0
for (ch, _), p in posts.items():
    t = p['text']
    if not THREAT.search(t) or SKIP_CH_WORDS.search(t):
        continue
    places = tg.find(t)
    if not places:
        continue
    used += 1
    d = kyiv(datetime.fromisoformat(p['dt']))
    y = str(d.year)
    if y not in YEARS:
        continue
    yi, day = YEARS.index(y), d.date().isoformat()
    kinds = [0] + [k for k, rx in ((1, MISSILE), (2, DRONE), (3, KAB)) if rx.search(t)]
    for pl in places:
        for k in kinds:
            days[pl[0]][k][yi].add(day)

oi = {o: i for i, o in enumerate(OBLASTS)}
pts = []
for g, d in days.items():
    pl = tg.place[g]
    pts.append([pl[2], pl[3], pl[1], oi.get(pl[4], -1)] + [[len(s) for s in d[k]] for k in range(4)])
pts.sort(key=lambda p: -sum(p[4]))
to = max(p['dt'] for p in posts.values())[:10]
out = {'years': YEARS, 'to': to, 'oblasts': OBLASTS, 'p': pts,
       'source': 'Telegram: @kpszsu, @monitorwarr, @war_monitor, @vanek_nikolaev'}
path = os.path.join(ROOT, 'data', 'flights.json')
json.dump(out, open(path, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
print('posts with places', used, 'places', len(pts), 'to', to, 'size', os.path.getsize(path))
for p in pts[:8]:
    print(p[2], p[4])
