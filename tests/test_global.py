"""The service at any point of the planet: GPS from BlueOS, three sources
side by side, an honest consensus.  No test touches the network."""
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app import positions, sources
from app.main import app

T0 = datetime(2026, 10, 3, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def fresh_cache():
    """Every test starts without remembered answers."""
    sources._cache.clear()


def fake_openmeteo(url):
    """A model answer: a clean semidiurnal wave of 1 m."""
    t = [("2026-10-03T%02d:00" % h) for h in range(24)]
    import math
    v = [round(math.sin(2 * math.pi * h / 12.42), 3) for h in range(24)]
    return {"latitude": 48.0, "longitude": -5.0,
            "hourly": {"time": t, "sea_level_height_msl": v}}


def fake_ioc(url):
    """A gauge list and ten-minute data of the same wave plus a datum."""
    import math
    if "stationlist" in url:
        return [{"Code": "bres", "Location": "Brest", "Lat": 48.38,
                 "Lon": -4.49, "status": 1},
                {"Code": "far", "Location": "Far", "Lat": 10.0,
                 "Lon": 100.0, "status": 1}]
    rows = []
    for h in range(24):
        for m in (0, 10, 20, 30, 40, 50):
            x = h + m / 60.0
            rows.append({"slevel": 3.0 + math.sin(2 * math.pi * x / 12.42),
                         "stime": "2026-10-03 %02d:%02d:00" % (h, m),
                         "sensor": "rad"})
    return rows


def test_haversine_and_nearest():
    st = [{"Code": "a", "Lat": 48.4, "Lon": -4.5},
          {"Code": "b", "Lat": 0.0, "Lon": 0.0}]
    s, d = sources.nearest_station(48.38, -4.49, st)
    assert s["Code"] == "a" and d < 5
    assert sources.haversine_km(0, 0, 0, 1) == pytest.approx(111.19, abs=0.1)


def test_equilibrium_is_global_and_small_inland():
    for lat, lon in [(42.65, 77.08), (-33.9, 18.4), (0.0, -160.0)]:
        r = sources.equilibrium(lat, lon, T0, 48)
        assert r["status"] == "ok" and len(r["values"]) == 48
        assert max(abs(v) for v in r["values"]) < 0.4


def test_three_sources_agree_on_a_clean_wave():
    r = sources.point(48.38, -4.49, T0, 24, None,
                      {"openmeteo": fake_openmeteo, "ioc": fake_ioc})
    names = {s["name"]: s["status"] for s in r["sources"]}
    assert names == {"equilibrium": "ok", "openmeteo": "ok", "ioc": "ok"}
    c = r["consensus"]
    assert c["verdict"] == "agree"
    assert c["sources_used"] == ["ioc", "openmeteo"]  # theory only baseline


def test_a_failing_source_is_a_status_not_a_crash():
    def boom(url):
        raise OSError("network down")
    r = sources.point(48.38, -4.49, T0, 24, None,
                      {"openmeteo": boom, "ioc": boom})
    st = {s["name"]: s["status"] for s in r["sources"]}
    assert st["openmeteo"] == "error" and st["ioc"] == "error"
    assert r["consensus"]["verdict"] == "theory_only"


def test_a_lake_has_only_theory():
    def inland(url):
        return {"hourly": {"time": ["2026-10-03T00:00"],
                           "sea_level_height_msl": [None]}}
    r = sources.point(42.65, 77.08, T0, 1, ["equilibrium", "openmeteo"],
                      {"openmeteo": inland})
    assert r["consensus"]["verdict"] == "theory_only"


def test_disagreeing_sources_are_flagged():
    def bent(url):
        d = fake_openmeteo(url)
        d["hourly"]["sea_level_height_msl"] = [
            v * 3 for v in d["hourly"]["sea_level_height_msl"]]
        return d
    r = sources.point(48.38, -4.49, T0, 24, ["openmeteo", "ioc"],
                      {"openmeteo": bent, "ioc": fake_ioc})
    assert r["consensus"]["verdict"] == "disagree"


def test_ioc_refuses_a_far_gauge():
    r = sources.ioc(-60.0, -170.0, T0, 6, fake_ioc)
    assert r["status"] == "no_data" and "gauge" in r["why"]


def test_blueos_zero_message_is_no_fix():
    zero = {"message": {"type": "GLOBAL_POSITION_INT", "lat": 0, "lon": 0,
                        "alt": 0, "time_boot_ms": 0}}
    assert positions.parse_position(zero, None) is None
    assert positions.from_blueos(lambda url: zero) is None


def test_blueos_position_is_read_in_degrees():
    msg = {"message": {"type": "GLOBAL_POSITION_INT", "lat": 424000000,
                       "lon": 770800000, "alt": 1607000,
                       "time_boot_ms": 5}}
    pos = positions.from_blueos(lambda url: msg)
    assert pos["lat"] == pytest.approx(42.4) and pos["alt_m"] == 1607.0
    assert pos["source"] == "GLOBAL_POSITION_INT"


def test_gps_raw_needs_a_fix():
    raw = {"message": {"fix_type": {"type": "GPS_FIX_TYPE_NO_FIX"},
                       "lat": 10, "lon": 10}}
    assert positions.parse_position(None, raw) is None
    raw["message"]["fix_type"] = {"type": "GPS_FIX_TYPE_3D_FIX"}
    raw["message"]["lat"], raw["message"]["lon"] = 484000000, -49000000
    assert positions.parse_position(None, raw)["source"] == "GPS_RAW_INT"


def test_api_contract(monkeypatch):
    c = TestClient(app)
    monkeypatch.setattr(sources, "http_json", fake_openmeteo)
    assert c.get("/v1.0/sources").json()["sources"][0]["name"] == "equilibrium"
    assert c.get("/v1.0/point", params={"lat": 91, "lon": 0}).status_code \
        == 422
    r = c.get("/v1.0/point", params={"lat": 42.65, "lon": 77.08,
                                     "hours": 6, "use": "equilibrium"})
    assert r.status_code == 200
    assert r.json()["consensus"]["verdict"] == "theory_only"
    monkeypatch.setattr(positions, "from_blueos", lambda: None)
    assert c.get("/v1.0/here").status_code == 503
