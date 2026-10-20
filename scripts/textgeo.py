"""Поиск населённых пунктов Украины в тексте (укр./рус., с падежами) по GeoNames.

    from textgeo import TextGeo
    tg = TextGeo()
    tg.find("Два «Кинджали» летять на Стрий або Бурштин")  -> [place, place]
place = (geonameid, укр. имя, lat, lon, область, население)

Как матчится:
- берутся только слова с заглавной буквы; слово, которое в корпусе чаще встречается со строчной
  (Увага, Загроза, Ракета…), отбрасывается — см. common_words();
- основа имени без изменяемого окончания (Шепетівка -> шепетів: Шепетівці/Шепетівку; Львів -> льво-/льві-;
  Коломия -> коломи-), после основы — не больше 3 букв окончания, либо прилагательное перед ТЕС/ТЕЦ/громадою
  («Бурштинська ТЕС» -> Бурштин);
- формы областей (Франківщина, Харківська область) — не места;
- тёзки: сначала город в области, названной в тексте; без области — самый крупный город, а село —
  только если имя уникально и длинное (иначе неоднозначно и пропускается).
"""
import os, re, zipfile, subprocess
from collections import defaultdict, Counter
from common import TMP, ADMIN1

APOS = re.compile("[’'ʼ`´]")
ADJ_NEXT = re.compile(r'^(тес|тэс|тец|тэц|гес|гэс|гаэс|гаес|аес|аэс|нпз|громад|міськ|городск|залізнич|аеродром|аэродром)', re.I)
ADMIN_NEXT = re.compile(r'^(област|обл\b|ова|ода|район|р-н|рай)', re.I)
VOWEL_END = set('аяеоиіїєюуьй')

OB_STEMS = {
    'Вінницька область': ['вінниччин', 'винниччин', 'вінницьк', 'винницк'], 'Волинська область': ['волин', 'волын'],
    'Дніпропетровська область': ['дніпропетр', 'днепропетр'], 'Донецька область': ['донеччин', 'донетчин', 'донецьк', 'донецк'],
    'Житомирська область': ['житомирщ', 'житомирськ', 'житомирск'], 'Закарпатська область': ['закарпат'],
    'Запорізька область': ['запоріжж', 'запорізьк', 'запорожск', 'запорожь'],
    'Івано-Франківська область': ['франківщ', 'франковщ', 'прикарпат', 'франківськ', 'франковск'],
    'Київська область': ['київщ', 'київськ', 'киевск', 'киевщ'], 'Кіровоградська область': ['кіровоград', 'кировоград'],
    'Луганська область': ['луганщ', 'луганськ', 'луганск'], 'Львівська область': ['львівщ', 'львівськ', 'львовск', 'львовщ'],
    'Миколаївська область': ['миколаївщ', 'миколаївськ', 'николаевск', 'николаевщ'], 'Одеська область': ['одещ', 'одеськ', 'одесск'],
    'Полтавська область': ['полтавщ', 'полтавськ', 'полтавск'], 'Рівненська область': ['рівненщ', 'рівненськ', 'ровенск', 'ровенщ'],
    'Сумська область': ['сумщ', 'сумськ', 'сумск'], 'Тернопільська область': ['тернопільщ', 'тернопільськ', 'тернопольск', 'тернопольщ'],
    'Харківська область': ['харківщ', 'харківськ', 'харьковск', 'харьковщ'], 'Херсонська область': ['херсонщ', 'херсонськ', 'херсонск'],
    'Хмельницька область': ['хмельниччин', 'хмельниччин', 'хмельницьк', 'хмельницк'], 'Черкаська область': ['черкащ', 'черкаськ', 'черкасск'],
    'Чернівецька область': ['буковин', 'чернівецьк', 'черновицк'], 'Чернігівська область': ['чернігівщ', 'чернігівськ', 'черниговск', 'черниговщ'],
}
# названия, совпадающие с оружием, техникой и частыми словами
STOP = {'шахед', 'герань', 'калібр', 'калибр', 'іскандер', 'искандер', 'кинджал', 'кинжал', 'циркон', 'онікс', 'оникс',
        'бандероль', 'гербера', 'пародія', 'паляниця', 'верба', 'нептун', 'патріот', 'граніт', 'гроза', 'буря', 'смерч',
        'ураган', 'торнадо', 'точка', 'оса', 'тор', 'бук', 'панцир', 'україна', 'україни', 'україні', 'росія', 'росії',
        'русь', 'дача', 'слава', 'мир', 'шлях', 'нива', 'зоря', 'промінь', 'перемога', 'дружба', 'надія', 'свобода',
        'воля', 'весна', 'мрія', 'квітень', 'травень', 'червень', 'липень', 'серпень', 'вересень', 'жовтень',
        'листопад', 'грудень', 'січень', 'лютий', 'березень', 'майдан', 'крим', 'чорне', 'азов', 'дніпро-1',
        # российские города и аэродромы — у них есть украинские сёла-тёзки
        'брянськ', 'брянск', 'курськ', 'курск', 'бєлгород', 'белгород', 'білгород', 'ростов', 'воронеж', 'орел', 'орел',
        'орла', 'смоленськ', 'смоленск', 'міллерово', 'миллерово', 'таганрог', 'шаталово', 'шаталове', 'енгельс',
        'энгельс', 'моздок', 'оленья', 'оленя', 'морозовськ', 'морозовск', 'приморсько-ахтарськ', 'єйськ', 'ейск',
        'липецьк', 'липецк', 'саки', 'джанкой', 'чауда', 'гвардійське', 'гвардейское', 'каспій', 'каспий', 'москва',
        'бєларусь', 'беларусь', 'білорусь', 'гомель', 'мозир', 'мозырь', 'румунія', 'румынии', 'молдова', 'польща',
        # оккупированные города — в мониторинге это районы пуска («з ТОТ Донецьк»), а не цели
        'донецьк', 'донецьку', 'донецьком', 'донецк', 'донецке', 'донецка', 'луганськ', 'луганську', 'луганск',
        'луганске', 'горлівка', 'горлівку', 'горлівці', 'горловка', 'горловку', 'макіївка', 'макіївку', 'макеевка'}


STOP_PREFIX = ('збройн', 'вооруж', 'генштаб', 'повітрян', 'воздушн', 'росія', 'росії', 'россия', 'россии',
               'українськ', 'российск', 'русск', 'буковин', 'прикарпат', 'закарпат', 'волин', 'волын', 'поділл',
               'подолье', 'полісс', 'полесь', 'галичин', 'слобожан', 'донбас', 'таврі', 'бессараб')
STREET_PREV = {'ул', 'вул', 'вулиця', 'вулиці', 'улица', 'улице', 'просп', 'проспект', 'пл', 'площа', 'провулок', 'пер', 'бульвар'}
REAR = {'Вінницька область', 'Волинська область', 'Житомирська область', 'Закарпатська область', 'Івано-Франківська область',
        'Київська область', 'Київ', 'Кіровоградська область', 'Львівська область', 'Полтавська область', 'Рівненська область',
        'Тернопільська область', 'Хмельницька область', 'Черкаська область', 'Чернівецька область', 'Одеська область'}
FRONT_REPORT = re.compile(r'напрямк|направлени', re.I)
FRONTL = {'Донецька область', 'Луганська область', 'Запорізька область', 'Херсонська область', 'Харківська область',
          'Сумська область', 'Дніпропетровська область', 'Чернігівська область', 'Миколаївська область'}
MAJOR = 100000  # город такого размера однозначен и без названной области
# Кривий Ріг склоняется с чередованием (Кривому Розі) — формы списком
KR_FORMS = [(f, '703845') for f in ('кривий ріг', 'кривого рогу', 'кривому розі', 'кривому рогу', 'кривим рогом',
                                    'кривой рог', 'кривого рога', 'кривом роге', 'кривому рогу', 'кривым рогом')]


def low(s):
    return APOS.sub('', s.lower()).replace('ё', 'е')


def stem_variants(w):
    """Основы слова имени, к которым присоединяются падежные окончания."""
    out = set()
    if len(w) < 4:
        return out
    for v in {w, re.sub('[іi]в$', 'ов', w), re.sub('їв$', 'єв', w), re.sub('ів$', 'ев', w)}:
        if v.endswith(('ий', 'ій', 'ой')) and len(v) >= 6:
            out.add(v[:-2])           # Хмельницький -> хмельницьк (Хмельницькому, Хмельницького)
        elif v.endswith(('ка', 'ки')) and len(v) >= 6:
            out.add(v[:-2])           # Шепетівка -> шепетів (Шепетівці, Шепетівку)
        elif v[-1] in VOWEL_END:
            out.add(v[:-1])           # Коломия -> коломи, Чернівці -> чернівц
        else:
            out.add(v)                # Бурштин, Калуш, Львов-
            alt = {'к': 'ц', 'г': 'з', 'х': 'с'}.get(v[-1])
            if alt and len(v) >= 6:
                out.add(v[:-1] + alt)  # Кременчук -> кременчуц (Кременчуці)
    return {s for s in out if len(s) >= 4}


class TextGeo:
    def __init__(self):
        alt = os.path.join(TMP, 'altnames_UA.zip')
        if not os.path.exists(alt):
            subprocess.run(['curl', '-sL', '-o', alt, 'https://download.geonames.org/export/dump/alternatenames/UA.zip'], check=True)
        names = defaultdict(set)
        uk = {}
        for line in zipfile.ZipFile(alt).open('UA.txt').read().decode('utf-8').splitlines():
            f = line.split('\t')
            if f[7] == '1' or f[2] not in ('uk', 'ru', ''):
                continue
            if re.search('[а-яіїєґ]', f[3].lower()):
                names[f[1]].add(f[3])
                if f[2] == 'uk' and (f[1] not in uk or f[4] == '1'):
                    uk[f[1]] = f[3]
        self.place = {}
        for line in zipfile.ZipFile(os.path.join(TMP, 'UA.zip')).open('UA.txt').read().decode('utf-8').splitlines():
            f = line.split('\t')
            if f[6] != 'P' or f[7] in ('PPLX', 'PPLH', 'PPLQ', 'PPLW'):
                continue
            ob = ADMIN1.get(f[10])
            if not ob or f[0] not in names or ob in ('Автономна Республіка Крим', 'Севастополь'):
                continue
            pop = int(f[14] or 0)
            big = f[7] in ('PPLC', 'PPLA', 'PPLA2') or pop >= 10000
            self.place[f[0]] = (f[0], uk.get(f[0], sorted(names[f[0]])[0]), round(float(f[4]), 4), round(float(f[5]), 4), ob, pop, big)
        # индекс: первые 4 буквы -> [(основа, число_слов, geonameid, полное имя)]
        self.idx = defaultdict(list)
        self.idx3 = defaultdict(list)  # многословные имена — по 3 буквам (Біла -> біл-: Білій, Білої)
        self.exact = defaultdict(set)  # короткие имена (Рава, Ірпінь…) — точное совпадение формы
        self.namesakes = defaultdict(set)
        for g, p in self.place.items():
            for n in names[g]:
                n = low(n).split('(')[0].strip()
                if not n or n in STOP:
                    continue
                self.namesakes[n].add(g)
                parts = n.replace('-', ' - ').split() if ' ' in n else [n]
                if len(parts) == 1:
                    self.exact[n].add(g)
                    for s in stem_variants(n):
                        self.idx[s[:4]].append((s, 1, g, n))
                else:  # «Біла Церква», «Нова Каховка»: обе основы подряд
                    st = [w[:-2] if w.endswith(('ка', 'ки')) and len(w) >= 6 else w[:-1] if w[-1] in VOWEL_END and len(w) > 3
                          else w for w in parts if w != '-']
                    self.idx3[st[0][:3]].append((tuple(st), len(st), g, n))
        # частые слова: в корпусе со строчной чаще, чем с заглавной — не места
        self.common = set()

    def learn_common(self, texts):
        cap, lw = Counter(), Counter()
        for t in texts:
            for m in re.finditer(r"[А-ЯІЇЄҐЁа-яіїєґё’'ʼ-]+", t):
                w = m.group(0)
                (cap if w[0].isupper() else lw)[low(w)] += 1
        self.common = {w for w, c in lw.items() if c >= 5 and c >= cap.get(w, 0)}

    def oblasts_in(self, t):
        t = low(t)
        obs = {o for o, ss in OB_STEMS.items() if any(s in t for s in ss)}
        if re.search(r'(?<![а-яіїєґ])(київ|києв|киев)', t):
            obs.add('Київ')
        return obs

    def _cands(self, toks, i):
        """Кандидаты для токена i: [(geonameid, длина в токенах)]."""
        w = toks[i]
        out = []
        if w in self.exact:
            out += [(g, 1) for g in self.exact[w]]
        for s, n, g, full in self.idx.get(w[:4], []) + self.idx3.get(w[:3], []):
            if n == 1:
                if w.startswith(s) and w != s or w == s:
                    rest = w[len(s):]
                    if 'щин' in rest or 'ччин' in rest:
                        continue
                    nxt = toks[i + 1] if i + 1 < len(toks) else ''
                    if ADMIN_NEXT.match(nxt):
                        continue  # «Миколаївська область», «Калуському районі» — не населённый пункт
                    if len(rest) <= 3:
                        if re.match('^(ськ|цьк|зьк|ск|цк)', rest):
                            continue
                        out.append((g, 1))
                    elif re.match('^(ськ|цьк|зьк|ськ|ск|цк|зк)', rest) and len(rest) <= 7 and ADJ_NEXT.match(nxt) \
                            and not ADMIN_NEXT.match(nxt):
                        out.append((g, 1))
            else:
                if i + n - 1 < len(toks) and all(toks[i + k].startswith(s[k]) and len(toks[i + k]) - len(s[k]) <= 3
                                                 for k in range(n)):
                    out.append((g, n))
        return out

    def find(self, text, oblasts=None):
        """Населённые пункты в тексте. oblasts — области из контекста (если уже известны)."""
        obs = set(oblasts or ()) | self.oblasts_in(text)
        ms = list(re.finditer(r"[А-ЯІЇЄҐЁа-яіїєґё’'ʼ-]+", text))
        raw = [m.group(0) for m in ms]
        spans = [m.span() for m in ms]
        words = [low(x).strip('-') for x in raw]  # все слова: следующее нужно для «Бурштинська ТЕС»
        found = {}
        covered = set()
        lt = low(text)
        for form, g in KR_FORMS:
            if form in lt and g in self.place:
                found[g] = self.place[g]
        front_report = bool(FRONT_REPORT.search(text))
        for i, w in enumerate(words):
            if i in covered or not raw[i][0].isupper() or len(w) < 3 or w in STOP or w in self.common:
                continue
            if w.startswith(STOP_PREFIX) or 'щин' in w or 'ччин' in w or (i > 0 and words[i - 1] in STREET_PREV):
                continue
            nxt = words[i + 1] if i + 1 < len(words) else ''
            if nxt.startswith(('мор', 'моря')):
                continue  # «Чорного моря»
            cs = self._cands(words, i)
            if not cs:
                continue
            longest = max(n for _, n in cs)
            cs = [c for c in cs if c[1] == longest]  # «Нова Каховка» важнее «Каховки»
            if longest == 1:
                # рядом слово с заглавной, которое не место: имя и фамилия («Женя Галич», «Максим Козицький»)
                if any(0 <= j < len(raw) and raw[j][:1].isupper() and not raw[j].isupper() and len(raw[j]) > 2
                       and words[j] not in self.common and not self._cands(words, j) and not self.oblasts_in(raw[j])
                       and not text[min(spans[i][1], spans[j][1]):max(spans[i][0], spans[j][0])].strip()
                       for j in (i - 1, i + 1)):
                    continue
            covered |= set(range(i + 1, i + longest))
            gs = {g for g, _ in cs}
            pl = [self.place[g] for g in gs]
            in_ob = [p for p in pl if p[4] in obs]
            bigs_out = [p for p in pl if p[5] >= MAJOR and p not in in_ob]
            if in_ob and (any(p[6] for p in in_ob) or not bigs_out):
                pick = max(in_ob, key=lambda p: (p[6], p[5]))
            else:
                bigs = [p for p in pl if p[6]]
                if bigs:
                    pick = max(bigs, key=lambda p: p[5])
                else:
                    continue  # село без названной области — слишком много тёзок
            # город-тёзка в другой области, а в тексте названа своя область без него — не берём
            if obs and pick[4] not in obs and not pick[6]:
                continue
            if front_report and pick[5] < MAJOR and pick[4] in REAR:
                continue  # сводка с фронта про тыловой тёзку
            if pick[4] not in obs and pick[4] in REAR and pick[5] < MAJOR and any(p[4] in FRONTL for p in pl):
                continue  # тыловой городок с тёзкой у фронта, область не названа — неоднозначно
            found[pick[0]] = pick
        return list(found.values())
