"""Site catalogue and time-series assembly.

This layer reads ``data/sites.json``, picks the physics that is true
for each kind of water and returns the components separately, so a
reader can always see which part of the level is astronomy and which is
melt, wind or season.
"""

import json
import math
import os
from datetime import timedelta

from app import physics

DATA_PATH = os.environ.get(
    "TIDES_DATA",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(
        __file__))), "data", "sites.json"),
)

MAX_POINTS = 5000


def load_catalogue(path=DATA_PATH):
    """Load the site catalogue from JSON."""
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


CATALOGUE = load_catalogue()


def _v(param):
    """Return the bare value of a tagged parameter."""
    return param["value"]


def get_site(site_id, catalogue=None):
    """Return a site record by id, or None if it does not exist."""
    cat = catalogue or CATALOGUE
    for site in cat["sites"]:
        if site["id"] == site_id:
            return site
    return None


def list_sites(catalogue=None):
    """Return a short public description of every site."""
    cat = catalogue or CATALOGUE
    out = []
    for site in cat["sites"]:
        out.append({
            "id": site["id"],
            "kind": site["kind"],
            "name_ru": site["name_ru"],
            "name_en": site["name_en"],
            "lat": site["lat"],
            "lon": site["lon"],
            "components": COMPONENTS[site["kind"]],
        })
    return out


# Which components each kind of water has, with their units.  Rivers of
# the Issyk-Kul basin get an "astro" component that is identically zero
# so the API states the absence of a tide explicitly instead of hiding
# the column.
COMPONENTS = {
    "lake": {"astro": "m", "surge": "m", "total": "m"},
    "sea": {"astro": "m", "surge": "m", "total": "m"},
    "river_melt": {"astro": "m^3/s", "base": "m^3/s",
                   "melt": "m^3/s", "total": "m^3/s"},
    "river_seasonal": {"astro": "m", "seasonal": "m",
                       "surge": "m", "total": "m"},
}

TOTAL_MEANING = {
    "lake": "level anomaly about mean_level, m",
    "sea": "level anomaly about mean_level, m",
    "river_melt": "discharge, m^3/s (stage needs a rating curve: unknown)",
    "river_seasonal": "stage above winter low water, m",
}

_NO_TIDE_RIVER = {
    "value": 0.0,
    "unit": "m",
    "tag": ("[П] a river that does not reach the ocean has no tide; the "
            "mm-scale tide of Issyk-Kul does not propagate upstream "
            "against the current"),
}


def _wind_params(site, cat):
    """Collect the tagged parameters of the wind-setup formula."""
    c = cat["constants"]
    p = site["params"]
    return {
        "drag_coefficient": c["drag_coefficient"],
        "rho_air": c["rho_air"],
        "g": c["g"],
        "fetch": p["fetch"],
        "setup_depth": p["setup_depth"],
        "onshore_wind_from": p["onshore_wind_from"],
        "rho_water": p["rho_water"],
    }


def site_surge(site, cat, wind_speed, wind_from):
    """Return the steady wind setup for a site (m)."""
    w = _wind_params(site, cat)
    return physics.wind_setup(
        wind_speed, wind_from, _v(w["onshore_wind_from"]), _v(w["fetch"]),
        _v(w["setup_depth"]), _v(w["drag_coefficient"]), _v(w["rho_air"]),
        _v(w["rho_water"]), _v(w["g"]))


def _eq_amps(cat):
    """Return the equilibrium amplitudes from the constants block."""
    c = cat["constants"]
    return {n: _v(c["eq_amp_" + n]) for n in physics.CONSTITUENTS}


def _station(site, cat):
    """Return a compact station record for the melt model."""
    st = cat["stations"][site["station"]]
    return {
        "elev": _v(st["elevation_m"]),
        "t_mean": _v(st["t_mean_monthly"]),
        "t_half": _v(st["t_half_range_monthly"]),
    }


def params_used(site, cat):
    """Return every tagged parameter the model of a site uses."""
    c = cat["constants"]
    p = site["params"]
    kind = site["kind"]
    used = {}
    if kind == "lake":
        for n in physics.CONSTITUENTS:
            used["eq_amp_" + n] = c["eq_amp_" + n]
        used["gamma2"] = c["gamma2"]
        used["nodal_factors"] = c["nodal_factors"]
        used["lake_points"] = p["lake_points"]
        used["mean_level"] = p["mean_level"]
        used["seiche_amplitude"] = p["seiche_amplitude"]
        used.update(_wind_params(site, cat))
    elif kind == "sea":
        for n in physics.CONSTITUENTS:
            used["astro_%s_amp" % n] = p["astro_%s_amp" % n]
        used["astro_phase_lag"] = p["astro_phase_lag"]
        used["nodal_factors"] = c["nodal_factors"]
        used["mean_level"] = p["mean_level"]
        used.update(_wind_params(site, cat))
    elif kind == "river_melt":
        st = cat["stations"][site["station"]]
        used["astro"] = dict(_NO_TIDE_RIVER, unit="m^3/s")
        used["station_elevation"] = st["elevation_m"]
        used["t_mean_monthly"] = st["t_mean_monthly"]
        used["t_half_range_monthly"] = st["t_half_range_monthly"]
        for key in ("lapse_rate", "ddf_ice", "temp_peak_local_hour"):
            used[key] = c[key]
        for key in ("melt_area", "melt_elevation", "lag", "reservoir_k",
                    "base_flow_monthly"):
            used[key] = p[key]
    elif kind == "river_seasonal":
        used["astro"] = _NO_TIDE_RIVER
        for key in ("flood_peak_doy", "flood_amplitude", "flood_sigma",
                    "surge_fraction"):
            used[key] = p[key]
        used.update(_wind_params(site, cat))
    return used


def point(site, t, cat=None, wind_speed=0.0, wind_from=0.0):
    """Return all components of one site at one UTC instant."""
    cat = cat or CATALOGUE
    kind = site["kind"]
    p = site["params"]
    c = cat["constants"]
    if kind == "lake":
        astro = physics.static_lake_tide(
            t, site["lat"], site["lon"], _v(p["lake_points"]),
            _eq_amps(cat), _v(c["gamma2"]))
        surge = site_surge(site, cat, wind_speed, wind_from)
        return {"astro": astro, "surge": surge, "total": astro + surge}
    if kind == "sea":
        amps = {n: _v(p["astro_%s_amp" % n]) for n in physics.CONSTITUENTS}
        astro = physics.harmonic_tide(t, site["lon"], amps,
                                      _v(p["astro_phase_lag"]))
        surge = site_surge(site, cat, wind_speed, wind_from)
        return {"astro": astro, "surge": surge, "total": astro + surge}
    if kind == "river_melt":
        base = physics.monthly_interp(t, _v(p["base_flow_monthly"]))
        melt = physics.routed_melt(
            t, site["lon"], _station(site, cat), _v(p["melt_area"]),
            _v(p["melt_elevation"]), _v(c["lapse_rate"]),
            _v(c["ddf_ice"]), _v(c["temp_peak_local_hour"]),
            _v(p["lag"]), _v(p["reservoir_k"]))
        return {"astro": 0.0, "base": base, "melt": melt,
                "total": base + melt}
    if kind == "river_seasonal":
        seasonal = physics.seasonal_flood(
            t, _v(p["flood_peak_doy"]), _v(p["flood_amplitude"]),
            _v(p["flood_sigma"]))
        share = _v(p["surge_fraction"])
        surge = share * site_surge(site, cat, wind_speed, wind_from)
        return {"astro": 0.0, "seasonal": seasonal, "surge": surge,
                "total": seasonal + surge}
    raise ValueError("unknown site kind: %s" % kind)


def series(site, start, hours, step_min, cat=None, wind_speed=0.0,
           wind_from=0.0):
    """Return a deterministic time series for a site.

    The wind is held constant over the window: the module computes the
    steady setup for the wind the caller states, it does not forecast
    the wind.
    """
    cat = cat or CATALOGUE
    start = physics.as_utc(start)
    n = int(math.floor(hours * 60.0 / step_min)) + 1
    if n > MAX_POINTS:
        raise ValueError("too many points: %d > %d" % (n, MAX_POINTS))
    rows = []
    for i in range(n):
        t = start + timedelta(minutes=i * step_min)
        comp = point(site, t, cat, wind_speed, wind_from)
        row = {"t": t.strftime("%Y-%m-%dT%H:%M:%SZ")}
        for key, value in comp.items():
            row[key] = round(value, 6)
        rows.append(row)
    return rows
