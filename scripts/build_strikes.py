"""Прилёты за всю войну по населённым пунктам -> data/strikes.json.

Источник — VIINA (github.com/zhukovyuri/VIINA): заголовки новостей украинских СМИ, привязанные к населённому
пункту GeoNames и размеченные моделью по типу события. Берём дедуплицированные события (event_1pd —
одно событие на место в день): военное событие с авиаударом / БпЛА / артиллерией, не инициированное ВСУ.

Сырая привязка шумит, особенно в тылу, где событий мало: однофамильцы (Золочів на Харківщині -> Львівщина),
фронтовые сводки Генштаба, футбольный «Карпати». Поэтому событие засчитывается, только если хоть один из его
заголовков: упоминает название места; содержит слово про удар; не называет другую область без своей;
и для тыловых областей — не является сводкой «на … напрямку».
Геопривязка до области/района (GEO_PRECISION ADM1/ADM2) отбрасывается — это центроиды, а не места.

Формат: {years, to, oblasts, p: [[lat, lon, имя, обл_индекс, [дней с ударами по годам], [из них с разрушениями
или жертвами], [дата, заголовок, url] последнего удара], ...]}
"""
import csv, glob, json, os, re, zipfile, subprocess
from collections import defaultdict
from common import ROOT, TMP, ADMIN1

csv.field_size_limit(10 ** 8)
V = os.path.join(TMP, 'viina')
YEARS = ['2022', '2023', '2024', '2025', '2026']
B = 'https://media.githubusercontent.com/media/zhukovyuri/VIINA/main/Data/'
os.makedirs(V, exist_ok=True)
for y in YEARS:
    for k in ('event_1pd', 'event_info'):
        z = os.path.join(V, f'{k}_{y}.zip')
        if not os.path.exists(z) or (y == YEARS[-1] and os.path.getmtime(z) < __import__('time').time() - 6 * 3600):
            subprocess.run(['curl', '-sL', '-o', z, f'{B}{k}_latest_{y}.zip'], check=True)
        if not os.path.exists(os.path.join(V, f'{k}_latest_{y}.csv')) or y == YEARS[-1]:
            zipfile.ZipFile(z).extractall(V)

# украинские и русские названия, области — из GeoNames
alt = os.path.join(TMP, 'altnames_UA.zip')
if not os.path.exists(alt):
    subprocess.run(['curl', '-sL', '-o', alt, 'https://download.geonames.org/export/dump/alternatenames/UA.zip'], check=True)
uk, ru = {}, defaultdict(set)
for line in zipfile.ZipFile(alt).open('UA.txt').read().decode('utf-8').splitlines():
    f = line.split('\t')
    if f[7] == '1':  # историческое
        continue
    if f[2] == 'uk' and (f[1] not in uk or f[4] == '1'):
        uk[f[1]] = f[3]
    if f[2] in ('uk', 'ru'):
        ru[f[1]].add(f[3])
ob_of, city = {}, set()
for line in zipfile.ZipFile(os.path.join(TMP, 'UA.zip')).open('UA.txt').read().decode('utf-8').splitlines():
    f = line.split('\t')
    ob_of[f[0]] = ADMIN1.get(f[10])
    if f[7] in ('PPLC', 'PPLA', 'PPLA2') or int(f[14] or 0) >= 10000:
        city.add(f[0])
# в каких областях есть населённый пункт с таким названием (для поиска тёзок)
name_obs = defaultdict(set)
for g, names in ru.items():
    if ob_of.get(g):
        for n in names:
            name_obs[re.sub("[’'ʼ`]", '', n.lower())].add(ob_of[g])


def low(s):
    return re.sub("[’'ʼ`]", '', s.lower()).replace('ё', 'е')


def stems(g, ascii_name):
    out = set()
    for n in ru.get(g, set()) | ({uk[g]} if g in uk else set()):
        n = low(n).split('(')[0].strip()
        for v in {n, re.sub('[іi]в$', 'ов', n), re.sub('їв$', 'єв', n), re.sub('ь$', '', n)}:
            if len(v) >= 3:
                out.add(v[:max(3, len(v) - 2)] if len(v) > 4 else v[:-1] if len(v) > 3 else v)
    return out or {low(ascii_name)[:5]}


ATTACK = re.compile(r'удар|атак|обстр|вибух|взрыв|приліт|прилет|ракет|дрон|бпла|безпілот|беспилот|шахед|герань|'
                    r'бомб|каб|авіа|авиа|снаряд|артил|пошкодж|поврежд|зруйн|разруш|загин|погиб|поранен|ранен|'
                    r'пожеж|пожар|уламк|обломк|влучан|попадан|збил|сбил|збит|сбит', re.I)
FRONT_REPORT = re.compile(r'напрямк|направлени', re.I)
# основы названий областей: «на Харківщині», «Харківської області», «Харьковской области» ...
OB_STEMS = {
    'Вінницька область': ['вінниц', 'винниц'], 'Волинська область': ['волин', 'волын'],
    'Дніпропетровська область': ['дніпропетр', 'днепропетр'], 'Донецька область': ['донеч', 'донецьк', 'донецк'],
    'Житомирська область': ['житомирщ', 'житомирськ', 'житомирск'], 'Закарпатська область': ['закарпат'],
    'Запорізька область': ['запоріжж', 'запорізьк', 'запорожск', 'запорожь'], 'Івано-Франківська область': ['франків', 'франков', 'прикарпат'],
    'Київська область': ['київщ', 'київськ', 'киевск', 'киевщ'], 'Кіровоградська область': ['кіровоград', 'кировоград'],
    'Луганська область': ['луганщ', 'луганськ', 'луганск'], 'Львівська область': ['львівщ', 'львівськ', 'львовск', 'львовщ'],
    'Миколаївська область': ['миколаївщ', 'миколаївськ', 'николаевск', 'николаевщ'], 'Одеська область': ['одещ', 'одеськ', 'одесск'],
    'Полтавська область': ['полтавщ', 'полтавськ', 'полтавск'], 'Рівненська область': ['рівненщ', 'рівненськ', 'ровенск', 'ровенщ'],
    'Сумська область': ['сумщ', 'сумськ', 'сумск'], 'Тернопільська область': ['тернопільщ', 'тернопільськ', 'тернопольск'],
    'Харківська область': ['харківщ', 'харківськ', 'харьковск', 'харьковщ'], 'Херсонська область': ['херсонщ', 'херсонськ', 'херсонск'],
    'Хмельницька область': ['хмельниччин', 'хмельницьк', 'хмельницк'], 'Черкаська область': ['черкащ', 'черкаськ', 'черкасск'],
    'Чернівецька область': ['буковин', 'чернівецьк', 'черновицк'], 'Чернігівська область': ['чернігівщ', 'чернігівськ', 'черниговск', 'черниговщ'],
    'Автономна Республіка Крим': ['крим', 'крым'],
}
FRONTL = {'Донецька область', 'Луганська область', 'Запорізька область', 'Херсонська область', 'Харківська область',
          'Сумська область', 'Дніпропетровська область', 'Чернігівська область', 'Миколаївська область'}
# центры областей: «під Львовом» тоже называет свою область
CENTER = {'Львівська область': ['львів', 'львов'], 'Волинська область': ['луцьк', 'луцк'], 'Рівненська область': ['рівн', 'ровн'],
          'Тернопільська область': ['терноп'], 'Івано-Франківська область': ['франків', 'франков'], 'Закарпатська область': ['ужгород'],
          'Чернівецька область': ['чернівц', 'черновц'], 'Хмельницька область': ['хмельниц'], 'Вінницька область': ['вінниц', 'винниц'],
          'Житомирська область': ['житомир'], 'Київська область': ['київ', 'києв', 'киев'], 'Київ': ['київ', 'києв', 'киев'],
          'Черкаська область': ['черкас'], 'Кіровоградська область': ['кропивниц', 'кировоград'], 'Полтавська область': ['полтав'],
          'Одеська область': ['одес'], 'Миколаївська область': ['миколаїв', 'николаев'], 'Херсонська область': ['херсон'],
          'Запорізька область': ['запоріж', 'запорож'], 'Дніпропетровська область': ['дніпр', 'днепр'],
          'Харківська область': ['харків', 'харьков'], 'Сумська область': ['сум'], 'Чернігівська область': ['черніг', 'черниг'],
          'Донецька область': ['донец', 'донеч']}
UKR_INIT = re.compile(r'(українськ|украинск)\w* (військ|войск|сил|дрон|бпла|захисник)|\bвсу\b|'
                      r'зсу (вдари|удари|атакува|обстріля)|сили оборони (вдари|уразили|атакува)', re.I)
REAR = {'Вінницька область', 'Волинська область', 'Житомирська область', 'Закарпатська область', 'Івано-Франківська область',
        'Київська область', 'Київ', 'Кіровоградська область', 'Львівська область', 'Полтавська область', 'Рівненська область',
        'Тернопільська область', 'Хмельницька область', 'Черкаська область', 'Чернівецька область', 'Одеська область'}


def valid(text, g, st):
    t = low(text)
    if not ATTACK.search(t) or UKR_INIT.search(t):
        return False
    if not any(re.search(r'(?<![а-яіїєґa-z])' + re.escape(s), t) for s in st):
        return False
    ob = ob_of.get(g)
    named = {o for o, ss in OB_STEMS.items() if any(s in t for s in ss)}
    if named & {'Київська область', 'Київ'}:
        named |= {'Київська область', 'Київ'}
    if named and ob not in named:
        return False  # однофамилец в другой области
    if ob in REAR and FRONT_REPORT.search(t):
        return False  # сводка с фронта про тёзку
    own = ob in named or any(s in t for s in CENTER.get(ob, []))
    if g not in city and not own:
        return False  # село: заголовок должен назвать свою область или её центр
    twins = set().union(*[name_obs.get(low(n), set()) for n in ru.get(g, set()) | {uk.get(g, '')}]) - {ob}
    if ob not in FRONTL and twins & FRONTL and not own:
        return False  # есть тёзка у фронта, а своя область не названа
    return True


# 1) кандидаты из event_1pd — любой точности: точные проверяем до села, остальные — на упоминание района
cand = []  # (год_индекс, geonameid, дата, ids, с разрушениями, точная привязка)
pos, aname = {}, {}
for y_i, y in enumerate(YEARS):
    for r in csv.DictReader(open(os.path.join(V, f'event_1pd_latest_{y}.csv'), encoding='utf-8')):
        if r['t_mil_b'] != '1' or r['a_ukr_init_b'] == '1':
            continue
        strike = r['t_airstrike_b'] == '1' or r['t_uav_b'] == '1' or r['t_artillery_b'] == '1'
        if not strike and r['t_ied_b'] != '1':
            continue
        g = r['geonameid']
        ids = [i.strip() for i in r['event_ids'].split(',')]
        # «взрыв» без метки удара — только для районного уровня и только с явными словами (см. raions_in)
        cand.append((y_i, g, r['date'], ids, r['t_property_b'] == '1' or r['t_civcas_b'] == '1',
                     strike and r['GEO_PRECISION'] not in ('ADM1', 'ADM2'), strike))
        pos[g] = (round(float(r['latitude']), 4), round(float(r['longitude']), 4))
        aname[g] = r['asciiname']

# 2) заголовки нужных отчётов
need = {i for c in cand for i in c[3]}
texts = {}
for f in sorted(glob.glob(os.path.join(V, 'event_info_latest_*.csv'))):
    for r in csv.DictReader(open(f, encoding='utf-8')):
        if r['event_id'] in need:
            texts[r['event_id']] = (r['text'], r['url'])

# районы (GeoNames ADM2): «у Стрийському районі» -> Стрийський район. Ключ — основа прилагательного.
RAION_RE = re.compile(r'([а-яіїєґ]{3,}?)(?:ськ|цьк|зьк|ск|цк|зк)[а-яіїєґ]* район')
raion = {}           # geonameid -> (lat, lon, область, имя)
raion_key = defaultdict(set)
for line in zipfile.ZipFile(os.path.join(TMP, 'UA.zip')).open('UA.txt').read().decode('utf-8').splitlines():
    f = line.split('\t')
    if f[7] == 'ADM2' and ADMIN1.get(f[10]) not in ('Автономна Республіка Крим', 'Севастополь', None):
        raion[f[0]] = [round(float(f[4]), 4), round(float(f[5]), 4), ADMIN1.get(f[10]), None]
for g, names in ru.items():
    if g in raion:
        for n in names:
            m = RAION_RE.search(low(n))
            if m:
                raion_key[m.group(1)].add(g)
            if 'район' in n.lower() and re.search('[іїє]|[сцз]ьк', n.lower()) and not raion[g][3]:
                raion[g][3] = n[0].upper() + n[1:].replace(' Район', ' район')


BLAST = re.compile(r'вибухи|взрывы|ракет|атак|удар|дрон|шахед|бпла|обстр', re.I)


# запасной путь: GeoNames знает не все районы после реформы 2020 — ищем райцентр по основе («стрий» -> Стрий)
centers = []  # (норм.имя, geonameid, lat, lon, область, имя)
for line in zipfile.ZipFile(os.path.join(TMP, 'UA.zip')).open('UA.txt').read().decode('utf-8').splitlines():
    f = line.split('	')
    if f[7] in ('PPLA', 'PPLA2') and f[0] in uk and ADMIN1.get(f[10]) not in ('Автономна Республіка Крим', 'Севастополь', None):
        centers.append((low(uk[f[0]]), 'c' + f[0], round(float(f[4]), 4), round(float(f[5]), 4), ADMIN1.get(f[10]), uk[f[0]]))


def raion_by_center(stem, named):
    pre = stem[:max(4, len(stem) - 1)]
    gs = [c for c in centers if c[0].startswith(pre) and (not named or c[4] in named)]
    if len(gs) != 1:
        return set()
    c = gs[0]
    raion.setdefault(c[1], [c[2], c[3], c[4], f'р-н {c[5]}'])
    return {c[1]}


def raions_in(text, strike=True):
    t = low(text)
    if not ATTACK.search(t) or UKR_INIT.search(t) or (not strike and (not BLAST.search(t) or 'газ' in t)):
        return set()
    named = {o for o, ss in OB_STEMS.items() if any(s in t for s in ss)}
    out = set()
    for m in RAION_RE.finditer(t):
        gs = raion_key.get(m.group(1), set())
        if named:
            gs = {g for g in gs if raion[g][2] in named}
        if not gs:
            gs = raion_by_center(m.group(1), named)
        if len(gs) == 1:  # тёзки-районы без названной области — пропускаем
            out |= gs
    return out


# 3) проверка и агрегация
SKIP_OB = {'Автономна Республіка Крим', 'Севастополь'}  # в Крыму это в основном удары ВСУ
st_cache = {}
days = defaultdict(lambda: [set() for _ in YEARS])
hits = defaultdict(lambda: [set() for _ in YEARS])
rdays = defaultdict(lambda: [set() for _ in YEARS])
rhits = defaultdict(lambda: [set() for _ in YEARS])
last, rlast = {}, {}
kept = rkept = 0
from textgeo import TextGeo
tgeo = TextGeo()
tgeo.learn_common(t for t, _ in texts.values())
BLAST2 = re.compile(r'вибух|взрыв|ракет|атак|удар|дрон|шахед|бпла|обстр|приліт|прилет|влуч|попад|уламк|обломк', re.I)
tg_kept = 0


def mark(g, y_i, dt, dmg, text, url):
    days[g][y_i].add(dt)
    if dmg:
        hits[g][y_i].add(dt)
    if dt >= last.get(g, ('',))[0]:
        last[g] = (dt, text[:160], url)


for y_i, g, dt, ids, dmg, precise, strike in cand:
    tx = [texts[i] for i in ids if i in texts]
    # места, названные в самом заголовке («Бурштинська ТЕС» -> Бурштин) — главный путь
    got = False
    for t in tx:
        lt = low(t[0])
        if not ATTACK.search(lt) or UKR_INIT.search(lt) or (not strike and (not BLAST2.search(lt) or 'газ' in lt)):
            continue
        for pl in tgeo.find(t[0]):
            pos.setdefault(pl[0], (pl[2], pl[3]))
            aname.setdefault(pl[0], pl[1])
            mark(pl[0], y_i, dt, dmg, t[0], t[1])
            got = True
    if got:
        tg_kept += 1
        continue
    if precise and ob_of.get(g) not in SKIP_OB:
        st = st_cache.get(g) or st_cache.setdefault(g, stems(g, aname[g]))
        ok = [t for t in tx if valid(t[0], g, st)]
        if ok:
            kept += 1
            days[g][y_i].add(dt)
            if dmg:
                hits[g][y_i].add(dt)
            if dt >= last.get(g, ('',))[0]:
                last[g] = (dt, ok[0][0][:160], ok[0][1])
            continue
    for t in tx:  # точного места нет — может, назван район
        rs = raions_in(t[0], strike)
        for rg in rs:
            rdays[rg][y_i].add(dt)
            if dmg:
                rhits[rg][y_i].add(dt)
            if dt >= rlast.get(rg, ('',))[0]:
                rlast[rg] = (dt, t[0][:160], t[1])
        if rs:
            rkept += 1
            break

oblasts = sorted({o for o in ob_of.values() if o})
oi = {o: i for i, o in enumerate(oblasts)}
iso = lambda d: f'{d[:4]}-{d[4:6]}-{d[6:]}'
pts = []
for g, d in days.items():
    dt, tx, url = last[g]
    pts.append([pos[g][0], pos[g][1], uk.get(g, aname[g]), oi.get(ob_of.get(g), -1),
                [len(s) for s in d], [len(s) for s in hits[g]], [iso(dt), tx, url]])
pts.sort(key=lambda p: -sum(p[4]))
rts = []
for g, d in rdays.items():
    dt, tx, url = rlast[g]
    lat, lon, ob, nm = raion[g]
    rts.append([lat, lon, nm or g, oi.get(ob, -1), [len(s) for s in d], [len(s) for s in rhits[g]], [iso(dt), tx, url]])
rts.sort(key=lambda p: -sum(p[4]))
out = {'years': YEARS, 'to': max(p[6][0] for p in pts), 'oblasts': oblasts, 'p': pts, 'r': rts,
       'source': 'VIINA, github.com/zhukovyuri/VIINA (Zhukov, University of Michigan)'}
path = os.path.join(ROOT, 'data', 'strikes.json')
json.dump(out, open(path, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
print('candidates', len(cand), 'places', len(pts), f'(по тексту {tg_kept}, по VIINA {kept})', 'raions', len(rts), f'(событий {rkept})',
      'to', out['to'], 'size', os.path.getsize(path))
