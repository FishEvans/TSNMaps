"""Shared object types, display defaults and normalization rules."""
from typing import Any, Dict, List, Optional


ZONE_STYLE_MAP = {
    "fcs_zone": {
        "label": "Fuel Collection Zone",
        "fill": "#2f7986",
        "outline": "#7fe7ff",
        "text": "#c9fbff",
    }
}

DEFAULT_ZONE_STYLE = {
    "label": "Zone",
    "fill": "#7a5622",
    "outline": "#ffd37f",
    "text": "#fff0bf",
}

FCS_ZONE_TYPE = "fcs_zone"

DEFAULT_FCS_ZONE_RADIUS = 5000

DEFAULT_FCS_MIN_SPACING = 30000

DEFAULT_FCS_DENSITY_RADIUS = 12500

DEFAULT_FCS_DENSITY_PERCENTILE = 56

DEFAULT_FCS_MIN_SCORE = 8.0

DEFAULT_FCS_SPACING_JITTER = 0.30

DEFAULT_FCS_DESCRIPTION = "Auto-generated from nebula density."

STATION_OR_PLATFORM_TYPES = {"station", "platform"}

DEFAULT_PLANET_CLASS = 'EarthLike'

RELAY_TYPE_SENSOR = 'Sensor Relay'

RELAY_TYPE_WARNING_BUOY = 'Warning Buoy'

RELAY_TYPE_OPTIONS = [RELAY_TYPE_SENSOR, RELAY_TYPE_WARNING_BUOY]

WARNING_BUOY_DEFAULT_PING = 2

WARNING_BUOY_DEFAULT_RANGE = 15000

# Preserve the existing distinction: the editor supplies a fallback range for
# legacy entries, while the placement toolbar starts new buoys at 12,000.
WARNING_BUOY_PLACEMENT_RANGE = 12000

GRID_MODES = ['off', 'grid', 'sector', 'combined']

GRID_SPACING = {'grid': 20000, 'sector': 100000}

def get_zone_style(zone_type: Any) -> Optional[Dict[str, str]]:
    zone_key = str(zone_type or "").strip().lower()
    if not zone_key:
        return None
    if zone_key in ZONE_STYLE_MAP:
        return ZONE_STYLE_MAP[zone_key]
    if zone_key.endswith("_zone"):
        return {
            **DEFAULT_ZONE_STYLE,
            "label": zone_key.replace("_", " ").title(),
        }
    return None

def is_zone_type(zone_type: Any) -> bool:
    return get_zone_style(zone_type) is not None

def object_has_blank_or_invalid_hull(obj: Any, valid_hull_keys: set) -> bool:
    if not isinstance(obj, dict):
        return False
    if str(obj.get("type", "")).strip().lower() not in STATION_OR_PLATFORM_TYPES:
        return False
    hull = str(obj.get("hull", "") or "").strip()
    if not hull:
        return True
    return bool(valid_hull_keys) and hull.casefold() not in valid_hull_keys

def _normalize_roles(entry: Dict[str, Any]) -> set:
    roles = set()
    raw_roles = entry.get('roles')
    if isinstance(raw_roles, str):
        roles.update(r.strip().lower() for r in raw_roles.split(',') if r.strip())
    elif isinstance(raw_roles, list):
        roles.update(str(r).strip().lower() for r in raw_roles if str(r).strip())
    raw_role = entry.get('role')
    if isinstance(raw_role, str) and raw_role.strip():
        roles.add(raw_role.strip().lower())
    return roles

def normalize_relay_type(value: Any) -> str:
    text = str(value or '').strip().casefold()
    if text == RELAY_TYPE_WARNING_BUOY.casefold():
        return RELAY_TYPE_WARNING_BUOY
    return RELAY_TYPE_SENSOR

def ensure_relay_dict(entry: Any) -> Dict[str, Any]:
    if isinstance(entry, dict):
        coord = entry.get('coordinate', [0, 0, 0])
        if not (isinstance(coord, (list, tuple)) and len(coord) >= 3):
            coord = [0, 0, 0]
        entry['coordinate'] = [coord[0], coord[1], coord[2]]
        entry['type'] = normalize_relay_type(entry.get('type'))
        return entry

    coord = entry if isinstance(entry, (list, tuple)) and len(entry) >= 3 else [0, 0, 0]
    return {
        'coordinate': [coord[0], coord[1], coord[2]],
        'type': RELAY_TYPE_SENSOR,
    }


def system_has_blank_or_invalid_station_hull(data, valid_hull_keys):
    objects = data.get("objects", {}) if isinstance(data, dict) else {}
    if not isinstance(objects, dict):
        return False
    return any(object_has_blank_or_invalid_hull(obj, valid_hull_keys) for obj in objects.values())
