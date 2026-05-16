import argparse
import json
from collections import deque
from pathlib import Path


def normalize_system_name(name):
    if name is None:
        return ""
    value = str(name).strip()
    if value.lower().endswith(".json"):
        value = value[:-5]
    return value


def load_systems(systems_dir):
    systems = {}
    for path in sorted(systems_dir.glob("*.json"), key=lambda p: p.name.lower()):
        if path.name.lower() == "package.json":
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict) and "systemMapCoord" in data:
            systems[path.stem] = data
    return systems


def build_adjacency(systems, include_hidden=True):
    name_map = {name.lower(): name for name in systems.keys()}
    adjacency = {name: set() for name in systems.keys()}
    for system_name, data in systems.items():
        objects = data.get("objects", {})
        if not isinstance(objects, dict):
            continue
        for gate_data in objects.values():
            if not isinstance(gate_data, dict):
                continue
            if gate_data.get("type") not in ("jumpnode", "jumppoint"):
                continue
            if not include_hidden and gate_data.get("hideonmap", False):
                continue
            destinations = gate_data.get("destinations")
            if not isinstance(destinations, dict):
                continue
            for dest_system in destinations.values():
                dest_name = normalize_system_name(dest_system)
                if not dest_name:
                    continue
                dest_key = dest_name.lower()
                if dest_key not in name_map:
                    continue
                canonical_dest = name_map[dest_key]
                adjacency[system_name].add(canonical_dest)
                adjacency[canonical_dest].add(system_name)
    return adjacency


def bfs_distances(start, adjacency):
    distances = {start: 0}
    queue = deque([start])
    while queue:
        current = queue.popleft()
        for neighbor in adjacency.get(current, ()):
            if neighbor in distances:
                continue
            distances[neighbor] = distances[current] + 1
            queue.append(neighbor)
    return distances


def main():
    parser = argparse.ArgumentParser(
        description="Export a jump-distance table JSON (shortest hop counts)."
    )
    parser.add_argument(
        "--systems-dir",
        default=Path("data") / "missions" / "Map Designer" / "Terrain",
        type=Path,
        help="Directory containing system JSON files.",
    )
    parser.add_argument(
        "--out",
        default=Path("data") / "exports" / "jump_table.json",
        type=Path,
        help="Output JSON path.",
    )
    parser.add_argument(
        "--exclude-hidden",
        action="store_true",
        help="Exclude jumps with hideonmap=true from the hop graph.",
    )
    args = parser.parse_args()

    systems_dir = args.systems_dir
    systems = load_systems(systems_dir)
    if not systems:
        raise SystemExit(f"No system JSON files found in {systems_dir}")

    adjacency = build_adjacency(systems, include_hidden=not args.exclude_hidden)
    system_names = sorted(systems.keys(), key=str.lower)

    out_path = args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)

    distances_table = {}
    for src in system_names:
        distances = bfs_distances(src, adjacency)
        row = {}
        for dst in system_names:
            if src == dst:
                row[dst] = 0
            elif dst in distances:
                row[dst] = distances[dst]
            else:
                row[dst] = "-"
        distances_table[src] = row

    payload = {
        "systems": system_names,
        "include_hidden": not args.exclude_hidden,
        "distances": distances_table,
    }
    with out_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


if __name__ == "__main__":
    main()
