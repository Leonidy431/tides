"""Three independent sources of the water level at any point, run side by
side (docs/TZ.md, tools/choose_sources.py).

* ``equilibrium`` : theory, computed here; works offline everywhere.  It
  is the equilibrium tide of the Moon and the Sun times the elastic
  Earth's response, which is what a lake gauge feels and what an ocean
  gauge only roughly does; the ocean's own response (resonance, shelves)
  is not in it.
* ``openmeteo``   : a global ocean model with tides (Open-Meteo Marine,
  hourly ``sea_level_height_msl``); no data inland.
* ``ioc``         : observations of the nearest tide gauge of the IOC Sea
  Level Station Monitoring, hourly means of the last hours; the past only.

None of them is trusted alone.  Every source answers with its own status
and licence; ``consensus`` compares them after each has lost its own mean
(their datums differ) and says how far they agree.  Nothing is invented:
a source without data returns no series and says why.
"""
import json
import math
import os
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from app import model, physics

TIMEOUT_S = 12
IOC_RADIUS_KM = 150.0
IOC_LIST_TTL_S = 24 * 3600
CACHE_TTL_S = 600
AGREE_M = 0.15
AGREE_FRAC = 0.12   # of the tide's own swing, for big ocean tides
GAMMA = 0.69          # 1 + k2 - h2, elastic Earth's response [П]
UA = "tides-blueos-extension/0.2"
_cache = {}


def http_json(url, timeout=TIMEOUT_S, attempts=2):
    """GET a JSON document, trying twice; raises OSError or ValueError.

    One retry covers a dropped handshake on a weak link (the vehicle's
    uplink, or a proxy under load); more would only hide an outage.
    """
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for n in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except OSError:
            if n == attempts - 1:
                raise
            time.sleep(0.5)


def _cached(key, ttl, make):
    """A tiny time-limited memory cache around `make()`."""
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    value = make()
    _cache[key] = (time.time(), value)
    return value


def hours_grid(t0, hours):
    """The hourly UTC grid of a request, as ISO strings 'YYYY-MM-DDTHH:00'."""
    n = int(math.ceil(hours))
    return [(t0 + timedelta(hours=i)).strftime("%Y-%m-%dT%H:00:00Z")
            for i in range(n)]


def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance in kilometres."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) \
        * math.sin(dl / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(a))


def equilibrium(lat, lon, t0, hours, fetch=None):
    """The theory baseline: computed here, never fails."""
    amps = model._eq_amps(model.CATALOGUE)
    out = []
    for iso in hours_grid(t0, hours):
        t = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        out.append(round(GAMMA * physics.equilibrium_tide(t, lat, lon,
                                                          amps), 5))
    return {"status": "ok", "values": out}


def openmeteo(lat, lon, t0, hours, fetch=http_json):
    """A global ocean model's sea level with tides, hourly."""
    grid = hours_grid(t0, hours)
    q = urllib.parse.urlencode({
        "latitude": lat, "longitude": lon, "timezone": "UTC",
        "hourly": "sea_level_height_msl", "start_date": grid[0][:10],
        "end_date": grid[-1][:10]})
    doc = fetch("https://marine-api.open-meteo.com/v1/marine?" + q)
    h = doc.get("hourly", {})
    table = dict(zip(h.get("time", []), h.get("sea_level_height_msl", [])))
    vals = [table.get(iso[:13] + ":00") for iso in grid]
    if all(v is None for v in vals):
        return {"status": "no_data",
                "why": "no model sea level here (inland or off the grid)"}
    return {"status": "ok", "values": vals,
            "grid_point": [doc.get("latitude"), doc.get("longitude")]}


def ioc_stations(fetch=http_json):
    """The IOC station list (cached a day): the working ones only."""
    url = ("https://www.ioc-sealevelmonitoring.org/service.php?"
           "query=stationlist&showall=a&format=json")
    rows = _cached(("ioc-list",), IOC_LIST_TTL_S, lambda: fetch(url))
    return [r for r in rows if r.get("status") == 1
            and r.get("Lat") is not None and r.get("Lon") is not None]


def nearest_station(lat, lon, stations):
    """The nearest working gauge and its distance in km, or (None, inf)."""
    best, dist = None, float("inf")
    for s in stations:
        d = haversine_km(lat, lon, float(s["Lat"]), float(s["Lon"]))
        if d < dist:
            best, dist = s, d
    return best, dist


def ioc(lat, lon, t0, hours, fetch=http_json):
    """Hourly means of the nearest gauge; only hours already observed."""
    st, dist = nearest_station(lat, lon, ioc_stations(fetch))
    if st is None or dist > IOC_RADIUS_KM:
        return {"status": "no_data",
                "why": "no working gauge within %d km (nearest %.0f km)"
                       % (IOC_RADIUS_KM, dist)}
    grid = hours_grid(t0, hours)
    now = datetime.now(timezone.utc)
    stop = min(datetime.fromisoformat(grid[-1].replace("Z", "+00:00"))
               + timedelta(hours=1), now)
    start = datetime.fromisoformat(grid[0].replace("Z", "+00:00"))
    if stop <= start:
        return {"status": "no_data", "why": "gauges report the past only",
                "station": st["Code"], "distance_km": round(dist, 1)}
    q = urllib.parse.urlencode({
        "query": "data", "code": st["Code"], "format": "json",
        "timestart": start.strftime("%Y-%m-%dT%H:%M:%S"),
        "timestop": stop.strftime("%Y-%m-%dT%H:%M:%S")})
    rows = fetch("https://www.ioc-sealevelmonitoring.org/service.php?" + q)
    buckets = {}
    for r in rows:
        key = r["stime"].replace(" ", "T")[:13] + ":00:00Z"
        buckets.setdefault(key, []).append(float(r["slevel"]))
    vals = [round(sum(buckets[k]) / len(buckets[k]), 4) if k in buckets
            else None for k in grid]
    if all(v is None for v in vals):
        return {"status": "no_data", "why": "the gauge sent nothing",
                "station": st["Code"], "distance_km": round(dist, 1)}
    return {"status": "ok", "values": vals, "station": st["Code"],
            "station_name": st.get("Location"),
            "distance_km": round(dist, 1)}


SOURCES = {
    "equilibrium": {
        "fn": equilibrium, "kind": "theory",
        "method": "equilibrium tide of Moon and Sun x 0.69, computed here",
        "licence": "own code (MIT); constants tagged in data/sites.json",
        "offline": True},
    "openmeteo": {
        "fn": openmeteo, "kind": "model",
        "method": "Open-Meteo Marine API, sea_level_height_msl (hourly)",
        "licence": "CC BY 4.0, free for non-commercial use; commercial "
                   "use needs their plan [П: open-meteo.com/en/licence]",
        "offline": False},
    "ioc": {
        "fn": ioc, "kind": "observation",
        "method": "IOC Sea Level Station Monitoring, nearest gauge",
        "licence": "IOC SLSMF data policy: free for non-commercial use "
                   "with attribution; check before commercial use [В]",
        "offline": False},
}


def run_source(name, lat, lon, t0, hours, fetch=None):
    """One source, guarded: an error becomes a status, never a crash."""
    spec = SOURCES[name]
    key = (name, round(lat, 2), round(lon, 2), t0.isoformat(), hours)

    def make():
        try:
            return (spec["fn"](lat, lon, t0, hours, fetch) if fetch
                    else spec["fn"](lat, lon, t0, hours))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            return {"status": "error", "why": "%s: %s"
                    % (type(exc).__name__, exc)}
    res = dict(_cached(key, CACHE_TTL_S if spec["offline"] is False
                       else 0, make))
    res.update({"name": name, "kind": spec["kind"],
                "method": spec["method"], "licence": spec["licence"]})
    return res


def consensus(results, grid):
    """Compare the sources after each loses its own mean.

    Datums differ (theory has none, the model is relative to mean sea
    level, a gauge to its own zero), so only the shape is compared: the
    median of the demeaned series per hour, and the widest spread.
    """
    ok = [r for r in results if r["status"] == "ok"]
    # Theory is a baseline, not a measurement: it joins the vote only
    # when nothing physical (model or gauge) answered.  On a lake that is
    # exactly right; on a coast it would drown the two real sources.
    physical = [r for r in ok if r["kind"] != "theory"]
    live = {r["name"]: r["values"] for r in (physical or ok)}
    demeaned = {}
    for name, vals in live.items():
        real = [v for v in vals if v is not None]
        if real:
            m = sum(real) / len(real)
            demeaned[name] = [None if v is None else v - m for v in vals]
    series, spread = [], 0.0
    for i, iso in enumerate(grid):
        col = sorted(d[i] for d in demeaned.values() if d[i] is not None)
        if not col:
            series.append({"t": iso, "median": None, "n": 0})
            continue
        mid = col[len(col) // 2] if len(col) % 2 else \
            (col[len(col) // 2 - 1] + col[len(col) // 2]) / 2
        spread = max(spread, col[-1] - col[0])
        series.append({"t": iso, "median": round(mid, 4), "n": len(col)})
    n_live = len(demeaned)
    tol = AGREE_M
    if n_live == 0:
        verdict = "no_source"
    elif not physical:
        verdict = "theory_only"
    elif n_live == 1:
        verdict = "single_source"
    else:
        meds = [x["median"] for x in series if x["median"] is not None]
        swing = max(meds) - min(meds) if meds else 0.0
        tol = max(AGREE_M, AGREE_FRAC * swing)
        verdict = "agree" if spread <= tol else "disagree"
    return {"verdict": verdict, "sources_used": sorted(demeaned),
            "spread_max_m": round(spread, 4),
            "agree_within_m": round(tol, 3),
            "series": series,
            "note": "demeaned shapes compared; datums differ by source"}


def point(lat, lon, t0, hours, names=None, fetch=None):
    """All requested sources in parallel, plus their consensus."""
    names = [n for n in (names or SOURCES) if n in SOURCES]
    with ThreadPoolExecutor(max_workers=len(names) or 1) as pool:
        futs = {n: pool.submit(run_source, n, lat, lon, t0, hours,
                               (fetch or {}).get(n)) for n in names}
        results = [futs[n].result() for n in names]
    grid = hours_grid(t0, hours)
    return {"lat": lat, "lon": lon, "time": "UTC", "start": grid[0],
            "step_min": 60, "sources": results,
            "consensus": consensus(results, grid)}


def catalogue():
    """Static facts about the sources (no network)."""
    return [{"name": n, "kind": s["kind"], "method": s["method"],
             "licence": s["licence"], "offline": s["offline"]}
            for n, s in SOURCES.items()]
