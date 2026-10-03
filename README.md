# tides — приливы, нагоны и «приливы» рек: Иссык-Куль и Каспий

Расширение BlueOS (Docker) для ROV и для игры **ludus**. Считает уровень
воды и его составляющие для поста на Иссык-Куле, пяти рек бассейна
(Каракол, Джергалан, Тюп, Чон-Кызыл-Суу, Чу) и Каспия (Северный у дельты
Волги, Махачкала, Баку, Волга у Астрахани, Урал у Атырау).

**Главное — честная физика.** Каждое число в `data/sites.json` помечено:
`[П]` — из источника (указан), `[В]` — оценка автора модуля (порядок
величины, без калибровки по постам), `неизвестно` — значение не известно.
Случайности нет: те же входы дают тот же ответ. Время — UTC, единицы — СИ.

## Что модуль считает

| Вода | Что есть на самом деле | Модель |
|---|---|---|
| Иссык-Куль | бессточное озеро; астрономический прилив — **миллиметры** (у Чолпон-Аты ≈ 2 мм); сейши — сантиметры (от ветра) | статический наклон зеркала по равновесному приливу M2, S2, K1, O1 (Cartwright & Tayler 1971, γ2 = 0,69), объём сохраняется; ветровой нагон |
| Реки у Иссык-Куля | **приливов нет.** «Прилив/отлив» — суточный цикл таяния ледников: утром мало воды, к вечеру много; сильнее всего в июне–августе; весной — половодье | градусо-дни (DDF льда 7 мм/(°C·сут) [В], диапазон Hock 2003 [П]), суточный ход температуры, градиент 6,5 К/км, запаздывание + линейный резервуар; результат — **расход, м³/с** |
| Каспий | астрономический прилив — **сантиметры** [В]; главное — ветровые **нагоны и сгоны** (на мелком Северном Каспии — метры), сейши | гармоники M2, S2, K1, O1 с малыми амплитудами [В]; нагон η = C_d·ρ_a·U²·L/(ρ_w·g·h) для разгона L и глубины h |
| Волга, Урал | приливов нет; уровень задаёт весенне-летнее половодье и (у Атырау) доля морского нагона | сезонная волна половодья [В] + доля нагона [В] |

### Чего модуль НЕ делает (честно)

- Не измеряет — только считает. Датчиков не читает.
- Не прогнозирует ветер: нагон считается для ветра, который задаёте вы
  (`wind_speed`, `wind_from`), как установившийся.
- Не даёт уровень реки в метрах: кривая расходов постов неизвестна,
  поэтому для рек — расход.
- Сейши в ряд не входят (их размах зависит от ветровой истории; для
  Иссык-Куля дан только период по Мериану, ≈ 1,9 ч [В]).
- Гармонические постоянные Каспия и параметры рек не откалиброваны по
  гидропостам. Это порядок величины, помеченный `[В]`. Замените их
  данными постов — модель примет их без правки кода.
- Линейная формула нагона завышает результат, когда нагон сравним с
  глубиной; API в этом случае пишет предупреждение в `warnings`.

## API

| Запрос | Ответ |
|---|---|
| `GET /` | страница с графиком (чистый JS/SVG, без CDN) |
| `GET /register_service` | JSON для обнаружения сервиса BlueOS |
| `GET /v1.0/sites` | список мест |
| `GET /v1.0/level?site=…&start=…&hours=…&step_min=…&wind_speed=…&wind_from=…` | ряд: `astro`, `melt`/`base` или `surge`/`seasonal`, `total`; единицы; все параметры с метками (`params_used`) |
| `GET /v1.0/explain?site=…` | текст по-русски: почему здесь есть или нет прилива |
| `GET /docs` | OpenAPI |

`start` — ISO-8601 в UTC (`2026-07-15T00:00:00Z`); по умолчанию — начало
текущего часа. Не больше 5000 точек за запрос.

## Запуск

```sh
docker build -t leonidy431/tides:dev .
docker run --rm -p 9050:9050 leonidy431/tides:dev
curl http://localhost:9050/register_service
curl 'http://localhost:9050/v1.0/level?site=karakol_river&start=2026-07-15T00:00:00Z&hours=24&step_min=60'
```

Тесты в контейнере (стадия `test` в образ расширения не попадает):

```sh
docker build --target test -t leonidy431/tides:test .
docker run --rm leonidy431/tides:test
```

За прокси с подменой TLS передайте его сертификат секретом сборки
(в образ он не попадает):
`docker build --secret id=pipca,src=/path/to/ca.crt …`.

Без Docker: `pip install -r requirements-dev.txt && pytest -q &&
uvicorn app.main:app --port 9050`.

### BlueOS

1. **Extensions → Install from repository** (когда образ опубликован в
   Docker Hub как `leonidy431/tides`), либо
2. **Extensions → Installed → «+» (manual install)** с такими полями:

```json
{
  "identifier": "leonidy431.tides",
  "name": "Tides",
  "docker": "leonidy431/tides",
  "tag": "dev",
  "permissions": {
    "ExposedPorts": {"9050/tcp": {}},
    "HostConfig": {"PortBindings": {"9050/tcp": [{"HostPort": "9050"}]}}
  }
}
```

Образ должен быть доступен BlueOS: опубликован в реестре или загружен на
борт (`docker save` / `docker load`). Метки образа (`version`,
`permissions`, `authors`, `company`, `readme`, `type`, `tags`,
`requirements`) — по соглашениям расширений BlueOS.

## Как игра ludus использует модуль

Godot-сцена погружения (`godot/` в репо ludus) берёт уровень двумя путями:

- **живой:** `HTTPRequest` к `http://<адрес-BlueOS>:9050/v1.0/level?...`
  (на борту ROV);
- **запечённый:** `python -m app.bake --site issyk_kul_cholpon_ata --start
  2026-07-15T00:00:00Z --hours 72 --step-min 30 --out issyk.json` — файл
  той же формы, что ответ API, кладётся в данные игры. Игра без сети
  читает его тем же парсером.

Строки `explain` годятся для рассказчика и для ИИ-напарника: «В реке
приливов нет — это ледник тает к вечеру».

## Запуск в песочнице

Команды и ответы первого прогона: `docs/sandbox-run-2026-10-03.md`.

## Лицензия

MIT, см. `LICENSE`.

---

## English summary

**tides** is a BlueOS extension (FastAPI in Docker, port 9050) that
computes honest water levels for Issyk-Kul, five rivers of its basin and
the Caspian Sea. Issyk-Kul is endorheic: its astronomical tide is
millimetres (static mass-conserving tilt of the equilibrium tide). The
rivers have **no tide**; their daily "tide" is the glacier-melt cycle
(degree-day model, low in the morning, peak in the evening, strongest in
June–August), returned as discharge in m³/s. The Caspian has a
centimetre-scale astronomical tide (harmonic M2, S2, K1, O1 with
estimated amplitudes) and metre-scale wind surges in the shallow north
(steady setup η = C_d·ρ_a·U²·L/(ρ_w·g·h) for the wind you specify). The
Volga and Ural are modelled by their seasonal flood. Every parameter is
tagged `[П]` (source) or `[В]` (estimate) or unknown, everything is
deterministic, times are UTC and units SI. Endpoints: `/`,
`/register_service`, `/v1.0/sites`, `/v1.0/level`, `/v1.0/explain`,
`/docs`. Run: `docker build -t leonidy431/tides:dev . && docker run -p
9050:9050 leonidy431/tides:dev`.
