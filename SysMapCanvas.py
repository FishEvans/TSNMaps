import tkinter as tk
from tkinter import ttk
import SystemEditor
import random
import math
import time
import os
import json
from typing import Tuple

_DARK_GREEN = "#006400"

def _load_ct_maps(toolbar):
    """
    Lazy-load and cache cargo_teams faction/race maps on the toolbar so
    SysMapCanvas doesn't need SystemEditor internals.
    """
    rtf = getattr(toolbar, '_race_to_faction_cf', None)
    ftr = getattr(toolbar, '_faction_to_races_cf', None)
    if rtf is not None and ftr is not None:
        return rtf, ftr
    rtf, ftr = {}, {}
    try:
        base = getattr(toolbar, 'base', os.getcwd())
        ct_path = os.path.join(base, 'cargo_teams.json')
        with open(ct_path, 'r') as f:
            ct = json.load(f)
        races = ct.get('Races', {}) or {}
        for race, info in races.items():
            fac = str(info.get('Faction', '')).strip()
            if not fac:
                continue
            rtf[race.casefold()] = fac.casefold()
            ftr.setdefault(fac.casefold(), set()).add(race.casefold())
    except Exception:
        rtf, ftr = {}, {}
    setattr(toolbar, '_race_to_faction_cf', rtf)
    setattr(toolbar, '_faction_to_races_cf', ftr)
    return rtf, ftr

def _split_hulls_by_side(hulls, side_val, hull_side_map, toolbar):
    side_cf = (side_val or '').casefold()
    if not side_cf:
        return [], [], list(hulls)
    race_to_faction_cf, faction_to_races_cf = _load_ct_maps(toolbar)
    allowed = {side_cf}
    if side_cf in race_to_faction_cf:
        fac_cf = race_to_faction_cf[side_cf]
        allowed.add(fac_cf)
        allowed |= set(faction_to_races_cf.get(fac_cf, set()))
    if side_cf in faction_to_races_cf:
        allowed |= set(faction_to_races_cf.get(side_cf, set()))
    match_side, match_faction, others = [], [], []
    for h in hulls:
        h_side_cf = str(hull_side_map.get(h, '')).casefold()
        if h_side_cf == side_cf:
            match_side.append(h)
        elif h_side_cf in allowed:
            match_faction.append(h)
        else:
            others.append(h)
    return match_side, match_faction, others

def _build_hull_options(hulls, side_val, hull_side_map, toolbar, include_others):
    match_side, match_faction, others = _split_hulls_by_side(
        hulls, side_val, hull_side_map, toolbar
    )
    match_side_sorted = sorted(match_side, key=str.casefold)
    match_faction_sorted = sorted(match_faction, key=str.casefold)
    others_sorted = sorted(others, key=str.casefold)
    ordered = match_side_sorted + match_faction_sorted
    if include_others:
        ordered += others_sorted
    return ordered, len(match_side_sorted)

def _hull_has_any_role(hull_key, roles_cf, hull_role_map, hull_category_map):
    role_val = hull_role_map.get(hull_key, '') or ''
    if isinstance(role_val, str) and role_val:
        if role_val.casefold() in roles_cf:
            return True
    cats = hull_category_map.get(hull_key, set()) or set()
    return any(r in cats for r in roles_cf)

def _filter_hulls_by_roles(hulls, roles, hull_role_map, hull_category_map):
    roles_cf = {r.casefold() for r in roles}
    return [
        h for h in hulls
        if _hull_has_any_role(h, roles_cf, hull_role_map, hull_category_map)
    ]

def _load_ct_races_display(toolbar, fallback):
    races = getattr(toolbar, '_ct_races_list', None)
    race_to_faction_cf = getattr(toolbar, '_ct_race_to_faction_cf', None)
    if races is not None and race_to_faction_cf is not None:
        return races, race_to_faction_cf
    races = []
    race_to_faction_cf = {}
    try:
        base = getattr(toolbar, 'base', os.getcwd())
        ct_path = os.path.join(base, 'cargo_teams.json')
        with open(ct_path, 'r') as f:
            ct = json.load(f)
        races_map = ct.get('Races', {}) or {}
        for race, info in races_map.items():
            if not isinstance(race, str) or not race.strip():
                continue
            races.append(race)
            fac = ''
            if isinstance(info, dict):
                fac = str(info.get('Faction', '')).strip()
            if fac:
                race_to_faction_cf[race.casefold()] = fac
    except Exception:
        races = [r for r in (fallback or []) if isinstance(r, str) and r.strip()]
    setattr(toolbar, '_ct_races_list', races)
    setattr(toolbar, '_ct_race_to_faction_cf', race_to_faction_cf)
    return races, race_to_faction_cf

def _apply_combobox_item_colors(cb):
    green_count = getattr(cb, "_green_count", 0)
    lb = _get_combobox_listbox(cb)
    if lb is None:
        return False
    for i in range(lb.size()):
        color = _DARK_GREEN if i < green_count else "black"
        try:
            lb.itemconfig(i, foreground=color)
        except tk.TclError:
            pass
    return True

def _schedule_combobox_colors(cb):
    tries = 10
    def _attempt():
        nonlocal tries
        if _apply_combobox_item_colors(cb):
            return
        tries -= 1
        if tries > 0:
            cb.after(25, _attempt)
    cb.after(10, _attempt)

def _get_combobox_listbox(cb):
    try:
        popdown = cb.tk.call("ttk::combobox::PopdownWindow", cb)
        return cb.nametowidget(popdown + ".f.l")
    except Exception:
        return None


def _ensure_hull_color_binding(cb):
    if getattr(cb, "_hull_color_bound", False):
        return
    lb = _get_combobox_listbox(cb)
    if lb is None:
        return
    lb.bind("<Map>", lambda e, _cb=cb: _apply_combobox_item_colors(_cb), add="+")
    cb._hull_color_bound = True

# Canvas event handlers extracted for modularity
def on_canvas_press(event, ctx):
    # Unpack context
    toolbar = ctx['toolbar']
    map_canvas = ctx['map_canvas']
    sm = ctx['sm']
    ter_lb = ctx['ter_lb']
    relay_order = ctx['relay_order']
    relay_lb = ctx['relay_lb']
    objs = ctx['objs']
    obj_lb = ctx['obj_lb']
    terrain_keys = ctx['terrain_keys']

    valid_hulls = ctx['valid_hulls']
    hull_side_map = ctx.get('hull_side_map', {})
    hull_role_map = ctx.get('hull_role_map', {})
    hull_category_map = ctx.get('hull_category_map', {})

    align_var = ctx['align_var']
    show_relay = ctx['show_relay']
    show_object = ctx['show_object']
    show_terrain = ctx['show_terrain']
    draw_map = ctx['draw_map']
    drag_data = ctx['drag_data']
    screen_to_coord = ctx['screen_to_coord']
    win = ctx['win']

    # Small helper for consistent dialog via Toolbar helpers
    def _dlg(title: str, near_pointer: bool = True):
        near = "pointer" if near_pointer else "toolbar"
        return toolbar.make_dialog(title, near=near)


    # ── Measurement tool: right‐click to place two points, draw line & show distance ──
    if event.num == 3:
        # retrieve or init point list
        pts = ctx.get('measure_points', [])
        # if already two points, clear previous measurement
        if len(pts) >= 2:
            pts = []
            map_canvas.delete('measure_point', 'measure_line', 'measure_label')

        # convert click to world coords
        xw, zw = screen_to_coord(event.x, event.y)
        # draw point marker
        map_canvas.create_oval(
            event.x - 3, event.y - 3,
            event.x + 3, event.y + 3,
            fill='yellow', tags='measure_point'
        )
        pts.append((xw, zw, event.x, event.y))

        # once two points are set, draw line and label distance
        if len(pts) == 2:
            x1, z1, px1, py1 = pts[0]
            x2, z2, px2, py2 = pts[1]
            # line between points
            map_canvas.create_line(px1, py1, px2, py2,
                                   fill='Dark Green', width=2, tags='measure_line')

            # calculate distance using current zoom scale:
            # pixel distance divided by ctx['map_scale'] = world units
            scale = ctx.get('map_scale', 1.0) or 1.0
            dist_px = math.hypot(px2 - px1, py2 - py1)
            dist = dist_px / scale
            # compute travel time: 100K units = 60 seconds
            travel_time = dist / 100000.0 * 17.8
            secs_total = int(round(travel_time))
            mins = secs_total // 60
            secs = secs_total % 60
            # format in thousands (e.g. 1.5K) and append time mm:ss
            label = f"{dist/1000:.1f}K ({mins}:{secs:02d})"
            # midpoint for label placement
            mx = (px1 + px2) / 2
            my = (py1 + py2) / 2
            map_canvas.create_text(
                mx, my,
                text=label,
                fill='Red',
                font=('Arial', 14, 'bold'),
                tags='measure_label'
            )

        # store for next click
        ctx['measure_points'] = pts
        return

    # ── Planet placement mode (single-point terrain) ─────────────────────────
    if getattr(toolbar, 'planet_mode', False):
        ctx['push_undo']()
        # world coords for center
        screen_to_coord = ctx['screen_to_coord']
        bx, bz = screen_to_coord(event.x, event.y)
        sm  = ctx['sm']
        ter_lb = ctx['ter_lb']
        terrain_keys = ctx['terrain_keys']

        dlg, body, footer = _dlg("New Planet", near_pointer=True)
        name_var = tk.StringVar(value=f"Planet {random.randint(1,999)}")
        toolbar.labeled_entry(body, "Name:", name_var, width=22, row=0, col=0)

        def create_planet():
            # integer-like key (timestamp) for terrain dict
            key = str(int(time.time() * 1000))
            sm.data.setdefault('terrain', {})[key] = {
                'type': 'planet',
                'name': name_var.get().strip() or key,
                'coordinate': [bx, 0, bz]
            }
            terrain_keys.append(key)
            ter_lb.insert(tk.END, key)
            ctx['draw_map'](ctx)
            dlg.destroy()
            # exit planet placement mode
            toolbar.planet_mode = False
            if getattr(toolbar, 'planet_btn', None):
                toolbar.planet_btn.config(relief=tk.RAISED, bg='#333333', activebackground='#333333')

        tk.Button(dlg, text="Add", command=create_planet).grid(row=1, column=0, columnspan=2, pady=6)
        dlg.update_idletasks()
        dlg.geometry(f"+{event.x_root - dlg.winfo_width()//2}+{event.y_root - dlg.winfo_height()//2}")
        return


    if toolbar.blackhole_mode:
        ctx['push_undo']()
        # get map coords
        bx, bz = screen_to_coord(event.x, event.y)
        # popup to name & size the new black hole
        dlg = tk.Toplevel(win)
        dlg.title("New Blackhole")
        tk.Label(dlg, text="Name:").pack(anchor='w')
        name_var = tk.StringVar(value=f"Blackhole{random.randint(1,99)}")
        tk.Entry(dlg, textvariable=name_var).pack(fill=tk.X)
        tk.Label(dlg, text="Size:").pack(anchor='w')
        size_var = tk.IntVar(value=1000)
        tk.Spinbox(dlg, from_=1, to=1000000, textvariable=size_var).pack(fill=tk.X)
        tk.Label(dlg, text="Strength:").pack(anchor='w')
        str_var = tk.IntVar(value=500)
        tk.Spinbox(dlg, from_=1, to=1000000, textvariable=str_var).pack(fill=tk.X)
        def create_bh():

            # enforce integer‐only key (timestamp fallback)
            raw = name_var.get().strip()
            if raw.isdigit():
                key = raw
            else:
                dlg.bell()
                key = str(int(time.time() * 1000))
            sm.data.setdefault('terrain', {})[key] = {
                'type': 'blackhole',
                'name': key,
                'coordinate': [bx, 0, bz],
                'size': size_var.get(),
                'strength': str_var.get()
            }
            terrain_keys.append(key)
            ter_lb.insert(tk.END, key)
            draw_map(ctx)
            dlg.destroy()
        tk.Button(dlg, text="Add", command=create_bh).pack(pady=5)
        dlg.update_idletasks()  # ensure correct winfo_width/height
        w = dlg.winfo_width()
        h = dlg.winfo_height()
        x = event.x_root - w // 2
        y = event.y_root - h // 2
        dlg.geometry(f"+{x}+{y}")
        # exit blackhole‐placement mode
        toolbar.blackhole_mode = False
        toolbar.blackhole_btn.config(
            relief=tk.RAISED,
            bg='#333333',
            activebackground='#333333'
        )
        return

    # ── Debris-field placement mode (ARMED via toolbar dialog) ───────────────
    if getattr(toolbar, 'debris_mode', False):
        # Only place if a pending config exists (dialog 'Add' pressed)
        cfg = getattr(toolbar, 'debris_pending', None)
        if cfg:
            # capture undo THEN add
            ctx['push_undo']()
            pan_x, pan_y, scale = ctx['pan_x'], ctx['pan_y'], ctx['map_scale']
            cx = (event.x - pan_x) / scale
            cz = -(event.y - pan_y) / scale
            sm  = ctx['sm']
            ter_lb = ctx['ter_lb']
            terrain_keys = ctx['terrain_keys']

            key = str(int(time.time() * 1000))
            sm.data.setdefault('terrain', {})[key] = {
                'type': 'debris_field',
                'seed': int(cfg.get('seed', 2010)),
                'coordinate': [cx, 0, cz],
                'density': int(cfg.get('density', 30)),
                'scatter': int(cfg.get('scatter', 10000))
            }
            terrain_keys.append(key)
            ter_lb.insert(tk.END, key)
            ctx['draw_map'](ctx)

            # disarm mode & clear pending
            toolbar.debris_pending = None
            toolbar.debris_mode = False
            if getattr(toolbar, 'debris_btn', None):
                toolbar.debris_btn.config(relief=tk.RAISED, bg='#333333', activebackground='#333333')
            return
        else:
            # No config armed; ignore click (user must press Debris icon → Add)
            return

        def add_debris():
            key = str(int(time.time() * 1000))
            sm.data.setdefault('terrain', {})[key] = {
                'type': 'debris_field',
                'seed': seed_var.get(),
                'coordinate': [cx, 0, cz],
                'density': dens_var.get(),
                'scatter': scat_var.get()
            }
            terrain_keys.append(key)
            ter_lb.insert(tk.END, key)
    # ── Platform placement mode (dialog for Name + Hull) ───────────────
    if toolbar.platform_mode:
        # capture undo BEFORE creating anything
        ctx['push_undo']()
        # convert click → map coords using current pan/zoom
        pan_x, pan_y = ctx['pan_x'], ctx['pan_y']
        scale = ctx['map_scale']
        px = (event.x - pan_x) / scale
        pz = -(event.y - pan_y) / scale

        # Build hull options biased to platform/static/defense roles
        valid_hulls       = ctx.get('valid_hulls', []) or []
        hull_role_map     = ctx.get('hull_role_map', {}) or {}
        hull_category_map = ctx.get('hull_category_map', {}) or {}
        plat_hulls = _filter_hulls_by_roles(
            valid_hulls, {'platform', 'static', 'defense'}, hull_role_map, hull_category_map
        )
        # Open a compact dialog near the pointer
        dlg, body, footer = _dlg("New Platform", near_pointer=True)

        # Name
        default_name = toolbar.gen_platform_name()
        name_var = tk.StringVar(value=default_name)
        toolbar.labeled_entry(body, "Name:", name_var, width=22, row=0, col=0)

        # Faction/Side
        tk.Label(body, text="Faction:").grid(row=1, column=0, padx=6, pady=2, sticky='e')
        faction_var = tk.StringVar(value="UNKNOWN")
        tk.Label(body, textvariable=faction_var).grid(row=1, column=1, padx=6, pady=2, sticky='w')
        tk.Label(body, text="Side:").grid(row=2, column=0, padx=6, pady=2, sticky='e')
        race_names, race_to_faction_cf = _load_ct_races_display(toolbar, [])
        default_side = (align_var.get() or sm.get_alignment() or "")
        side_default = default_side if default_side in race_names else ''
        side_var = tk.StringVar(value=side_default)
        side_cb = ttk.Combobox(body, textvariable=side_var, values=race_names, state='readonly', width=24)
        side_cb.grid(row=2, column=1, padx=6, pady=2, sticky='w')
        def update_faction_label(*_):
            side = side_var.get().strip()
            if not side:
                faction_var.set("UNKNOWN")
                return
            fac = race_to_faction_cf.get(side.casefold(), '')
            faction_var.set(fac if fac else "UNKNOWN")
        side_var.trace_add('write', update_faction_label)
        update_faction_label()

        # Hull (Combobox)
        tk.Label(body, text="Hull:").grid(row=3, column=0, padx=6, pady=4, sticky='e')
        hull_var = tk.StringVar(value='defense_platform_beam')
        hull_cb  = ttk.Combobox(body, textvariable=hull_var, state='readonly', width=24)
        hull_cb.grid(row=3, column=1, padx=6, pady=4, sticky='w')
        hull_cb.bind("<Button-1>", lambda e, cb=hull_cb: _schedule_combobox_colors(cb), add="+")
        _ensure_hull_color_binding(hull_cb)
        # Filters
        show_all_var = tk.BooleanVar(value=False)
        relax_role_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            body, text="Show all hulls",
            variable=show_all_var
        ).grid(row=4, column=0, columnspan=2, sticky='w', padx=6, pady=(2, 0))
        tk.Checkbutton(
            body, text="Relax role filter",
            variable=relax_role_var
        ).grid(row=5, column=0, columnspan=2, sticky='w', padx=6, pady=(0, 2))

        def update_platform_hulls(*_):
            base_pool = valid_hulls if relax_role_var.get() else plat_hulls
            opts, green_count = _build_hull_options(
                base_pool, side_var.get(), hull_side_map, toolbar, include_others=show_all_var.get()
            )
            hull_cb['values'] = opts
            hull_cb._green_count = green_count
            _schedule_combobox_colors(hull_cb)
            if hull_var.get() not in opts:
                if 'defense_platform_beam' in opts:
                    hull_var.set('defense_platform_beam')
                else:
                    hull_var.set(opts[0] if opts else '')

        side_var.trace_add('write', update_platform_hulls)
        show_all_var.trace_add('write', update_platform_hulls)
        relax_role_var.trace_add('write', update_platform_hulls)
        update_platform_hulls()

        def _create_platform():
            name = (name_var.get() or "").strip() or toolbar.gen_platform_name()
            # ensure unique name if already present
            sm = ctx['sm']
            if name in sm.data.setdefault('objects', {}):
                # append a numeric suffix
                suffix = 2
                base = name
                while f"{base} {suffix}" in sm.data['objects']:
                    suffix += 1
                name = f"{base} {suffix}"
            # create the object
            sm.data.setdefault('objects', {})[name] = {
                'coordinate': [px, 0, pz],
                'sides':      [side_var.get()],
                'hull':       hull_var.get(),
                'type':       'platform',
                'cargo':      {},
                'teams':      {}
            }
            # update sidebar & redraw
            ctx['objs'].append(name)
            ctx['obj_lb'].insert(tk.END, name)
            ctx['draw_map'](ctx)
            dlg.destroy()
            # leave platform mode
            toolbar.toggle_platform_mode()

        def _cancel():
            dlg.destroy()
            # also exit placement mode to avoid accidental re-clicks
            toolbar.toggle_platform_mode()

        # Footer: complete buttons row and exit handler early
        toolbar.footer_buttons(
            footer,
            [
                ("Add", _create_platform, {"width": 12}),
                ("Cancel", _cancel, {"width": 12})
            ]
        )
        return

    if toolbar.multi_mode:
        ctx['push_undo']()
        # DEBUG: mark click in multi mode
        map_canvas.create_oval(event.x-3, event.y-3, event.x+3, event.y+3, fill='red', tags='debug')
        # convert screen to map coords using current pan/zoom
        pan_x = ctx['pan_x']; pan_y = ctx['pan_y']; map_scale = ctx['map_scale']
        mx = (event.x - pan_x) / map_scale
        mz = -(event.y - pan_y) / map_scale
        cfg = toolbar.multi_config
        pattern = cfg.get('pattern')
        if pattern == 'Line':
            if 'start' not in cfg:
                cfg['start'] = [mx,0,mz]
                map_canvas.create_oval(event.x-5, event.y-5, event.x+5, event.y+5, fill='blue', tags='batch_start')
            else:
                cfg['end'] = [mx,0,mz]
                x0,z0 = cfg['start'][0], cfg['start'][2]
                x1,z1 = cfg['end'][0], cfg['end'][2]
                dx, dz = x1-x0, z1-z0
                dist = math.hypot(dx, dz)
                repeat = cfg['repeat']
                count = math.ceil(dist / repeat) or 1
                for i in range(count+1):
                    t = i / count
                    ix = x0 + dx * t
                    iz = z0 + dz * t
                    name = toolbar.gen_relay_name()
                    sm.data.setdefault('sensor_relay', {})[name] = {'coordinate': [ix,0,iz]}
                    relay_order.append(name)
                    relay_lb.insert(tk.END, name)
                draw_map(ctx)
                map_canvas.delete('batch_start')
                toolbar.multi_mode = False
                # reset the Multi‐relay button visuals
                toolbar.multi_btn.config(
                    relief=tk.RAISED,
                    bg='#333333',
                    activebackground='#333333'
                )
                
        elif pattern == 'Circle':
            radius = cfg.get('radius', 0)
            repeat = cfg.get('repeat')
            # center point
            name_center = toolbar.gen_relay_name()
            sm.data.setdefault('sensor_relay', {})[name_center] = {'coordinate': [mx,0,mz]}
            relay_order.append(name_center)
            relay_lb.insert(tk.END, name_center)
            # perimeter relays
            circumference = 2 * math.pi * radius
            count = math.ceil(circumference / repeat) or 1
            for i in range(count):
                angle = 2 * math.pi * i / count
                ix = mx + radius * math.cos(angle)
                iz = mz + radius * math.sin(angle)
                name = toolbar.gen_relay_name()
                sm.data.setdefault('sensor_relay', {})[name] = {'coordinate': [ix,0,iz]}
                relay_order.append(name)
                relay_lb.insert(tk.END, name)
            draw_map(ctx)
            toolbar.multi_mode = False
            toolbar.multi_btn.config(
                relief=tk.RAISED,
                bg='#333333',
                activebackground='#333333'
                )
        return
    # Sensor relay placement mode: prompt for name and place
    if toolbar.sensor_mode:
        ctx['push_undo']()
        # convert click → world coords using current pan/zoom
        pan_x     = ctx['pan_x']
        pan_y     = ctx['pan_y']
        map_scale = ctx['map_scale']
        mx = (event.x - pan_x) / map_scale
        mz = -(event.y - pan_y) / map_scale
        default_name = toolbar.gen_relay_name()
        dlg, body, footer = _dlg('New Sensor Relay', near_pointer=True)
        name_var = tk.StringVar(value=default_name)
        toolbar.labeled_entry(body, "Name:", name_var, width=22, row=0, col=0)
        def add_relay():
            name = name_var.get().strip()
            if not name:
                return
            sm.data.setdefault('sensor_relay', {})[name] = {'coordinate': [mx, 0, mz]}
            relay_order.append(name)
            relay_lb.insert(tk.END, name)
            draw_map(ctx)
            dlg.destroy()
            toolbar.toggle_sensor_mode()
        toolbar.footer_buttons(footer, [("Add", add_relay, {"width": 12})])
        return
        
    # ── Gate placement mode: create new jump_point ────────────────────────
    if toolbar.gate_mode:
        ctx['push_undo']()
        # convert click → map coords using current pan/zoom
        pan_x     = ctx['pan_x']
        pan_y     = ctx['pan_y']
        map_scale = ctx['map_scale']
        gx = (event.x - pan_x) / map_scale
        gz = -(event.y - pan_y) / map_scale
        # Prompt for gate name (consistent dialog)
        dlg, body, footer = _dlg('New Gate', near_pointer=True)
        name_var = tk.StringVar(value=toolbar.gen_gate_name())
        toolbar.labeled_entry(body, "Name:", name_var, width=22, row=0, col=0)

        def add_gate():
            name = name_var.get().strip()
            if not name:
                return
            # insert as a jump_point object
            sm.data.setdefault('objects', {})[name] = {
                'coordinate': [gx, 0, gz],
                'type': 'jumpnode',
                'jumppointtype': 'Node',
                'destinations': {},
                'state': 'Tethered',
                'drift': 0
            }
            objs.append(name)
            obj_lb.insert(tk.END, name)
            draw_map(ctx)
            dlg.destroy()
            toolbar.toggle_gate_mode()

        tk.Button(dlg, text='Add', command=add_gate)\
            .grid(row=1, column=0, columnspan=2, pady=5)
        dlg.update_idletasks()
        w = dlg.winfo_width(); h = dlg.winfo_height()
        x = event.x_root - w // 2; y = event.y_root - h // 2
        dlg.geometry(f"+{x}+{y}")
        return

    # Relay selection / start drag
    for item in map_canvas.find_withtag('relay_pt'):
        x1, y1, x2, y2 = map_canvas.bbox(item)
        if x1 <= event.x <= x2 and y1 <= event.y <= y2:
            tags = map_canvas.gettags(item)
            if len(tags) > 1:
                relay = tags[1]
                show_relay(relay)
                drag_data['relay'] = relay
                drag_data['x'], drag_data['y'] = event.x, event.y
                return
    # New terrain placement modes
    if toolbar.asteroid_mode or toolbar.nebula_mode:
        ctx['push_undo']()
        # convert click to world coords using current pan/zoom
        pan_x     = ctx['pan_x']
        pan_y     = ctx['pan_y']
        map_scale = ctx['map_scale']
        mx = (event.x - pan_x) / map_scale
        mz = -(event.y - pan_y) / map_scale

        mode_type = 'asteroids' if toolbar.asteroid_mode else 'nebulas'
        nt = drag_data.get('new_terrain')
        if nt is None:
            # First click: set start
            drag_data['new_terrain'] = {'type': mode_type, 'start': [mx,0,mz]}
            map_canvas.create_oval(event.x-4, event.y-4, event.x+4, event.y+4, fill='blue', tags='new_terrain_start')
        else:
            # Second click: set end and open dialog
            nt['end'] = [mx,0,mz]
            map_canvas.create_oval(event.x-4, event.y-4, event.x+4, event.y+4, fill='blue', tags='new_terrain_end')
            dlg, body, footer = _dlg('New Terrain', near_pointer=True)
            dens_var = tk.IntVar(value=125)
            toolbar.labeled_spinbox(body, 'Density:', dens_var, frm=1, to=100000, row=0, col=0)
            scat_var = tk.IntVar(value=10000)
            toolbar.labeled_spinbox(body, 'Scatter:', scat_var, frm=1, to=50000, row=1, col=0)
            def add_terrain():
                # enforce integer‐only key (use timestamp if user’s entry invalid or blank)
                # integer‐only key: use millisecond timestamp
                key = str(int(time.time() * 1000))
                sm.data.setdefault('terrain', {})[key] = {
                    'type': mode_type,
                    'seed': 2010,
                    'start': nt['start'],
                    'end': nt['end'],
                    'density': dens_var.get(),
                    'scatter': scat_var.get(),
                    'composition': ['Ast. Std Rand'] if mode_type == 'asteroids' else []
                }
                terrain_keys.append(key)
                ter_lb.insert(tk.END, key)
                draw_map(ctx)
                dlg.destroy()
                map_canvas.delete('new_terrain_start', 'new_terrain_end')
                drag_data['new_terrain'] = None
                if toolbar.asteroid_mode: toolbar.toggle_asteroid_mode()
                else: toolbar.toggle_nebula_mode()
            tk.Button(dlg, text='Add', command=add_terrain).grid(row=2, column=0, columnspan=2)
            dlg.update_idletasks()  # ensure correct winfo_width/height
            w = dlg.winfo_width()
            h = dlg.winfo_height()
            x = event.x_root - w // 2
            y = event.y_root - h // 2
            dlg.geometry(f"+{x}+{y}")
        return
    # Station placement mode: create new station
    if toolbar.station_mode:
        pan_x     = ctx['pan_x']
        pan_y     = ctx['pan_y']
        map_scale = ctx['map_scale']
        mx = (event.x - pan_x) / map_scale
        mz = -(event.y - pan_y) / map_scale
        default_side = align_var.get() or sm.get_alignment()
        default_hull = 'starbase_command'
        new_name = toolbar.gen_station_name()
        dlg = tk.Toplevel(win)
        dlg.title('New Station')
        tk.Label(dlg, text='Name:').grid(row=0, column=0)
        name_var = tk.StringVar(value=new_name)
        tk.Entry(dlg, textvariable=name_var).grid(row=0, column=1)
        tk.Label(dlg, text='Faction:').grid(row=1, column=0)
        faction_var = tk.StringVar(value="UNKNOWN")
        tk.Label(dlg, textvariable=faction_var).grid(row=1, column=1, sticky='w')
        tk.Label(dlg, text='Side:').grid(row=2, column=0)
        race_names, race_to_faction_cf = _load_ct_races_display(toolbar, [])
        side_default = default_side if default_side in race_names else ''
        side_var2 = tk.StringVar(value=side_default)
        side_cb2 = ttk.Combobox(dlg, textvariable=side_var2, values=race_names, state='readonly')
        side_cb2.grid(row=2, column=1)
        def update_faction_label(*_):
            side = side_var2.get().strip()
            if not side:
                faction_var.set("UNKNOWN")
                return
            fac = race_to_faction_cf.get(side.casefold(), '')
            faction_var.set(fac if fac else "UNKNOWN")
        side_var2.trace_add('write', update_faction_label)
        update_faction_label()
        tk.Label(dlg, text='Hull:').grid(row=3, column=0)
        hull_var2 = tk.StringVar(value=default_hull)
        hull_cb2 = ttk.Combobox(dlg, textvariable=hull_var2, state='readonly')
        hull_cb2.grid(row=3, column=1)
        hull_cb2.bind("<Button-1>", lambda e, cb=hull_cb2: _schedule_combobox_colors(cb), add="+")
        _ensure_hull_color_binding(hull_cb2)
        # Checkbox to allow full (unfiltered) hull list
        show_all_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            dlg, text="Show all hulls",
            variable=show_all_var
        ).grid(row=4, column=0, columnspan=2, sticky='w', pady=(2, 0))
        relax_role_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            dlg, text="Relax role filter",
            variable=relax_role_var
        ).grid(row=5, column=0, columnspan=2, sticky='w', pady=(0, 2))
        station_hulls = _filter_hulls_by_roles(
            valid_hulls, {'station'}, hull_role_map, hull_category_map
        )

        def update_hull_values(*_):
            include_others = show_all_var.get()
            hull_pool = valid_hulls if relax_role_var.get() else station_hulls
            opts, green_count = _build_hull_options(
                hull_pool, side_var2.get(), hull_side_map, toolbar, include_others
            )
            hull_cb2['values'] = opts
            hull_cb2._green_count = green_count
            _schedule_combobox_colors(hull_cb2)
            # Reset selection if current not in filtered set
            if hull_var2.get() not in opts:
                hull_var2.set(opts[0] if opts else '')

        # Wire changes: when side or checkbox changes, refresh hull options
        side_var2.trace_add('write', update_hull_values)
        show_all_var.trace_add('write', update_hull_values)
        relax_role_var.trace_add('write', update_hull_values)
        # Initialize hull list once dialog is built
        update_hull_values()
 
        def add_station():
        # capture state _just before_ we create this one new station
            ctx['push_undo']()
            name = name_var.get().strip()
            if not name:
                dlg.destroy()
                toolbar.toggle_station_mode()
                return
            obj = {
                'coordinate':[mx,0,mz],
                'sides':[side_var2.get()],
                'hull':hull_var2.get(),
                'type':'station',
                'facilities':[], 'cargo':{}, 'teams':{}
            }
            sm.data['objects'][name] = obj
            objs.append(name)
            obj_lb.insert(tk.END, name)
            draw_map(ctx)
            dlg.destroy()
            toolbar.toggle_station_mode()
        tk.Button(dlg, text='Add', command=add_station).grid(row=6, column=0, columnspan=2)
        dlg.update_idletasks()  # ensure correct winfo_width/height
        w = dlg.winfo_width()
        h = dlg.winfo_height()
        x = event.x_root - w // 2
        y = event.y_root - h // 2
        dlg.geometry(f"+{x}+{y}")
        return



    # Terrain point selection / start drag
    for tag in map_canvas.find_withtag('terrain_pt'):
        x1, y1, x2, y2 = map_canvas.bbox(tag)
        if x1 <= event.x <= x2 and y1 <= event.y <= y2:
            tags = map_canvas.gettags(tag)
            key, pt_type = tags[1], tags[2]
            idx = terrain_keys.index(key)
            ter_lb.selection_clear(0, tk.END)
            ter_lb.selection_set(idx)
            ter_lb.see(idx)
            # capture before any terrain-point move
            ctx['push_undo']()
            show_terrain(key)
            drag_data['terrain'] = (key, pt_type)
            drag_data['x'], drag_data['y'] = event.x, event.y
            return
    # — allow black‐hole dots (tagged 'terrain') to be dragged like terrain_pts —
    for tag in map_canvas.find_withtag('terrain'):
        x1,y1,x2,y2 = map_canvas.bbox(tag)
        if x1 <= event.x <= x2 and y1 <= event.y <= y2:
            key = map_canvas.gettags(tag)[1]  # the terrain key
            feat = sm.get_terrain_feature(key)
            ttype = feat.get('type','').lower()
            if ttype in ('blackhole', 'debris_field', 'planet'):
                # capture before blackhole center move
                ctx['push_undo']()
                show_terrain(key)
                drag_data['terrain'] = (key, 'coord')
                drag_data['x'], drag_data['y'] = event.x, event.y
                return
    # Object selection / start drag
    # Prefer true hit-testing under the cursor; do NOT depend on sidebar list membership.
    for item in reversed(map_canvas.find_overlapping(event.x, event.y, event.x, event.y)):
        tags = map_canvas.gettags(item)
        if 'obj' in tags:
            # tags are ('obj', <name>) from draw_map; find the object name tag
            name = None
            for t in tags:
                if t != 'obj':
                    name = t
                    break
            if name:
                # capture before any object move
                ctx['push_undo']()
                show_object(name)
                drag_data['obj'] = name
                drag_data['x'], drag_data['y'] = event.x, event.y
                return
    # Otherwise start panning
    drag_data['panning'] = True
    drag_data['x'], drag_data['y'] = event.x, event.y

def on_canvas_drag(event, ctx):
    # Unpack context for drag
    map_canvas = ctx['map_canvas']
    sm = ctx['sm']
    drag_data = ctx['drag_data']
    screen_to_coord = ctx['screen_to_coord']
    draw_map = ctx['draw_map']
    pan_x = ctx['pan_x']
    pan_y = ctx['pan_y']
    map_scale = ctx['map_scale']
    new_x = (event.x - pan_x) / map_scale
    new_z = -(event.y - pan_y) / map_scale
    # Handle terrain point dragging
    if drag_data.get('terrain'):
        key, pt_type = drag_data['terrain']

        feat = sm.get_terrain_feature(key)

        if pt_type == 'start':
            feat['start']      = [new_x, 0, new_z]
        elif pt_type == 'end':
            feat['end']        = [new_x, 0, new_z]
        elif pt_type == 'coord':
            # moving a black hole center
            feat['coordinate'] = [new_x, 0, new_z]

        sm.update_terrain_feature(key, feat)
        drag_data['x'], drag_data['y'] = event.x, event.y
        draw_map(ctx)
    # Handle object dragging
    elif drag_data.get('relay'):
        # move both oval and any label, update data
        relay = drag_data['relay']
        dx = event.x - drag_data['x']
        dy = event.y - drag_data['y']
        for item in map_canvas.find_withtag(relay):
            map_canvas.move(item, dx, dy)
        sx, sy = map_canvas.coords(map_canvas.find_withtag(relay)[0])[:2]
        # convert using current pan/zoom
        x = (sx - pan_x) / map_scale
        z = -(sy - pan_y) / map_scale
        sm.data['sensor_relay'][relay] = [x, 0, z]
        drag_data['x'], drag_data['y'] = event.x, event.y
        # do not redraw map here to allow smooth dragging
        # draw_map(ctx)

    elif drag_data.get('obj'):
        name = drag_data['obj']
        # Move marker visually (both the oval + label share the <name> tag)
        dx = event.x - drag_data['x']
        dy = event.y - drag_data['y']
        map_canvas.move(name, dx, dy)
        # Use the OVAL center (not the text) to compute world coordinate
        sx = sy = None
        for it in map_canvas.find_withtag(name):
            if map_canvas.type(it) == 'oval':
                x1, y1, x2, y2 = map_canvas.coords(it)
                sx = (x1 + x2) / 2.0
                sy = (y1 + y2) / 2.0
                break
        if sx is None:
            # Fallback: cursor position
            sx, sy = event.x, event.y
        # convert using current pan/zoom
        x = (sx - pan_x) / map_scale
        z = -(sy - pan_y) / map_scale
        sm.update_object_coordinate(name, [x, 0, z])
        drag_data['x'], drag_data['y'] = event.x, event.y
    # Handle panning
    elif drag_data.get('panning'):
        dx = event.x - drag_data['x']
        dy = event.y - drag_data['y']
        pan_x += dx
        pan_y += dy
        drag_data['x'], drag_data['y'] = event.x, event.y
        ctx['pan_x']     = pan_x
        ctx['pan_y']     = pan_y
        ctx['map_scale'] = map_scale
        draw_map(ctx)
        # Draw concentric range circles under all elements
        def _draw_range_rings(ctx):
            map_canvas = ctx['map_canvas']
            # Remove any previous rings
            map_canvas.delete('range_ring')
            pan_x = ctx['pan_x']; pan_y = ctx['pan_y']; scale = ctx['map_scale']
            # Screen center corresponds to world (0,0)
            x0 = pan_x; y0 = pan_y
            for radius, outline, width in [
                (200000, 'white', 1),
                (500000, 'white', 1),
                (999999, 'red',   3),
            ]:
                rpx = radius * scale
                map_canvas.create_oval(
                    x0 - rpx, y0 - rpx,
                    x0 + rpx, y0 + rpx,
                    outline=outline, width=width,
                    tags='range_ring'
                )
            # Keep rings beneath everything else
            map_canvas.tag_lower('range_ring')

        _draw_range_rings(ctx)
        return


def on_map_zoom(event, ctx):
    # Unpack context for zoom
    pan_x = ctx['pan_x']
    pan_y = ctx['pan_y']
    map_scale = ctx['map_scale']
    draw_map = ctx['draw_map']
    # Determine zoom factor
    factor = 1.2 if event.delta > 0 else 1/1.2
    # Adjust pan to zoom around cursor
    pan_x = event.x + factor * (pan_x - event.x)
    pan_y = event.y + factor * (pan_y - event.y)
    map_scale *= factor
    # Save updated pan/zoom back to context
    ctx['pan_x'] = pan_x
    ctx['pan_y'] = pan_y
    ctx['map_scale'] = map_scale
    draw_map(ctx)

    # Draw concentric range circles under all elements
    def _draw_range_rings(ctx):
        map_canvas = ctx['map_canvas']
        # Remove any previous rings
        map_canvas.delete('range_ring')
        pan_x = ctx['pan_x']; pan_y = ctx['pan_y']; scale = ctx['map_scale']
        # Screen center corresponds to world (0,0)
        x0 = pan_x; y0 = pan_y
        for radius, outline, width in [
            (200000, 'white', 1),
            (500000, 'white', 1),
            (999999, 'red',   3),
        ]:
            rpx = radius * scale
            map_canvas.create_oval(
                x0 - rpx, y0 - rpx,
                x0 + rpx, y0 + rpx,
                outline=outline, width=width,
                tags='range_ring'
            )
        # Keep rings beneath everything else
        map_canvas.tag_lower('range_ring')

    _draw_range_rings(ctx)
