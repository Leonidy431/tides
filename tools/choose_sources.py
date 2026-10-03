"""Choose the three sources the service runs side by side (chorus of the
gurus: hydrographer, geodesist, API engineer, BlueOS integrator, licence
lawyer, sceptic).

The pool is honest, not padded: SOURCES below are the real candidates the
chorus knows (16), and a choice is a TRIPLE of them (C(16,3) = 560), each
scored on six parameters of its own plus the independence of the three.
The operator asked for the best three out of 999; there are not 999 real
options, and filling the pool with invented ones is forbidden (TABOO
0.07), so the pool is 560 and this file says so.

A triple's score is the sum of its members' scores, plus 8 for every
distinct method (theory, model, observation) and 6 if one member works
offline (the vehicle is often out of reach).  The best triple that is
implemented NOW is the service; the best triple overall is the upgrade.

Parameters, 0..10 (higher is better):
    coverage   a point anywhere on the planet
    accuracy   skill for the real sea level at a coast
    offline    works without a network
    licence    open and usable in a product
    live       reachable and returning data in the sandbox probe
    upkeep     stable, maintained, documented
[В] The scores are the chorus's estimates; "live" is measured (probe of
2026-10-03: Open-Meteo answers with parameters, IOC 200, NOAA 403).

Usage: python3 tools/choose_sources.py [--json out.json]
"""
import argparse
import itertools
import json
import sys


def row(name, group, ready, cov, acc, off, lic, live, up):
    """One candidate: name, method group, implemented, six scores."""
    return (name, group, ready, dict(coverage=cov, accuracy=acc,
                                     offline=off, licence=lic, live=live,
                                     upkeep=up))


SOURCES = [
    row("equilibrium", "theory", True, 10, 3, 10, 10, 10, 10),
    row("openmeteo", "model", True, 9, 6, 0, 6, 10, 8),
    row("ioc", "observation", True, 5, 9, 0, 6, 10, 7),
    row("eot20", "model", False, 9, 8, 9, 9, 0, 6),
    row("fes2014", "model", False, 9, 9, 9, 3, 0, 7),
    row("tpxo", "model", False, 9, 9, 9, 3, 0, 8),
    row("got410", "model", False, 9, 7, 9, 8, 0, 5),
    row("noaa_coops", "observation", False, 2, 10, 0, 9, 0, 9),
    row("worldtides", "model", False, 9, 8, 0, 2, 0, 8),
    row("stormglass", "model", False, 9, 7, 0, 2, 0, 8),
    row("admiralty", "observation", False, 7, 10, 0, 1, 0, 10),
    row("copernicus", "model", False, 10, 8, 0, 7, 0, 8),
    row("nao99b", "model", False, 9, 7, 9, 6, 0, 4),
    row("uhslc", "observation", False, 5, 9, 0, 7, 0, 7),
    row("psmsl", "observation", False, 5, 2, 0, 8, 0, 8),
    row("scrape", "model", False, 6, 4, 0, 0, 0, 1),
]


def score(member):
    """A member's own score: the plain sum of its six parameters."""
    return sum(member[3].values())


def triple_score(trio):
    """Members + 8 per distinct method + 6 if one works offline."""
    groups = {m[1] for m in trio}
    offline = any(m[3]["offline"] >= 9 for m in trio)
    return sum(score(m) for m in trio) + 8 * len(groups) \
        + (6 if offline else 0)


def best(pool, ready_only):
    """The triples, highest first."""
    rows = []
    for trio in itertools.combinations(pool, 3):
        if ready_only and not all(m[2] for m in trio):
            continue
        rows.append((triple_score(trio), [m[0] for m in trio]))
    return sorted(rows, reverse=True)


def main(argv):
    """Print the pool, the best triple now and the upgrade."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json")
    args = ap.parse_args(argv)
    n = sum(1 for _ in itertools.combinations(SOURCES, 3))
    now = best(SOURCES, True)
    upgrade = best(SOURCES, False)
    print("candidates %d, triples %d (not 999: no padding)"
          % (len(SOURCES), n))
    print("best triple READY NOW:", now[0])
    print("best triple overall  :", upgrade[0])
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump({"candidates": len(SOURCES), "triples": n,
                       "ready_now": now[:5], "overall": upgrade[:5],
                       "note": "scores are the chorus's estimates [В]"},
                      fh, ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
