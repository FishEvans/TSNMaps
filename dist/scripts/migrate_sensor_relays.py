#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
from typing import Any


EXCLUDE_FILES = {"package.json", "galmapinfo.json"}
DEFAULT_ROOT = Path("data") / "missions" / "Map Designer"
WARNING_PREFIX = "NAV HAZ"
SENSOR_RELAY_TYPE = "Sensor Relay"
WARNING_BUOY_TYPE = "Warning Buoy"
WARNING_BROADCAST = "Keep Clear"
WARNING_PING = 2
WARNING_RANGE = 12000


def iter_map_files(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*.json")
        if path.is_file() and path.name.lower() not in EXCLUDE_FILES
    )


def normalize_coordinate(value: Any) -> list[Any]:
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        return [value[0], value[1], value[2]]
    return [0, 0, 0]


def migrate_relay(name: str, entry: Any) -> dict[str, Any]:
    if isinstance(entry, dict):
        migrated = dict(entry)
        migrated["coordinate"] = normalize_coordinate(migrated.get("coordinate"))
    else:
        migrated = {"coordinate": normalize_coordinate(entry)}

    if name.upper().startswith(WARNING_PREFIX):
        migrated["type"] = WARNING_BUOY_TYPE
        migrated["broadcast"] = WARNING_BROADCAST
        migrated["ping"] = WARNING_PING
        migrated["range"] = WARNING_RANGE
    else:
        migrated["type"] = SENSOR_RELAY_TYPE
        migrated.pop("broadcast", None)
        migrated.pop("ping", None)
        migrated.pop("range", None)

    return migrated


def migrate_file(path: Path, dry_run: bool) -> tuple[bool, int]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    if not isinstance(data, dict):
        return False, 0

    sensor_relays = data.get("sensor_relay")
    if not isinstance(sensor_relays, dict):
        return False, 0

    changed = 0
    updated_relays: dict[str, Any] = {}
    for name, entry in sensor_relays.items():
        migrated = migrate_relay(name, entry)
        updated_relays[name] = migrated
        if migrated != entry:
            changed += 1

    if changed == 0:
        return False, 0

    data["sensor_relay"] = updated_relays
    if not dry_run:
        with path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=4)

    return True, changed


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Convert legacy sensor relay entries to the new relay format and "
            "upgrade NAV HAZ relays to Warning Buoy entries."
        )
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=DEFAULT_ROOT,
        help="Root folder to scan recursively for map JSON files.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report the files that would change without writing them.",
    )
    args = parser.parse_args()

    root = args.root
    if not root.exists() or not root.is_dir():
        raise SystemExit(f"Map root does not exist or is not a directory: {root}")

    files_scanned = 0
    files_changed = 0
    relays_changed = 0

    for path in iter_map_files(root):
        files_scanned += 1
        updated, changed = migrate_file(path, dry_run=args.dry_run)
        if not updated:
            continue
        files_changed += 1
        relays_changed += changed
        print(f"{path}: {changed} relay entr{'y' if changed == 1 else 'ies'} updated")

    mode = "Dry run" if args.dry_run else "Updated"
    print(
        f"{mode}: {relays_changed} relay entr{'y' if relays_changed == 1 else 'ies'} "
        f"across {files_changed} file(s) scanned from {files_scanned} JSON file(s)."
    )


if __name__ == "__main__":
    main()
