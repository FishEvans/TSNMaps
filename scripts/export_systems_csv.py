import argparse
import json
from pathlib import Path


def normalize_system_name(name):
    if name is None:
        return ""
    value = str(name).strip()
    if value.lower().endswith(".json"):
        value = value[:-5]
    return value


def normalize_list(values):
    if not isinstance(values, list):
        return []
    cleaned = [str(v) for v in values if v not in (None, "")]
    return sorted(cleaned, key=str.lower)


def format_jump_entry(gate_name, dest_system, dest_gate):
    return {
        "gate": gate_name,
        "dest_system": dest_system or "Unknown",
        "dest_gate": dest_gate or "",
    }


def collect_jump_entries(objects):
    unhidden = []
    hidden = []
    if not isinstance(objects, dict):
        return unhidden, hidden
    for gate_name, gate_data in objects.items():
        if not isinstance(gate_data, dict):
            continue
        if gate_data.get("type") not in ("jumpnode", "jumppoint"):
            continue
        is_hidden = bool(gate_data.get("hideonmap", False))
        destinations = gate_data.get("destinations")
        if isinstance(destinations, dict) and destinations:
            for dest_gate, dest_system in destinations.items():
                entry = format_jump_entry(
                    gate_name,
                    normalize_system_name(dest_system),
                    normalize_system_name(dest_gate),
                )
                (hidden if is_hidden else unhidden).append(entry)
        else:
            entry = format_jump_entry(gate_name, "", "")
            (hidden if is_hidden else unhidden).append(entry)
    return unhidden, hidden


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


def main():
    parser = argparse.ArgumentParser(
        description="Export system overview JSON with faction, assets, exports, and jumps."
    )
    parser.add_argument(
        "--systems-dir",
        default=Path("data") / "missions" / "Map Designer" / "Terrain",
        type=Path,
        help="Directory containing system JSON files.",
    )
    parser.add_argument(
        "--out",
        default=Path("data") / "exports" / "systems_overview.json",
        type=Path,
        help="Output JSON path.",
    )
    args = parser.parse_args()

    systems_dir = args.systems_dir
    systems = load_systems(systems_dir)
    if not systems:
        raise SystemExit(f"No system JSON files found in {systems_dir}")

    out_path = args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)

    payload = []
    for system_name in sorted(systems.keys(), key=str.lower):
        data = systems[system_name]
        meta = data.get("metadata", {}) if isinstance(data.get("metadata"), dict) else {}
        intel = meta.get("intel", {}) if isinstance(meta.get("intel"), dict) else {}
        assets = normalize_list(intel.get("assets", []))
        exports = normalize_list(meta.get("exports", []))
        objects = data.get("objects", {})
        unhidden, hidden = collect_jump_entries(objects)
        payload.append(
            {
                "system": system_name,
                "faction": data.get("systemalignment", "Unknown"),
                "strategic_assets": assets,
                "exports": exports,
                "unhidden_jumps": unhidden,
                "hidden_jumps": hidden,
            }
        )
    with out_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


if __name__ == "__main__":
    main()
