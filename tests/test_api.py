"""API contract tests for BlueOS discovery and the level endpoint."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_register_service_fields():
    r = client.get("/register_service")
    assert r.status_code == 200
    d = r.json()
    for key in ("name", "description", "icon", "company", "version",
                "webpage", "api"):
        assert d[key], key
    assert d["icon"] == "mdi-waves"
    assert d["api"] == "/docs"


def test_index_page_has_no_cdn():
    r = client.get("/")
    assert r.status_code == 200
    assert "<svg" in r.text
    assert "http://" not in r.text and "https://" not in r.text


def test_sites_list():
    sites = client.get("/v1.0/sites").json()["sites"]
    kinds = [s["kind"] for s in sites]
    assert kinds.count("lake") >= 1
    assert kinds.count("river_melt") >= 4
    assert kinds.count("sea") >= 3


def test_level_shape():
    r = client.get("/v1.0/level", params={
        "site": "caspian_north_volga_delta",
        "start": "2026-07-15T00:00:00Z", "hours": 6, "step_min": 60,
        "wind_speed": 15, "wind_from": 135})
    assert r.status_code == 200
    d = r.json()
    assert d["time"] == "UTC"
    assert len(d["series"]) == 7
    assert set(d["units"]) == {"astro", "surge", "total"}
    row = d["series"][0]
    assert set(row) == {"t", "astro", "surge", "total"}
    assert abs(row["astro"] + row["surge"] - row["total"]) < 1e-5
    for p in d["params_used"].values():
        assert "tag" in p


def test_level_river_components():
    d = client.get("/v1.0/level", params={
        "site": "karakol_river", "start": "2026-07-15T00:00:00Z",
        "hours": 2, "step_min": 60}).json()
    assert set(d["series"][0]) == {"t", "astro", "base", "melt", "total"}


def test_level_errors():
    assert client.get("/v1.0/level", params={"site": "x"}).status_code == 404
    r = client.get("/v1.0/level", params={
        "site": "karakol_river", "start": "nope"})
    assert r.status_code == 400
    r = client.get("/v1.0/level", params={
        "site": "karakol_river", "hours": 1488, "step_min": 1})
    assert r.status_code == 400


def test_explain_russian():
    t = client.get("/v1.0/explain",
                   params={"site": "karakol_river"}).text
    assert "Приливов в этой реке нет" in t
    t = client.get("/v1.0/explain",
                   params={"site": "issyk_kul_cholpon_ata"}).text
    assert "мм" in t


def test_level_warns_outside_linear_range():
    d = client.get("/v1.0/level", params={
        "site": "caspian_north_volga_delta", "hours": 1, "step_min": 60,
        "start": "2026-07-15T00:00:00Z", "wind_speed": 25,
        "wind_from": 135}).json()
    assert d["warnings"]
