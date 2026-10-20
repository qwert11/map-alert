# Карта тревог и атак

https://qwert11.github.io/map-alert/

Три режима: «Прилёты 2022–26» (по умолчанию) — где по городам и сёлам были удары, по годам, с проверкой
радиуса 10/25 км вокруг любого места; «По ночам» и «30 ночей» — траектории атак последнего месяца.

Ночь за ночью: где была воздушная тревога, откуда и куда летели ракеты и дроны,
где были прилёты. Таймлайн ночи проигрывается: области загораются по тревогам,
треки ползут по времени сообщений мониторов.

## Откуда данные

| Слой | Источник |
|---|---|
| Прилёты по населённым пунктам с 2022 | [VIINA](https://github.com/zhukovyuri/VIINA) — заголовки СМИ, привязанные к месту; каждый проверен на название места, слово про удар и область (`scripts/build_strikes.py`) |
| Тревоги по областям в ночи атак | архив eTryvoga, [датасет Vadimkin](https://github.com/Vadimkin/ukrainian-air-raid-sirens-dataset), сверенный с официальным |
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
4. `scripts/build_alerts.py <с даты>` → `data/alerts.json` (через `scripts/alerts_clean.py`: eTryvoga теряет отбои,
   тревоги дольше 6 ч сверяются с официальным архивом)
5. `scripts/build_site.py` — геокодирование по GeoNames, чистка → `data/nights/D.json`, `data/index.json`
6. `scripts/build_strikes.py` — прилёты за всю войну из VIINA → `data/strikes.json`

Границы областей — geoBoundaries ADM1 (`scripts/build_geo.py` → `data/oblasts.geojson`).
Перезапустить извлечение одной ночи: удалить `data/extract/D.json` и запустить шаг 3 с этой датой.
