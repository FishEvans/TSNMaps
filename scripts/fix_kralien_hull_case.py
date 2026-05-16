#!/usr/bin/env python3
import argparse
from pathlib import Path


OLD_VALUE = "starbase_Kralien"
NEW_VALUE = "starbase_kralien"


def iter_map_files(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*.json")
        if path.is_file() and path.name.lower() != "package.json"
    )


def replace_in_file(path: Path, dry_run: bool) -> int:
    try:
        original = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        original = path.read_text(encoding="utf-8", errors="replace")

    replacements = original.count(OLD_VALUE)
    if replacements == 0:
        return 0

    updated = original.replace(OLD_VALUE, NEW_VALUE)
    if not dry_run:
        path.write_text(updated, encoding="utf-8")

    return replacements


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Replace starbase_Kralien with starbase_kralien in map JSON files."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("data") / "missions" / "Map Designer",
        help="Root folder to scan recursively for map JSON files.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report changes without writing files.",
    )
    args = parser.parse_args()

    root = args.root
    if not root.exists() or not root.is_dir():
        raise SystemExit(f"Map root does not exist or is not a directory: {root}")

    files_scanned = 0
    files_changed = 0
    replacements_made = 0

    for path in iter_map_files(root):
        files_scanned += 1
        replacements = replace_in_file(path, dry_run=args.dry_run)
        if replacements == 0:
            continue
        files_changed += 1
        replacements_made += replacements
        print(f"{path}: {replacements} replacement(s)")

    mode = "Dry run" if args.dry_run else "Updated"
    print(
        f"{mode}: {replacements_made} replacement(s) across "
        f"{files_changed} file(s) scanned from {files_scanned} JSON file(s)."
    )


if __name__ == "__main__":
    main()
