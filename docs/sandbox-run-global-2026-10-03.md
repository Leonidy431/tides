# Прогон v0.2 в песочнице (2026-10-03)

Образ `leonidy431/tides:dev` собран (`docker build --secret id=pipca,...`), запущен на сети хоста (чтобы достать прокси песочницы); ядро BlueOS 1.4.0 работает рядом.

```
$ curl http://127.0.0.1:9050/v1.0/here          # аппарата нет, GPS нет
{"detail":"BlueOS has no GPS fix (mavlink2rest empty or lat/lon zero); use /v1.0/point?lat=..&lon=.. or set BLUEOS_URL"} [503]
```

Живые вызовы трёх источников (12 часов от 2026-10-03T00Z):

| Точка | equilibrium | openmeteo | ioc | согласие |
|---|---|---|---|---|
| Брест (48,38; −4,49) | ok | ok | ok, мареограф `bres` в 0,7 км | `agree` по ioc+openmeteo, разброс 0,18 м |
| Перт (−32,05; 115,74) | ok | ok | ok, мареограф `hill` | `agree`, разброс 0,02 м |
| Иссык-Куль (42,65; 77,08) | ok (мм) | no_data (суша) | no_data (мареографа нет) | `theory_only` |

Позиция BlueOS: маршрут `GET /v1/mavlink/vehicles/1/components/1/messages/GLOBAL_POSITION_INT` у mavlink2rest отвечает нулевым шаблоном без аппарата; модуль считает его «нет фикса». Настоящий GPS в песочнице не проверен: аппарата нет.

Не проверено: установка из менеджера расширений, работа на аппарате и в шлеме, коммерческие лицензии источников.
