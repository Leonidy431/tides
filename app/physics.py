"""Deterministic water-level physics for Issyk-Kul and the Caspian.

Every function here is pure: the same inputs always give the same
outputs.  There is no randomness anywhere, because the operator's
project forbids simulated or random results.  Time is always UTC and
all quantities are SI unless a name says otherwise.
"""

import math
from datetime import datetime, timedelta, timezone

# The Unix epoch is Julian Day 2440587.5 and J2000.0 is JD 2451545.0.
# The difference between UTC and Terrestrial Time (~69 s) is ignored,
# because it shifts the lunar argument by far less than a degree.
_JD_UNIX_EPOCH = 2440587.5
_JD_J2000 = 2451545.0

SEMIDIURNAL = ("M2", "S2")
DIURNAL = ("K1", "O1")
CONSTITUENTS = SEMIDIURNAL + DIURNAL


def as_utc(t):
    """Return ``t`` as an aware UTC datetime.

    Naive datetimes are treated as UTC, so the API never silently
    mixes local time into the astronomy.
    """
    if t.tzinfo is None:
        return t.replace(tzinfo=timezone.utc)
    return t.astimezone(timezone.utc)


def julian_centuries(t):
    """Return Julian centuries since J2000.0 for a UTC datetime."""
    jd = as_utc(t).timestamp() / 86400.0 + _JD_UNIX_EPOCH
    return (jd - _JD_J2000) / 36525.0


def astronomical_arguments(t):
    """Return the Greenwich equilibrium arguments V (degrees).

    Mean longitudes follow Meeus (Astronomical Algorithms, 1998); the
    argument formulas follow Schureman (1958).  Nodal corrections are
    omitted on purpose (f = 1, u = 0): they change the amplitudes by a
    few per cent, which is invisible at the mm..cm scale of these
    waters.
    """
    big_t = julian_centuries(t)
    s = 218.3164477 + 481267.88123421 * big_t
    h = 280.46646 + 36000.76983 * big_t
    utc = as_utc(t)
    hours = (utc.hour + utc.minute / 60.0 + utc.second / 3600.0
             + utc.microsecond / 3.6e9)
    # T is the hour angle of the mean Sun at Greenwich.
    hour_angle = 180.0 + 15.0 * hours
    return {
        "M2": 2.0 * hour_angle - 2.0 * s + 2.0 * h,
        "S2": 2.0 * hour_angle,
        "K1": hour_angle + h + 90.0,
        "O1": hour_angle - 2.0 * s + h - 90.0,
    }


def _species(name):
    """Return the tidal species number (2 or 1) of a constituent."""
    return 2 if name in SEMIDIURNAL else 1


def equilibrium_tide(t, lat, lon, eq_amps, args=None):
    """Return the equilibrium tide height (m) at a point.

    ``eq_amps`` maps constituent names to equilibrium amplitudes.  The
    semidiurnal latitude factor is cos^2(lat) and the diurnal one is
    sin(2 lat), as in the classical expansion of the tide potential.
    """
    if args is None:
        args = astronomical_arguments(t)
    phi = math.radians(lat)
    total = 0.0
    for name in CONSTITUENTS:
        k = _species(name)
        if k == 2:
            geo = math.cos(phi) ** 2
        else:
            geo = math.sin(2.0 * phi)
        phase = math.radians(args[name] + k * lon)
        total += eq_amps[name] * geo * math.cos(phase)
    return total


def static_lake_tide(t, lat, lon, lake_points, eq_amps, gamma2):
    """Return the tide (m) of a small closed lake at a gauge.

    A lake whose own seiche period (hours) is much shorter than the
    tidal periods (12..25 h) follows the tide potential quasi-statically.
    Its volume is conserved, so the water surface can only tilt: the
    gauge sees the equilibrium tide at the gauge minus its mean over
    the lake, scaled by the tilt factor gamma2 because the lake bed
    itself rises and falls with the body tide.
    """
    args = astronomical_arguments(t)
    here = equilibrium_tide(t, lat, lon, eq_amps, args)
    mean = sum(equilibrium_tide(t, p[0], p[1], eq_amps, args)
               for p in lake_points) / len(lake_points)
    return gamma2 * (here - mean)


def harmonic_tide(t, lon, amps, phase_lag_deg=0.0):
    """Return a harmonic tide prediction (m) from constituent amplitudes.

    The phase is the local equilibrium argument minus a Greenwich phase
    lag.  Where the real lag is unknown the caller passes 0 and the data
    file says so.
    """
    args = astronomical_arguments(t)
    total = 0.0
    for name, amp in amps.items():
        k = _species(name)
        phase = math.radians(args[name] + k * lon - phase_lag_deg)
        total += amp * math.cos(phase)
    return total


def wind_setup(speed, wind_from_deg, onshore_from_deg, fetch, depth,
               drag, rho_air, rho_water, g):
    """Return the steady wind setup (m) at the downwind gauge.

    The balance of wind stress against the surface slope gives
    eta = C_d * rho_a * U^2 * L / (rho_w * g * h).  Only the wind
    component blowing toward the gauge counts, so the effective speed is
    U * cos(angle off the onshore direction).  A negative result is a
    setdown (сгон).  The formula is linear in depth and is only valid
    while eta stays small against h.
    """
    if depth <= 0:
        raise ValueError("depth must be positive")
    off = math.radians(wind_from_deg - onshore_from_deg)
    u_eff = speed * math.cos(off)
    stress_term = drag * rho_air * u_eff * abs(u_eff)
    return stress_term * fetch / (rho_water * g * depth)


def day_of_year(t):
    """Return the fractional day of year (0-based) of a UTC datetime."""
    utc = as_utc(t)
    start = datetime(utc.year, 1, 1, tzinfo=timezone.utc)
    return (utc - start).total_seconds() / 86400.0


def monthly_interp(t, values):
    """Interpolate 12 monthly values linearly between mid-months.

    Interpolating avoids a step change at each month boundary, which
    would show up as a false jump in discharge.
    """
    doy = day_of_year(t)
    month_len = 365.2425 / 12.0
    pos = doy / month_len - 0.5
    i0 = math.floor(pos)
    frac = pos - i0
    a = values[i0 % 12]
    b = values[(i0 + 1) % 12]
    return a + (b - a) * frac


def local_solar_hour(t, lon):
    """Return the local mean solar hour (0..24) at an east longitude."""
    utc = as_utc(t)
    hours = (utc.hour + utc.minute / 60.0 + utc.second / 3600.0)
    return (hours + lon / 15.0) % 24.0


def air_temperature(t, lon, t_mean_monthly, t_half_range_monthly,
                    peak_hour):
    """Return the station air temperature (degC) for a UTC instant.

    The day is a cosine around the monthly mean with its maximum at the
    usual afternoon hour; this is the simplest shape that still puts
    the melt in the afternoon.
    """
    mean = monthly_interp(t, t_mean_monthly)
    half = monthly_interp(t, t_half_range_monthly)
    hour = local_solar_hour(t, lon)
    return mean + half * math.cos(2.0 * math.pi * (hour - peak_hour) / 24.0)


def melt_inflow(t, lon, station, melt_area_km2, melt_elev, lapse,
                ddf_mm_per_degc_day, peak_hour):
    """Return the instantaneous melt water production (m^3/s).

    Degree-day melt: melt = DDF * max(T, 0), with the temperature
    carried from the station up to the melting area by the lapse rate.
    """
    t_station = air_temperature(t, lon, station["t_mean"],
                                station["t_half"], peak_hour)
    t_melt = t_station - lapse * (melt_elev - station["elev"])
    melt_m_per_s = ddf_mm_per_degc_day * max(t_melt, 0.0) / 1000.0 / 86400.0
    return melt_area_km2 * 1.0e6 * melt_m_per_s


def routed_melt(t, lon, station, melt_area_km2, melt_elev, lapse,
                ddf_mm_per_degc_day, peak_hour, lag_h, k_h,
                quad_step_h=0.25):
    """Return melt discharge at the gauge (m^3/s) after routing.

    The water travels for ``lag_h`` hours and is then spread by a linear
    reservoir with constant ``k_h``.  The convolution integral is
    evaluated with a fixed midpoint rule so the result is deterministic.
    """
    span = 8.0 * k_h
    n = max(1, int(round(span / quad_step_h)))
    total = 0.0
    weight_sum = 0.0
    for i in range(n):
        tau = (i + 0.5) * quad_step_h
        w = math.exp(-tau / k_h)
        back = timedelta(hours=lag_h + tau)
        q = melt_inflow(t - back, lon, station, melt_area_km2, melt_elev,
                        lapse, ddf_mm_per_degc_day, peak_hour)
        total += w * q
        weight_sum += w
    # Normalising by the discrete weights keeps the volume exact even
    # though the exponential tail is cut at 8 reservoir constants.
    return total / weight_sum


def seasonal_flood(t, peak_doy, amplitude, sigma_days):
    """Return the seasonal flood stage (m above winter low water).

    A Gaussian in day of year is the simplest shape with one spring
    peak; the distance wraps around New Year so December and January
    meet smoothly.
    """
    doy = day_of_year(t)
    d = (doy - peak_doy + 182.62) % 365.2425 - 182.62
    return amplitude * math.exp(-0.5 * (d / sigma_days) ** 2)


def merian_period(length, depth, g):
    """Return the uninodal seiche period (s) by Merian's formula."""
    return 2.0 * length / math.sqrt(g * depth)
