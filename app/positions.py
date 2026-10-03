"""Where is the vehicle?  Ask BlueOS for its GPS position.

BlueOS keeps the autopilot's messages behind ``mavlink2rest``; behind the
core's nginx the routes are

    /mavlink2rest/v1/mavlink/vehicles/<sys>/components/<comp>/messages/
        GLOBAL_POSITION_INT      (lat, lon in degrees * 1e7, alt in mm)
        GPS_RAW_INT              (fix_type, lat, lon, ...)

and, straight on the mavlink2rest port, the same under ``/v1/mavlink``.
Without a vehicle the list ``/v1/mavlink`` is empty, and the message
route answers a zeroed template (lat = lon = 0): that is NOT a fix, and
this module says so instead of reporting the Gulf of Guinea.
"""
import json
import os
import urllib.request

DEFAULT_BASES = ("http://127.0.0.1/mavlink2rest",
                 "http://127.0.0.1:6040",
                 "http://host.docker.internal/mavlink2rest")
ROUTE = "/v1/mavlink/vehicles/1/components/1/messages/%s"
TIMEOUT_S = 4


def _get(url):
    """Fetch JSON from `url`; any failure is None (the caller decides)."""
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT_S) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (OSError, ValueError):
        return None


def _bases():
    """The bases to try: the operator's own first, then the defaults."""
    own = os.environ.get("BLUEOS_URL")
    return ((own.rstrip("/"),) if own else ()) + DEFAULT_BASES


def parse_position(global_msg, gps_msg):
    """Make a position record from the two messages, or None.

    GLOBAL_POSITION_INT is preferred (the autopilot's fused position);
    GPS_RAW_INT is used when it carries a fix of 2D or better.
    """
    if global_msg:
        m = global_msg.get("message", {})
        lat, lon = m.get("lat", 0) / 1e7, m.get("lon", 0) / 1e7
        if (lat, lon) != (0.0, 0.0) and abs(lat) <= 90 and abs(lon) <= 180:
            return {"lat": lat, "lon": lon, "source": "GLOBAL_POSITION_INT",
                    "alt_m": m.get("alt", 0) / 1000.0,
                    "time_boot_ms": m.get("time_boot_ms")}
    if gps_msg:
        m = gps_msg.get("message", {})
        fix = m.get("fix_type", {})
        fix = fix.get("type") if isinstance(fix, dict) else fix
        lat, lon = m.get("lat", 0) / 1e7, m.get("lon", 0) / 1e7
        good = str(fix) not in ("GPS_FIX_TYPE_NO_GPS",
                                "GPS_FIX_TYPE_NO_FIX", "0", "1", "None")
        if good and (lat, lon) != (0.0, 0.0):
            return {"lat": lat, "lon": lon, "source": "GPS_RAW_INT",
                    "fix": str(fix)}
    return None


def from_blueos(fetch=_get):
    """The vehicle's position from BlueOS, or None when it has no fix."""
    for base in _bases():
        glob = fetch(base + ROUTE % "GLOBAL_POSITION_INT")
        raw = fetch(base + ROUTE % "GPS_RAW_INT")
        pos = parse_position(glob, raw)
        if pos:
            pos["blueos"] = base
            return pos
    return None
