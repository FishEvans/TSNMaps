"""Required silent game-compatibility migrations, independent of Tk.

Successful corrections intentionally persist on load. Keep these separate from
user edits and undo history; warning lists are presented by the calling UI.
Name migrations and incoming gate references are handled by SystemMap.migrate_names.
"""
from MapTypes import DEFAULT_PLANET_CLASS


def migrate_legacy_structure(system):
    # ── Normalize old relay entries (bare lists) into dicts ───────────────
    sr = system.data.get('sensor_relay', {})
    for key, val in list(sr.items()):
        if isinstance(val, list):
            sr[key] = {'coordinate': val}

    # ── Migrate legacy "jump_point" types to "jumpnode"/"jumppoint" ───
    migrated = False
    for obj_key, obj in system.data.get('objects', {}).items():
        if obj.get('type') == 'jump_point':
            st = obj.get('state', '')
            # fix typo in state
            if st == 'Unteathered':
                obj['state'] = 'Untethered'
                st = 'Untethered'
            # Map by state.
            if st == 'Tethered':
                obj['type'] = 'jumpnode'
            elif st == 'Untethered':
                obj['type'] = 'jumppoint'
            migrated = True

    if migrated:
        # Persist the silent migration immediately.
        system.save()

    # ── Ensure asteroid fields have default composition ──────────────
    comp_changed = False
    for tkey, feat in system.data.get('terrain', {}).items():
        if feat.get('type', '').lower() == 'asteroids':
            # If missing or empty, assign default composition.
            if not feat.get('composition'):
                feat['composition'] = ['Ast. Std Rand']
                comp_changed = True
    if comp_changed:
        # Silently persist the added compositions.
        system.save()


def migrate_sides(system, valid_sides):
    """
    On load, silently fix common side typos and warn about anything else invalid.
      - 'TSN'     → 'USFP'
      - 'pirate'  → 'Pirate'
    Only checks objects of type: station, platform, static.
    Warnings list any remaining sides not in Settings.json Races.
    """
    fset = set(valid_sides)
    remap = {'tsn': 'USFP', 'pirate': 'Pirate'}
    changed = False
    issues = []
    for obj_name in system.list_objects():
        obj = system.get_object(obj_name)
        otype = (obj.get('type') or '').lower()
        if otype not in ('station', 'platform', 'static'):
            continue
        sides = obj.get('sides')
        if not isinstance(sides, list) or not sides:
            continue
        # apply silent remaps
        new_sides = []
        for s in sides:
            s2 = remap.get(str(s).lower(), s)
            if s2 != s:
                changed = True
            new_sides.append(s2)
        obj['sides'] = new_sides
        # flag anything not in the allowed list
        for s in new_sides:
            if s not in fset:
                issues.append(f"{obj_name}: invalid side '{s}'")
    if changed:
        # persist silent fixes immediately
        system.save()
    return issues


def migrate_planet_classes(system, valid_planet_classes):
    valid_class_set = set(valid_planet_classes)
    changed = False
    issues = []
    for terrain_key, feat in system.data.get('terrain', {}).items():
        if not isinstance(feat, dict):
            continue
        if str(feat.get('type', '')).lower() != 'planet':
            continue
        cls = feat.get('class')
        if not isinstance(cls, str) or not cls.strip():
            feat['class'] = DEFAULT_PLANET_CLASS
            cls = DEFAULT_PLANET_CLASS
            changed = True
        else:
            cls = cls.strip()
            if cls != feat.get('class'):
                feat['class'] = cls
                changed = True
        if valid_class_set and cls not in valid_class_set:
            display_name = feat.get('name', terrain_key)
            issues.append(f"{terrain_key} ({display_name}): invalid planet class '{cls}'")
    if changed:
        system.save()
    return issues
