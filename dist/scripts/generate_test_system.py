import argparse
import json
import math
from datetime import date
from pathlib import Path


DEFAULT_SHIPMAP = Path("HTML") / "Images" / "Ships" / "ShipMap.json"
DEFAULT_OUT = Path("data") / "exports" / "AAATestSystem.json"
PLANET_CLUSTER_OFFSET = 40000.0
PLANET_SPACING = 25000.0


def normalize_roles(entry):
    roles = set()
    raw_roles = entry.get("roles")
    if isinstance(raw_roles, str):
        roles.update(r.strip().lower() for r in raw_roles.split(",") if r.strip())
    elif isinstance(raw_roles, list):
        roles.update(str(r).strip().lower() for r in raw_roles if str(r).strip())
    raw_role = entry.get("role")
    if isinstance(raw_role, str) and raw_role.strip():
        roles.add(raw_role.strip().lower())
    return roles


def load_shipmap(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Failed to read ShipMap: {path} ({exc})")
    if not isinstance(data, list):
        raise SystemExit(f"ShipMap is not a list: {path}")
    return data


def collect_spawn_entries(entries):
    station_hulls = []
    platform_hulls = []
    static_hulls = []
    planets = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        key = entry.get("key")
        if not key:
            continue
        roles = normalize_roles(entry)
        if "planet" in roles:
            name = entry.get("name")
            if not isinstance(name, str) or not name.strip():
                name = key
            description = entry.get("long_desc")
            if not isinstance(description, str):
                description = ""
            planets.append(
                {
                    "key": key,
                    "name": name.strip(),
                    "description": description.strip(),
                }
            )
            continue
        if "station" in roles:
            station_hulls.append(key)
        if "platform" in roles:
            platform_hulls.append(key)
        if "static" in roles:
            static_hulls.append(key)

    spawns = []
    station_hulls_set = set(station_hulls)
    static_only_hulls = [key for key in static_hulls if key not in station_hulls_set]

    for key in station_hulls:
        spawns.append(("station", key))

    for key in platform_hulls:
        spawns.append(("platform", key))

    for key in static_only_hulls:
        spawns.append(("station", key))
    counts = {
        "stations": len(station_hulls) + len(static_only_hulls),
        "platforms": len(platform_hulls),
        "statics": len(static_only_hulls),
        "planets": len(planets),
    }
    return spawns, planets, counts


def make_unique_name(base, obj_type, used):
    name = base
    if name in used:
        name = f"{base} ({obj_type})"
    if name in used:
        suffix = 2
        while f"{base} ({obj_type} {suffix})" in used:
            suffix += 1
        name = f"{base} ({obj_type} {suffix})"
    used.add(name)
    return name


def build_objects(spawns, spacing, per_row):
    objects = {}
    used_names = set()
    for idx, (obj_type, hull) in enumerate(spawns):
        row = idx // per_row
        col = idx % per_row
        x = float(col * spacing)
        z = float(row * spacing)
        obj = {
            "coordinate": [x, 0, z],
            "sides": ["USFP"],
            "hull": hull,
            "type": obj_type,
        }
        if obj_type == "station":
            obj.update(
                {
                    "facilities": [],
                    "cargo": {},
                    "teams": {},
                    "description": "",
                }
            )
        else:
            obj.update(
                {
                    "cargo": {},
                    "teams": {},
                }
            )
        name = make_unique_name(hull, obj_type, used_names)
        objects[name] = obj
    return objects


def build_planets(planets):
    if not planets:
        return {}

    per_row = max(1, math.ceil(math.sqrt(len(planets))))
    terrain_planets = {}
    for idx, planet in enumerate(planets):
        row = idx // per_row
        col = idx % per_row
        x = float(PLANET_CLUSTER_OFFSET + (col * PLANET_SPACING))
        z = float(PLANET_CLUSTER_OFFSET + (row * PLANET_SPACING))
        terrain_planets[f"planet_{idx + 1:03d}"] = {
            "type": "planet",
            "name": planet["name"],
            "coordinate": [x, 0, z],
            "description": planet["description"],
            "class": planet["key"],
        }

    return terrain_planets


def build_terrain(planets):
    base_z = -10000.0
    terrain = {
        "Test Asteroid Field": {
            "type": "asteroids",
            "seed": 2010,
            "start": [-20000.0, 0, base_z],
            "end": [-30000.0, 0, base_z],
            "density": 200,
            "scatter": 5000,
            "composition": ["Ast. Std Rand"],
        },
        "Test Nebula": {
            "type": "nebulas",
            "seed": 2010,
            "start": [-35000.0, 0, base_z],
            "end": [-45000.0, 0, base_z],
            "density": 200,
            "scatter": 5000,
            "composition": [],
        },
        "Test Debris Field": {
            "type": "debris_field",
            "seed": 2010,
            "coordinate": [-50000.0, 0, base_z],
            "density": 50,
            "scatter": 5000,
        },
        "Test Black Hole": {
            "type": "blackhole",
            "name": "Test Black Hole",
            "coordinate": [-60000.0, 0, base_z],
            "size": 1000,
            "strength": 500,
        },
    }
    terrain.update(build_planets(planets))
    return terrain


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Generate a test system with one of each station and platform hull, "
            "plus planet terrain entries, all forced to the USFP side."
        )
    )
    parser.add_argument(
        "--shipmap",
        type=Path,
        default=DEFAULT_SHIPMAP,
        help="Path to ShipMap.json.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help="Output system JSON path.",
    )
    parser.add_argument(
        "--spacing",
        type=float,
        default=1000.0,
        help="Distance between successive objects.",
    )
    parser.add_argument(
        "--per-row",
        type=int,
        default=10,
        help="Number of objects per row.",
    )
    args = parser.parse_args()
    if args.per_row <= 0:
        raise SystemExit("--per-row must be a positive integer.")

    entries = load_shipmap(args.shipmap)
    spawns, planets, counts = collect_spawn_entries(entries)
    if not spawns and not planets:
        raise SystemExit("No station/platform/static/planet hulls found in ShipMap.")

    objects = build_objects(spawns, args.spacing, args.per_row)
    terrain = build_terrain(planets)
    terrain_features = len(terrain) - counts["planets"]
    generated_on = date.today().isoformat()

    payload = {
        "systemMapCoord": [0, 0, 0],
        "systemalignment": "USFP",
        "metadata": {
            "sysdescription": (
                "Autogenerated TestSystem. Generated "
                f"{generated_on}. Stations: {counts['stations']}. "
                f"Platforms: {counts['platforms']}. "
                f"Statics: {counts['statics']}. "
                f"Planets: {counts['planets']}. "
                f"Terrain: {terrain_features}."
            )
        },
        "objects": objects,
        "sensor_relay": {},
        "terrain": terrain,
        "traffic": {},
    }

    out_path = args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=4), encoding="utf-8")

    print(
        f"Wrote {len(objects)} objects "
        f"({counts['stations']} stations, "
        f"{counts['platforms']} platforms, "
        f"{counts['statics']} statics), "
        f"{counts['planets']} planets, and "
        f"{terrain_features} terrain items to {out_path}"
    )


if __name__ == "__main__":
    main()
