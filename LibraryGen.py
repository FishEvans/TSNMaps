import html
import json
import math
import os
import re
import sys
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

from ShipDescriptionResolver import (
    clean_description,
    load_authoritative_description_index,
    load_authoritative_ship_stats_index,
    load_shipdata_index,
    normalize_roles,
    prettify_label,
    resolve_ship_description,
)


OUTPUT_NAME = "Library.html"
DEFAULT_FACTION = "Unaligned"
BROKEN_BEAM_CATEGORY = "BrokenBeam"
MISSING_DATABASE_DESC_CATEGORY = "Missing Database Desc"
MISSING_SHIPDATA_DESC_CATEGORY = "Missing ShipData Description"
MISSING_SYSTEM_HEALTH_CATEGORY = "Missing System Health Data"
MISSING_DESIGN_ORIGIN_ICON_CATEGORY = "Missing Design Origin Icon"
MISSING_SHIP_IMAGE_CATEGORY = "Missing Ship Image"
ONI_CATEGORIES = [
    BROKEN_BEAM_CATEGORY,
    MISSING_DATABASE_DESC_CATEGORY,
    MISSING_SHIPDATA_DESC_CATEGORY,
    MISSING_SYSTEM_HEALTH_CATEGORY,
    MISSING_DESIGN_ORIGIN_ICON_CATEGORY,
    MISSING_SHIP_IMAGE_CATEGORY,
]
COMMENTED_BEAM_ANGLE_ARCS_ENABLED = False


def get_base_path():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


BASE = Path(get_base_path())
HTML_DIR = BASE / "HTML"
SHIPS_DIR = HTML_DIR / "Images" / "Ships"
FACTIONS_DIR = HTML_DIR / "Images" / "Factions"
SHIPMAP_PATH = SHIPS_DIR / "ShipMap.json"
SHIPDATA_PATH = BASE / "scripts" / "Referance" / "shipData.yaml"
SETTINGS_PATH = BASE / "Settings.json"
OUTPUT_PATH = HTML_DIR / OUTPUT_NAME
FACTION_ICON_ALIASES = {
    "skaraan": "Skarran",
}


def load_json(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def build_side_catalog(settings):
    factions = []
    faction_lookup = {}
    for faction in settings.get("Factions", []):
        label = str(faction).strip()
        if not label:
            continue
        factions.append(label)
        faction_lookup[label.casefold()] = label

    side_lookup = dict(faction_lookup)
    race_to_faction = {}
    races = settings.get("Races", {})
    if isinstance(races, dict):
        for race_name, race_meta in races.items():
            side_name = str(race_name).strip()
            if not side_name:
                continue
            side_lookup[side_name.casefold()] = side_name

            if not isinstance(race_meta, dict):
                continue
            faction_name = str(race_meta.get("Faction", "")).strip()
            if not faction_name:
                continue
            canonical_faction = faction_lookup.get(faction_name.casefold(), faction_name)
            faction_lookup[canonical_faction.casefold()] = canonical_faction
            race_to_faction[side_name.casefold()] = canonical_faction

    return factions, faction_lookup, side_lookup, race_to_faction


def canonical_side_label(raw_side, side_lookup, discovered_sides):
    raw_side = str(raw_side or "").strip()
    if not raw_side:
        return "Unknown"

    folded = raw_side.casefold()
    if folded in side_lookup:
        return side_lookup[folded]
    if folded in discovered_sides:
        return discovered_sides[folded]

    label = prettify_label(raw_side)
    discovered_sides[folded] = label
    return label


def resolve_faction(raw_side, faction_lookup, race_to_faction):
    folded = str(raw_side or "").strip().casefold()
    if not folded:
        return DEFAULT_FACTION
    if folded in race_to_faction:
        return race_to_faction[folded]
    if folded in faction_lookup:
        return faction_lookup[folded]
    return DEFAULT_FACTION


def resolve_image_src(artfileroot):
    artfileroot = str(artfileroot or "").strip().strip("/\\")
    fallback = SHIPS_DIR / "unknown256.png"
    fallback_rel = "Images/Ships/unknown256.png"

    if not artfileroot:
        return fallback_rel if fallback.exists() else ""

    parts = [part for part in re.split(r"[\\/]+", artfileroot) if part]
    if not parts:
        return fallback_rel if fallback.exists() else ""

    stem = parts[-1]
    folders = parts[:-1]
    for size in ("256", "1024"):
        candidate = SHIPS_DIR.joinpath(*folders, f"{stem}{size}.png")
        if candidate.exists():
            encoded_parts = [quote(part) for part in folders + [f"{stem}{size}.png"]]
            return "Images/Ships/" + "/".join(encoded_parts)

    return fallback_rel if fallback.exists() else ""


def is_missing_ship_image(image_src):
    clean = str(image_src or "").strip().replace("\\", "/").casefold()
    return not clean or clean.endswith("/unknown256.png") or clean == "images/ships/unknown256.png"


def resolve_faction_icon_src(*labels):
    fallback_name = "Unknown.png"
    fallback = FACTIONS_DIR / fallback_name

    for label in labels:
        clean = str(label or "").strip()
        if not clean:
            continue

        candidates = [clean]
        alias = FACTION_ICON_ALIASES.get(clean.casefold())
        if alias:
            candidates.append(alias)

        for candidate in candidates:
            exact = FACTIONS_DIR / f"{candidate}.png"
            if exact.exists():
                return "Images/Factions/" + quote(exact.name)

        folded = f"{clean}.png".casefold()
        for icon_path in FACTIONS_DIR.glob("*.png"):
            if icon_path.name.casefold() == folded:
                return "Images/Factions/" + quote(icon_path.name)

    if fallback.exists():
        return "Images/Factions/" + quote(fallback_name)
    return ""


def is_missing_faction_icon(icon_src):
    clean = str(icon_src or "").strip().replace("\\", "/").casefold()
    return not clean or clean.endswith("/unknown.png") or clean == "images/factions/unknown.png"


def description_html(long_desc):
    clean = str(long_desc or "").strip()
    if not clean:
        return '<p class="entry-description empty">No description available.</p>'

    paragraphs = [part.strip() for part in clean.split("^") if part.strip()]
    if not paragraphs:
        return '<p class="entry-description empty">No description available.</p>'

    return "".join(
        f'<p class="entry-description">{html.escape(paragraph)}</p>'
        for paragraph in paragraphs
    )


def role_chip_html(roles):
    parts = normalize_roles(roles)
    if not parts:
        return '<span class="meta-chip subdued">No roles</span>'

    chips = []
    for role in parts:
        label = role.replace("_", " ")
        chips.append(f'<span class="meta-chip">{html.escape(prettify_label(label))}</span>')
    return "".join(chips)


def faction_options_html(factions):
    options = ['<option value="all">All factions</option>']
    for faction in factions:
        options.append(
            f'<option value="{html.escape(faction.casefold())}">{html.escape(faction)}</option>'
        )
    return "".join(options)


def category_key(label):
    key = re.sub(r"[^a-z0-9]+", "-", str(label or "").casefold()).strip("-")
    return key or "uncategorized"


def category_options_html(categories, entries=None):
    counts = {}
    if entries is not None:
        counts = {category_key(category): 0 for category in categories}
        for entry in entries:
            for category in entry.get("categories", []):
                key = category_key(category)
                counts[key] = counts.get(key, 0) + 1

    options = ['<option value="all">All categories</option>']
    for category in categories:
        key = category_key(category)
        count = counts.get(key)
        disabled = ' disabled' if count == 0 else ''
        label = category if count is None else f"{category} ({count})"
        options.append(
            f'<option value="{html.escape(key)}"{disabled}>{html.escape(label)}</option>'
        )
    return "".join(options)


def _coerce_number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_int(value):
    number = _coerce_number(value)
    if number is None:
        return None
    if float(number).is_integer():
        return int(number)
    return round(number, 1)


def _normalize_stat_list(values):
    if not isinstance(values, (list, tuple)):
        return []
    normalized = []
    for value in values:
        coerced = _coerce_int(value)
        if coerced is not None:
            normalized.append(coerced)
    return normalized


def _shield_stat_label(values):
    shields = _normalize_stat_list(values)
    if not shields:
        return None
    if len(shields) == 1:
        return f"Shield {shields[0]} Omni"
    return f"Shield F{shields[0]} / B{shields[1]}"


def _shield_stat_values(values):
    shields = _normalize_stat_list(values)
    if not shields:
        return None, None
    if len(shields) == 1:
        return shields[0], shields[0]
    return shields[0], shields[1]


def _system_health_total(values):
    system_health = _normalize_stat_list(values)
    if not system_health:
        return None
    return sum(system_health)


def _normalize_abilities(values):
    if not isinstance(values, (list, tuple)):
        return []
    normalized = []
    seen = set()
    for value in values:
        label = str(value or "").strip()
        if not label:
            continue
        key = label.casefold()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(label)
    return normalized


def _position_ring(position):
    if not isinstance(position, (list, tuple)) or len(position) < 3:
        return None
    x = _coerce_number(position[0])
    z = _coerce_number(position[2])
    if x is None or z is None:
        return None
    return math.hypot(x, z)


def _angle_intervals(angle, width):
    if width >= 359.5:
        return [(0.0, 360.0)]

    start = (float(angle) - (float(width) / 2.0)) % 360.0
    end = (float(angle) + (float(width) / 2.0)) % 360.0
    if start <= end:
        return [(start, end)]
    return [(0.0, end), (start, 360.0)]


def _interval_overlap(left, right):
    return max(0.0, min(left[1], right[1]) - max(left[0], right[0]))


def _arc_sector_overlap(angle, width, sector_center, sector_width):
    arc_intervals = _angle_intervals(angle, width)
    sector_intervals = _angle_intervals(sector_center, sector_width)
    return sum(
        _interval_overlap(arc_interval, sector_interval)
        for arc_interval in arc_intervals
        for sector_interval in sector_intervals
    )


def _beam_port_dpm(port):
    cycle_time = _coerce_number(port.get("cycle_time"))
    damage_coeff = _coerce_number(port.get("damage_coeff"))
    if cycle_time is None or cycle_time <= 0 or damage_coeff is None:
        return None
    return damage_coeff * (60.0 / cycle_time)


def _format_dpm(value):
    return _format_number(value, fallback="0")


def _format_number(value, fallback="Unknown"):
    number = _coerce_number(value)
    if number is None:
        return fallback
    rounded = round(number, 1)
    if float(rounded).is_integer():
        return str(int(rounded))
    return f"{rounded:.1f}"


@lru_cache(maxsize=1)
def load_commented_beam_angles():
    if not SHIPDATA_PATH.exists():
        return {}

    result = {}
    current_key = None
    current_group = None
    in_beam_list = False
    in_port = False
    current_angle = None

    for raw_line in SHIPDATA_PATH.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()

        key_match = re.match(r'"key"\s*:\s*"([^"]+)"', stripped)
        if key_match:
            current_key = key_match.group(1)
            current_group = None
            in_beam_list = False
            in_port = False
            current_angle = None
            continue

        if current_key is None:
            continue

        group_match = re.match(r'"([^"]+)"\s*:\s*\[', stripped)
        if group_match and not in_beam_list:
            group_name = group_match.group(1)
            if "beam" in group_name.casefold():
                current_group = group_name
                in_beam_list = True
                in_port = False
                current_angle = None
            continue

        if not in_beam_list:
            continue

        if stripped.startswith("]") and not in_port:
            current_group = None
            in_beam_list = False
            in_port = False
            current_angle = None
            continue

        if stripped.startswith("{") and not in_port:
            in_port = True
            current_angle = None
            continue

        if not in_port:
            continue

        angle_match = re.search(r'#?\s*"barrel_angle"\s*:\s*(-?\d+(?:\.\d+)?)', stripped)
        if angle_match:
            current_angle = float(angle_match.group(1))

        if stripped.startswith("}"):
            group_angles = result.setdefault(current_key, {}).setdefault(current_group, [])
            group_angles.append(current_angle)
            in_port = False
            current_angle = None

    return result


@lru_cache(maxsize=1)
def load_commented_beam_angle_ships():
    if not SHIPDATA_PATH.exists():
        return set()

    result = set()
    current_key = None
    current_group = None
    in_beam_list = False
    in_port = False
    port_has_commented_angle = False

    for raw_line in SHIPDATA_PATH.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()

        key_match = re.match(r'"key"\s*:\s*"([^"]+)"', stripped)
        if key_match:
            current_key = key_match.group(1)
            current_group = None
            in_beam_list = False
            in_port = False
            port_has_commented_angle = False
            continue

        if current_key is None:
            continue

        group_match = re.match(r'"([^"]+)"\s*:\s*\[', stripped)
        if group_match and not in_beam_list:
            group_name = group_match.group(1)
            if "beam" in group_name.casefold():
                current_group = group_name
                in_beam_list = True
                in_port = False
                port_has_commented_angle = False
            continue

        if not in_beam_list:
            continue

        if stripped.startswith("]") and not in_port:
            current_group = None
            in_beam_list = False
            in_port = False
            port_has_commented_angle = False
            continue

        if stripped.startswith("{") and not in_port:
            in_port = True
            port_has_commented_angle = False
            continue

        if not in_port:
            continue

        if re.match(r'#\s*"barrel_angle"\s*:\s*-?\d+(?:\.\d+)?', stripped):
            port_has_commented_angle = True

        if stripped.startswith("}"):
            if port_has_commented_angle and current_key and current_group:
                result.add(current_key)
            in_port = False
            port_has_commented_angle = False

    return result


def _beam_arc_entries(ship_key, shipdata_entry):
    if not isinstance(shipdata_entry, dict):
        return []

    arcs = []
    commented_angles = {}
    if COMMENTED_BEAM_ANGLE_ARCS_ENABLED:
        commented_angles = load_commented_beam_angles().get(ship_key, {})
    hull_port_sets = shipdata_entry.get("hull_port_sets")
    if isinstance(hull_port_sets, dict):
        for group_name, ports in hull_port_sets.items():
            if "beam" not in str(group_name or "").casefold() or not isinstance(ports, list):
                continue
            fallback_angles = commented_angles.get(group_name, [])
            for index, port in enumerate(ports):
                if not isinstance(port, dict):
                    continue
                arcwidth = _coerce_number(port.get("arcwidth"))
                if arcwidth is None or arcwidth <= 0:
                    continue
                angle = _coerce_number(port.get("barrel_angle"))
                if angle is None and index < len(fallback_angles):
                    angle = _coerce_number(fallback_angles[index])
                if angle is None:
                    continue
                arcs.append(
                    {
                        "angle": angle,
                        "width": max(1.0, min(360.0, arcwidth)),
                        "colour": str(port.get("arccolor") or port.get("color") or "#73d0ff"),
                        "ring": _position_ring(port.get("position")),
                        "dpm": _beam_port_dpm(port),
                    }
                )

    hull_portsets = shipdata_entry.get("hull_portsets")
    if isinstance(hull_portsets, list):
        for port in hull_portsets:
            if not isinstance(port, dict):
                continue
            if str(port.get("type", "")).casefold() != "beam":
                continue
            arcwidth = _coerce_number(port.get("arcwidth"))
            if arcwidth is None or arcwidth <= 0:
                continue
            colour = port.get("arccolor") or port.get("beamcolor") or "#73d0ff"
            if isinstance(colour, list):
                colour = colour[0] if colour else "#73d0ff"
            angle = _coerce_number(port.get("barrel_angle"))
            arcs.append(
                {
                    "angle": angle if angle is not None else 0.0,
                    "width": max(1.0, min(360.0, arcwidth)),
                    "colour": str(colour or "#73d0ff"),
                    "ring": _position_ring(port.get("position")),
                    "dpm": _beam_port_dpm(port),
                }
            )

    return arcs


def _beam_dpm_summary(beam_arcs):
    summary = {"forward": 0.0, "aft": 0.0, "total": 0.0}
    sector_width = 80.0
    minimum_overlap = 0.001

    for arc in beam_arcs:
        dpm = _coerce_number(arc.get("dpm"))
        if dpm is None:
            continue

        angle = _coerce_number(arc.get("angle"))
        width = _coerce_number(arc.get("width"))
        if angle is None or width is None or width <= 0:
            continue

        summary["total"] += dpm
        if _arc_sector_overlap(angle, width, 0.0, sector_width) >= minimum_overlap:
            summary["forward"] += dpm
        if _arc_sector_overlap(angle, width, 180.0, sector_width) >= minimum_overlap:
            summary["aft"] += dpm

    return summary


def _max_beam_range(shipdata_entry):
    if not isinstance(shipdata_entry, dict):
        return None

    max_range = None
    hull_port_sets = shipdata_entry.get("hull_port_sets")
    if isinstance(hull_port_sets, dict):
        for group_name, ports in hull_port_sets.items():
            if "beam" not in str(group_name or "").casefold() or not isinstance(ports, list):
                continue
            for port in ports:
                if not isinstance(port, dict):
                    continue
                beam_range = _coerce_int(port.get("range"))
                if beam_range is None:
                    continue
                if max_range is None or beam_range > max_range:
                    max_range = beam_range

    hull_portsets = shipdata_entry.get("hull_portsets")
    if isinstance(hull_portsets, list):
        for port in hull_portsets:
            if not isinstance(port, dict):
                continue
            if str(port.get("type", "")).casefold() != "beam":
                continue
            beam_range = _coerce_int(port.get("range"))
            if beam_range is None:
                continue
            if max_range is None or beam_range > max_range:
                max_range = beam_range

    return max_range


def _drone_endurance(shipdata_entry):
    if not isinstance(shipdata_entry, dict):
        return None
    drone_endurance = _coerce_int(shipdata_entry.get("drone_launch_timer"))
    if drone_endurance is None:
        return None
    return drone_endurance if drone_endurance > 0 else None


def _polar_to_svg(cx, cy, radius, angle_degrees):
    radians = math.radians(angle_degrees)
    x = cx + radius * math.sin(radians)
    y = cy - radius * math.cos(radians)
    return x, y


def _beam_outline_path(cx, cy, radius, start_angle, end_angle):
    start_x, start_y = _polar_to_svg(cx, cy, radius, start_angle)
    end_x, end_y = _polar_to_svg(cx, cy, radius, end_angle)
    span = (end_angle - start_angle) % 360.0
    large_arc_flag = 1 if span > 180 else 0
    return (
        f"M {cx:.2f} {cy:.2f} "
        f"L {start_x:.2f} {start_y:.2f} "
        f"A {radius:.2f} {radius:.2f} 0 {large_arc_flag} 1 {end_x:.2f} {end_y:.2f} "
        f"L {cx:.2f} {cy:.2f}"
    )


def _merge_beam_intervals(angles):
    intervals = []
    for angle, width in angles:
        if width >= 359.5:
            return [(0.0, 360.0)]

        start = (angle - (width / 2.0)) % 360.0
        end = (angle + (width / 2.0)) % 360.0
        if start <= end:
            intervals.append((start, end))
        else:
            intervals.append((0.0, end))
            intervals.append((start, 360.0))

    if not intervals:
        return []

    intervals.sort()
    merged = [list(intervals[0])]
    for start, end in intervals[1:]:
        current = merged[-1]
        if start <= current[1] + 0.5:
            current[1] = max(current[1], end)
        else:
            merged.append([start, end])

    if len(merged) > 1 and merged[0][0] <= 0.5 and merged[-1][1] >= 359.5:
        wrapped = [merged[-1][0] - 360.0, merged[0][1]]
        middle = merged[1:-1]
        merged = [wrapped] + middle

    normalized = []
    for start, end in merged:
        span = end - start
        if span >= 359.5:
            return [(0.0, 360.0)]
        normalized.append((start % 360.0, end % 360.0))
    return normalized


def _cluster_ring_values(rings, tolerance=8.0):
    if not rings:
        return []

    sorted_rings = sorted(float(ring) for ring in rings)
    clusters = [[sorted_rings[0]]]
    for ring in sorted_rings[1:]:
        if abs(ring - clusters[-1][-1]) <= tolerance:
            clusters[-1].append(ring)
        else:
            clusters.append([ring])

    return [sum(cluster) / len(cluster) for cluster in clusters]


def beam_overlay_svg(beam_arcs):
    if not beam_arcs:
        return ""

    cx = cy = 50.0
    base_radius = 34.5
    min_radius = 24.0
    max_radius = 45.0
    grouped_arcs = {}
    for index, arc in enumerate(beam_arcs):
        colour = str(arc["colour"])
        grouped_arcs.setdefault(colour, []).append((index, arc))

    segments = []
    for colour_value, members in grouped_arcs.items():
        colour = html.escape(colour_value)
        signature_groups = {}
        for original_index, arc in members:
            signature = (round(float(arc["angle"]) % 360.0, 3), round(float(arc["width"]), 3))
            signature_groups.setdefault(signature, []).append((original_index, arc))

        for duplicate_members in signature_groups.values():
            duplicate_members = sorted(duplicate_members, key=lambda item: item[0])
            half_span = (len(duplicate_members) - 1) / 2.0
            required_inset = half_span * 2.2
            centred_radius = min(max_radius - required_inset, max(min_radius + required_inset, base_radius))
            if len(duplicate_members) <= 1:
                local_step = 0.0
            else:
                max_inset = min(centred_radius - min_radius, max_radius - centred_radius)
                local_step = min(2.2, max_inset / half_span if half_span else 2.2)

            for offset_index, (_original_index, arc) in enumerate(duplicate_members):
                radius = centred_radius + ((offset_index - half_span) * local_step)
                width = float(arc["width"])
                if width >= 359.5:
                    segments.append(
                        f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{radius:.2f}" '
                        f'fill="none" stroke="{colour}" stroke-width="3" stroke-opacity="0.78" />'
                    )
                    continue

                start_angle = float(arc["angle"]) - (width / 2.0)
                end_angle = float(arc["angle"]) + (width / 2.0)
                path = _beam_outline_path(cx, cy, radius, start_angle, end_angle)
                segments.append(
                    f'<path d="{path}" fill="none" stroke="{colour}" '
                    f'stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" stroke-opacity="0.92" />'
                )

    segments.append(
        '<circle cx="50" cy="50" r="2.4" fill="#ebf4ff" fill-opacity="0.95" />'
    )

    return (
        '<svg class="beam-overlay" viewBox="0 0 100 100" aria-hidden="true" focusable="false">'
        + "".join(segments)
        + "</svg>"
    )


def health_table_html(entry):
    def value_text(value):
        if value is None:
            return "Unknown"
        return _format_number(value)

    forward_shield = value_text(entry.get("shield_forward"))
    aft_shield = value_text(entry.get("shield_aft"))
    hull_points = value_text(entry.get("hull_points"))
    system_health = value_text(entry.get("system_health_total"))

    return (
        '<table class="health-table">'
        '<tbody>'
        '<tr>'
        f'<td><span>Forward Shield</span><strong>{html.escape(forward_shield)}</strong></td>'
        f'<td><span>Hull</span><strong>{html.escape(hull_points)}</strong></td>'
        '</tr>'
        '<tr>'
        f'<td><span>Aft Shield</span><strong>{html.escape(aft_shield)}</strong></td>'
        f'<td><span>System Health</span><strong>{html.escape(system_health)}</strong></td>'
        '</tr>'
        '</tbody>'
        '</table>'
    )


def faction_icon_html(entry):
    icon_src = str(entry.get("faction_icon_src") or "").strip()
    if not icon_src:
        return ""
    label = str(entry.get("side") or entry.get("faction") or "Unknown")
    return (
        '<div class="health-faction-icon">'
        '<span>Design Origin</span>'
        f'<img src="{html.escape(icon_src)}" alt="{html.escape(label)} icon" loading="lazy" />'
        f'<strong>{html.escape(label)}</strong>'
        '</div>'
    )


def render_cards(entries):
    cards = []
    for entry in entries:
        stats = []
        if entry["BRange"] is not None:
            stats.append(
                f'<span class="stat-pill">Max Beam Range {html.escape(_format_number(entry["BRange"]))}</span>'
            )
        if entry["DRange"] is not None:
            stats.append(
                f'<span class="stat-pill">Drone Endurance {html.escape(_format_number(entry["DRange"]))}</span>'
            )
        if not stats:
            stats.append('<span class="stat-pill empty">No range data</span>')

        image_markup = '<div class="image-missing">No image</div>'
        if entry["image_src"]:
            dpm_summary = entry.get("dpm_summary", {})
            image_markup = (
                '<div class="entry-image-frame">'
                '<div class="dpm-badge dpm-badge-top">'
                f'<span>Fwd DPM</span><strong>{html.escape(_format_dpm(dpm_summary.get("forward")))}</strong>'
                '</div>'
                f'<img src="{entry["image_src"]}" alt="{html.escape(entry["name"])}" loading="lazy" />'
                f'{beam_overlay_svg(entry["beam_arcs"])}'
                '<div class="dpm-badge-stack dpm-badge-bottom">'
                '<div class="dpm-badge">'
                f'<span>Aft DPM</span><strong>{html.escape(_format_dpm(dpm_summary.get("aft")))}</strong>'
                '</div>'
                '<div class="dpm-badge total">'
                f'<span>Total DPM</span><strong>{html.escape(_format_dpm(dpm_summary.get("total")))}</strong>'
                '</div>'
                '</div>'
                "</div>"
            )

        abilities_markup = ""
        if entry["abilities"]:
            ability_pills = "".join(
                f'<span class="meta-chip subdued">{html.escape(ability)}</span>'
                for ability in entry["abilities"]
            )
            abilities_markup = (
                '<div class="abilities-block">'
                '<p class="abilities-title">Known Possible Special Systems</p>'
                f'<div class="abilities-row">{ability_pills}</div>'
                '</div>'
            )

        categories = list(entry.get("categories", []))
        category_keys = " ".join(category_key(category) for category in categories)
        broken_beam_attr = "true" if entry.get("broken_beam") else "false"
        category_markup = "".join(
            f'<span class="meta-chip oni-only oni-category-chip">{html.escape(category)}</span>'
            for category in categories
        )

        cards.append(
            f"""
      <article class="entry-card"
        data-faction="{html.escape(entry['faction_key'])}"
        data-side="{html.escape(entry['side_key'])}"
        data-side-label="{html.escape(entry['side'])}"
        data-categories="{html.escape(category_keys)}"
        data-broken-beam="{broken_beam_attr}"
        data-search="{html.escape(entry['search_blob'])}">
        <div class="entry-image">{image_markup}</div>
        <div class="entry-body">
          <div class="entry-header">
            <div>
              <p class="eyebrow">{html.escape(entry['faction'])} / {html.escape(entry['side'])}</p>
              <h2>{html.escape(entry['name'])}</h2>
            </div>
            <code>{html.escape(entry['key'])}</code>
          </div>
          <div class="meta-row">
            <span class="meta-chip faction">{html.escape(entry['faction'])}</span>
            <span class="meta-chip side">{html.escape(entry['side'])}</span>
            {category_markup}
            {role_chip_html(entry['roles'])}
          </div>
          <div class="health-summary">
            {health_table_html(entry)}
            {faction_icon_html(entry)}
          </div>
          <div class="description-block">{description_html(entry['long_desc'])}</div>
          {abilities_markup}
          <div class="range-block">
            <div class="stats-row">{''.join(stats)}</div>
          </div>
        </div>
      </article>"""
        )
    return "".join(cards)


def format_version_tag(date_str, revision_number):
    if not date_str:
        return ""
    date_str = str(date_str).strip()
    y = m = d = None
    m1 = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", date_str)
    m2 = re.match(r"^(\d{2})/(\d{2})/(\d{4})$", date_str)
    m3 = re.match(r"^(\d{4})/(\d{2})/(\d{2})$", date_str)
    if m1:
        y, m, d = m1.group(1), m1.group(2), m1.group(3)
    elif m2:
        d, m, y = m2.group(1), m2.group(2), m2.group(3)
    elif m3:
        y, m, d = m3.group(1), m3.group(2), m3.group(3)
    if not (y and m and d):
        return ""
    day = str(int(d))
    month = str(int(m))
    yy = str(y)[-2:]
    ver = revision_number if revision_number is not None else 0
    return f"{day}{month}{yy}.{ver}"


def build_page(entries, faction_labels):
    cards = render_cards(entries)
    faction_options = faction_options_html(faction_labels)
    category_options = category_options_html(ONI_CATEGORIES, entries)
    total_entries = len(entries)
    build_version = format_version_tag(datetime.now().strftime("%Y-%m-%d"), 0)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Ship Library</title>
  <style>
    :root {{
      --bg: #07111f;
      --bg-panel: rgba(8, 17, 30, 0.88);
      --bg-card: rgba(13, 24, 40, 0.95);
      --line: rgba(125, 183, 255, 0.24);
      --line-strong: rgba(125, 183, 255, 0.52);
      --text: #ebf4ff;
      --muted: #9fb3cc;
      --accent: #73d0ff;
      --accent-strong: #3aa8e0;
      --chip: rgba(35, 66, 104, 0.9);
      --shadow: 0 18px 45px rgba(0, 0, 0, 0.38);
      --radius: 20px;
    }}

    * {{ box-sizing: border-box; }}

    body {{
      margin: 0;
      min-height: 100vh;
      color: var(--text);
      font-family: "Trebuchet MS", "Segoe UI", sans-serif;
      background:
        radial-gradient(circle at top, rgba(78, 139, 211, 0.22), transparent 38%),
        linear-gradient(180deg, rgba(3, 7, 14, 0.72), rgba(3, 7, 14, 0.94)),
        url("Images/starfield.jpg") center/cover fixed;
    }}

    .page {{
      width: min(1500px, calc(100vw - 32px));
      margin: 24px auto 48px;
    }}

    .hero {{
      padding: 28px;
      border: 1px solid var(--line);
      border-radius: 28px;
      background: linear-gradient(180deg, rgba(8, 20, 36, 0.95), rgba(8, 17, 30, 0.8));
      box-shadow: var(--shadow);
      backdrop-filter: blur(10px);
    }}

    .hero-top {{
      display: flex;
      align-items: start;
      justify-content: space-between;
      gap: 20px;
      margin-bottom: 20px;
    }}

    .hero-copy {{
      max-width: 60rem;
    }}

    .hero-side {{
      display: grid;
      gap: 12px;
      justify-items: end;
      min-width: 260px;
    }}

    .hero h1 {{
      margin: 0;
      font-size: clamp(2rem, 4vw, 3.5rem);
      letter-spacing: 0.03em;
    }}

    .hero p {{
      margin: 8px 0 0;
      max-width: 60rem;
      color: var(--muted);
      line-height: 1.5;
    }}

    .page-nav-stack {{
      display: grid;
      gap: 8px;
      width: min(100%, 280px);
    }}

    .page-nav-link {{
      width: 100%;
      min-height: 44px;
      padding: 12px 18px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      border: 1px solid rgba(255, 255, 255, 0.12);
      border-radius: 999px;
      color: #f1f5fb;
      background: rgba(54, 54, 54, 0.94);
      box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.03);
      cursor: pointer;
      text-decoration: none;
      text-align: center;
      font-family: "Consolas", "Lucida Console", monospace;
      font-size: 0.82rem;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      transition: transform 0.18s ease, border-color 0.18s ease, box-shadow 0.18s ease, filter 0.18s ease;
    }}

    .page-nav-link:hover,
    .page-nav-link:focus-visible {{
      transform: translateY(-1px);
      filter: brightness(1.06);
      outline: none;
    }}

    .page-nav-link.page-nav-map {{
      border-color: rgba(255, 255, 255, 0.18);
      background: linear-gradient(180deg, rgba(77, 77, 77, 0.96), rgba(54, 54, 54, 0.96));
      box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.04), 0 8px 18px rgba(0, 0, 0, 0.24);
    }}

    .page-nav-link.page-nav-library {{
      border-color: rgba(125, 183, 255, 0.45);
      background: linear-gradient(180deg, rgba(27, 51, 84, 0.96), rgba(18, 35, 58, 0.96));
      box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.04), 0 8px 18px rgba(6, 14, 28, 0.28);
    }}

    .page-nav-link.page-nav-production {{
      border-color: rgba(147, 255, 215, 0.3);
      background: linear-gradient(180deg, rgba(18, 46, 39, 0.96), rgba(12, 29, 25, 0.96));
      box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.04), 0 8px 18px rgba(0, 0, 0, 0.28);
    }}

    .page-nav-link.page-nav-auth {{
      border-color: rgba(255, 213, 106, 0.38);
      background: linear-gradient(180deg, rgba(65, 50, 21, 0.96), rgba(42, 31, 16, 0.96));
      box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.04), 0 8px 18px rgba(0, 0, 0, 0.28);
    }}

    .filter-bar {{
      display: grid;
      grid-template-columns: minmax(240px, 2fr) minmax(180px, 1fr) minmax(180px, 1fr);
      gap: 14px;
      margin-top: 20px;
    }}

    body.oni-authenticated .filter-bar {{
      grid-template-columns: minmax(240px, 2fr) minmax(160px, 1fr) minmax(160px, 1fr) minmax(160px, 1fr);
    }}

    .filter-group {{
      display: flex;
      flex-direction: column;
      gap: 6px;
    }}

    .filter-group label {{
      color: var(--muted);
      font-size: 0.92rem;
      letter-spacing: 0.03em;
      text-transform: uppercase;
    }}

    .filter-group input,
    .filter-group select {{
      width: 100%;
      padding: 14px 16px;
      border: 1px solid var(--line);
      border-radius: 14px;
      color: var(--text);
      background: rgba(10, 21, 36, 0.9);
      outline: none;
    }}

    .results-bar {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: center;
      margin: 20px 2px 0;
      color: var(--muted);
    }}

    .card-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 18px;
      margin-top: 22px;
    }}

    .entry-card {{
      display: grid;
      grid-template-columns: 160px minmax(0, 1fr);
      gap: 18px;
      padding: 18px;
      border: 1px solid var(--line);
      border-radius: var(--radius);
      background: var(--bg-card);
      box-shadow: var(--shadow);
      overflow: hidden;
    }}

    .entry-image {{
      display: flex;
      flex-direction: column;
      align-items: stretch;
      justify-content: center;
      min-height: 300px;
      border-radius: 16px;
      background:
        radial-gradient(circle at top, rgba(115, 208, 255, 0.18), transparent 48%),
        linear-gradient(180deg, rgba(14, 27, 44, 0.95), rgba(8, 15, 27, 0.98));
      border: 1px solid rgba(115, 208, 255, 0.12);
      padding: 14px;
      gap: 12px;
    }}

    .entry-image-frame {{
      position: relative;
      width: min(132px, 100%);
      aspect-ratio: 1;
      display: flex;
      align-items: center;
      justify-content: center;
      margin: auto 0;
    }}

    .entry-image img {{
      position: relative;
      z-index: 1;
      width: 100%;
      max-width: 132px;
      height: auto;
      object-fit: contain;
      transform: rotate(180deg);
      filter: drop-shadow(0 10px 16px rgba(0, 0, 0, 0.45));
    }}

    .dpm-badge,
    .dpm-badge-stack {{
      position: absolute;
      left: 50%;
      z-index: 3;
      pointer-events: none;
    }}

    .dpm-badge {{
      min-width: 86px;
      padding: 4px 7px;
      border: 1px solid rgba(147, 255, 215, 0.3);
      border-radius: 8px;
      color: var(--text);
      background: rgba(5, 16, 25, 0.82);
      box-shadow: 0 5px 16px rgba(0, 0, 0, 0.32);
      text-align: center;
    }}

    .dpm-badge span {{
      display: block;
      color: var(--muted);
      font-size: 0.62rem;
      line-height: 1;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }}

    .dpm-badge strong {{
      display: block;
      margin-top: 2px;
      font-size: 0.9rem;
      line-height: 1;
    }}

    .dpm-badge-top {{
      top: 0;
      transform: translate(-50%, calc(-100% - 20px));
    }}

    .dpm-badge-stack {{
      bottom: 0;
      display: grid;
      gap: 4px;
      transform: translate(-50%, calc(100% + 20px));
    }}

    .dpm-badge-stack .dpm-badge {{
      position: static;
      transform: none;
    }}

    .dpm-badge.total {{
      border-color: rgba(255, 213, 106, 0.32);
    }}

    .beam-overlay {{
      position: absolute;
      inset: 0;
      width: 100%;
      height: 100%;
      z-index: 2;
      pointer-events: none;
      filter: drop-shadow(0 0 10px rgba(115, 208, 255, 0.18));
    }}

    .image-missing {{
      color: var(--muted);
      font-size: 0.95rem;
      text-align: center;
    }}

    .entry-body {{
      min-width: 0;
    }}

    .entry-header {{
      display: flex;
      justify-content: space-between;
      gap: 14px;
      align-items: start;
    }}

    .eyebrow {{
      margin: 0 0 8px;
      color: var(--accent);
      font-size: 0.82rem;
      letter-spacing: 0.12em;
      text-transform: uppercase;
    }}

    .entry-header h2 {{
      margin: 0;
      font-size: 1.45rem;
      line-height: 1.15;
    }}

    .entry-header code {{
      padding: 5px 8px;
      border-radius: 10px;
      color: #c9e7ff;
      background: rgba(31, 57, 91, 0.88);
      white-space: nowrap;
    }}

    .meta-row,
    .stats-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }}

    .meta-row {{
      margin-top: 14px;
    }}

    .stats-row {{
      margin-top: 0;
    }}

    .meta-chip,
    .stat-pill {{
      display: inline-flex;
      align-items: center;
      min-height: 32px;
      padding: 6px 10px;
      border: 1px solid rgba(129, 176, 255, 0.12);
      border-radius: 999px;
      background: var(--chip);
      font-size: 0.88rem;
      line-height: 1.2;
    }}

    .meta-chip.subdued,
    .stat-pill.empty {{
      color: var(--muted);
      background: rgba(24, 39, 61, 0.86);
    }}

    .oni-only,
    .oni-only-block {{
      display: none;
    }}

    body.oni-authenticated .oni-only {{
      display: inline-flex;
    }}

    body.oni-authenticated .oni-only-block {{
      display: flex;
    }}

    .oni-category-chip {{
      color: #ffe7a7;
      border-color: rgba(255, 213, 106, 0.38);
      background: rgba(77, 56, 21, 0.88);
    }}

    .health-summary {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) 136px;
      gap: 0;
      align-items: stretch;
      margin-top: 12px;
    }}

    .health-table {{
      width: 100%;
      border-collapse: collapse;
      table-layout: fixed;
      overflow: hidden;
      border: 1px solid rgba(129, 176, 255, 0.14);
      border-radius: 8px 0 0 8px;
      background: rgba(8, 17, 30, 0.42);
    }}

    .health-table td {{
      padding: 8px 10px;
      border: 1px solid rgba(129, 176, 255, 0.14);
      vertical-align: top;
    }}

    .health-table span {{
      display: block;
      color: var(--muted);
      font-size: 0.72rem;
      line-height: 1.1;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }}

    .health-table strong {{
      display: block;
      margin-top: 4px;
      color: var(--text);
      font-size: 1rem;
      line-height: 1.1;
    }}

    .health-faction-icon {{
      display: flex;
      flex-direction: column;
      gap: 5px;
      align-items: center;
      justify-content: center;
      min-height: 84px;
      padding: 9px 10px;
      border: 1px solid rgba(129, 176, 255, 0.14);
      border-left: 0;
      border-radius: 0 8px 8px 0;
      background: rgba(8, 17, 30, 0.42);
    }}

    .health-faction-icon span {{
      color: var(--muted);
      font-size: 0.62rem;
      line-height: 1.1;
      letter-spacing: 0.08em;
      text-align: center;
      text-transform: uppercase;
    }}

    .health-faction-icon img {{
      width: 100%;
      max-width: 72px;
      height: auto;
      object-fit: contain;
      filter: drop-shadow(0 6px 10px rgba(0, 0, 0, 0.35));
    }}

    .health-faction-icon strong {{
      max-width: 100%;
      color: var(--text);
      font-size: 0.82rem;
      line-height: 1.1;
      text-align: center;
      overflow-wrap: anywhere;
    }}

    .description-block {{
      margin-top: 14px;
      padding-top: 14px;
      border-top: 1px solid rgba(125, 183, 255, 0.14);
    }}

    .abilities-block {{
      margin-top: 14px;
      padding-top: 14px;
      border-top: 1px solid rgba(125, 183, 255, 0.14);
    }}

    .range-block {{
      margin-top: 14px;
      padding-top: 14px;
      border-top: 1px solid rgba(125, 183, 255, 0.14);
    }}

    .abilities-title {{
      margin: 0 0 10px;
      color: var(--muted);
      font-size: 0.82rem;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }}

    .abilities-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }}

    .entry-description {{
      margin: 0 0 8px;
      color: #d7e8fa;
      line-height: 1.5;
    }}

    .entry-description:last-child {{
      margin-bottom: 0;
    }}

    .entry-description.empty {{
      color: var(--muted);
    }}

    .empty-state {{
      display: none;
      margin-top: 24px;
      padding: 24px;
      border: 1px dashed var(--line-strong);
      border-radius: var(--radius);
      background: rgba(8, 17, 30, 0.72);
      color: var(--muted);
      text-align: center;
    }}

    @media (max-width: 980px) {{
      .filter-bar {{
        grid-template-columns: 1fr;
      }}

      body.oni-authenticated .filter-bar {{
        grid-template-columns: 1fr;
      }}

      .results-bar {{
        flex-direction: column;
        align-items: start;
      }}

      .card-grid {{
        grid-template-columns: 1fr;
      }}
    }}

    @media (max-width: 760px) {{
      .page {{
        width: min(100vw - 20px, 1500px);
        margin-top: 10px;
      }}

      .hero {{
        padding: 20px;
      }}

      .hero-top {{
        flex-direction: column;
      }}

      .hero-side {{
        width: 100%;
        justify-items: stretch;
      }}

      .entry-card {{
        grid-template-columns: 1fr;
      }}

      .entry-image {{
        min-height: 350px;
      }}

      .entry-image-frame {{
        width: min(180px, 100%);
      }}

      .entry-image img {{
        max-width: 180px;
      }}

      .entry-header {{
        flex-direction: column;
      }}

      .health-summary {{
        grid-template-columns: minmax(0, 1fr) 104px;
      }}

      .health-faction-icon {{
        min-height: 76px;
        padding: 6px;
      }}

      .health-faction-icon img {{
        max-width: 56px;
      }}
    }}
  </style>
</head>
<body>
  <main class="page">
    <section class="hero">
      <div class="hero-top">
        <div class="hero-copy">
          <h1>Ship Library</h1>
          <p>
            USFP ONI Database: A curated registry of confirmed hulls, variants, and field notes compiled from patrol reports, dockyard manifests, and recovered telemetry.
          </p>
          <p>
            Last updated on stardate {html.escape(build_version)}.
          </p>
        </div>
        <div class="hero-side">
          <div class="page-nav-stack">
            <a class="page-nav-link page-nav-map" href="index.html">Galactic Map</a>
            <button class="page-nav-link page-nav-library" type="button">Ship Library</button>
            <a class="page-nav-link page-nav-production" href="ProductionFlow.html">Production Flow</a>
            <button id="oni-login-btn" class="page-nav-link page-nav-auth" type="button">ONI Login</button>
          </div>
        </div>
      </div>

      <div class="filter-bar">
        <div class="filter-group">
          <label for="search-input">Search</label>
          <input id="search-input" type="search" placeholder="Name, key, role, description..." />
        </div>
        <div class="filter-group">
          <label for="faction-filter">Faction</label>
          <select id="faction-filter">{faction_options}</select>
        </div>
        <div class="filter-group">
          <label for="side-filter">Side</label>
          <select id="side-filter">
            <option value="all">All sides</option>
          </select>
        </div>
        <div class="filter-group oni-only-block">
          <label for="category-filter">Category</label>
          <select id="category-filter">
            {category_options}
          </select>
        </div>
      </div>

      <div class="results-bar">
        <div id="results-count">Showing {total_entries} of {total_entries} entries</div>
        <div id="active-filter-label">All factions and sides</div>
      </div>
    </section>

    <section class="card-grid" id="card-grid">
{cards}
    </section>

    <section class="empty-state" id="empty-state">
      No entries match the current filter selection.
    </section>
  </main>

  <script>
    const cards = Array.from(document.querySelectorAll('.entry-card'));
    const searchInput = document.getElementById('search-input');
    const factionFilter = document.getElementById('faction-filter');
    const sideFilter = document.getElementById('side-filter');
    const categoryFilter = document.getElementById('category-filter');
    const resultsCount = document.getElementById('results-count');
    const activeFilterLabel = document.getElementById('active-filter-label');
    const emptyState = document.getElementById('empty-state');
    const oniLoginBtn = document.getElementById('oni-login-btn');

    function enterGMMode() {{
      document.cookie = "gmMode=1; path=/; max-age=31536000";
    }}

    function isGM() {{
      return document.cookie
        .split(';')
        .some((cookie) => cookie.trim() === 'gmMode=1');
    }}

    function exitGMMode() {{
      document.cookie = "gmMode=; path=/; expires=Thu, 01 Jan 1970 00:00:00 UTC;";
    }}

    function syncOniAuthUI() {{
      const authenticated = isGM();
      document.body.classList.toggle('oni-authenticated', authenticated);
      if (oniLoginBtn) {{
        oniLoginBtn.textContent = authenticated ? 'ONI Logout' : 'ONI Login';
      }}
      if (!authenticated && categoryFilter) {{
        categoryFilter.value = 'all';
      }}
    }}

    function toggleOniAuth() {{
      if (isGM()) {{
        exitGMMode();
        syncOniAuthUI();
        applyFilters();
        return;
      }}

      const pwd = prompt('Enter ONI Auth Code:');
      if (pwd === 'oni1') {{
        enterGMMode();
        syncOniAuthUI();
        applyFilters();
      }} else {{
        alert('Incorrect password');
      }}
    }}

    const sideCatalog = Array.from(new Map(
      cards.map((card) => [
        card.dataset.side,
        {{
          value: card.dataset.side,
          label: card.dataset.sideLabel,
          faction: card.dataset.faction,
        }},
      ])
    ).values()).sort((a, b) => a.label.localeCompare(b.label));

    function rebuildSideOptions() {{
      const selectedFaction = factionFilter.value;
      const previousValue = sideFilter.value;
      const filteredSides = sideCatalog.filter((side) => {{
        return selectedFaction === 'all' || side.faction === selectedFaction;
      }});

      sideFilter.innerHTML = '';

      const allOption = document.createElement('option');
      allOption.value = 'all';
      allOption.textContent = 'All sides';
      sideFilter.appendChild(allOption);

      filteredSides.forEach((side) => {{
        const option = document.createElement('option');
        option.value = side.value;
        option.textContent = side.label;
        sideFilter.appendChild(option);
      }});

      const canReusePrevious = filteredSides.some((side) => side.value === previousValue);
      sideFilter.value = canReusePrevious ? previousValue : 'all';
    }}

    function applyFilters() {{
      const term = searchInput.value.trim().toLowerCase();
      const selectedFaction = factionFilter.value;
      const selectedSide = sideFilter.value;
      const selectedCategory = categoryFilter ? categoryFilter.value : 'all';
      const showOniOnly = isGM();
      let visibleCount = 0;

      cards.forEach((card) => {{
        const factionMatch = selectedFaction === 'all' || card.dataset.faction === selectedFaction;
        const sideMatch = selectedSide === 'all' || card.dataset.side === selectedSide;
        const categories = (card.dataset.categories || '').split(' ').filter(Boolean);
        const categoryMatch = selectedCategory === 'all'
          || (showOniOnly && categories.includes(selectedCategory));
        const searchMatch = !term || card.dataset.search.includes(term);
        const visible = factionMatch && sideMatch && categoryMatch && searchMatch;

        card.style.display = visible ? '' : 'none';
        if (visible) {{
          visibleCount += 1;
        }}
      }});

      resultsCount.textContent = `Showing ${{visibleCount}} of ${{cards.length}} entries`;

      const factionLabel = selectedFaction === 'all'
        ? 'All factions'
        : factionFilter.options[factionFilter.selectedIndex].textContent;
      const sideLabel = selectedSide === 'all'
        ? 'all sides'
        : sideFilter.options[sideFilter.selectedIndex].textContent;
      const categoryLabel = selectedCategory === 'all' || !showOniOnly
        ? ''
        : `, ${{categoryFilter.options[categoryFilter.selectedIndex].textContent}}`;
      activeFilterLabel.textContent = `${{factionLabel}}, ${{sideLabel}}${{categoryLabel}}`;
      emptyState.style.display = visibleCount === 0 ? 'block' : 'none';
    }}

    factionFilter.addEventListener('change', () => {{
      rebuildSideOptions();
      applyFilters();
    }});
    sideFilter.addEventListener('change', applyFilters);
    if (categoryFilter) {{
      categoryFilter.addEventListener('change', applyFilters);
    }}
    searchInput.addEventListener('input', applyFilters);
    if (oniLoginBtn) {{
      oniLoginBtn.addEventListener('click', toggleOniAuth);
    }}

    syncOniAuthUI();
    rebuildSideOptions();
    applyFilters();
  </script>
</body>
</html>"""


def main():
    settings = load_json(SETTINGS_PATH) if SETTINGS_PATH.exists() else {}
    ship_entries = load_json(SHIPMAP_PATH)
    if not isinstance(ship_entries, list):
        raise ValueError(f"{SHIPMAP_PATH} does not contain a ship list.")
    shipdata_index = load_shipdata_index()
    broken_beam_ship_keys = load_commented_beam_angle_ships()
    authoritative_descriptions = load_authoritative_description_index()
    authoritative_ship_stats = load_authoritative_ship_stats_index()

    factions_from_settings, faction_lookup, side_lookup, race_to_faction = build_side_catalog(settings)
    discovered_sides = {}
    discovered_factions = []
    seen_factions = set()
    prepared = []

    for raw_entry in ship_entries:
        if not isinstance(raw_entry, dict):
            continue

        key = str(raw_entry.get("key", "")).strip()
        name = str(raw_entry.get("name", "")).strip() or key or "Unnamed Entry"
        raw_side = raw_entry.get("side", "")
        side_label = canonical_side_label(raw_side, side_lookup, discovered_sides)
        if side_label.casefold() == "unknown":
            continue

        roles = normalize_roles(raw_entry.get("roles", []))
        if not roles:
            continue

        faction_label = resolve_faction(raw_side, faction_lookup, race_to_faction)
        if faction_label.casefold() not in seen_factions:
            discovered_factions.append(faction_label)
            seen_factions.add(faction_label.casefold())

        resolved_description = resolve_ship_description(
            key,
            name=name,
            side=side_label,
            roles=roles,
            shipmap_entry=raw_entry,
        )
        search_blob = " ".join(
            [
                key,
                name,
                side_label,
                faction_label,
                " ".join(roles),
                resolved_description["description"],
            ]
        ).casefold()
        shipdata_entry = shipdata_index.get(key, {})
        beam_arcs = _beam_arc_entries(key, shipdata_entry)
        image_src = resolve_image_src(raw_entry.get("artfileroot", ""))
        faction_icon_src = resolve_faction_icon_src(side_label, faction_label)
        authoritative_description = authoritative_descriptions.get(key, {})
        stat_entry = authoritative_ship_stats.get(key, {})
        shield_forward, shield_aft = _shield_stat_values(
            shipdata_entry.get("shields") if isinstance(shipdata_entry, dict) else None
        )
        if shield_forward is None and shield_aft is None:
            shield_forward, shield_aft = _shield_stat_values(stat_entry.get("shields"))
        hull_points = None
        if isinstance(shipdata_entry, dict):
            hull_points = _coerce_int(shipdata_entry.get("hullpoints"))
        system_health_total = _system_health_total(stat_entry.get("systemhealth"))
        abilities = _normalize_abilities(stat_entry.get("abilities"))
        broken_beam = key in broken_beam_ship_keys
        categories = []
        if broken_beam:
            categories.append(BROKEN_BEAM_CATEGORY)
        if not clean_description(authoritative_description.get("description", "")):
            categories.append(MISSING_DATABASE_DESC_CATEGORY)
        if not (
            isinstance(shipdata_entry, dict)
            and clean_description(shipdata_entry.get("long_desc", ""))
        ):
            categories.append(MISSING_SHIPDATA_DESC_CATEGORY)
        if system_health_total is None:
            categories.append(MISSING_SYSTEM_HEALTH_CATEGORY)
        if is_missing_faction_icon(faction_icon_src):
            categories.append(MISSING_DESIGN_ORIGIN_ICON_CATEGORY)
        if is_missing_ship_image(image_src):
            categories.append(MISSING_SHIP_IMAGE_CATEGORY)
        beam_range = raw_entry.get("BRange")
        if beam_range is None:
            beam_range = _max_beam_range(shipdata_entry)
        drone_endurance = raw_entry.get("DRange")
        if drone_endurance is None:
            drone_endurance = _drone_endurance(shipdata_entry)

        prepared.append(
            {
                "key": key,
                "name": name,
                "side": side_label,
                "side_key": side_label.casefold(),
                "faction": faction_label,
                "faction_key": faction_label.casefold(),
                "roles": roles,
                "long_desc": resolved_description["description"],
                "BRange": beam_range,
                "DRange": drone_endurance,
                "shield_forward": shield_forward,
                "shield_aft": shield_aft,
                "hull_points": hull_points,
                "system_health_total": system_health_total,
                "abilities": abilities,
                "categories": categories,
                "broken_beam": broken_beam,
                "beam_arcs": beam_arcs,
                "dpm_summary": _beam_dpm_summary(beam_arcs),
                "image_src": image_src,
                "faction_icon_src": faction_icon_src,
                "search_blob": search_blob,
            }
        )

    faction_labels = []
    seen_faction_labels = set()
    for faction in factions_from_settings + discovered_factions:
        folded = faction.casefold()
        if folded in seen_faction_labels:
            continue
        faction_labels.append(faction)
        seen_faction_labels.add(folded)

    prepared.sort(
        key=lambda entry: (
            entry["faction"].casefold(),
            entry["side"].casefold(),
            entry["name"].casefold(),
            entry["key"].casefold(),
        )
    )

    HTML_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(build_page(prepared, faction_labels), encoding="utf-8")
    print(f"LibraryGen summary: built 1 library page with {len(prepared)} entries.")
    print(f"  - {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
