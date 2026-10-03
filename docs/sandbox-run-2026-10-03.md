# Прогон в песочнице — 2026-10-03

Что доказывает этот файл: образ собирается, контейнер отвечает, тесты
зелёные. Он **не** доказывает, что модель совпадает с гидропостами:
параметры с меткой `[В]` не откалиброваны (см. README).

## Сборка

```sh
docker build --secret id=pipca,src=/root/.ccr/ca-bundle.crt \
  -t leonidy431/tides:dev .
docker build --secret id=pipca,src=/root/.ccr/ca-bundle.crt \
  --target test -t leonidy431/tides:test .
docker images leonidy431/tides
```

Секрет `pipca` нужен только песочнице (прокси с подменой TLS); в образ
сертификат не попадает.

```text
leonidy431/tides:test  a145e960f458  disk 219MB
leonidy431/tides:dev  62118a4aeb8d  disk 210MB
content size (docker image inspect .Size): leonidy431/tides:dev 51251111 B; base python:3.12-slim 46237854 B
```

## Тесты (в контейнере)

```sh
docker run --rm leonidy431/tides:test
```

```text
21 passed, 1 warning in 0.86s
```

(Предупреждение — DeprecationWarning библиотеки starlette, не наше.)

## Запуск и запросы

```sh
docker run -d --name tides-dev -p 9050:9050 leonidy431/tides:dev
```

Длинные массивы урезаны: показаны первые 3 и последняя строка ряда и
3 параметра из `params_used`; сводка min/max посчитана по полному ряду.

### register_service

```sh
curl -s http://localhost:9050/register_service
```

```json
{
 "name": "Tides",
 "description": "Приливы, нагоны и суточный цикл таяния: Иссык-Куль, реки бассейна и Каспий. Honest levels, every number tagged.",
 "icon": "mdi-waves",
 "company": "Leonidy431",
 "version": "0.1.0",
 "webpage": "https://github.com/Leonidy431/tides",
 "api": "/docs",
 "works_in_relative_paths": true
}
```

### sites

```sh
curl -s http://localhost:9050/v1.0/sites
```

```json
{
 "sites": [
  {
   "id": "issyk_kul_cholpon_ata",
   "kind": "lake",
   "name_ru": "Иссык-Куль, водомерный пост Чолпон-Ата",
   "name_en": "Issyk-Kul lake gauge, Cholpon-Ata",
   "lat": 42.645,
   "lon": 77.08,
   "components": {
    "astro": "m",
    "surge": "m",
    "total": "m"
   }
  },
  {
   "id": "karakol_river",
   "kind": "river_melt",
   "name_ru": "р. Каракол (выход из ущелья)",
   "name_en": "Karakol river at the gorge outlet",
   "lat": 42.47,
   "lon": 78.43,
   "components": {
    "astro": "m^3/s",
    "base": "m^3/s",
    "melt": "m^3/s",
    "total": "m^3/s"
   }
  },
  {
   "id": "jergalan_river",
   "kind": "river_melt",
   "name_ru": "р. Джергалан (Жыргалан)",
   "name_en": "Jergalan river",
   "lat": 42.57,
   "lon": 78.93,
   "components": {
    "astro": "m^3/s",
    "base": "m^3/s",
    "melt": "m^3/s",
    "total": "m^3/s"
   }
  },
  "... 11 sites total"
 ]
}
```

### Иссык-Куль, ветер 15 м/с с юга

```sh
curl -s 'http://localhost:9050/v1.0/level?site=issyk_kul_cholpon_ata&start=2026-07-15T00:00:00Z&hours=24&step_min=60&wind_speed=15&wind_from=180'
```

```json
{
 "site": "issyk_kul_cholpon_ata",
 "warnings": [],
 "kind": "lake",
 "name_ru": "Иссык-Куль, водомерный пост Чолпон-Ата",
 "lat": 42.645,
 "lon": 77.08,
 "time": "UTC",
 "start": "2026-07-15T00:00:00Z",
 "step_min": 60.0,
 "wind": {
  "speed_m_s": 15.0,
  "from_deg": 180.0,
  "note": "steady setup for this wind; not a forecast"
 },
 "units": {
  "astro": "m",
  "surge": "m",
  "total": "m"
 },
 "total_meaning": "level anomaly about mean_level, m",
 "params_used": {
  "eq_amp_M2": {
   "value": 0.24233,
   "unit": "m",
   "tag": "[П] equilibrium tide amplitude, Cartwright & Tayler 1971 (latitude factor cos^2 lat)"
  },
  "eq_amp_S2": {
   "value": 0.11274,
   "unit": "m",
   "tag": "[П] equilibrium tide amplitude, Cartwright & Tayler 1971 (latitude factor cos^2 lat)"
  },
  "eq_amp_K1": {
   "value": 0.14156,
   "unit": "m",
   "tag": "[П] equilibrium tide amplitude, Cartwright & Tayler 1971 (latitude factor sin 2 lat)"
  },
  "...": "16 tagged parameters in full response"
 }
}

series (25 rows):
{"t": "2026-07-15T00:00:00Z", "astro": 0.00197, "surge": 0.007847, "total": 0.009816}
{"t": "2026-07-15T01:00:00Z", "astro": 0.001514, "surge": 0.007847, "total": 0.009361}
{"t": "2026-07-15T02:00:00Z", "astro": 0.000794, "surge": 0.007847, "total": 0.00864}
... 21 rows omitted ...
{"t": "2026-07-16T00:00:00Z", "astro": 0.001924, "surge": 0.007847, "total": 0.00977}

summary of the full series:
astro: min -0.00157 at 2026-07-15T17:00:00Z, max 0.00197 at 2026-07-15T00:00:00Z
surge: min 0.007847 at 2026-07-15T00:00:00Z, max 0.007847 at 2026-07-15T00:00:00Z
total: min 0.006276 at 2026-07-15T17:00:00Z, max 0.009816 at 2026-07-15T00:00:00Z
```

### р. Каракол, июльские сутки

```sh
curl -s 'http://localhost:9050/v1.0/level?site=karakol_river&start=2026-07-15T00:00:00Z&hours=24&step_min=60'
```

```json
{
 "site": "karakol_river",
 "warnings": [],
 "kind": "river_melt",
 "name_ru": "р. Каракол (выход из ущелья)",
 "lat": 42.47,
 "lon": 78.43,
 "time": "UTC",
 "start": "2026-07-15T00:00:00Z",
 "step_min": 60.0,
 "wind": {
  "speed_m_s": 0.0,
  "from_deg": 0.0,
  "note": "steady setup for this wind; not a forecast"
 },
 "units": {
  "astro": "m^3/s",
  "base": "m^3/s",
  "melt": "m^3/s",
  "total": "m^3/s"
 },
 "total_meaning": "discharge, m^3/s (stage needs a rating curve: unknown)",
 "params_used": {
  "astro": {
   "value": 0.0,
   "unit": "m^3/s",
   "tag": "[П] a river that does not reach the ocean has no tide; the mm-scale tide of Issyk-Kul does not propagate upstream against the current"
  },
  "station_elevation": {
   "value": 1716,
   "unit": "m a.s.l.",
   "tag": "[В] approximate station elevation"
  },
  "t_mean_monthly": {
   "value": [
    -6.4,
    -5.0,
    1.0,
    8.3,
    12.3,
    15.6,
    17.8,
    17.3,
    12.9,
    6.6,
    -0.3,
    -4.6
   ],
   "unit": "degC, Jan..Dec",
   "tag": "[В] approximate climatology, order of magnitude; replace with station normals"
  },
  "...": "12 tagged parameters in full response"
 }
}

series (25 rows):
{"t": "2026-07-15T00:00:00Z", "astro": 0.0, "base": 4.453351, "melt": 1.150097, "total": 5.603448}
{"t": "2026-07-15T01:00:00Z", "astro": 0.0, "base": 4.454036, "melt": 0.824081, "total": 5.278116}
{"t": "2026-07-15T02:00:00Z", "astro": 0.0, "base": 4.45472, "melt": 0.59048, "total": 5.0452}
... 21 rows omitted ...
{"t": "2026-07-16T00:00:00Z", "astro": 0.0, "base": 4.469779, "melt": 1.169829, "total": 5.639607}

summary of the full series:
astro: min 0.0 at 2026-07-15T00:00:00Z, max 0.0 at 2026-07-15T00:00:00Z
base: min 4.453351 at 2026-07-15T00:00:00Z, max 4.469779 at 2026-07-16T00:00:00Z
melt: min 0.221774 at 2026-07-15T05:00:00Z, max 7.274934 at 2026-07-15T15:00:00Z
total: min 4.678547 at 2026-07-15T05:00:00Z, max 11.738553 at 2026-07-15T15:00:00Z
```

### Северный Каспий, ЮВ ветер 15 м/с

```sh
curl -s 'http://localhost:9050/v1.0/level?site=caspian_north_volga_delta&start=2026-07-15T00:00:00Z&hours=24&step_min=60&wind_speed=15&wind_from=135'
```

```json
{
 "site": "caspian_north_volga_delta",
 "warnings": [
  "linear setup formula out of range: |surge| 2.27 m > 0.3 * depth 4.0 m; the formula overestimates because the water column deepens as it piles up"
 ],
 "kind": "sea",
 "name_ru": "Северный Каспий, взморье дельты Волги",
 "lat": 45.55,
 "lon": 47.95,
 "time": "UTC",
 "start": "2026-07-15T00:00:00Z",
 "step_min": 60.0,
 "wind": {
  "speed_m_s": 15.0,
  "from_deg": 135.0,
  "note": "steady setup for this wind; not a forecast"
 },
 "units": {
  "astro": "m",
  "surge": "m",
  "total": "m"
 },
 "total_meaning": "level anomaly about mean_level, m",
 "params_used": {
  "astro_M2_amp": {
   "value": 0.005,
   "unit": "m",
   "tag": "[В] shallow north Caspian damps the already small tide; order of magnitude"
  },
  "astro_S2_amp": {
   "value": 0.002,
   "unit": "m",
   "tag": "[В] order of magnitude"
  },
  "astro_K1_amp": {
   "value": 0.004,
   "unit": "m",
   "tag": "[В] order of magnitude"
  },
  "...": "14 tagged parameters in full response"
 }
}

series (25 rows):
{"t": "2026-07-15T00:00:00Z", "astro": 0.004261, "surge": 2.272245, "total": 2.276506}
{"t": "2026-07-15T01:00:00Z", "astro": -0.00047, "surge": 2.272245, "total": 2.271775}
{"t": "2026-07-15T02:00:00Z", "astro": -0.004513, "surge": 2.272245, "total": 2.267733}
... 21 rows omitted ...
{"t": "2026-07-16T00:00:00Z", "astro": 0.006311, "surge": 2.272245, "total": 2.278556}

summary of the full series:
astro: min -0.007917 at 2026-07-15T04:00:00Z, max 0.012 at 2026-07-15T21:00:00Z
surge: min 2.272245 at 2026-07-15T00:00:00Z, max 2.272245 at 2026-07-15T00:00:00Z
total: min 2.264328 at 2026-07-15T04:00:00Z, max 2.284245 at 2026-07-15T21:00:00Z
```

### explain: р. Каракол

```sh
curl -s 'http://localhost:9050/v1.0/explain?site=karakol_river'
```

```text
р. Каракол (выход из ущелья)

Приливов в этой реке нет. Река течёт с гор в бессточное озеро, а крошечный прилив озера (миллиметры) против течения не поднимается.
То, что похоже на «прилив и отлив», — суточный цикл таяния ледников и снега: утром вода низкая, к вечеру растёт. Сильнее всего в июне–августе, зимой почти исчезает.
Расчёт: градусо-дни (DDF = 7 мм/(°C·сут) [В]), температура станции поднята по градиенту 6,5 К/км до высоты таяния, затем запаздывание и линейный резервуар [В].
Модельный июльский день: пик талой воды ≈ 20.5 ч по местному солнечному времени (+7.3 м³/с), минимум +0.2 м³/с.
Числа — порядок величины, не калибровка по гидропосту. Уровень воды (м) по расходу не считается: кривая расходов поста неизвестна.

Все параметры и их метки [П]/[В] — в /v1.0/level.
```

