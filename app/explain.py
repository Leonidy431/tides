"""Plain Russian explanations of why a site has or has no tide.

The numbers in the text are computed from the same model and data file
as the API, so the explanation can never drift from the series.
"""

from datetime import datetime, timedelta, timezone

from app import model, physics

# A fixed reference window keeps the text deterministic: the same site
# always gets the same explanation.
_REF_START = datetime(2026, 1, 1, tzinfo=timezone.utc)
_REF_JULY = datetime(2026, 7, 15, tzinfo=timezone.utc)


def _max_abs_astro(site, cat, days=30, step_min=60):
    """Return the largest |astro| over a fixed 30-day window (m)."""
    best = 0.0
    for i in range(int(days * 24 * 60 / step_min)):
        t = _REF_START + timedelta(minutes=i * step_min)
        best = max(best, abs(model.point(site, t, cat)["astro"]))
    return best


def _setup_text(site, cat, speeds=(10.0, 20.0)):
    """Return a sentence with the setup for onshore winds."""
    onshore = site["params"]["onshore_wind_from"]["value"]
    parts = []
    for u in speeds:
        eta = model.site_surge(site, cat, u, onshore)
        parts.append("%.0f м/с → %.3f м" % (u, eta))
    return "; ".join(parts)


def explain(site_id, cat=None):
    """Return the Russian explanation text for a site."""
    cat = cat or model.CATALOGUE
    site = model.get_site(site_id, cat)
    if site is None:
        raise KeyError(site_id)
    kind = site["kind"]
    name = site["name_ru"]
    p = site["params"]
    g = cat["constants"]["g"]["value"]
    lines = [name, ""]
    if kind == "lake":
        amp = _max_abs_astro(site, cat)
        period = physics.merian_period(
            p["lake_length"]["value"], p["mean_depth"]["value"], g)
        lines += [
            "Иссык-Куль — бессточное озеро, с океаном не связано. "
            "Прилив здесь не приходит снаружи: Луна и Солнце лишь "
            "слегка наклоняют зеркало воды внутри самого озера.",
            "Расчёт: статический наклон по равновесному приливу "
            "(Cartwright & Tayler 1971) с коэффициентом γ2 = 0,69, "
            "объём озера сохраняется.",
            "Наибольший астрономический прилив у поста за 30 суток: "
            "%.1f мм. Это миллиметры — ни глазом, ни рейкой его не "
            "увидеть." % (amp * 1000.0),
            "Сейши: период основной продольной сейши по формуле "
            "Мериана ≈ %.1f ч [В]; размах — сантиметры, задаётся "
            "ветром, в ряд не включён (неизвестно)." % (period / 3600.0),
            "Ветровой нагон при ветре к посту: %s [В]."
            % _setup_text(site, cat),
            "Настоящие изменения уровня озера — сезонные и многолетние "
            "(приток рек, испарение), а не приливы.",
        ]
    elif kind == "river_melt":
        rows = model.series(site, _REF_JULY, 48, 15, cat)
        day = rows[-97:]
        peak = max(day, key=lambda r: r["melt"])
        low = min(day, key=lambda r: r["melt"])
        hour_utc = int(peak["t"][11:13]) + int(peak["t"][14:16]) / 60.0
        local = (hour_utc + site["lon"] / 15.0) % 24.0
        lines += [
            "Приливов в этой реке нет. Река течёт с гор в бессточное "
            "озеро, а крошечный прилив озера (миллиметры) против "
            "течения не поднимается.",
            "То, что похоже на «прилив и отлив», — суточный цикл таяния "
            "ледников и снега: утром вода низкая, к вечеру растёт. "
            "Сильнее всего в июне–августе, зимой почти исчезает.",
            "Расчёт: градусо-дни (DDF = 7 мм/(°C·сут) [В]), температура "
            "станции поднята по градиенту 6,5 К/км до высоты таяния, "
            "затем запаздывание и линейный резервуар [В].",
            "Модельный июльский день: пик талой воды ≈ %.1f ч по "
            "местному солнечному времени (+%.1f м³/с), минимум +%.1f "
            "м³/с." % (local, peak["melt"], low["melt"]),
            "Числа — порядок величины, не калибровка по гидропосту. "
            "Уровень воды (м) по расходу не считается: кривая расходов "
            "поста неизвестна.",
        ]
    elif kind == "sea":
        amp = sum(p["astro_%s_amp" % n]["value"]
                  for n in physics.CONSTITUENTS)
        lines += [
            "Каспий — замкнутое море-озеро. Астрономический прилив "
            "здесь — сантиметры: сумма амплитуд M2, S2, K1, O1 у этой "
            "точки ≈ %.1f см [В]." % (amp * 100.0),
            "Гармонические постоянные (амплитуды и фазы) — оценка [В]; "
            "фазы поста неизвестны и приняты равными местному "
            "равновесному приливу.",
            "Главные колебания уровня — ветровые нагоны и сгоны. На "
            "мелком Северном Каспии они достигают метров и заходят в "
            "дельту Волги на десятки километров.",
            "Нагон по формуле η = C_d·ρ_a·U²·L/(ρ_w·g·h) при ветре к "
            "берегу: %s." % _setup_text(site, cat),
            "Формула стационарная и линейная: при нагоне, сравнимом с "
            "глубиной, она завышает результат. Сейши Каспия (часы) "
            "в ряд не включены.",
        ]
    elif kind == "river_seasonal":
        peak_doy = p["flood_peak_doy"]["value"]
        peak_day = _REF_START + timedelta(days=peak_doy)
        lines += [
            "Приливов в реке нет: прилив Каспия — сантиметры и в "
            "дельте теряется.",
            "Уровень реки определяет весенне-летнее половодье: пик "
            "около %s [В], подъём ≈ %.1f м над зимней меженью [В]."
            % (peak_day.strftime("%d.%m"),
               p["flood_amplitude"]["value"]),
            "Морской нагон доходит сюда долей %.1f [В]."
            % p["surge_fraction"]["value"],
        ]
    lines += ["", "Все параметры и их метки [П]/[В] — в /v1.0/level."]
    return "\n".join(lines)
