#!/usr/bin/env python3
import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


DEFAULT_ROOT = Path("data") / "missions" / "Map Designer" / "Terrain"
TARGET_OBJECT_TYPES = {"station", "platform"}
TARGET_CARGO_KEYS = {"Data Core", "Data Chip", "Black Box"}
TARGET_CARGO_KEY_LOOKUP = {key.casefold(): key for key in TARGET_CARGO_KEYS}


def iter_system_files(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*.json")
        if path.is_file() and path.name.lower() != "package.json"
    )


def remove_target_cargo(cargo: dict[str, Any]) -> Counter[str]:
    removed: Counter[str] = Counter()
    for key in list(cargo.keys()):
        target_name = TARGET_CARGO_KEY_LOOKUP.get(str(key).strip().casefold())
        if target_name is None:
            continue
        removed[target_name] += 1
        del cargo[key]
    return removed


def clean_system_file(path: Path, dry_run: bool) -> tuple[bool, int, Counter[str]]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    if not isinstance(data, dict):
        return False, 0, Counter()

    objects = data.get("objects")
    if not isinstance(objects, dict):
        return False, 0, Counter()

    changed_objects = 0
    removed_totals: Counter[str] = Counter()

    for obj in objects.values():
        if not isinstance(obj, dict):
            continue
        obj_type = str(obj.get("type", "")).strip().lower()
        if obj_type not in TARGET_OBJECT_TYPES:
            continue
        cargo = obj.get("cargo")
        if not isinstance(cargo, dict):
            continue

        removed = remove_target_cargo(cargo)
        if removed:
            changed_objects += 1
            removed_totals.update(removed)

    if not removed_totals:
        return False, 0, Counter()

    if not dry_run:
        with path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=4)

    return True, changed_objects, removed_totals


def format_counts(counts: Counter[str]) -> str:
    return ", ".join(
        f"{key}: {counts[key]}" for key in sorted(counts) if counts[key]
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Remove Data Core, Data Chip, and Black Box cargo entries from all "
            "station/platform objects in system JSON files."
        )
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=DEFAULT_ROOT,
        help="Root folder to scan recursively for system JSON files.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report changes without writing files.",
    )
    args = parser.parse_args()

    root = args.root
    if not root.exists() or not root.is_dir():
        raise SystemExit(f"System root does not exist or is not a directory: {root}")

    files_scanned = 0
    files_changed = 0
    objects_changed = 0
    total_removed: Counter[str] = Counter()
    failed_files: list[tuple[Path, str]] = []

    for path in iter_system_files(root):
        files_scanned += 1
        try:
            updated, changed_objects, removed = clean_system_file(
                path,
                dry_run=args.dry_run,
            )
        except (OSError, json.JSONDecodeError) as exc:
            failed_files.append((path, str(exc)))
            continue

        if not updated:
            continue

        files_changed += 1
        objects_changed += changed_objects
        total_removed.update(removed)
        print(
            f"{path}: removed {format_counts(removed)} "
            f"from {changed_objects} object(s)"
        )

    mode = "Dry run" if args.dry_run else "Updated"
    print(
        f"{mode}: removed {format_counts(total_removed) or '0 cargo entries'} "
        f"from {objects_changed} station/platform object(s) across "
        f"{files_changed} file(s), scanned {files_scanned} JSON file(s)."
    )

    if failed_files:
        print("Failed files:")
        for path, error in failed_files:
            print(f"  {path}: {error}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
