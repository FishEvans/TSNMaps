import os
import sys
import json
import glob
import argparse
from pathlib import Path
import math
import random
import re
from LocMapTemplate import build_object_button, render_locmap_html
from ShipDescriptionResolver import resolve_ship_description

# Helper to locate resources when running as a module or frozen executable
def get_base_path():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    try:
        return os.path.dirname(os.path.abspath(__file__))
    except NameError:
        # Fallback if __file__ is not defined
        return os.getcwd()

# Base directories\
BASE = get_base_path()
JSON_FOLDER =  Path(get_base_path()) / "data/missions/Map Designer/Terrain"
DEFAULT_HTML_DIR = Path(BASE) / 'HTML'

# Configuration for station side colors
STATION_SIDE_COLORS = {
    'TSN': 'green',
    'USFP': 'blue'
}
DEFAULT_STATION_COLOR = 'red'

# Optional color mapping for planet classes. Keys should match the
# 'class' value in planet objects. Fallback color used when no class
# or no mapping entry exists.
PLANET_CLASS_COLORS = {
    'Terrestrial': '#9acd32',
    'Gas Giant': '#ffd27f',
    'Ice': '#bfefff',
    'Desert': '#f4a460',
    'Ocean': '#4fc3f7'
}
PLANET_CLASS_FALLBACK = '#98FB98'  # pale green

ZONE_STYLE_MAP = {
    'fcs_zone': {
        'label': 'Fuel Collection Zone',
        'fill_rgba': '54,191,214',
        'line_color': '#7fe7ff',
        'marker_color': '#7fe7ff',
        'text_color': '#bff7ff',
        'button_color': '#2d7f8e',
        'show_plot_label': False,
    }
}
DEFAULT_ZONE_STYLE = {
    'label': 'Zone',
    'fill_rgba': '214,149,54',
    'line_color': '#ffd37f',
    'marker_color': '#ffd37f',
    'text_color': '#fff0bf',
    'button_color': '#8e622d',
    'show_plot_label': True,
}

# Grid reference generator
def get_grid_reference(x, z):
    grid_size = 20000
    origin_x = -240000
    origin_z = 280000

    dx = int((x - origin_x) // grid_size)
    dz = int((z - origin_z) // grid_size)

    col = dx % 100  # Numbers increase left to right (x)
    row = dz % 26   # Letters increase bottom to top (z)

    letter = chr(ord('A') + row)
    number = f"{col:02d}"
    return f"{letter}{number}"

def is_hidden(obj):
    return str(obj.get('hideonmap')).lower() == 'true'

def get_zone_style(zone_type):
    zone_key = str(zone_type or '').strip().lower()
    if not zone_key:
        return None
    if zone_key in ZONE_STYLE_MAP:
        return ZONE_STYLE_MAP[zone_key]
    if zone_key.endswith('_zone'):
        return {
            **DEFAULT_ZONE_STYLE,
            'label': zone_key.replace('_', ' ').title(),
        }
    return None

def is_zone_type(zone_type):
    return get_zone_style(zone_type) is not None

def build_circle_points(x0, y0, radius, segments=48):
    angles = [2 * math.pi * i / segments for i in range(segments)]
    xs = [x0 + radius * math.cos(a) for a in angles]
    ys = [y0 + radius * math.sin(a) for a in angles]
    return xs, ys

def generate_line_coords(start, end, count, radius, seed=None, y_range=(-600, 600),
                         clumps=(), voids=()):
    # Keep LocMapGen in sync with the deterministic asteroid/nebula placement
    # used by the editor and runtime terrain generator.
    rng = random.Random(seed)
    coords = []

    dx = end[0] - start[0]
    dz = end[2] - start[2]
    length = math.hypot(dx, dz)

    if length == 0:
        return []

    for _ in range(count):
        t = rng.random()
        cx = start[0] + t * dx
        cz = start[2] + t * dz

        u = max(1e-6, rng.random())
        d = radius * math.sqrt(-math.log(u))

        angle = rng.uniform(0, 2 * math.pi)
        ox = math.cos(angle) * d
        oz = math.sin(angle) * d

        x = cx + ox
        z = cz + oz
        y = rng.uniform(*y_range)

        density_bias = 0.0

        for cx_, cz_, r, s in clumps:
            dist = math.hypot(x - cx_, z - cz_)
            if dist < r:
                density_bias += (1 - dist / r) ** 2 * s

        for vx_, vz_, r, s in voids:
            dist = math.hypot(x - vx_, z - vz_)
            if dist < r:
                density_bias -= (1 - dist / r) ** 2 * s

        if density_bias != 0:
            push = density_bias * radius * 0.15
            x += rng.uniform(-push, push)
            z += rng.uniform(-push, push)

        coords.append((x, y, z))

    return coords

# Load external ship map once
shipmap_path = Path('HTML') / 'Images' / 'Ships' / 'ShipMap.json'
with open(shipmap_path) as f:
    loaded_map = json.load(f)
    if isinstance(loaded_map, list):
        SHIP_MAP = {entry['key']: entry for entry in loaded_map if 'key' in entry}
    else:
        SHIP_MAP = loaded_map

class MapViewer:
    def __init__(self, system_file):
        try:
            with open(system_file) as f:
                self.system_data = json.load(f)
        except Exception as e:
            raise ValueError(f"Error loading system file {system_file}: {e}")
        self.objects = self.system_data.get('objects', {})
        self.terrain = self.system_data.get('terrain', {})
        self.system_file = system_file
        self.system_name = Path(system_file).stem
        self.warnings = []
        # Local system maps should NOT be offset by systemMapCoord.
        # That offset is only for positioning systems on the galactic map.
        # Force zero offset here so local maps render in their native coordinates. This note left more for absentmined AI's (third time its tried to implament this!)
        self.offset = [0, 0, 0]

        if 'sensor_relay' in self.system_data:
            for name, coord in self.system_data['sensor_relay'].items():
                if name in self.objects:
                    continue
                entry = {'type': 'sensor_relay'}
                # pull out coordinate (as before)…
                if isinstance(coord, dict) and 'coordinate' in coord:
                    entry['coordinate'] = coord['coordinate']
                    # …but also carry over any hideonmap/description flags
                    relay_type = str(coord.get('type', '')).strip()
                    if relay_type:
                        entry['relayType'] = relay_type
                    for fld in ('hideonmap', 'HideOnSCMap', 'description', 'broadcast', 'ping', 'range'):
                        if fld in coord:
                            entry[fld] = coord[fld]
                else:
                    entry['coordinate'] = coord
                self.objects[name] = entry

    def project(self, coord):
        # For local system maps, return raw X,Z without any offset.
        x, y, z = coord
        return x, z

    def get_station_color(self, obj):
        for side, color in STATION_SIDE_COLORS.items():
            if side in obj.get('sides', []):
                return color
        return DEFAULT_STATION_COLOR

    def _warn(self, message):
        self.warnings.append(message)

    def _build_button_markup(self, names, obj_data, color_lookup=None):
        buttons = []
        for name in names:
            if name not in obj_data:
                continue
            color = color_lookup.get(name) if color_lookup else None
            buttons.append(build_object_button(name, obj_data[name]['hidden'], color))
        return '\n    '.join(buttons)

    def _build_html_context(
        self,
        out_path,
        sys_name,
        alignment,
        fig_json,
        obj_data,
        system_meta,
        stations,
        relays,
        planets,
        gates,
        zones,
        zone_button_color_map,
        planet_trace_indices,
        blackhole_trace_indices,
    ):
        station_color_map = {name: color for name, color in stations}
        return {
            'title': os.path.basename(out_path),
            'sys_name': sys_name,
            'alignment': alignment,
            'fig_json': json.dumps(fig_json),
            'obj_data': json.dumps(obj_data),
            'system_meta': json.dumps(system_meta),
            'gate_buttons': self._build_button_markup(gates, obj_data),
            'station_buttons': self._build_button_markup(
                [name for name, _ in stations],
                obj_data,
                color_lookup=station_color_map,
            ),
            'relay_buttons': self._build_button_markup(relays, obj_data),
            'zone_buttons': self._build_button_markup(
                zones,
                obj_data,
                color_lookup=zone_button_color_map,
            ),
            'planet_buttons': self._build_button_markup(planets, obj_data),
            'planet_trace_indices': json.dumps(planet_trace_indices),
            'blackhole_trace_indices': json.dumps(blackhole_trace_indices),
        }

    def _render_zone_feature(self, name, zone, trace_target, data_target, obj_data, zones, zone_button_color_map):
        zone_type = str(zone.get('type', '')).strip().lower()
        style = get_zone_style(zone_type)
        if style is None:
            return False

        coord = zone.get('coordinate')
        try:
            radius = float(zone.get('radius', 0) or 0)
        except Exception:
            radius = 0.0
        if not (isinstance(coord, (list, tuple)) and len(coord) >= 2 and radius > 0):
            return True

        x0, y0 = self.project(coord)
        hidden = is_hidden(zone)
        grid_ref = get_grid_reference(x0, y0)
        display_name = f"**{name}**" if hidden else name
        xs, ys = build_circle_points(x0, y0, radius)

        if hidden:
            fill = 'rgba(255,255,0,0.35)'
            line_color = 'yellow'
            line_width = 2
            marker_color = 'yellow'
            text_color = 'yellow'
        else:
            fill = f"rgba({style['fill_rgba']},0.30)"
            line_color = style['line_color']
            line_width = 2
            marker_color = style['marker_color']
            text_color = style['text_color']
        show_plot_label = bool(style.get('show_plot_label', True))

        area_trace = {
            'type': 'scatter',
            'x': xs + [xs[0]],
            'y': ys + [ys[0]],
            'fill': 'toself',
            'fillcolor': fill,
            'line': {'shape': 'spline', 'color': line_color, 'width': line_width},
            'hoverinfo': 'none',
        }
        center_trace = {
            'type': 'scatter',
            'x': [x0],
            'y': [y0],
            'mode': 'markers+text' if show_plot_label else 'markers',
            'marker': {
                'symbol': 'circle-open',
                'size': 10,
                'color': marker_color,
                'line': {'color': marker_color, 'width': 2},
            },
            'hovertext': [f"{name} [{grid_ref}]"],
            'hoverinfo': 'text',
        }
        if show_plot_label:
            center_trace['text'] = [display_name]
            center_trace['textposition'] = 'top center'
            center_trace['textfont'] = {'color': text_color, 'size': 12}
        if hidden:
            area_trace['gmOnly'] = True
            center_trace['gmOnly'] = True

        trace_target.append(area_trace)
        data_target.append(center_trace)

        entry = {
            'type': zone_type,
            'zoneLabel': style['label'],
            'x': x0,
            'y': y0,
            'grid': grid_ref,
            'hidden': hidden,
            'label': display_name,
            'radius': int(radius) if radius.is_integer() else radius,
        }
        if zone.get('description'):
            entry['description'] = zone['description']
        obj_data[name] = entry
        zones.append(name)
        zone_button_color_map[name] = style['button_color']
        return True

    def generate(self, output_html=None):
        if output_html:
            out_path = output_html
        else:
            os.makedirs(DEFAULT_HTML_DIR, exist_ok=True)
            sys_name = os.path.splitext(os.path.basename(self.system_file))[0]
            out_path = os.path.join(DEFAULT_HTML_DIR, f"{sys_name}.html")

        sys_name = os.path.splitext(os.path.basename(self.system_file))[0]
        alignment = self.system_data.get('systemalignment', '')
        metadata = self.system_data.get('metadata', {})
        intel = metadata.get('intel', {}) if isinstance(metadata.get('intel', {}), dict) else {}

        def ensure_list(value):
            if isinstance(value, list):
                return value
            if value is None:
                return []
            return [str(value)]

        def pick_last_author(meta):
            if meta.get('last_revision_author'):
                return meta.get('last_revision_author')
            authors = meta.get('all_authors')
            if isinstance(authors, list) and authors:
                return authors[-1]
            if meta.get('original_author'):
                return meta.get('original_author')
            return ''

        def pick_original_author(meta):
            if meta.get('original_author'):
                return meta.get('original_author')
            authors = meta.get('all_authors')
            if isinstance(authors, list) and authors:
                return authors[0]
            return ''

        def format_version_tag(date_str, revision_number):
            if not date_str:
                return ''
            date_str = str(date_str).strip()
            y = m = d = None
            m1 = re.match(r'^(\d{4})-(\d{2})-(\d{2})$', date_str)
            m2 = re.match(r'^(\d{2})/(\d{2})/(\d{4})$', date_str)
            m3 = re.match(r'^(\d{4})/(\d{2})/(\d{2})$', date_str)
            if m1:
                y, m, d = m1.group(1), m1.group(2), m1.group(3)
            elif m2:
                d, m, y = m2.group(1), m2.group(2), m2.group(3)
            elif m3:
                y, m, d = m3.group(1), m3.group(2), m3.group(3)
            if not (y and m and d):
                return ''
            day = str(int(d))
            month = str(int(m))
            yy = str(y)[-2:]
            ver = revision_number if revision_number is not None else 0
            return f"{day}{month}{yy}.{ver}"

        revision_number = metadata.get('revision_number')
        version_tag = format_version_tag(metadata.get('revision_date'), revision_number)
        all_authors = ensure_list(metadata.get('all_authors', []))

        system_meta = {
            'system_name': sys_name,
            'description': metadata.get('sysdescription', ''),
            'exports': ensure_list(metadata.get('exports', [])),
            'assets': ensure_list(intel.get('assets', [])),
            'focus': metadata.get('focus', ''),
            'intel': {
                'pirate': intel.get('pirate', ''),
                'enemy': intel.get('enemy', '')
            },
            'original_author': pick_original_author(metadata),
            'last_author': pick_last_author(metadata),
            'revision_number': revision_number if revision_number is not None else 0,
            'version_tag': version_tag,
            'all_authors': all_authors
        }
        terrain_traces = []
           # data = terrain_traces[:]
        data = []
        obj_data = {}
        gates, stations, relays, planets, zones = [], [], [], [], []
        zone_button_color_map = {}

        # --- Terrain rendering ---
        # Support:
        #  - asteroids / nebulas : rectangular "lane" between start/end with width from scatter
        #  - debris_field        : circular area centered at coordinate with radius = scatter
        for key, r in self.terrain.items():
            ttype = r.get('type', '')
            hidden = is_hidden(r)

            if self._render_zone_feature(
                key,
                r,
                terrain_traces,
                terrain_traces,
                obj_data,
                zones,
                zone_button_color_map,
            ):
                continue

            # ---------- Rectangular "lane" style (asteroids / nebulas) ----------
            if ttype in ('asteroids', 'nebulas'):
                if 'start' not in r or 'end' not in r:
                    continue

                start = r.get('start')
                end = r.get('end')
                x1, y1 = self.project(r['start'])
                x2, y2 = self.project(r['end'])
                length = math.hypot(x2 - x1, y2 - y1)
                width = 2 * r.get('scatter', 0)
                area = length * width
                density = r.get('density', 0)
                eff_den = density * 1e8 / area if area else density
                alpha = max(0.4, min(1, eff_den / 200))
                # base colors (RGBA will be set below)
                if ttype == 'asteroids':
                    rgb = '165,42,42'       # brown-ish
                else:
                    rgb = '128,0,128'       # purple
                # Orientation vectors for rectangle corners
                ux, uy = ((x2 - x1) / length, (y2 - y1) / length) if length else (1, 0)
                vx, vy = -uy, ux
                cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
                hl, hw = length / 2, width / 2
                corners_x = [
                    cx + ux * hl + vx * hw, cx - ux * hl + vx * hw,
                    cx - ux * hl - vx * hw, cx + ux * hl - vx * hw
                ]
                corners_y = [
                    cy + uy * hl + vy * hw, cy - uy * hl + vy * hw,
                    cy - uy * hl - vy * hw, cy + uy * hl - vy * hw
                ]

                if hidden:
                    fill = 'rgba(255,255,0,0.6)'  # yellow tint for GM-only
                    line_color = 'yellow'
                    line_width = 2
                else:
                    fill = f'rgba({rgb},{alpha})'
                    line_color = fill
                    line_width = 0

                terrain_trace = {
                    'type': 'scatter',
                    'x': corners_x + [corners_x[0]],
                    'y': corners_y + [corners_y[0]],
                    'fill': 'toself',
                    'fillcolor': fill,
                    'line': {'shape': 'spline', 'color': line_color, 'width': line_width},
                    'hoverinfo': 'none'
                }
                if hidden:
                    terrain_trace['gmOnly'] = True
                terrain_traces.append(terrain_trace)

                try:
                    density = max(0, min(int(r.get('density', 0) or 0), 10000))
                except Exception:
                    density = 0
                try:
                    scatter = float(r.get('scatter', 0) or 0)
                except Exception:
                    scatter = 0.0
                seed = r.get('seed')

                if (
                    density > 0
                    and scatter > 0
                    and isinstance(start, (list, tuple))
                    and isinstance(end, (list, tuple))
                    and len(start) >= 3
                    and len(end) >= 3
                ):
                    coords = generate_line_coords(start, end, density, scatter, seed=seed)
                    if coords:
                        if hidden:
                            dot_color = 'yellow'
                        elif ttype == 'nebulas':
                            dot_color = '#C24BFF'
                        else:
                            dot_color = '#D8A25A'

                        dot_trace = {
                            'type': 'scatter',
                            'x': [gx for gx, _, _ in coords],
                            'y': [gz for _, _, gz in coords],
                            'mode': 'markers',
                            'marker': {
                                'size': 4 if ttype == 'nebulas' else 2,
                                'color': dot_color,
                                'opacity': 0.8,
                            },
                            'hoverinfo': 'none',
                        }
                        if hidden:
                            dot_trace['gmOnly'] = True
                        terrain_traces.append(dot_trace)
                continue

            # ---------- Circular debris field (center + radius) ----------
            if ttype == 'debris_field':
                coord = r.get('coordinate')
                radius = float(r.get('scatter', 0) or 0)
                if not (isinstance(coord, (list, tuple)) and len(coord) >= 2 and radius > 0):
                    continue

                x0, y0 = self.project(coord)

                # Alpha scaling similar to lanes, but using circle area
                density = r.get('density', 0)
                area = math.pi * radius * radius
                eff_den = density * 1e8 / area if area else density
                alpha = max(0.4, min(1, eff_den / 200))

                if hidden:
                    fill = 'rgba(255,255,0,0.6)'   # GM-only highlight
                    line_color = 'yellow'
                    line_width = 2
                else:
                    # Dark grey fill for visible debris
                    fill = f'rgba(64,64,64,{alpha})'
                    line_color = fill
                    line_width = 0

                # Approximate circle with polygon
                N = 48
                angles = [2 * math.pi * i / N for i in range(N)]
                xs = [x0 + radius * math.cos(a) for a in angles]
                ys = [y0 + radius * math.sin(a) for a in angles]

                terrain_trace = {
                    'type': 'scatter',
                    'x': xs + [xs[0]],
                    'y': ys + [ys[0]],
                    'fill': 'toself',
                    'fillcolor': fill,
                    'line': {'shape': 'spline', 'color': line_color, 'width': line_width},
                    'hoverinfo': 'none'
                }
                if hidden:
                    terrain_trace['gmOnly'] = True
                terrain_traces.append(terrain_trace)
                continue

            # ---------- Minefield (axis-aligned rectangle) ----------
            if ttype in ('hidden_minefield', 'minefield'):
                coord = r.get('coordinate')
                width = float(r.get('width', 15000) or 0)
                height = float(r.get('height', 15000) or 0)
                if not (isinstance(coord, (list, tuple)) and len(coord) >= 2 and width > 0 and height > 0):
                    continue

                x0, y0 = self.project(coord)
                # Width/height are treated as extents from center (full size = 2x)
                extent_w = width
                extent_h = height

                # Alpha scaling based on density and area
                density = r.get('density', 0)
                area = (width * 2) * (height * 2)
                eff_den = density * 1e8 / area if area else density
                alpha = max(0.4, min(1, eff_den / 200))

                is_hidden_minefield = (ttype == 'hidden_minefield')
                if hidden:
                    fill = 'rgba(255,255,0,0.6)'  # GM-only highlight
                    line_color = 'yellow'
                    line_width = 2
                else:
                    fill = f'rgba({204 if is_hidden_minefield else 255},{0 if is_hidden_minefield else 153},0,{alpha})'
                    line_color = fill
                    line_width = 0

                corners_x = [
                    x0 - extent_w, x0 + extent_w, x0 + extent_w, x0 - extent_w
                ]
                corners_y = [
                    y0 - extent_h, y0 - extent_h, y0 + extent_h, y0 + extent_h
                ]

                terrain_trace = {
                    'type': 'scatter',
                    'x': corners_x + [corners_x[0]],
                    'y': corners_y + [corners_y[0]],
                    'fill': 'toself',
                    'fillcolor': fill,
                    'line': {'shape': 'linear', 'color': line_color, 'width': line_width},
                    'hoverinfo': 'none'
                }
                if hidden:
                    terrain_trace['gmOnly'] = True
                terrain_traces.append(terrain_trace)

                # Center warning marker + label
                warn_trace = {
                    'type': 'scatter',
                    'x': [x0],
                    'y': [y0],
                    'mode': 'markers+text',
                    'marker': {
                        'symbol': 'triangle-up',
                        'size': 18,
                        'color': '#FFA500',
                        'line': {'color': '#FFD700', 'width': 2}
                    },
                    'text': ['Mines'],
                    'textposition': 'bottom center',
                    'textfont': {'color': 'white', 'size': 12},
                    'hoverinfo': 'none'
                }
                if hidden:
                    warn_trace['gmOnly'] = True
                terrain_traces.append(warn_trace)
                continue

            # ---------- Planet rendering (point objects with optional class/description) ----------
            if ttype == 'planet':
                coord = r.get('coordinate')
                if not (isinstance(coord, (list, tuple)) and len(coord) >= 2):
                    continue
                x0, y0 = self.project(coord)
                display = r.get('name', key)
                grid_ref = get_grid_reference(x0, y0)
                hidden = is_hidden(r)

                # visual styling
                # choose color based on class, fallback to pale green
                cls = r.get('class')
                if hidden:
                    fill_color = 'yellow'
                else:
                    fill_color = PLANET_CLASS_COLORS.get(cls, PLANET_CLASS_FALLBACK)
                # increase icon size by 10x (user request)
                size = 50
                text_size = 14

                trace = {
                    'type': 'scatter',
                    'x': [x0], 'y': [y0],
                    'mode': 'markers+text',
                    'marker': {'symbol': 'circle', 'size': size, 'color': fill_color},
                    'text': [display],
                    'textposition': 'top center',
                    'textfont': {'color': 'white', 'size': text_size},
                    'hovertext': [f"{display} [{grid_ref}]"],
                    'hoverinfo': 'text'
                }
                if hidden:
                    trace['gmOnly'] = True

                trace['meta'] = {
                    'base_marker_size': size,
                    'base_text_size': text_size,
                    'scale_on_zoom': True,
                    'map_object_type': 'planet',
                }
                terrain_traces.append(trace)
                # We'll expose planets into obj_data later (alongside blackholes)
                # store a lightweight marker in a temp list for later processing
                # use the display name as the key
                r['_planet_display_name'] = display
                planets.append(display)
                continue

        data.extend(terrain_traces)

        # ——— Add black holes as their own markers ———
        # ——— Prep a helper so we treat hideonmap exactly the same everywhere ———
        blackholes = []
        for key, r in self.terrain.items():
            if r.get('type') != 'blackhole' or is_hidden(r):
                continue
            coord = r.get('coordinate')
            if isinstance(coord, (list, tuple)) and len(coord) >= 2:
                x, y = self.project(coord)
                display = key
                grid_ref = get_grid_reference(x, y)
                # add scatter marker+label for the black hole
                bh_size = 20
                text_size = 12
                bh_trace = {
                    'type': 'scatter',
                    'x': [x], 'y': [y],
                    'mode': 'markers+text',
                    'marker': {'symbol': 'star', 'size': bh_size, 'color': 'yellow'},
                    'text': [display],
                    'textposition': 'top center',
                    'textfont': {'color': 'white', 'size': text_size},
                    'hovertext': [f"{display} [{grid_ref}]"],
                    'hoverinfo': 'text'
                }
                bh_trace['meta'] = {
                    'base_marker_size': bh_size,
                    'base_text_size': text_size,
                    'scale_on_zoom': True,
                    'map_object_type': 'blackhole',
                }
                data.append(bh_trace)
                # expose it to the JS highlight/info panel
                obj_data[display] = {'type': 'blackhole', 'x': x, 'y': y, 'grid': grid_ref}
                blackholes.append(display)
        # ——— Expose planets from terrain into obj_data so they appear in the info panel ———
        for key, r in self.terrain.items():
            if r.get('type') != 'planet':
                continue
            coord = r.get('coordinate')
            if not (isinstance(coord, (list, tuple)) and len(coord) >= 2):
                continue
            x, y = self.project(coord)
            display = r.get('name', key)
            hidden = is_hidden(r)
            grid_ref = get_grid_reference(x, y)
            entry = {'type': 'planet', 'x': x, 'y': y, 'grid': grid_ref, 'hidden': hidden}
            if r.get('description'):
                entry['description'] = r.get('description')
            if r.get('class'):
                entry['class'] = r.get('class')
            obj_data[display] = entry
            # ensure planet is listed for sidebar buttons
            if display not in planets:
                planets.append(display)

        for name, obj in self.objects.items():
            # now skip solely based on hideonmap
            hidden = is_hidden(obj)

            if self._render_zone_feature(
                name,
                obj,
                data,
                data,
                obj_data,
                zones,
                zone_button_color_map,
            ):
                continue

            x, y = self.project(obj.get('coordinate', [0, 0, 0]))
            typ = obj.get('type', '')
            grid_ref = get_grid_reference(x, y)
            symbol = 'circle'
            mode = 'markers+text'
            color = 'white'
            size = 12
            text_size = 14
            marker_line = None
            text_color = 'white'

            if typ in ('jumppoint', 'jumpnode'):
                symbol = 'circle-open'
                size = 16
                text_size = 20
                color = '#50CC50'
                marker_line = {'color': '#50CC50', 'width': 5}  # bolder circle outline
                text_color = '#50CC50'  # gate label color
                gates.append(name)
            elif typ == 'station':
                symbol = 'square'
                color = self.get_station_color(obj)
                stations.append((name, color))
            elif typ == 'sensor_relay':
                relay_type = str(obj.get('relayType', 'Sensor Relay')).strip().casefold()
                if relay_type == 'warning buoy':
                    symbol = 'triangle-up'
                    size = 8
                    color = 'orange'
                    text_color = 'orange'
                    if re.match(r'^(?:WB[- ]?\d+|Warning Buoy \d+)$', name):
                        size = 5
                        mode = 'markers'
                    else:
                        mode = 'markers+text'
                        relays.append(name)
                else:
                    symbol = 'circle'
                    if re.match(r'^(?:SR[- ]?\d+|Sensor Relay \d+)$', name):
                        size = 3
                        mode = 'markers'
                    else:
                        size = 6
                        color = '#FF13F0'
                        mode = 'markers+text'
                        relays.append(name)
            
            elif typ == 'platform':
                symbol = 'pentagon-open'
                size = 3
                color = 'orange'
                mode = 'markers'
            
            
            trace = {
                'type': 'scatter',
                'x': [x],
                'y': [y],
                'mode': mode,
                'marker': {'symbol': symbol, 'size': size, 'color': color},
                'hovertext': [f"{name} [{grid_ref}]"],
                'hoverinfo': 'text'
            }

            # apply outline styling for open symbols (e.g., jumppoint/jumpnode)
            if marker_line is not None:
                trace['marker']['line'] = marker_line

            display_name = f"**{name}**" if hidden else name
            if 'text' in mode:
                trace.update({
                    'text': [display_name],
                    'textposition': 'top center',
                    'textfont': {'color': text_color, 'size': text_size}
                })
            #data.append(trace)

            if hidden:
                trace['gmOnly'] = True
            # attach meta so JS can rescale markers on zoom
            trace['meta'] = {'base_marker_size': size, 'base_text_size': text_size}
            data.append(trace)

            entry = {
                'type': typ,
                'x': x,
                'y': y,
                'grid': grid_ref,
                'hidden': hidden,
                'label': f"**{name}**" if hidden else name
            }

            # ——— carry over description if present ———
            if obj.get('description'):
                entry['description'] = obj['description']            
            if typ == 'sensor_relay':
                relay_type = obj.get('relayType')
                if relay_type:
                    entry['relayType'] = relay_type
                for relay_field in ('broadcast', 'ping', 'range'):
                    if relay_field in obj and obj.get(relay_field) not in (None, ''):
                        entry[relay_field] = obj.get(relay_field)
            
            if typ in ('jump_point', 'jumppoint', 'jumpnode'):
                raw_dest = obj.get('destinations', {})
                clean_dest = {
                    str(k): str(v) for k, v in raw_dest.items()
                    if isinstance(k, (str, int)) and isinstance(v, (str, int))
                }
                if clean_dest:
                    entry['destinations'] = clean_dest
            if typ == 'station':
                entry.update({'hull': obj.get('hull', 'Unknown'), 'facilities': obj.get('facilities', []), 'sides': obj.get('sides', [])})
                hull_key = obj.get('hull')
                hull_data = SHIP_MAP.get(hull_key)
                if not hull_data and hull_key:
                    self._warn(f"{sys_name}: no match found for hull '{hull_key}'")
                if hull_data:
                    entry['hullName'] = hull_data.get('name')
                    entry['hullImage'] = f"Images/Ships/{hull_data.get('artfileroot')}256.png"
                    entry['hullDescription'] = resolve_ship_description(
                        hull_key,
                        name=hull_data.get('name', ''),
                        side=hull_data.get('side', ''),
                        roles=hull_data.get('roles', []),
                        shipmap_entry=hull_data,
                    )['description']
            obj_data[name] = entry

        gates.sort()
        stations.sort(key=lambda x: x[0])
        relays.sort()
        blackholes.sort()
        zones.sort()

        layout = {
    'title': sys_name,
    'paper_bgcolor': 'black',
    'plot_bgcolor': 'black',
    'font': {'color': 'white'},
    'margin': {'l': 0, 'r': 0, 't': 40, 'b': 0},
    'autosize': True,
    'dragmode': 'pan',
        'hovermode': 'closest',
    'xaxis': {
        'color': 'white',
        'showgrid': True,
        'gridcolor': 'gray',
        'dtick': 20000,
        'title': 'X Axis'
    },
    'yaxis': {
        'color': 'white',
        'showgrid': True,
        'gridcolor': 'gray',
        'dtick': 20000,
        'scaleanchor': 'x',
        'scaleratio': 1,
        'title': 'Z Axis'
    },
    'shapes': [
    ]
}
        fig_json = {'data': data, 'layout': layout}
        # compute trace indices for planets and blackholes so JS can efficiently rescale only them
        planet_trace_indices = []
        blackhole_trace_indices = []
        # data is terrain_traces followed by object traces; only traces explicitly
        # tagged as scalable should resize during Plotly zoom.
        for i, t in enumerate(data):
            try:
                meta = t.get('meta', {})
                if not meta.get('scale_on_zoom'):
                    continue
                if meta.get('map_object_type') == 'planet':
                    planet_trace_indices.append(i)
                    continue
                if meta.get('map_object_type') == 'blackhole':
                    blackhole_trace_indices.append(i)
            except Exception:
                continue
        template_context = self._build_html_context(
            out_path=out_path,
            sys_name=sys_name,
            alignment=alignment,
            fig_json=fig_json,
            obj_data=obj_data,
            system_meta=system_meta,
            stations=stations,
            relays=relays,
            planets=planets,
            gates=gates,
            zones=zones,
            zone_button_color_map=zone_button_color_map,
            planet_trace_indices=planet_trace_indices,
            blackhole_trace_indices=blackhole_trace_indices,
        )

        try:
            html = render_locmap_html(template_context)
        except RuntimeError as exc:
            raise RuntimeError(
                f"Error rendering local map HTML for {sys_name}: {exc}"
            ) from exc

        with open(out_path, 'w') as f:
            f.write(html)

      
    def plot(self, output_html=None):
        self.generate(output_html)

# Module entry point
def main():
    os.chdir(BASE)
    parser = argparse.ArgumentParser(description='Generate interactive map HTML from system JSON')
    parser.add_argument('system_files', nargs='*', help='JSON files to process')
    parser.add_argument('-d', '--output-dir', default=None, help='Override HTML output directory')
    args = parser.parse_args()
    files = args.system_files or glob.glob(str(JSON_FOLDER / '*.json'))
    built_systems = []
    failed_systems = []
    warnings = []
    for jf in files:
        system_name = Path(jf).stem
        out_dir = args.output_dir or DEFAULT_HTML_DIR
        os.makedirs(out_dir, exist_ok=True)
        out_file = os.path.join(out_dir, os.path.splitext(os.path.basename(jf))[0] + '.html')
        try:
            viewer = MapViewer(jf)
            viewer.plot(out_file)
            built_systems.append(system_name)
            warnings.extend(viewer.warnings)
        except Exception as exc:
            failed_systems.append((system_name, str(exc)))

    print(
        f"LocMapGen summary: built {len(built_systems)} system map(s), "
        f"failed {len(failed_systems)}, warnings {len(warnings)}."
    )
    if failed_systems:
        print("LocMapGen failed systems:")
        for system_name, error in failed_systems:
            print(f"  - {system_name}: {error}")
    if warnings:
        print("LocMapGen warnings:")
        for warning in warnings:
            print(f"  - {warning}")

if __name__ == '__main__':
    main()
