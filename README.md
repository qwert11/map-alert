# Карта тревог и атак

https://qwert11.github.io/map-alert/

Три режима: «По ночам» и «30 ночей» — атаки последнего месяца, «Вся война» — тревоги
по областям с февраля 2022 с фильтром по годам (часы под тревогой, помесячно, по времени суток).

Ночь за ночью: где была воздушная тревога, откуда и куда летели ракеты и дроны,
где были прилёты. Таймлайн ночи проигрывается: области загораются по тревогам,
треки ползут по времени сообщений мониторов.

## Откуда данные

| Слой | Источник |
|---|---|
| Тревоги по областям, вся война с 25.02.2022 | архив eTryvoga, [датасет Vadimkin](https://github.com/Vadimkin/ukrainian-air-raid-sirens-dataset) (`volunteer_data_uk.csv`), сверенный с официальным (`official_data_uk.csv`) |
| Траектории | посты [@kpszsu](https://t.me/s/kpszsu), [@monitorwarr](https://t.me/s/monitorwarr), [@war_monitor](https://t.me/s/war_monitor), [@vanek_nikolaev](https://t.me/s/vanek_nikolaev) |
| Сколько запущено/сбито | утренние сводки Повітряних сил |
| Прилёты | ОВА/МВА, ДСНС, СМИ — поиск по каждой ночи |

Треки восстанавливает языковая модель (`claude -p`) по ленте сообщений: склеивает
«КР на Житомирщині курсом на захід» → «КР повз Шепетівку» → … в одну линию.
Это схема по сообщениям, а не радарный трек. Координаты точек сверяются с GeoNames.
Прилёты — с точностью до населённого пункта или района, только опубликованное.

## Как обновить

```powershell
Start-Process powershell -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','update.ps1' -WindowStyle Hidden
```

Шаги (`update.ps1`):

1. `scripts/collect_tg.py <канал> <с даты>` — посты через `t.me/s/<канал>?before=<id>` → `_tmp/tg/*.jsonl`
2. `scripts/split_nights.py` — ночь на D = окно с 12:00 D−1 до 12:00 D по Киеву → `_tmp/nights/D.txt`
3. `scripts/run_extract.py [параллельно]` — `claude -p` по `scripts/extract_prompt.md` на каждую новую ночь → `data/extract/D.json`
4. `scripts/build_alerts.py <с даты>` → `data/alerts.json`; `scripts/build_history.py` → `data/history.json` (вся война).
   Оба берут архив через `scripts/alerts_clean.py`: eTryvoga теряет отбои, поэтому тревоги дольше 6 ч
   сверяются с официальным архивом и обрезаются, где он их не подтверждает
5. `scripts/build_site.py` — геокодирование по GeoNames, чистка → `data/nights/D.json`, `data/index.json`

Границы областей — geoBoundaries ADM1 (`scripts/build_geo.py` → `data/oblasts.geojson`).
Перезапустить извлечение одной ночи: удалить `data/extract/D.json` и запустить шаг 3 с этой датой.
