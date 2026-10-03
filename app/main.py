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
from app import model

VERSION = "0.1.0"
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "static")

app = FastAPI(
    title="tides",
    version=VERSION,
    description=(
        "Honest water levels for Issyk-Kul, its rivers and the Caspian: "
        "astronomical tide where it exists (mm..cm), glacier-melt daily "
        "cycle in the rivers (no tide there), wind setup and seasonal "
        "floods.  Every parameter is tagged [П] source or [В] estimate."
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
            "Приливы, нагоны и суточный цикл таяния: Иссык-Куль, реки "
            "бассейна и Каспий. Honest levels, every number tagged."
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
