"""Траектории за всю войну: посты мониторов -> наблюдения «тип, место, время» -> треки -> data/paths/<год>.json.

Линия рисуется только между конкретными населёнными пунктами, где цель видели («повз Турбів», «через Прилуки»,
«в районі Охтирки»), с временем поста. «Курсом на Х» — не положение, а подсказка направления; «на півночі
Житомирщини» — слишком грубо, в линии не идёт. Склейка точек в трек — по физике:
- скорость: шахед до ~230 км/ч, реактивный дрон и «Бандероль» до ~650, крылатая ракета до ~1000 (+15 км на неточность места);
- направление: следующая точка должна лежать по курсу, который мониторы назвали в прошлый раз (±65°),
  или по направлению к названной цели;
- две строки одного поста — разные группы, между собой не склеиваются; если трек можно продолжить двумя
  одинаково хорошими способами — не угадываем, начинаем новый.
Баллистика — прямая от района пуска («з Брянська», «загроза балістики з Курська» за ≤20 мин) до цели.
КАБы не трекаются.

python scripts/build_paths.py            # разбор (кэш _tmp/paths_obs.json) + треки + файлы сайта
python scripts/build_paths.py --reparse  # заново разобрать посты
"""
import glob, json, math, os, re, sys
from collections import defaultdict
from datetime import datetime, timedelta
from common import ROOT, TMP, OBLASTS
from split_nights import kyiv
from textgeo import TextGeo, low

CHANNELS = ['kpszsu', 'monitorwarr', 'war_monitor', 'vanek_nikolaev']
# областные мониторы и новостные каналы сетей «Головне», «Труха», «Вайб», «MNR» (история с 2024, _tmp/hist_reg/):
# область канала — контекст для сёл без названной области («Повз Піщанку на Бар» у вінницького каналу)
REGIONAL = {
    'vinnytsia_golovne': ['Вінницька область'], 'vinnitsa_info': ['Вінницька область'],
    'khmelnych': ['Хмельницька область'], 'khmlv': ['Хмельницька область'], 'zt_radar': ['Житомирська область'],
    'rivne_golovne': ['Рівненська область'], 'rivne_radar': ['Рівненська область'],
    'truexaternopil': ['Тернопільська область'], 'lviv_golovne': ['Львівська область'],
    'truexafrankivsk': ['Івано-Франківська область'], 'Lutsk_monitor': ['Волинська область'], 'lutsk_radar': ['Волинська область'],
    'cherkasy_golovne': ['Черкаська область'], 'cherkasy_radar': ['Черкаська область'],
    'kyivradar': ['Київська область', 'Київ'],
}
# чистые мониторы: любое село в посте — где сейчас цель («⚠️ Миронівка, Богуслав»)
PURE_MONITORS = {'kyivradar', 'zt_radar', 'rivne_radar', 'Lutsk_monitor', 'lutsk_radar', 'cherkasy_radar'}
NATIONAL_EXTRA = ['kudy_letyt', 'deraketaua']
ALL_CHANNELS = CHANNELS + NATIONAL_EXTRA + list(REGIONAL)
# у областных мониторов тип часто не назван: «Повз Лисянки на виліт», «Курсом на Шумськ» — это дрон
MOVE = re.compile(r'повз|курс|напрям|у бік|в бік|в сторону|через|➡|→|на виліт|залітає|заходить|пролітає|летить|летять')
FOOTER = re.compile(r'головне|надіслати|наш чат|підпис|@\w|\||t\.me/|http', re.I)
NOT_MOVE = re.compile(r'тривог|тревог|відбій|отбой|мапу|карту|карта|osint|розвідка повідомляє|ймовірно може')
AT_WORD = re.compile(r'повз|через|в районі|у районі|в р-ні|біля|поблизу|над |висот|пролет|пролiт|пролітає|кружля')
OBS_CACHE = os.path.join(TMP, 'paths_obs.json')

# ---------- тип цели в строке ----------
KIND_RX = [
    ('kab', re.compile(r'(?<![а-яіїєґ])(каб|каби|кабы|кар/каб)(?![а-яіїєґ])|авіабомб|авиабомб|умпк|💣')),
    ('b', re.compile(r'балісти|баллисти|☄|(?<![а-яіїєґ])бр(?![а-яіїєґ])|кинджал|кинжал|аеробаліст|аэробаллист|циркон|kn-23|кн-23|іскандер-м|искандер-м')),
    ('l', re.compile(r'бандерол|мгкр|(?<![а-яіїєґ])мкр(?![а-яіїєґ])|s-8000|с-8000|баражуюч')),
    ('j', re.compile(r'реактив|🏍|рбпла|реактбпла|гера[нн]\w*[\s-]*[35](?!\d)')),
    ('m', re.compile(r'ракет|(?<![а-яіїєґ])кр(?![а-яіїєґ])|крилат|крылат|калібр|калибр|[хx]-\d|онікс|оникс|(?<![а-яіїєґ])кар(?![а-яіїєґ])|іскандер-к|искандер-к|швидкісн')),
    ('d', re.compile(r'бпла|бпла|шахед|шахід|шахид|мопед|дрон|герань|гербер|🛵|безпілотн|беспилотн')),
]
SKIP_SEG = re.compile(r'відбій|отбой|(?<![а-яіїєґ])чисто|реклам|донат|збір на|сбор на|розіграш|орлан|ланцет|фпв|fpv|'
                      r'артилер|артобстр|мінометн|минометн|ту-95|ту-22|ту-160|су-3\d|міг-31|миг-31|тактичн|тактическ', re.I)
IMPACT = re.compile(r'вибух|взрыв|приліт|прилет|влучан|попадан|спуск|мінус|минус|збит|сбит|знищ|уничтож|уламк|обломк')

# ---------- роль места: где цель сейчас (at) / куда летит (to) ----------
AT_M = (r'повз|через|в районі|у районі|в р-ні|у р-ні|р-н|р-ні|районі|біля|поблизу|над|в межах|у межах|'
        r'мимо|в районе|около|возле|под|пролет\w*|пролiт\w*|пролітає|пролетів|кружля\w*|крут\w*|'
        r'західніше|східніше|північніше|південніше|западне\w*|западней|восточне\w*|восточней|северне\w*|севернее|южнее|'
        r'на захід від|на схід від|на північ від|на південь від|к западу от|к востоку от|к северу от|к югу от|'
        r'з|із|зі|від|с|со|от|со стороны|з боку|в|у|во')
TO_M = (r'курс\w*\s+на|курс\w*|у напрямку|в напрямку|напрямок|напрямку|в направлении|направлени\w*|у бік|в бік|у сторону|'
        r'в сторону|на|до|к|вектор:?|➡️?|→|->|ціль|цель|летить на|летит на|летять на|летят на|подлета\w*|підліта\w*|заход\w* на')
ROLE_RX = re.compile(r'(?<![а-яіїєґa-z])(?:(?P<to>' + TO_M + r')|(?P<at>' + AT_M + r'))\s*[:.]?\s*'
                     r'(?:(?:н\.\s?п\.|нп|м\.|с\.|смт\.?|сел\.|г\.|пгт\.?)\s*)?(?:[«"]?[а-яіїєґё\'’ʼ-]+[»"]?\s*(?:/|,|\sта\s|\sі\s|\sи\s)\s*)*[«"]?$')

# ---------- курс ----------
_DIR_ADJ = [('північно-західн', 315), ('північно-східн', 45), ('південно-західн', 225), ('південно-східн', 135),
            ('северо-западн', 315), ('северо-восточн', 45), ('юго-западн', 225), ('юго-восточн', 135),
            ('північн', 0), ('південн', 180), ('західн', 270), ('східн', 90),
            ('северн', 0), ('южн', 180), ('западн', 270), ('восточн', 90)]
_DIR_NOUN = [('північний захід', 315), ('північний схід', 45), ('південний захід', 225), ('південний схід', 135),
             ('северо-запад', 315), ('северо-восток', 45), ('юго-запад', 225), ('юго-восток', 135),
             ('захід', 270), ('схід', 90), ('північ', 0), ('південь', 180), ('запад', 270), ('восток', 90), ('север', 0), ('юг', 180)]
ADJ_ALT = '|'.join(a for a, _ in _DIR_ADJ)
NOUN_ALT = '|'.join(a for a, _ in _DIR_NOUN)
HEAD_RX = [
    re.compile(r'курс\w*\W{1,3}(' + ADJ_ALT + r')'),
    re.compile(r'(' + ADJ_ALT + r')\w*\W{1,3}(курс|напрям|направл|вектор)'),
    re.compile(r'(?<![а-яіїєґ])на\s+(' + NOUN_ALT + r')(?![а-яіїєґ])'),
]
DIR_VAL = dict(_DIR_ADJ + _DIR_NOUN)

# ---------- районы пуска баллистики (РФ, ТОТ) ----------
LAUNCH = [
    (re.compile(r'брянськ|брянск'), 'Брянська обл.', 53.24, 34.36),
    (re.compile(r'курськ|курск|курщин'), 'Курська обл.', 51.73, 36.19),
    (re.compile(r'(бєлгород|белгород|білгород)(?!-дн|\s*-?\s*дн)'), 'Бєлгородська обл.', 50.60, 36.59),
    (re.compile(r'воронеж'), 'Воронезька обл.', 51.66, 39.20),
    (re.compile(r'ростов'), 'Ростовська обл.', 47.23, 39.72),
    (re.compile(r'таганрог'), 'Таганрог', 47.21, 38.94),
    (re.compile(r'міллерово|миллерово'), 'Міллерово', 48.92, 40.40),
    (re.compile(r'(?<![а-яіїєґ])(орл|орел|орьол|орел)'), 'Орловська обл.', 52.97, 36.07),
    (re.compile(r'(?<![а-яіїєґ])(крим|крым)'), 'Крим', 45.35, 34.0),
    (re.compile(r'тот донеч|тот донец|окупованого донецьк|з донецьк|с донецк|донецьку обл'), 'ТОТ Донеччини', 48.0, 37.8),
    (re.compile(r'тот запор|окупованої запор|з токмак|с токмак|бердянськ|бердянск|мелітопол|мелитопол'), 'ТОТ Запоріжжя', 46.85, 35.37),
    (re.compile(r'тот луган|луганськ|луганск'), 'ТОТ Луганщини', 48.57, 39.31),
]
LAUNCH_ONLY = re.compile(r'загроз|угроз|пуск|запуск|з |із |с |от ')


def km(a, b, c, d):
    t = math.pi / 180
    x = math.sin((c - a) * t / 2) ** 2 + math.cos(a * t) * math.cos(c * t) * math.sin((d - b) * t / 2) ** 2
    return 12742 * math.asin(math.sqrt(min(1, x)))


def brg(a, b, c, d):
    t = math.pi / 180
    y = math.sin((d - b) * t) * math.cos(c * t)
    x = math.cos(a * t) * math.sin(c * t) - math.sin(a * t) * math.cos(c * t) * math.cos((d - b) * t)
    return (math.atan2(y, x) / t) % 360


def angdiff(a, b):
    return abs((a - b + 180) % 360 - 180)


def seg_kind(s):
    for k, rx in KIND_RX:
        if rx.search(s):
            return k
    return None


def heading(s):
    s = re.sub(r'(північно|південно|северо|юго)[\s-]?', r'\1-', s)
    for rx in HEAD_RX:
        m = rx.search(s)
        if m:
            return DIR_VAL[m.group(1)]
    return None


def split_segments(text):
    parts = re.split(r'\n+|;|\s{2,}|(?<=[.!])\s+(?=[А-ЯІЇЄҐ0-9🛵🏍🚀☄⚠❗💥])', text)
    return [p.strip(' -—•▪️🔹🅿️\t') for p in parts if p and len(p.strip()) > 3]


def role(seg_low, pos):
    m = ROLE_RX.search(seg_low[max(0, pos - 45):pos])
    if not m:
        return None
    return 'to' if m.group('to') else 'at'


def parse_posts():
    posts = {}
    hist = glob.glob(os.path.join(TMP, 'hist', '*.jsonl')) + glob.glob(os.path.join(TMP, 'hist_reg', '*.jsonl'))
    for path in hist + glob.glob(os.path.join(TMP, 'tg', '*.jsonl')):
        ch = os.path.basename(path).rsplit('_', 1)[0] if path in hist else os.path.basename(path)[:-6]
        if ch not in ALL_CHANNELS:
            continue
        for line in open(path, encoding='utf-8'):
            if line.strip():
                p = json.loads(line)
                if p['dt'] >= '2022-02-24' and p['text']:
                    posts[(ch, p['id'])] = p
    print('posts', len(posts), flush=True)
    tg = TextGeo()
    tg.learn_common([p['text'] for p in posts.values()])
    obs = []  # [night, мин_от_начала_ночи, канал/id, сегмент№, группа, роль, lat, lon, имя, курс, цель_lat, цель_lon, launch, impact]
    for n, ((ch, pid), p) in enumerate(sorted(posts.items(), key=lambda kv: kv[1]['dt'])):
        if n % 20000 == 0:
            print(' parsed', n, len(obs), flush=True)
        k = kyiv(datetime.fromisoformat(p['dt']))
        night = (k + timedelta(hours=12)).date().isoformat()
        start = datetime.fromisoformat(night + 'T12:00').replace(tzinfo=k.tzinfo) - timedelta(days=1)
        minute = round((k - start).total_seconds() / 60, 1)
        src = f'{ch}/{pid}'
        post_obs = tg.oblasts_in(p['text']) | set(REGIONAL.get(ch, []))
        kind_prev = None
        for si, seg in enumerate(split_segments(p['text'])):
            sl = low(seg)
            if ch not in CHANNELS:
                if len(seg) > 160 or FOOTER.search(seg) or NOT_MOVE.search(sl):
                    continue  # новость, подпись канала («⚪ Рівне Головне | Наш чат»), объявление тревоги
                if ch not in PURE_MONITORS and not (MOVE.search(sl) or AT_WORD.search(sl)):
                    continue  # новостной канал: без «повз/курс/в районі» это не мониторинг («вибух на полігоні»)
            if SKIP_SEG.search(sl):
                kind_prev = None
                continue
            kind = seg_kind(sl) or kind_prev
            if not kind and ch in REGIONAL and (MOVE.search(sl) or ch in PURE_MONITORS):
                kind = 'd'
            kind_prev = kind
            if not kind or kind == 'kab':
                continue
            launch = None
            if kind == 'b':
                for rx, nm, la, lo in LAUNCH:
                    if rx.search(sl):
                        launch = [nm, la, lo]
                        break
            places = tg.find(seg, post_obs)
            if not places and not launch:
                continue
            hd = heading(sl)
            imp = 1 if IMPACT.search(sl) else 0
            roles = []
            sr = seg.lower()  # позиции — по исходному тексту (low() выбрасывает апострофы)
            first = min((tg.pos.get(pl[0], 0) for pl in places), default=99)
            bare_list = (first < 3 and ch in REGIONAL) or ch in PURE_MONITORS  # «🟥 Оліївка, Троковичі, Вереси» — где сейчас
            for pl in places:
                pos = tg.pos.get(pl[0], 0)
                r = role(sr, pos)
                if r is None:  # «Київ — спуск балістики», «Кременчук — ракети вздовж міста»
                    r = 'at' if imp or pos < 3 or bare_list else 'to'
                roles.append((pos, r, pl))
            roles.sort(key=lambda x: x[0])
            tgt = next((pl for _, r, pl in roles if r == 'to'), None)
            ats = [(pos, pl) for pos, r, pl in roles if r == 'at']
            # «через Бровари/Київ/Бориспіль» — варианты, а не положение: берём, только если места рядом
            if len(ats) > 1 and '/' in seg:
                la = sum(pl[2] for _, pl in ats) / len(ats)
                lo = sum(pl[3] for _, pl in ats) / len(ats)
                if max(km(la, lo, pl[2], pl[3]) for _, pl in ats) > 20:
                    ats = []
            for _, pl in ats:
                obs.append([night, minute, src, si, kind, 'at', pl[2], pl[3], pl[1], hd,
                            tgt[2] if tgt else None, tgt[3] if tgt else None, launch, imp])
            if kind == 'b' and (tgt or launch) and not ats:
                obs.append([night, minute, src, si, kind, 'to', tgt[2] if tgt else None, tgt[3] if tgt else None,
                            tgt[1] if tgt else None, hd, None, None, launch, imp])
    print('observations', len(obs), flush=True)
    json.dump(obs, open(OBS_CACHE, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    return obs


# ---------- склейка в треки ----------
VMAX = {'d': 200, 'j': 400, 'l': 450, 'm': 800}
GAP = {'d': 90, 'j': 50, 'l': 50, 'm': 45}
MAXSEG = {'d': 90, 'j': 150, 'l': 150, 'm': 200}  # км: дальше без промежуточных точек — уже догадка
MAXANG = 55
SLACK = 15     # км: неточность места («повз Х» — не над самим Х)
LAG = 3        # мин: посты выходят с разной задержкой


class Track:
    __slots__ = ('g', 'pts', 'last_t', 'last_src', 'hd', 'tgt')

    def __init__(self, g, o):
        self.g = g
        self.pts = [o]
        self.last_t = o['t']
        self.last_src = o['src']
        self.hd = o['hd']
        self.tgt = o['tgt']

    def expected(self, d=0):
        """Ожидаемый курс к точке на расстоянии d. За названной целью курс уже неизвестен."""
        a = self.pts[-1]
        if self.tgt:
            dt_ = km(a['lat'], a['lon'], *self.tgt)
            if dt_ > 15:
                return brg(a['lat'], a['lon'], *self.tgt) if d <= dt_ + 40 else 'past'
        if self.hd is not None:
            return self.hd
        if len(self.pts) >= 2:
            p = self.pts[-2]
            if km(p['lat'], p['lon'], a['lat'], a['lon']) > 10:
                return brg(p['lat'], p['lon'], a['lat'], a['lon'])
        return None


def link_night(obs, g):
    """Наблюдения одной ночи и группы (по времени) -> треки."""
    tracks, open_ = [], []
    for o in obs:
        open_ = [tr for tr in open_ if o['t'] - tr.last_t <= GAP[g]]
        cands = []
        for tr in open_:
            if tr.last_src == o['src']:
                continue  # строки одного поста — разные группы
            a = tr.pts[-1]
            dt = o['t'] - tr.last_t
            d = km(a['lat'], a['lon'], o['lat'], o['lon'])
            if d < 12 and dt <= 20:
                cands.append((0.3 * d / 12 + 0.2 * dt / 20, 'dup', tr))
                continue
            if dt < 1:
                continue
            reach = VMAX[g] * (dt + LAG) / 60 + SLACK
            if d > reach or d > MAXSEG[g]:
                continue
            b = brg(a['lat'], a['lon'], o['lat'], o['lon'])
            exp = tr.expected(d)
            score = 0.5 * d / reach + 0.3 * dt / GAP[g]
            if exp == 'past':
                continue  # далеко за названной целью — куда свернул, неизвестно
            if exp is None:
                if d > 60:
                    continue  # курса не знаем — дальний скачок не склеиваем
                score += 0.6
            else:
                ang = angdiff(b, exp)
                if ang > MAXANG:
                    continue
                score += ang / MAXANG
            if o['hd'] is not None and angdiff(b, o['hd']) > 80:
                continue  # новая точка летит не туда, откуда пришла бы
            cands.append((score, 'add', tr))
        cands.sort(key=lambda c: c[0])
        best = cands[0] if cands and cands[0][0] <= 1.5 else None
        if best and best[1] == 'add' and len(cands) > 1 and cands[1][1] == 'add' and cands[1][0] - best[0] < 0.3:
            a1, a2 = best[2].pts[-1], cands[1][2].pts[-1]
            if km(a1['lat'], a1['lon'], a2['lat'], a2['lon']) > 30:
                best = None  # два равных продолжения из разных мест — не угадываем
        if best is None:
            tr = Track(g, o)
            tracks.append(tr)
            open_.append(tr)
            continue
        tr = best[2]
        tr.last_t = o['t']
        tr.last_src = o['src']
        if best[1] == 'add':
            tr.pts.append(o)
            tr.hd, tr.tgt = o['hd'], o['tgt']  # старый курс и цель уже пройдены
        else:  # тот же борт в другом канале — дополняем курс и цель
            tr.hd = o['hd'] if o['hd'] is not None else tr.hd
            tr.tgt = o['tgt'] or tr.tgt
    return tracks


def ballistic(obs):
    """Баллистика: прямая от района пуска до цели."""
    out = []
    last_launch = None  # (t, launch)
    for o in obs:
        if o['launch']:
            last_launch = (o['t'], o['launch'])
        if o['lat'] is None:
            continue
        ln = o['launch'] or (last_launch[1] if last_launch and o['t'] - last_launch[0] <= 20 else None)
        if not ln:
            continue
        out.append({'g': 'b', 'pts': [{'t': o['t'], 'lat': ln[1], 'lon': ln[2], 'n': ln[0], 'src': o['src']}, o]})
    # одна цель за ночь из одного района — одна линия
    seen, res = set(), []
    for tr in out:
        k = (tr['pts'][0]['n'], round(tr['pts'][1]['lat'], 1), round(tr['pts'][1]['lon'], 1))
        if k not in seen:
            seen.add(k)
            res.append(tr)
    return res


def build_tracks(raw):
    by = defaultdict(list)
    for r in raw:
        night, t, src, si, kind, rl, la, lo, nm, hd, tla, tlo, launch, imp = r
        o = {'t': t, 'src': src, 'lat': la, 'lon': lo, 'n': nm, 'hd': hd,
             'tgt': (tla, tlo) if tla is not None else None, 'launch': launch, 'imp': imp}
        by[(night, kind)].append(o)
    res = []
    for (night, g), obs in sorted(by.items()):
        obs.sort(key=lambda o: (o['t'], o['src']))
        if g == 'b':
            trs = ballistic(obs)
        else:
            trs = [{'g': g, 'pts': tr.pts} for tr in link_night([o for o in obs if o['lat'] is not None], g)]
        for tr in trs:
            pts = tr['pts']
            if len(pts) < 2:
                continue
            length = sum(km(pts[i]['lat'], pts[i]['lon'], pts[i + 1]['lat'], pts[i + 1]['lon']) for i in range(len(pts) - 1))
            if length < 15:
                continue
            res.append({'night': night, 'g': tr['g'], 'pts': pts, 'km': length})
    return res


def write_site(tracks):
    out_dir = os.path.join(ROOT, 'data', 'paths')
    os.makedirs(out_dir, exist_ok=True)
    years = sorted({t['night'][:4] for t in tracks})
    ch_idx = {c: i for i, c in enumerate(ALL_CHANNELS)}
    index = {'years': [], 'groups': {'d': 'дроны «Шахед»', 'j': 'реактивные дроны', 'l': '«Бандероли»',
                                     'm': 'крылатые и др. ракеты', 'b': 'баллистика'}, 'channels': ALL_CHANNELS}
    for y in years:
        ts = [t for t in tracks if t['night'][:4] == y]
        names, nidx = [], {}
        nights = sorted({t['night'] for t in ts})
        ni = {n: i for i, n in enumerate(nights)}

        def name_i(n):
            if n not in nidx:
                nidx[n] = len(names)
                names.append(n)
            return nidx[n]
        rows = []
        for t in ts:
            # [группа, ночь, [lat, lon, имя, мин, канал, id], ...]
            pts = []
            for p in t['pts']:
                ch, pid = p['src'].split('/')
                pts += [round(p['lat'], 3), round(p['lon'], 3), name_i(p['n'] or ''), int(p['t']), ch_idx[ch], int(pid)]
            rows.append([t['g'], ni[t['night']], pts])
        path = os.path.join(out_dir, f'{y}.json')
        json.dump({'year': y, 'nights': nights, 'names': names, 't': rows}, open(path, 'w', encoding='utf-8'),
                  ensure_ascii=False, separators=(',', ':'))
        cnt = defaultdict(int)
        for t in ts:
            cnt[t['g']] += 1
        index['years'].append({'y': y, 'tracks': len(ts), 'nights': len(nights), 'by': cnt, 'size': os.path.getsize(path)})
        print(y, len(ts), dict(cnt), 'nights', len(nights), 'size', os.path.getsize(path), flush=True)
    index['to'] = max(t['night'] for t in tracks)
    json.dump(index, open(os.path.join(out_dir, 'index.json'), 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))


def main():
    if '--reparse' in sys.argv or not os.path.exists(OBS_CACHE):
        raw = parse_posts()
    else:
        raw = json.load(open(OBS_CACHE, encoding='utf-8'))
    tracks = build_tracks(raw)
    json.dump(tracks, open(os.path.join(TMP, 'paths_tracks.json'), 'w', encoding='utf-8'), ensure_ascii=False)
    print('tracks', len(tracks), flush=True)
    if '--no-site' not in sys.argv:
        write_site(tracks)


if __name__ == '__main__':
    main()
