#!/usr/bin/env python3
import os
import shutil
import json
import io
import re
import sys
import random

APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# — CONFIGURE THESE if needed —
SHIP_FILE     = 'shipData.yaml'       # path to your YAML/HJSON/JSON file
SRC_ROOT      = os.path.join('graphics', 'ships')  # where your source images live
DEST_ROOT     = os.path.join(APP_ROOT, 'HTML', 'Images', 'Ships')  # output tree + ShipMap.json
IMAGE_SIZES   = ['256', '1024']       # suffixes to copy


class ValidationError(Exception):
    pass

# Helper: tolerant loader for YAML/HJSON/JSON with comments and trailing commas
def _strip_comments_and_commas(text: str) -> str:
    # Remove inline '#' comments outside strings, and trailing commas.
    def _strip_hash_comments(s):
        out=[]; in_str=False; quote=''; esc=False; i=0
        while i<len(s):
            ch=s[i]
            if in_str:
                out.append(ch)
                if esc: esc=False
                elif ch=='\\': esc=True
                elif ch==quote: in_str=False
                i+=1; continue
            else:
                if ch in ('"', "'"):
                    in_str=True; quote=ch; out.append(ch); i+=1; continue
                if ch=='#':
                    while i<len(s) and s[i]!='\n': i+=1
                    continue
                out.append(ch); i+=1
        return ''.join(out)
    s = _strip_hash_comments(text)
    import re as _re
    s = _re.sub(r',\s*([\]\}])', r'\1', s)
    return s

def load_data(path):
    ext = os.path.splitext(path)[1].lower()
    with open(path, 'r', encoding='utf-8') as fp:
        raw = fp.read()
    # If YAML-ish with braces, carve out the main object from first '{' to last '}'
    if ext in ('.yaml', '.yml'):
        start = raw.find('{')
        end = raw.rfind('}')
        if start != -1 and end != -1 and end > start:
            raw = raw[start:end+1]
        raw = _strip_comments_and_commas(raw)
        try:
            import hjson as _hjson  # optional
            return _hjson.loads(raw)
        except Exception:
            return json.loads(raw)
    else:
        # Try HJSON first (comments tolerated), else plain JSON
        try:
            import hjson as _hjson
            with open(path, 'r', encoding='utf-8') as fp:
                return _hjson.load(fp)
        except ImportError:
            with open(path, 'r', encoding='utf-8') as fp:
                return json.load(fp)

def _max_beam_range(entry):
    """
    Return the largest beam range found on the entry, supporting both:
      - 'hull_port_sets': { 'beam ...': [ { range: ... }, ... ], ... }
      - 'hull_portsets' (list form used by some entries): [{ type:'beam', range: ... }, ...]
    If no beam ports are present, return None.
    """
    best = None
    # Dict style (common)
    hps = entry.get('hull_port_sets')
    if isinstance(hps, dict):
        for group_name, ports in hps.items():
            if isinstance(group_name, str) and 'beam' in group_name.lower() and isinstance(ports, list):
                for p in ports:
                    try:
                        rng = p.get('range')
                        if isinstance(rng, (int, float)):
                            best = rng if best is None else max(best, rng)
                    except AttributeError:
                        pass
    # List style (e.g., some biomech entries)
    hps_list = entry.get('hull_portsets')
    if isinstance(hps_list, list):
        for ps in hps_list:
            try:
                if str(ps.get('type', '')).lower() == 'beam':
                    rng = ps.get('range')
                    if isinstance(rng, (int, float)):
                        best = rng if best is None else max(best, rng)
            except AttributeError:
                pass
    return best


def _get_ship_entries(data):
    ships = data.get('#ship-list') or data.get('ship-list') or []
    return ships if isinstance(ships, list) else []


def _normalize_roles(roles):
    if isinstance(roles, str):
        return [r.strip().lower() for r in re.split(r'[,\s]+', roles) if r.strip()]
    if isinstance(roles, list):
        return [str(r).strip().lower() for r in roles if str(r).strip()]
    return []


def _get_image_paths(artroot, src_root, dest_root):
    parts = re.split(r'[\\/]+', artroot.strip().strip('/\\'))
    root_name = parts[-1]
    dest_sub = os.path.join(dest_root, *parts[:-1])
    image_pairs = []
    for size in IMAGE_SIZES:
        src_file = os.path.join(src_root, *parts[:-1], f"{root_name}{size}.png")
        dest_file = os.path.join(dest_sub, f"{root_name}{size}.png")
        image_pairs.append((src_file, dest_file))
    return parts, root_name, dest_sub, image_pairs


def resolve_paths(game_executable_path=None):
    ship_file = SHIP_FILE
    src_root = SRC_ROOT

    if game_executable_path:
        game_path = os.path.abspath(game_executable_path)
        game_root = os.path.dirname(game_path) if os.path.isfile(game_path) else game_path
        ship_file = os.path.join(game_root, 'Data', 'shipData.yaml')
        src_root = os.path.join(game_root, 'Data', SRC_ROOT)

    return ship_file, src_root, DEST_ROOT


def validate_source_data(game_executable_path=None, sample_size=5):
    ship_file, src_root, dest_root = resolve_paths(game_executable_path)

    if not os.path.isfile(ship_file):
        raise ValidationError(f"Ship data file not found: {ship_file}")
    if not os.access(ship_file, os.R_OK):
        raise ValidationError(f"Ship data file is not readable: {ship_file}")

    try:
        data = load_data(ship_file)
    except Exception as exc:
        raise ValidationError(f"Ship data file could not be read: {ship_file}\n{exc}") from exc

    ships = _get_ship_entries(data)
    if not ships:
        raise ValidationError("No '#ship-list' found in ship data.")

    candidates = [
        entry for entry in ships
        if (
            isinstance(entry, dict)
            and entry.get('key')
            and entry.get('artfileroot')
            and 'ship' in _normalize_roles(entry.get('roles', []))
        )
    ]
    if not candidates:
        raise ValidationError("No valid entries with role 'Ship' and an art file root were found.")

    sample_count = min(sample_size, len(candidates))
    sampled_entries = random.sample(candidates, sample_count)
    missing_images = []

    for entry in sampled_entries:
        artroot = entry['artfileroot']
        _, _, _, image_pairs = _get_image_paths(artroot, src_root, dest_root)
        for src_file, _ in image_pairs:
            if not os.path.isfile(src_file):
                missing_images.append(f"{entry.get('key')}: missing {src_file}")

    if missing_images:
        raise ValidationError(
            "Validation failed while checking sampled ship images:\n" + "\n".join(missing_images[:10])
        )

    return {
        'data': data,
        'ships': ships,
        'ship_file': ship_file,
        'src_root': src_root,
        'dest_root': dest_root,
        'sample_count': sample_count,
    }


def main(game_executable_path=None):
    context = validate_source_data(game_executable_path)
    data = context['data']
    ships = context['ships']
    src_root = context['src_root']
    dest_root = context['dest_root']

    if os.path.isdir(dest_root):
        shutil.rmtree(dest_root)

    # 2) Prepare output structures
    os.makedirs(dest_root, exist_ok=True)
    shipmap = []

    for entry in ships:
        key       = entry.get('key')
        name      = entry.get('name')
        side      = entry.get('side', '')
        artroot   = entry.get('artfileroot', '')
        long_desc = entry.get('long_desc', '')
        roles     = entry.get('roles', [])

        if not artroot or not key:
            print(f"– Skipping invalid entry: {entry}")
            continue

        parts, root_name, dest_sub, image_pairs = _get_image_paths(artroot, src_root, dest_root)
        os.makedirs(dest_sub, exist_ok=True)

        # Copy each size (include subfolders on the source path)
        for src_file, dest_file in image_pairs:
            if os.path.exists(src_file):
                shutil.copy2(src_file, dest_file)
                print(f"✅ Copied {src_file} → {dest_file}")
            else:
                print(f"⚠️  Missing {src_file}")

        # Append entry to output map
        out_entry = {
            'key': key,
            'name': name,
            'side': side,
            'artfileroot': artroot,
            'long_desc': long_desc,
            'roles': roles
        }
        # If roles include 'station' or 'static', add BRange and/or DRange
        roles_list = _normalize_roles(roles)

        if any(r in ('station', 'static') for r in roles_list):
            # Largest beam range, if any
            br = _max_beam_range(entry)
            if isinstance(br, (int, float)):
                out_entry['BRange'] = br
            # Drone launch timer > 0 -> DRange
            dlt = entry.get('drone_launch_timer')  # per example data
            if isinstance(dlt, (int, float)) and dlt > 0:
                out_entry['DRange'] = dlt

        shipmap.append(out_entry)

    # 3) Write out ShipMap.json
    shipmap_path = os.path.join(dest_root, 'ShipMap.json')
    with open(shipmap_path, 'w', encoding='utf-8') as out:
        json.dump(shipmap, out, indent=2, ensure_ascii=False)
    print(f"\n🎉 ShipMap.json written to {shipmap_path}")


if __name__ == '__main__':
    main()
