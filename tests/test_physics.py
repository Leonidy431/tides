"""Physics sanity tests: the honest orders of magnitude must hold."""

from datetime import datetime, timedelta, timezone

import pytest

from app import model, physics

START = datetime(2026, 1, 1, tzinfo=timezone.utc)
JULY = datetime(2026, 7, 15, tzinfo=timezone.utc)
CAT = model.CATALOGUE
C = CAT["constants"]


def _max_abs(site_id, key, days=30, step_min=60):
    """Return the largest |component| over a window of days."""
    site = model.get_site(site_id)
    rows = model.series(site, START, days * 24, step_min)
    return max(abs(r[key]) for r in rows)


def test_issyk_kul_tide_below_one_centimetre():
    # An endorheic lake 178 km long tilts by millimetres only.
    amp = _max_abs("issyk_kul_cholpon_ata", "astro")
    assert 0.0 < amp < 0.01


def test_caspian_astronomical_tide_below_twenty_centimetres():
    for sid in ("caspian_north_volga_delta", "caspian_middle_makhachkala",
                "caspian_south_baku"):
        amp = _max_abs(sid, "astro")
        assert 0.0 < amp < 0.2, sid


def test_rivers_have_no_tide():
    for site in CAT["sites"]:
        if site["kind"].startswith("river"):
            rows = model.series(site, START, 24, 60)
            assert all(r["astro"] == 0.0 for r in rows), site["id"]


def test_melt_peak_is_after_local_noon():
    # Karakol: short glacier river, the daily melt wave peaks in the
    # afternoon or evening local solar time, never in the morning.
    site = model.get_site("karakol_river")
    rows = model.series(site, JULY, 48, 15)[-96:]
    peak = max(rows, key=lambda r: r["melt"])
    t = datetime.fromisoformat(peak["t"].replace("Z", "+00:00"))
    local = physics.local_solar_hour(t, site["lon"])
    assert 12.0 < local < 24.0
    low = min(rows, key=lambda r: r["melt"])
    assert peak["melt"] > 2.0 * low["melt"]


def test_winter_has_no_melt_cycle():
    site = model.get_site("karakol_river")
    rows = model.series(site, datetime(2026, 1, 15, tzinfo=timezone.utc),
                        24, 60)
    assert max(r["melt"] for r in rows) < 1e-6


def _setup(u, h):
    return physics.wind_setup(u, 90.0, 90.0, 100000.0, h,
                              C["drag_coefficient"]["value"],
                              C["rho_air"]["value"], 1010.0,
                              C["g"]["value"])


def test_surge_grows_with_wind_squared():
    assert _setup(20.0, 10.0) == pytest.approx(4.0 * _setup(10.0, 10.0))


def test_surge_falls_with_depth():
    assert _setup(15.0, 20.0) == pytest.approx(0.5 * _setup(15.0, 10.0))
    assert _setup(15.0, 4.0) > _setup(15.0, 40.0)


def test_offshore_wind_gives_setdown():
    eta = physics.wind_setup(15.0, 270.0, 90.0, 1e5, 10.0, 1.3e-3, 1.225,
                             1010.0, 9.80665)
    assert eta < 0.0


def test_north_caspian_surge_reaches_metres():
    site = model.get_site("caspian_north_volga_delta")
    onshore = site["params"]["onshore_wind_from"]["value"]
    eta = model.site_surge(site, CAT, 20.0, onshore)
    assert 1.0 < eta < 5.0


def test_determinism():
    for site in CAT["sites"]:
        a = model.series(site, JULY, 12, 30, wind_speed=12, wind_from=100)
        b = model.series(site, JULY, 12, 30, wind_speed=12, wind_from=100)
        assert a == b


def test_every_parameter_is_tagged():
    for name, p in C.items():
        assert p["tag"].startswith(("[П]", "[В]", "неизвестно")), name
    for site in CAT["sites"]:
        for name, p in site["params"].items():
            assert "tag" in p and "unit" in p, (site["id"], name)
            assert p["tag"].startswith(("[П]", "[В]", "неизвестно")), name


def test_astronomical_arguments_s2_period():
    # S2 repeats exactly every 12 solar hours.
    a = physics.astronomical_arguments(JULY)["S2"]
    b = physics.astronomical_arguments(JULY + timedelta(hours=12))["S2"]
    assert (b - a) % 360.0 == pytest.approx(0.0, abs=1e-6)


def test_seasonal_flood_peaks_in_spring_summer():
    site = model.get_site("volga_astrakhan")
    june = model.point(site, datetime(2026, 6, 9, tzinfo=timezone.utc))
    jan = model.point(site, datetime(2026, 1, 15, tzinfo=timezone.utc))
    assert june["seasonal"] > 2.0 > 0.01 > jan["seasonal"]
