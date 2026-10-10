"""Shared map validation and gate-reference rules."""
import json
import copy
import math
from pathlib import Path
import re


JUMP_TYPES = frozenset({'jumpnode', 'jumppoint', 'jump_point'})


def normalize_legacy_names(data):
    """Plan the game's hyphen-to-space migration without overwriting entries."""
    # Required main-game naming conformity: legacy object, relay and terrain
    # names containing hyphens must be corrected when encountered. This is an
    # intentional silent migration, not optional cosmetic cleanup.
    migrated = copy.deepcopy(data)
    renames = {}
    for category in ('objects', 'sensor_relay', 'terrain'):
        entries = migrated.get(category, {})
        occupied = {name.casefold() for name in entries}
        category_renames = {}
        for old in list(entries):
            if '-' not in old:
                continue
            base = old.replace('-', ' ')
            new = base
            suffix = 2
            # Keep existing entries intact if the compliant name is occupied;
            # the returned mapping lets gate references follow the unique name.
            while new.casefold() in occupied:
                new = f'{base} {suffix}'
                suffix += 1
            occupied.add(new.casefold())
            entries[new] = entries.pop(old)
            category_renames[old] = new
        if category_renames:
            renames[category] = category_renames
    return migrated, renames


def is_gate(obj):
    return isinstance(obj, dict) and str(obj.get('type', '')).strip().casefold() in JUMP_TYPES


def system_key(name):
    name = str(name or '').strip().casefold()
    return name[:-5] if name.endswith('.json') else name


def validate_map_coordinate(value):
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError('systemMapCoord must contain exactly three numbers (X, Y, Z).')
    try:
        invalid = any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in value)
    except OverflowError:
        invalid = True
    if invalid:
        raise ValueError('systemMapCoord must contain three finite numbers (X, Y, Z).')
    return list(value)


def parse_map_coordinate_fields(values, previous):
    """Preserve untouched numbers exactly, including large integer coordinates."""
    if len(values) != 3 or len(previous) != 3:
        raise ValueError('Enter exactly three coordinates (X, Y, Z).')
    parsed = [old if text == str(old) else float(text)
              for text, old in zip(values, previous)]
    return validate_map_coordinate(parsed)


def read_system_documents(folder):
    documents, originals = {}, {}
    for path in sorted(Path(folder).resolve().iterdir()):
        if path.suffix.casefold() != '.json' or path.name.casefold() in {'package.json', 'galmapinfo.json'}:
            continue
        raw = path.read_bytes()
        try:
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError('Expected a JSON object')
            if not isinstance(data.get('objects', {}), dict):
                raise ValueError('objects must be a JSON object')
        except (ValueError, UnicodeError) as exc:
            raise ValueError(f'{path.name}: {exc}') from exc
        documents[path] = data
        originals[path] = raw
    return documents, originals


def rewrite_gate_references(data, target_system, renames):
    names = {old.casefold(): new for old, new in renames.items()}
    changed = False
    for obj in data.get('objects', {}).values():
        if not is_gate(obj) or not isinstance(obj.get('destinations'), dict):
            continue
        rewritten = {}
        for gate_name, system in obj['destinations'].items():
            new_name = names.get(gate_name.casefold(), gate_name) if system_key(system) == system_key(target_system) else gate_name
            if new_name in rewritten:
                raise ValueError(f'Renaming would overwrite destination {new_name!r}.')
            rewritten[new_name] = system
        if rewritten != obj['destinations']:
            obj['destinations'] = rewritten
            changed = True
    return changed


def name_mentions_system(gate_name, system_name):
    # Match full names, including multi-word names, without Alpha matching
    # Alphabet. Treat punctuation and whitespace as word separators.
    words = re.findall(r'\w+', system_name.casefold())
    gate_words = re.findall(r'\w+', gate_name.casefold())
    return bool(words) and any(gate_words[i:i + len(words)] == words
                               for i in range(len(gate_words) - len(words) + 1))


def find_gate_candidates(documents, source_name, gate_name):
    candidates = []
    for path, data in documents.items():
        if system_key(path.stem) == system_key(source_name):
            continue
        if not name_mentions_system(gate_name, path.stem):
            continue
        for name, obj in data.get('objects', {}).items():
            if is_gate(obj) and name_mentions_system(name, source_name):
                candidates.append((path, name))
    return candidates
