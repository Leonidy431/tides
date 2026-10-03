"""Bake a level series to a JSON file for offline use (e.g. Godot).

Usage::

    python -m app.bake --site issyk_kul_cholpon_ata \
        --start 2026-07-15T00:00:00Z --hours 72 --step-min 30 \
        --out issyk.json

The file has the same shape as GET /v1.0/level, so a game can read the
live API or a baked file with one parser.
"""

import argparse
import json

from app import main


def run(argv=None):
    """Parse arguments, compute the series and write the JSON file."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--site", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--hours", type=float, default=48.0)
    parser.add_argument("--step-min", type=float, default=30.0)
    parser.add_argument("--wind-speed", type=float, default=0.0)
    parser.add_argument("--wind-from", type=float, default=0.0)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    data = main.level(args.site, args.start, args.hours, args.step_min,
                      args.wind_speed, args.wind_from)
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=1)
    return args.out


if __name__ == "__main__":
    print(run())
