"""Общие справочники: области, нормализация названий, газетир GeoNames."""
import json, os, re, zipfile, subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = os.path.join(ROOT, '_tmp')

# код admin1 GeoNames -> название области как в архиве тревог
ADMIN1 = {
    '01': 'Черкаська область', '02': 'Чернігівська область', '03': 'Чернівецька область',
    '04': 'Дніпропетровська область', '05': 'Донецька область', '06': 'Івано-Франківська область',
    '07': 'Харківська область', '08': 'Херсонська область', '09': 'Хмельницька область',
    '10': 'Кіровоградська область', '11': 'Автономна Республіка Крим', '12': 'Київ',
    '13': 'Київська область', '14': 'Луганська область', '15': 'Львівська область',
    '16': 'Миколаївська область', '17': 'Одеська область', '18': 'Полтавська область',
    '19': 'Рівненська область', '20': 'Севастополь', '21': 'Сумська область',
    '22': 'Тернопільська область', '23': 'Вінницька область', '24': 'Волинська область',
    '25': 'Закарпатська область', '26': 'Запорізька область', '27': 'Житомирська область',
}
OBLASTS = sorted(set(ADMIN1.values()))

# geoBoundaries ADM1 (англ.) -> укр.
GB_NAMES = {
    'Kherson Oblast': 'Херсонська область', 'Volyn Oblast': 'Волинська область',
    'Rivne Oblast': 'Рівненська область', 'Zhytomyr Oblast': 'Житомирська область',
    'Kyiv Oblast': 'Київська область', 'Chernihiv Oblast': 'Чернігівська область',
    'Sumy Oblast': 'Сумська область', 'Kharkiv Oblast': 'Харківська область',
    'Luhansk Oblast': 'Луганська область', 'Donetsk Oblast': 'Донецька область',
    'Zaporizhia Oblast': 'Запорізька область', 'Lviv Oblast': 'Львівська область',
    'Ivano-Frankivsk Oblast': 'Івано-Франківська область', 'Zakarpattia Oblast': 'Закарпатська область',
    'Ternopil Oblast': 'Тернопільська область', 'Chernivtsi Oblast': 'Чернівецька область',
    'Odessa Oblast': 'Одеська область', 'Mykolaiv Oblast': 'Миколаївська область',
    'Autonomous Republic of Crimea': 'Автономна Республіка Крим', 'Vinnytsia Oblast': 'Вінницька область',
    'Khmelnytskyi Oblast': 'Хмельницька область', 'Cherkasy Oblast': 'Черкаська область',
    'Poltava Oblast': 'Полтавська область', 'Dnipropetrovsk Oblast': 'Дніпропетровська область',
    'Kirovohrad Oblast': 'Кіровоградська область', 'Kyiv': 'Київ', 'Sevastopol': 'Севастополь',
}

# Разговорные/русские основы -> область
_OB_ALIAS = {
    'днепропет': 'Дніпропетровська область', 'дніпропет': 'Дніпропетровська область',
    'николаев': 'Миколаївська область', 'одесс': 'Одеська область', 'харьков': 'Харківська область',
    'запорож': 'Запорізька область', 'херсон': 'Херсонська область', 'житомир': 'Житомирська область',
    'чернигов': 'Чернігівська область', 'черкас': 'Черкаська область', 'кировоград': 'Кіровоградська область',
    'киевск': 'Київська область', 'київщ': 'Київська область', 'київськ': 'Київська область',
    'полтав': 'Полтавська область', 'сумск': 'Сумська область', 'сумщ': 'Сумська область',
    'винниц': 'Вінницька область', 'ровен': 'Рівненська область', 'волын': 'Волинська область',
    'хмельниц': 'Хмельницька область', 'тернопол': 'Тернопільська область', 'львов': 'Львівська область',
    'ивано': 'Івано-Франківська область', 'прикарпат': 'Івано-Франківська область',
    'черновиц': 'Чернівецька область', 'буковин': 'Чернівецька область', 'закарпат': 'Закарпатська область',
    'донец': 'Донецька область', 'донеч': 'Донецька область', 'луган': 'Луганська область',
    'крым': 'Автономна Республіка Крим', 'крим': 'Автономна Республіка Крим', 'севастоп': 'Севастополь',
}


def norm(s):
    s = s.lower().replace('ё', 'е')
    s = re.sub("[’'ʼ`´‘]", '', s)
    s = re.sub(r'^(м\.|м |с\.|смт\.?|сел\.|г\.|пгт\.?)\s*', '', s.strip())
    s = re.sub(r'[\s\-–]+', ' ', s)
    return s.strip()


def ob_key(s):
    """Свободное написание области -> каноническое имя или None."""
    if not s:
        return None
    n = norm(s)
    if n in ('київ', 'киев', 'м київ', 'kyiv', 'столиця'):
        return 'Київ'
    for o in OBLASTS:
        if norm(o) == n:
            return o
    for o in OBLASTS:
        if o.endswith('область') and norm(o)[:6] == n[:6]:
            return o
    for k, v in _OB_ALIAS.items():
        if n.startswith(k):
            return v
    return None


def load_gazetteer():
    """{норм.имя: [[lat, lon, область, население, код], ...]} из GeoNames UA."""
    cache = os.path.join(TMP, 'gazetteer.json')
    if os.path.exists(cache):
        return json.load(open(cache, encoding='utf-8'))
    zp = os.path.join(TMP, 'UA.zip')
    if not os.path.exists(zp):
        subprocess.run(['curl', '-sL', '-o', zp, 'https://download.geonames.org/export/dump/UA.zip'], check=True)
    gaz = {}
    with zipfile.ZipFile(zp) as z:
        for line in z.open('UA.txt').read().decode('utf-8').splitlines():
            f = line.split('\t')
            fclass, fcode = f[6], f[7]
            if fclass not in ('P', 'A', 'H', 'S', 'L'):
                continue
            if fclass == 'A' and fcode not in ('ADM2', 'ADM3'):
                continue
            rec = [round(float(f[4]), 4), round(float(f[5]), 4), ADMIN1.get(f[10]), int(f[14] or 0), fcode]
            names = {f[1], f[2]} | set(f[3].split(',') if f[3] else [])
            for nm in names:
                k = norm(nm)
                if len(k) < 3:
                    continue
                gaz.setdefault(k, []).append(rec)
    json.dump(gaz, open(cache, 'w', encoding='utf-8'), ensure_ascii=False)
    return gaz


_RANK = {'PPLC': 9, 'PPLA': 8, 'PPLA2': 7, 'PPLA3': 6, 'PPL': 5, 'PPLX': 4, 'ADM2': 3, 'ADM3': 3}


def geocode(gaz, name, oblast=None, near=None):
    """Лучшее совпадение: своя область > близость к подсказке near=(lat,lon) > ранг и население."""
    cands = gaz.get(norm(name)) or []
    if not cands:
        return None
    ob = ob_key(oblast) if oblast else None

    def score(c):
        s = 0.0
        if ob and c[2] == ob:
            s += 1e9
        if near:
            d = ((c[0] - near[0]) ** 2 + (c[1] - near[1]) ** 2) ** 0.5
            s += 1e8 if d < 0.6 else 0
            s -= d * 1e6
        s += c[3] + _RANK.get(c[4], 0) * 1000
        return s
    return max(cands, key=score)
