"""FastAPI service of the BlueOS extension "tides".

The service only computes; it never reads sensors and never invents
measurements.  Every number it returns can be traced to a tagged
parameter in ``data/sites.json``.
"""

import os
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, PlainTextResponse

from app import explain as explain_mod
from app import model, positions, sources

VERSION = "0.2.0"
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "static")

app = FastAPI(
    title="tides",
    version=VERSION,
    description=(
        "Honest water levels at ANY point of the planet that has GPS "
        "coordinates (BlueOS position or lat/lon), from three independent "
        "sources run side by side: equilibrium-tide theory (offline), a "
        "global ocean model and the nearest tide gauge, with their "
        "agreement stated; plus the curated sites of Issyk-Kul, its "
        "rivers and the Caspian.  Every number says where it came from."
    ),
)


@app.get("/", include_in_schema=False)
def index():
    """Serve the single static page with the SVG plot."""
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/register_service")
def register_service():
    """Return the BlueOS service-discovery record."""
    return {
        "name": "Tides",
        "description": (
            "Приливы в любой точке планеты по GPS из BlueOS: три "
            "независимых источника (теория, модель океана, ближайший "
            "мареограф) и их согласие; Иссык-Куль и Каспий. Honest "
            "levels, every number says where it came from."
        ),
        "icon": "mdi-waves",
        "company": "Leonidy431",
        "version": VERSION,
        "webpage": "https://github.com/Leonidy431/tides",
        "api": "/docs",
        "works_in_relative_paths": True,
    }


@app.get("/v1.0/sites")
def sites():
    """List all sites with their kind and components."""
    return {"sites": model.list_sites()}


def _parse_start(start):
    """Parse an ISO-8601 start time; naive values are UTC."""
    if start is None:
        now = datetime.now(timezone.utc)
        return now.replace(minute=0, second=0, microsecond=0)
    try:
        value = datetime.fromisoformat(start.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(400, "start must be ISO-8601") from exc
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _warnings(rec, wind_speed, wind_from):
    """Flag results that leave the validity range of the formulas."""
    out = []
    if "setup_depth" not in rec["params"]:
        return out
    depth = rec["params"]["setup_depth"]["value"]
    eta = abs(model.site_surge(rec, model.CATALOGUE, wind_speed,
                               wind_from))
    # River sites feel only a share of the coastal surge.
    if "surge_fraction" in rec["params"]:
        eta *= rec["params"]["surge_fraction"]["value"]
    if eta > 0.3 * depth:
        out.append(
            "linear setup formula out of range: |surge| %.2f m > 0.3 * "
            "depth %.1f m; the formula overestimates because the water "
            "column deepens as it piles up" % (eta, depth))
    return out


@app.get("/v1.0/level")
def level(
    site: str,
    start: str = Query(None, description="ISO-8601 UTC; default: this hour"),
    hours: float = Query(48.0, gt=0, le=24 * 62),
    step_min: float = Query(30.0, ge=1, le=1440),
    wind_speed: float = Query(0.0, ge=0, le=60,
                              description="m/s, held constant"),
    wind_from: float = Query(0.0, ge=0, le=360,
                             description="deg, direction wind comes from"),
):
    """Return the level time series of one site with its components."""
    rec = model.get_site(site)
    if rec is None:
        raise HTTPException(404, "unknown site: %s" % site)
    t0 = _parse_start(start)
    try:
        rows = model.series(rec, t0, hours, step_min,
                            wind_speed=wind_speed, wind_from=wind_from)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {
        "site": rec["id"],
        "warnings": _warnings(rec, wind_speed, wind_from),
        "kind": rec["kind"],
        "name_ru": rec["name_ru"],
        "lat": rec["lat"],
        "lon": rec["lon"],
        "time": "UTC",
        "start": rows[0]["t"],
        "step_min": step_min,
        "wind": {"speed_m_s": wind_speed, "from_deg": wind_from,
                 "note": "steady setup for this wind; not a forecast"},
        "units": model.COMPONENTS[rec["kind"]],
        "total_meaning": model.TOTAL_MEANING[rec["kind"]],
        "params_used": model.params_used(rec, model.CATALOGUE),
        "series": rows,
    }


@app.get("/v1.0/explain", response_class=PlainTextResponse)
def explain(site: str):
    """Explain in Russian why there is or is no tide at a site."""
    try:
        return explain_mod.explain(site)
    except KeyError as exc:
        raise HTTPException(404, "unknown site: %s" % site) from exc


def _hours_start(start):
    """Start at the given hour, or at this UTC hour."""
    return _parse_start(start).replace(minute=0, second=0, microsecond=0)


@app.get("/v1.0/sources")
def list_sources():
    """The sources, their method and licence (no network is touched)."""
    return {"sources": sources.catalogue(),
            "agreement": "demeaned shapes of the physical sources are "
                         "compared; theory votes only when it is alone"}


@app.get("/v1.0/point")
def point(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    start: str = Query(None, description="ISO-8601 UTC; default: this hour"),
    hours: float = Query(48.0, gt=0, le=24 * 7),
    use: str = Query(None, description="comma list, default all three"),
):
    """The water level at any point: three sources and their consensus."""
    names = [n.strip() for n in use.split(",")] if use else None
    if names and not any(n in sources.SOURCES for n in names):
        raise HTTPException(400, "use: %s" % ", ".join(sources.SOURCES))
    return sources.point(lat, lon, _hours_start(start), hours, names)


@app.get("/v1.0/here")
def here(
    start: str = Query(None),
    hours: float = Query(48.0, gt=0, le=24 * 7),
    use: str = Query(None),
):
    """The water level where the vehicle is, by its BlueOS GPS position."""
    pos = positions.from_blueos()
    if pos is None:
        raise HTTPException(
            503, "BlueOS has no GPS fix (mavlink2rest empty or lat/lon "
                 "zero); use /v1.0/point?lat=..&lon=.. or set BLUEOS_URL")
    names = [n.strip() for n in use.split(",")] if use else None
    out = sources.point(pos["lat"], pos["lon"], _hours_start(start), hours,
                        names)
    out["position"] = pos
    return out
