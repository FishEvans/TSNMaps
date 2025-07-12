import tkinter as tk
from tkinter import ttk
import SystemEditor
import random
import math
import time

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
    valid_sides = ctx['valid_sides']
    valid_hulls = ctx['valid_hulls']
    align_var = ctx['align_var']
    show_relay = ctx['show_relay']
    show_object = ctx['show_object']
    show_terrain = ctx['show_terrain']
    draw_map = ctx['draw_map']
    drag_data = ctx['drag_data']
    screen_to_coord = ctx['screen_to_coord']
    win = ctx['win']
  
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

    # ── Platform placement mode ────────────────────────────────────────
    if toolbar.platform_mode:
        # snapshot for undo
        ctx['push_undo']()
        # compute world‐coords
        pan_x, pan_y = ctx['pan_x'], ctx['pan_y']
        scale = ctx['map_scale']
        px = (event.x - pan_x) / scale
        pz = -(event.y - pan_y) / scale

        # build default platform entry
        name = toolbar.gen_platform_name()
        ctx['sm'].data.setdefault('objects', {})[name] = {
            'coordinate': [px, 0, pz],
            'sides':      [ctx['align_var'].get()],
            'hull':       'defense_platform_beam',
            'type':       'platform',
            'cargo':      {},
            'teams':      {}
        }
        # update list & redraw
        ctx['objs'].append(name)
        ctx['obj_lb'].insert(tk.END, name)
        ctx['draw_map'](ctx)
        # leave platform mode
        toolbar.toggle_platform_mode()
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
        dlg = tk.Toplevel(win)
        dlg.title('New Sensor Relay')
        tk.Label(dlg, text='Name:').grid(row=0, column=0, padx=5, pady=5)
        name_var = tk.StringVar(value=default_name)
        tk.Entry(dlg, textvariable=name_var).grid(row=0, column=1, padx=5, pady=5)
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
        tk.Button(dlg, text='Add', command=add_relay).grid(row=1, column=0, columnspan=2, pady=5)
        dlg.update_idletasks()  # ensure correct winfo_width/height
        w = dlg.winfo_width()
        h = dlg.winfo_height()
        x = event.x_root - w // 2
        y = event.y_root - h // 2
        dlg.geometry(f"+{x}+{y}")
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
        # Prompt for gate name
        dlg = tk.Toplevel(win)
        dlg.title('New Gate')
        tk.Label(dlg, text='Name:').grid(row=0, column=0, padx=5, pady=5)
        name_var = tk.StringVar(value=toolbar.gen_gate_name())
        tk.Entry(dlg, textvariable=name_var).grid(row=0, column=1, padx=5, pady=5)

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
            dlg = tk.Toplevel(win)
            dlg.title('New Terrain')
            tk.Label(dlg, text='Density:').grid(row=0, column=0)
            dens_var = tk.IntVar(value=125)
            tk.Spinbox(dlg, from_=1, to=100000, textvariable=dens_var).grid(row=0, column=1)
            tk.Label(dlg, text='Scatter:').grid(row=1, column=0)
            scat_var = tk.IntVar(value=10000)
            tk.Spinbox(dlg, from_=1, to=50000, textvariable=scat_var).grid(row=1, column=1)
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
        tk.Label(dlg, text='Side:').grid(row=1, column=0)
        side_var2 = tk.StringVar(value=default_side)
        side_cb2 = ttk.Combobox(dlg, textvariable=side_var2, values=valid_sides, state='readonly')
        side_cb2.grid(row=1, column=1)
        tk.Label(dlg, text='Hull:').grid(row=2, column=0)
        hull_var2 = tk.StringVar(value=default_hull)
        hull_cb2 = ttk.Combobox(dlg, textvariable=hull_var2, values=valid_hulls, state='readonly')
        hull_cb2.grid(row=2, column=1)
 
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
        tk.Button(dlg, text='Add', command=add_station).grid(row=3, column=0, columnspan=2)
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
            if feat.get('type','').lower() == 'blackhole':
                # capture before blackhole center move
                ctx['push_undo']()
                show_terrain(key)
                drag_data['terrain'] = (key, 'coord')
                drag_data['x'], drag_data['y'] = event.x, event.y
                return
    # Object selection / start drag
    for tag in map_canvas.find_withtag('obj'):
        x1, y1, x2, y2 = map_canvas.bbox(tag)
        if x1 <= event.x <= x2 and y1 <= event.y <= y2:
            tags = map_canvas.gettags(tag)
            name = tags[1] if len(tags) > 1 else None
            if name in objs:
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
        # Move marker visually and update coords
        map_canvas.move(name, event.x - drag_data['x'], event.y - drag_data['y'])
        sx, sy = map_canvas.coords(name)[0:2]
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
