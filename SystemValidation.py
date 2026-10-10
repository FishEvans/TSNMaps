"""Read-only system validation; callers choose how to display the reports."""
import json
import math
from MapMetadata import get_incoming_only_gate_list
from MapTypes import is_zone_type


def is_number_like(value):
    if isinstance(value, bool):
        return False
    if not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(float(value))
    except Exception:
        return False


def validate_coordinate_value(value, label, issues, required_len=3):
    if not isinstance(value, (list, tuple)) or len(value) < required_len:
        issues.append(f"{label}: expected a coordinate list with at least {required_len} values.")
        return False
    ok = True
    for idx in range(required_len):
        if is_number_like(value[idx]):
            continue
        issues.append(f"{label}: coordinate index {idx} is not a finite number ({value[idx]!r}).")
        ok = False
    return ok


def collect_cargo_team_validation_issues(data, ct_config):
    cargo_set = set(ct_config.get('cargo', []))
    team_set  = set(ct_config.get('teams', []))
    issues    = []
    # Nothing to validate against? Skip quietly.
    if not cargo_set and not team_set:
        return issues
    objects = data.get('objects', {})
    if not isinstance(objects, dict):
        issues.append("objects must be a JSON object for cargo/team validation.")
        return issues
    for obj_name, obj in objects.items():
        if not isinstance(obj, dict):
            issues.append(f"{obj_name}: object entry is not a JSON object.")
            continue
        carg  = obj.get('cargo') or {}
        tms   = obj.get('teams') or {}
        if not isinstance(carg, dict):
            issues.append(f"{obj_name}: cargo must be a JSON object.")
            carg = {}
        if not isinstance(tms, dict):
            issues.append(f"{obj_name}: teams must be a JSON object.")
            tms = {}
        # Cargo checks
        for item, qty in carg.items():
            if item in team_set:
                issues.append(f"{obj_name}: '{item}' is a TEAM but appears under cargo.")
            elif item not in cargo_set:
                issues.append(f"{obj_name}: Unknown cargo item '{item}'.")
            if not isinstance(qty, int) or qty < 0:
                issues.append(f"{obj_name}: Cargo '{item}' has invalid qty {qty} (non-negative integer required).")
        # Team checks
        for item, qty in tms.items():
            if item in cargo_set:
                issues.append(f"{obj_name}: '{item}' is CARGO but appears under teams.")
            elif item not in team_set:
                issues.append(f"{obj_name}: Unknown team '{item}'.")
            if not isinstance(qty, int) or qty < 0:
                issues.append(f"{obj_name}: Team '{item}' has invalid qty {qty} (non-negative integer required).")
    return issues


def verify_system_data(data, *, filename, system_files, other_gate_index, ct_config):
    errors = []
    warnings = []

    try:
        encoded = json.dumps(data, indent=4, allow_nan=False)
        decoded = json.loads(encoded)
        if not isinstance(decoded, dict):
            errors.append("JSON round-trip did not produce an object at the root.")
    except Exception as exc:
        errors.append(f"Current system data cannot be serialized as valid JSON: {exc}")
        return errors, warnings

    if not isinstance(data, dict):
        errors.append("System root must be a JSON object.")
        return errors, warnings

    system_coord = data.get('systemMapCoord')
    validate_coordinate_value(system_coord, "systemMapCoord", errors)

    metadata = data.get('metadata', {})
    if metadata is not None and not isinstance(metadata, dict):
        errors.append("metadata must be a JSON object when present.")

    objects = data.get('objects', {})
    if not isinstance(objects, dict):
        errors.append("objects must be a JSON object.")
        objects = {}

    terrain_data = data.get('terrain', {})
    if not isinstance(terrain_data, dict):
        errors.append("terrain must be a JSON object.")
        terrain_data = {}

    relay_data = data.get('sensor_relay', {})
    if relay_data is not None and not isinstance(relay_data, dict):
        errors.append("sensor_relay must be a JSON object when present.")
        relay_data = {}

    current_gate_names = {
        str(obj_name).lower()
        for obj_name, obj in objects.items()
        if isinstance(obj, dict)
        and str(obj.get('type', '') or '').strip().lower() in ('jumpnode', 'jumppoint', 'jump_point')
    }
    gate_index = dict(other_gate_index)
    gate_index[filename] = current_gate_names
    incoming_only_gate_list = get_incoming_only_gate_list(data)
    incoming_only_gate_names = {name.casefold() for name in incoming_only_gate_list}
    for gate_name in incoming_only_gate_list:
        if gate_name.casefold() not in current_gate_names:
            warnings.append(
                f"Incoming-only metadata references missing jump object '{gate_name}'."
            )
    for obj_name, obj in objects.items():
        if not isinstance(obj, dict):
            errors.append(f"Object '{obj_name}' must be a JSON object.")
            continue
        obj_type = str(obj.get('type', '') or '').strip().lower()
        if not obj_type:
            errors.append(f"Object '{obj_name}' is missing a type.")
        coord = obj.get('coordinate')
        validate_coordinate_value(coord, f"Object '{obj_name}' coordinate", errors)
        if obj_type in ('jumpnode', 'jumppoint', 'jump_point'):
            if str(obj_name).casefold() not in incoming_only_gate_names:
                destinations = obj.get('destinations')
                if not isinstance(destinations, dict) or not destinations:
                    warnings.append(f"Jump object '{obj_name}' has no valid destinations.")
                else:
                    for dest_gate_name, dest_system_name in destinations.items():
                        gate_name = str(dest_gate_name or '').strip()
                        system_name = str(dest_system_name or '').strip()
                        if not gate_name or not system_name:
                            errors.append(f"Jump object '{obj_name}' has a blank destination entry.")
                            continue
                        dest_system_key = system_name.lower()
                        if dest_system_key.endswith('.json'):
                            dest_system_key = dest_system_key[:-5]
                        dest_filename = system_files.get(dest_system_key)
                        if not dest_filename:
                            warnings.append(
                                f"Jump object '{obj_name}' points to missing system '{system_name}'."
                            )
                            continue
                        if gate_name.lower() not in gate_index.get(dest_filename, set()):
                            warnings.append(
                                f"Jump object '{obj_name}' points to missing gate '{gate_name}' in system '{system_name}'."
                            )
        if is_zone_type(obj_type):
            radius = obj.get('radius')
            if not is_number_like(radius) or float(radius) <= 0:
                errors.append(f"Zone object '{obj_name}' must have a positive numeric radius.")
        cargo = obj.get('cargo')
        if cargo is not None and not isinstance(cargo, dict):
            errors.append(f"Object '{obj_name}' cargo must be a JSON object.")
        teams = obj.get('teams')
        if teams is not None and not isinstance(teams, dict):
            errors.append(f"Object '{obj_name}' teams must be a JSON object.")

    line_terrain_types = {'asteroids', 'nebulas'}
    coord_terrain_types = {'blackhole', 'planet'}
    box_terrain_types = {'hidden_minefield', 'minefield'}

    for terr_name, feat in terrain_data.items():
        if not isinstance(feat, dict):
            errors.append(f"Terrain '{terr_name}' must be a JSON object.")
            continue
        terr_type = str(feat.get('type', '') or '').strip().lower()
        if not terr_type:
            errors.append(f"Terrain '{terr_name}' is missing a type.")
            continue

        if terr_type in line_terrain_types:
            validate_coordinate_value(feat.get('start'), f"Terrain '{terr_name}' start", errors)
            validate_coordinate_value(feat.get('end'), f"Terrain '{terr_name}' end", errors)
            density = feat.get('density')
            scatter = feat.get('scatter')
            if not isinstance(density, int) or density < 0:
                errors.append(f"Terrain '{terr_name}' density must be a non-negative integer.")
            if not is_number_like(scatter) or float(scatter) < 0:
                errors.append(f"Terrain '{terr_name}' scatter must be a non-negative number.")
        elif terr_type in coord_terrain_types or is_zone_type(terr_type):
            validate_coordinate_value(feat.get('coordinate'), f"Terrain '{terr_name}' coordinate", errors)
            if is_zone_type(terr_type):
                radius = feat.get('radius')
                if not is_number_like(radius) or float(radius) <= 0:
                    errors.append(f"Terrain zone '{terr_name}' must have a positive numeric radius.")
        elif terr_type in box_terrain_types:
            validate_coordinate_value(feat.get('coordinate'), f"Terrain '{terr_name}' coordinate", errors)
            width = feat.get('width')
            height = feat.get('height')
            if not is_number_like(width) or float(width) <= 0:
                errors.append(f"Terrain '{terr_name}' width must be a positive number.")
            if not is_number_like(height) or float(height) <= 0:
                errors.append(f"Terrain '{terr_name}' height must be a positive number.")

    for relay_name, relay in relay_data.items():
        if isinstance(relay, dict):
            coord = relay.get('coordinate')
        else:
            coord = relay
        validate_coordinate_value(coord, f"Sensor relay '{relay_name}' coordinate", errors)

    warnings.extend(collect_cargo_team_validation_issues(data, ct_config))
    return errors, warnings
