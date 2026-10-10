"""Canvas rendering with explicit model and view inputs; owns no editor window."""
import math
import re
from MapTypes import (GRID_MODES, GRID_SPACING, RELAY_TYPE_WARNING_BUOY, STATION_OR_PLATFORM_TYPES,
    ensure_relay_dict, normalize_relay_type, object_has_blank_or_invalid_hull, get_zone_style)
from MapMetadata import get_incoming_only_gate_names
from TerrainGeometry import generate_line_coords


SIDE_VIEW_DIRECT_COLOURS = {
    "usfp": "#003f8f",
    "tsn": "#72cfff",
    "pirate": "#ff8c00",
    "pirates": "#ff8c00",
    "unknown": "#ffffff",
    "hjorden": "#2fbd5b",
    "hajorden": "#2fbd5b",
    "torgoth": "#c43b2f",
    "kralien": "#a55cff",
    "arvonian": "#d782ff",
    "skaraan": "#e3c84a",
    "ximni": "#ff66cc",
    "euphini": "#ffb347",
    "skull": "#ff6a00",
}

SIDE_VIEW_FACTION_COLOURS = {
    "usfp": "#003f8f",
    "pirate": "#ff8c00",
    "hegemony": "#b45cff",
    "ximni": "#ff66cc",
}

SIDE_VIEW_FALLBACK_COLOURS = (
    "#7dd3fc",
    "#f472b6",
    "#facc15",
    "#34d399",
    "#fb7185",
    "#c084fc",
    "#a3e635",
)

def draw_red_cross(canvas, sx, sy, radius=8, width=3, tags=()):
    canvas.create_line(
        sx - radius, sy - radius, sx + radius, sy + radius,
        fill="red", width=width, tags=tags
    )
    canvas.create_line(
        sx - radius, sy + radius, sx + radius, sy - radius,
        fill="red", width=width, tags=tags
    )

def _normalise_side_key(value):
    return re.sub(r"[^a-z0-9]+", "", str(value or "").strip().casefold())

def get_object_primary_side(obj):
    if not isinstance(obj, dict):
        return ""
    sides = obj.get("sides")
    if isinstance(sides, (list, tuple)):
        for side in sides:
            side_text = str(side or "").strip()
            if side_text:
                return side_text
        return ""
    if isinstance(sides, str):
        return sides.strip()
    return ""

def get_station_side_colour(side_value, race_to_faction_cf=None):
    side_text = str(side_value or "").strip()
    side_key = _normalise_side_key(side_text)
    if not side_key:
        return SIDE_VIEW_DIRECT_COLOURS["unknown"]
    if side_key in SIDE_VIEW_DIRECT_COLOURS:
        return SIDE_VIEW_DIRECT_COLOURS[side_key]

    faction_cf = ""
    if isinstance(race_to_faction_cf, dict):
        faction_cf = race_to_faction_cf.get(side_text.casefold(), "")
    faction_key = _normalise_side_key(faction_cf)
    if faction_key in SIDE_VIEW_FACTION_COLOURS:
        return SIDE_VIEW_FACTION_COLOURS[faction_key]

    return SIDE_VIEW_FALLBACK_COLOURS[sum(ord(ch) for ch in side_key) % len(SIDE_VIEW_FALLBACK_COLOURS)]

def draw_station_side_colour_legend(canvas):
    legend_items = (
        ("USFP", SIDE_VIEW_DIRECT_COLOURS["usfp"]),
        ("TSN", SIDE_VIEW_DIRECT_COLOURS["tsn"]),
        ("Pirate", SIDE_VIEW_DIRECT_COLOURS["pirate"]),
        ("Unknown", SIDE_VIEW_DIRECT_COLOURS["unknown"]),
        ("Hjorden", SIDE_VIEW_DIRECT_COLOURS["hjorden"]),
        ("Hegemony", SIDE_VIEW_FACTION_COLOURS["hegemony"]),
        ("Ximni", SIDE_VIEW_DIRECT_COLOURS["ximni"]),
    )
    x0, y0 = 10, 10
    row_h = 18
    width = 142
    height = 24 + (len(legend_items) * row_h)
    canvas.create_rectangle(
        x0, y0, x0 + width, y0 + height,
        fill="#071311", outline="#4aa68f", tags=("side_legend",)
    )
    canvas.create_text(
        x0 + 8, y0 + 8,
        text="Side Colours",
        fill="#d7fff2",
        anchor="nw",
        font=("Arial", 8, "bold"),
        tags=("side_legend",)
    )
    for idx, (label, colour) in enumerate(legend_items):
        y = y0 + 28 + (idx * row_h)
        canvas.create_rectangle(
            x0 + 10, y, x0 + 22, y + 12,
            fill=colour, outline="#111111", tags=("side_legend",)
        )
        canvas.create_text(
            x0 + 28, y - 1,
            text=label,
            fill="#eef6ff",
            anchor="nw",
            font=("Arial", 8),
            tags=("side_legend",)
        )

def draw_blue_gate_ring(canvas, sx, sy, radius=14, width=2, tags=()):
    canvas.create_oval(
        sx - radius, sy - radius, sx + radius, sy + radius,
        outline="#3aa7ff", width=width, tags=tags
    )

def draw_system_map(ctx, *, side_colour_view_var, grid_mode_index,
                    race_to_faction_cf, valid_hull_keys, terrain_keys):
    # Unpack pan/zoom state
    pan_x = ctx['pan_x']
    pan_y = ctx['pan_y']
    map_scale = ctx['map_scale']
    map_canvas = ctx['map_canvas']
    sm = ctx['sm']
    system_files = ctx.get('system_files', {})
    other_gate_index = ctx.get('other_gate_index', {})
    current_filename = ctx.get('current_system_filename', '')
    side_colour_view = bool(side_colour_view_var.get())
    gate_index = dict(other_gate_index)
    current_objects = sm.data.get('objects', {})
    incoming_only_gate_names = get_incoming_only_gate_names(sm.data)
    if current_filename:
        current_gate_names = set()
        for obj_name, obj in current_objects.items():
            if not isinstance(obj, dict):
                continue
            otype = str(obj.get('type', '')).lower()
            if otype in ('jumpnode', 'jumppoint', 'jump_point'):
                current_gate_names.add(obj_name.lower())
        gate_index[current_filename] = current_gate_names
    def has_invalid_destination(obj_name, obj):
        if str(obj_name).strip().casefold() in incoming_only_gate_names:
            return False
        destinations = obj.get('destinations')
        if not isinstance(destinations, dict) or not destinations:
            return True
        for dest_gate_name, dest_system_name in destinations.items():
            if not dest_gate_name or not dest_system_name:
                return True
            dest_system_key = str(dest_system_name).strip().lower()
            if not dest_system_key:
                return True
            if dest_system_key.endswith('.json'):
                dest_system_key = dest_system_key[:-5]
            dest_filename = system_files.get(dest_system_key)
            if not dest_filename:
                return True
            if str(dest_gate_name).lower() not in gate_index.get(dest_filename, set()):
                return True
        return False
    # Define local coordinate transforms to use updated pan/zoom
    hull_ranges = ctx.get('hull_ranges', {})
    def coord_to_screen(x, z):
        sx = x * map_scale + pan_x
        sy = -z * map_scale + pan_y
        return sx, sy
    def screen_to_coord(sx, sy):
        x = (sx - pan_x) / map_scale
        z = -(sy - pan_y) / map_scale
        return x, z

    pan_x = ctx['pan_x']
    pan_y = ctx['pan_y']
    map_scale = ctx['map_scale']
    map_canvas = ctx['map_canvas']
    sm = ctx['sm']
    # clear canvas
    map_canvas.delete('all')
    # draw gridlines based on current mode
    mode = GRID_MODES[grid_mode_index]
    if mode in ('grid', 'sector', 'combined'):
        w = map_canvas.winfo_width()
        h = map_canvas.winfo_height()
        x_min, z_max = screen_to_coord(0, 0)
        x_max, z_min = screen_to_coord(w, h)
        for key, spacing in GRID_SPACING.items():
            if mode == key or mode == 'combined':
                color = '#555555' if key == 'grid' else 'white'
                # vertical lines
                start_x = math.floor(x_min / spacing) * spacing
                end_x = math.ceil(x_max / spacing) * spacing
                x = start_x
                while x <= end_x:
                    sx, _ = coord_to_screen(x, 0)
                    map_canvas.create_line(sx, 0, sx, h, fill=color, tags='grid')
                    x += spacing
                # horizontal lines
                start_z = math.floor(z_min / spacing) * spacing
                end_z = math.ceil(z_max / spacing) * spacing
                z = start_z
                while z <= end_z:
                    _, sy = coord_to_screen(0, z)
                    map_canvas.create_line(0, sy, w, sy, fill=color, tags='grid')
                    z += spacing
    # draw sensor relays (interactive)
    for rname, entry in sm.list_sensor_relays().items():
        relay_entry = ensure_relay_dict(entry)
        if relay_entry is not entry:
            sm.data.setdefault('sensor_relay', {})[rname] = relay_entry
        coord = relay_entry['coordinate']
        relay_type = normalize_relay_type(relay_entry.get('type'))
        sx, sy = coord_to_screen(coord[0], coord[2])
        if relay_type == RELAY_TYPE_WARNING_BUOY:
            rr = 6
            color = 'orange'
            map_canvas.create_polygon(
                sx, sy - rr,
                sx + rr, sy + rr,
                sx - rr, sy + rr,
                fill=color,
                outline='',
                tags=('relay_pt', rname)
            )
            map_canvas.create_text(
                sx, sy - 12,
                text=rname,
                fill=color,
                font=('Arial', 8),
                tags=('relay_pt', rname)
            )
        else:
            rr = 5
            color = 'green' if (rname.startswith('SR-') or rname.startswith('Relay ')) else 'cyan'
            map_canvas.create_oval(
                sx-rr, sy-rr, sx+rr, sy+rr,
                fill=color, outline='', tags=('relay_pt', rname)
            )
            if color == 'cyan':
                map_canvas.create_text(
                    sx, sy-10,
                    text=rname, fill='cyan', font=('Arial',8), tags=('relay_pt', rname)
                )
    # draw objects (jumpnodes/jumppoints in green)
    # Use the *live* object names from the SystemMap so newly created items
    # always appear, regardless of how the sidebar list is sorted/colored.
    for name in sm.list_objects():
        obj = sm.get_object(name)
        coord = obj.get('coordinate', [0,0,0])
        otype = obj.get('type','').lower()
        sx, sy = coord_to_screen(coord[0], coord[2])

        zone_style = get_zone_style(otype)
        if zone_style is not None:
            try:
                radius = float(obj.get('radius', 0) or 0)
            except Exception:
                radius = 0.0
            if radius > 0:
                rpx = radius * map_scale
                map_canvas.create_oval(
                    sx - rpx, sy - rpx, sx + rpx, sy + rpx,
                    outline=zone_style['outline'],
                    fill=zone_style['fill'],
                    stipple='gray25',
                    tags=('obj', name)
                )
            r = 5
            map_canvas.create_oval(
                sx-r, sy-r, sx+r, sy+r,
                fill=zone_style['outline'], outline='',
                tags=('obj', name)
            )
            map_canvas.create_text(
                sx, sy-10,
                text=name,
                fill=zone_style['text'],
                font=('Arial', 8, 'bold'),
                tags=('obj', name)
            )
            continue

        # use green for jumpnode/jumppoint, white otherwise
        if side_colour_view and otype in STATION_OR_PLATFORM_TYPES:
            color = get_station_side_colour(get_object_primary_side(obj), race_to_faction_cf)
        else:
            color = 'light green' if otype in ('jumpnode','jumppoint') else 'white'

        # ── Jump node/point drift ring (pale blue) ─────────────────────────
        # If the object is a jumpnode/jumppoint and has a drift value,
        # draw a pale blue circle with radius == drift (in world units).
        if otype in ('jumpnode', 'jumppoint'):
            # Accept a few possible key spellings, default 0 if absent/non-numeric
            drift_val = (
                obj.get('drift', None)
                if obj.get('drift', None) not in (None, '')
                else obj.get('drift_range', obj.get('driftrange', 0))
            )
            try:
                drift_val = float(drift_val)
            except Exception:
                drift_val = 0.0
            if drift_val > 0:
                rpx = drift_val * map_scale
                map_canvas.create_oval(
                    sx - rpx, sy - rpx, sx + rpx, sy + rpx,
                    outline='light blue', width=2,
                    tags=('obj', name)
                )

        if otype in ('jumpnode', 'jumppoint') and has_invalid_destination(name, obj):
            ring_r = 12
            map_canvas.create_oval(
                sx - ring_r, sy - ring_r, sx + ring_r, sy + ring_r,
                outline='yellow', width=2,
                tags=('obj', name)
            )

        if otype in ('jumpnode', 'jumppoint') and name.casefold() in incoming_only_gate_names:
            draw_blue_gate_ring(map_canvas, sx, sy, radius=14, width=2, tags=('obj', name))


        # ── Station/static range visuals (weapon ranges) ───────────────────
        # BRange / DRange live in ShipMap.json on the hull entry (roles station/static).
        # We visualize:
        #  • Orange ring with radius = BRange (in world units) if BRange > 0.
        #  • Red ring with a fixed radius = 10,000 if DRange is non-zero (presence indicates defender missiles).
        # Notes:
        #  - Rings are drawn in world-units → converted to pixels via map_scale.
        #  - They share the object's name tag so they move/scale with the object.
        hull_key = obj.get('hull', '') or ''
        br, dr = hull_ranges.get(hull_key, (0, 0))
        # Allow per-object override if author put BRange/DRange on the object itself
        if 'BRange' in obj:
            try:
                br = float(obj['BRange'])
            except Exception:
                pass
        if 'DRange' in obj:
            try:
                dr = float(obj['DRange'])
            except Exception:
                pass

        # Orange BRange ring (radius == BRange world-units)
        if br and float(br) > 0:
            rpx = float(br) * map_scale
            map_canvas.create_oval(
                sx - rpx, sy - rpx, sx + rpx, sy + rpx,
                outline='orange', width=2,
                tags=('obj', name)
            )

        # Red DRange ring (any non-zero DRange → fixed 10,000 world-unit radius)
        if dr and float(dr) != 0.0:
            rpx = 10000 * map_scale
            map_canvas.create_oval(
                sx - rpx, sy - rpx, sx + rpx, sy + rpx,
                outline='red', width=2,
                tags=('obj', name)
            )


        # enlarge jumpnode/jumppoint markers
        if otype in ('jumpnode','jumppoint'):
            r = 8
        else:
            r = 5
        map_canvas.create_oval(
            sx-r, sy-r, sx+r, sy+r,
            fill=color, tags=('obj', name)
        )
        if object_has_blank_or_invalid_hull(obj, valid_hull_keys):
            draw_red_cross(map_canvas, sx, sy, radius=9, width=3, tags=('obj', name))
        map_canvas.create_text(
            sx, sy-10,
            text=name, fill=color,
            # bold and slightly larger for jump nodes
            font=('Arial',10,'bold') if otype in ('jumpnode','jumppoint') else ('Arial',8),
            tags=('obj', name)
        )
    # draw terrain as boxes
    for key in terrain_keys:
        feat = sm.get_terrain_feature(key)
        # blackhole rendering: yellow dot with black center
        t_type = feat.get('type','').lower()
        zone_style = get_zone_style(t_type)
        if zone_style is not None:
            coord = feat.get('coordinate', [0,0,0])
            try:
                radius = float(feat.get('radius', 0) or 0)
            except Exception:
                radius = 0.0
            sx, sy = coord_to_screen(coord[0], coord[2])
            if radius > 0:
                rpx = radius * map_scale
                map_canvas.create_oval(
                    sx - rpx, sy - rpx, sx + rpx, sy + rpx,
                    outline=zone_style['outline'],
                    fill=zone_style['fill'],
                    stipple='gray25',
                    tags=('terrain', key)
                )
            rr = 4
            map_canvas.create_oval(
                sx - rr, sy - rr, sx + rr, sy + rr,
                fill='blue',
                tags=('terrain_pt', key, 'coord')
            )
            map_canvas.create_text(
                sx, sy - 10,
                text=key,
                fill=zone_style['text'],
                font=('Arial', 8, 'bold'),
                tags=('terrain', key)
            )
            continue
        if t_type == 'blackhole':
            coord = feat.get('coordinate',[0,0,0])
            sx, sy = coord_to_screen(coord[0], coord[2])
            rr = 5  # same size as sensor relays
            # outer yellow dot
            map_canvas.create_oval(sx-rr, sy-rr, sx+rr, sy+rr, fill='yellow', outline='', tags=('terrain', key))
            # inner black dot
            r2 = rr / 2
            map_canvas.create_oval(sx-r2, sy-r2, sx+r2, sy+r2, fill='black', outline='', tags=('terrain', key))
            continue
        if t_type == 'planet':
            # Render as a red filled circle ~15,000 world units radius
            coord = feat.get('coordinate', [0,0,0])
            sx, sy = coord_to_screen(coord[0], coord[2])
            rpx = 15000 * map_scale
            map_canvas.create_oval(
                sx - rpx, sy - rpx, sx + rpx, sy + rpx,
                outline='red', fill='red',
                tags=('terrain', key)
            )
            # draggable/selectable center handle (blue), like other single-point terrain
            rr = 4
            map_canvas.create_oval(
                sx - rr, sy - rr, sx + rr, sy + rr,
                fill='blue',
                tags=('terrain_pt', key, 'coord')
            )
            # optional label (use name if present)
            pname = feat.get('name', '')
            if pname:
                map_canvas.create_text(
                    sx, sy - (10 if rpx > 15 else 0),
                    text=pname, fill='white', font=('Arial',8),
                    tags=('terrain', key)
                )
            continue
        if t_type == 'debris_field':
            # Circular area: center at 'coordinate', radius from 'scatter'
            coord = feat.get('coordinate', [0,0,0])
            radius = float(feat.get('scatter', 0) or 0)
            sx, sy = coord_to_screen(coord[0], coord[2])
            rpx = radius * map_scale
            # fill: mid-dark grey; keep beneath other elements via 'terrain' tag
            map_canvas.create_oval(
                sx - rpx, sy - rpx, sx + rpx, sy + rpx,
                outline='#666666', fill='#444444',
                tags=('terrain', key)
            )
            # draggable/selectable center handle (blue)
            rr = 4
            map_canvas.create_oval(
                sx - rr, sy - rr, sx + rr, sy + rr,
                fill='blue',
                tags=('terrain_pt', key, 'coord')
            )
            # optional label at center
            map_canvas.create_text(
                sx, sy - (10 if rpx > 15 else 0),
                text=key, fill='white', font=('Arial',8),
                tags=('terrain', key)
            )
            continue
        if t_type in ('hidden_minefield', 'minefield'):
            coord = feat.get('coordinate', [0,0,0])
            width = float(feat.get('width', 15000) or 0)
            height = float(feat.get('height', 15000) or 0)
            # Width/height are treated as extents from center (full size = 2x)
            extent_w = width
            extent_h = height
            x0, z0 = coord[0] - extent_w, coord[2] - extent_h
            x1, z1 = coord[0] + extent_w, coord[2] + extent_h
            sx0, sy0 = coord_to_screen(x0, z0)
            sx1, sy1 = coord_to_screen(x1, z1)
            outline = '#cc0000' if t_type == 'hidden_minefield' else '#ff9900'
            fill = '#552222' if t_type == 'hidden_minefield' else '#7a3d00'
            map_canvas.create_rectangle(
                sx0, sy0, sx1, sy1,
                outline=outline, fill=fill,
                tags=('terrain', key)
            )
            # draggable/selectable center handle (blue)
            sx, sy = coord_to_screen(coord[0], coord[2])
            rr = 4
            map_canvas.create_oval(
                sx - rr, sy - rr, sx + rr, sy + rr,
                fill='blue',
                tags=('terrain_pt', key, 'coord')
            )
            # label at center
            map_canvas.create_text(
                sx, sy - 10,
                text=key, fill='white', font=('Arial',8),
                tags=('terrain', key)
            )
            continue
        x0, _, z0 = feat.get('start', [0,0,0])
        x1, _, z1 = feat.get('end', [0,0,0])
        dx, dz = x1 - x0, z1 - z0
        length = math.hypot(dx, dz) or 1
        ux, uz = dx/length, dz/length
        px, pz = -uz, ux
        half = feat.get('scatter', 0)
        corners = [
            (x0 + px*half, z0 + pz*half),
            (x1 + px*half, z1 + pz*half),
            (x1 - px*half, z1 - pz*half),
            (x0 - px*half, z0 - pz*half)
        ]
        t_type = feat.get('type', '').lower()
        color = '#800080' if t_type == 'nebulas' else '#A52A2A' if t_type == 'asteroids' else 'cyan'
        pts = []
        for gx, gz in corners:
            sx2, sy2 = coord_to_screen(gx, gz)
            pts.extend([sx2, sy2])
        fill_color = color
        fill_stipple = ''
        if t_type in ('nebulas', 'asteroids'):
            # Tkinter doesn't support alpha in hex colors; use stipple for translucency.
            fill_stipple = 'gray25'
        map_canvas.create_polygon(
            pts, fill=fill_color, outline='',
            stipple=fill_stipple,
            tags=('terrain_poly', key)
        )
        # overlay exact placement dots for nebulae/asteroids
        if t_type in ('nebulas', 'asteroids'):
            density = int(feat.get('density', 125) or 0)
            density = max(0, min(density, 10000))
            seed = feat.get('seed')
            scatter = float(feat.get('scatter', 0) or 0)
            cache = ctx.setdefault('terrain_points_cache', {})
            cache_key = (t_type, tuple(feat.get('start', [0, 0, 0])), tuple(feat.get('end', [0, 0, 0])),
                         float(scatter), int(density), seed)
            coords = cache.get((key, cache_key))
            if coords is None and density > 0 and scatter > 0:
                coords = generate_line_coords(feat.get('start', [0, 0, 0]),
                                              feat.get('end', [0, 0, 0]),
                                              density, scatter, seed=seed)
                cache[(key, cache_key)] = coords
            if coords:
                dot_color = '#C24BFF' if t_type == 'nebulas' else '#D8A25A'
                dot_radius_world = 500 if t_type == 'nebulas' else 150
                rpx = dot_radius_world * map_scale
                for gx, _, gz in coords:
                    sx2, sy2 = coord_to_screen(gx, gz)
                    map_canvas.create_oval(
                        sx2 - rpx, sy2 - rpx, sx2 + rpx, sy2 + rpx,
                        fill=dot_color, outline='',
                        tags=('terrain_pt', key)
                    )
        # Label terrain at midpoint (hide names for asteroids & nebulas)
        if t_type not in ('asteroids', 'nebulas'):
            cx = (x0 + x1) / 2 * map_scale + pan_x
            cy = -(z0 + z1) / 2 * map_scale + pan_y
            map_canvas.create_text(cx, cy, text=key, fill='white', font=('Arial',8))
        # Draw start/end points
        ssx, ssy = coord_to_screen(x0, z0)
        esx, esy = coord_to_screen(x1, z1)
        r2 = 4
        map_canvas.create_oval(
            ssx-r2, ssy-r2, ssx+r2, ssy+r2,
            fill='blue', tags=('terrain_pt', key, 'start')
        )
        map_canvas.create_oval(
            esx-r2, esy-r2, esx+r2, esy+r2,
            fill='blue', tags=('terrain_pt', key, 'end')
        )

    # ── finally: push all terrain behind relays & objects ─────────────
    map_canvas.tag_lower('terrain_poly')
    map_canvas.tag_lower('terrain')
    map_canvas.tag_raise('terrain_pt')
    map_canvas.tag_raise('relay_pt')
    map_canvas.tag_raise('obj')
    if side_colour_view:
        draw_station_side_colour_legend(map_canvas)
        map_canvas.tag_raise('side_legend')
