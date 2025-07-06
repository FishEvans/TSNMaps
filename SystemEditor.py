#import os
import sys
import json
#import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
from typing import Any, Dict, List, Optional
from Toolbar import *
import SysMapCanvas
import math
import random
import copy
from PIL import Image, ImageTk
import re

# valid names: letters, digits, dot, space; 1–20 chars
_VALID_NAME = re.compile(r'^[A-Za-z0-9. ]{1,20}$')

g_obj_lb = None
g_relay_lb = None
g_ter_lb = None
g_ctx = None
# module‐scope holders for the last description edit
_last_desc_widget = None
_last_desc_obj    = None

def get_base_path():
    # when frozen by PyInstaller, use the folder where the EXE was started (the original exe), not the temp unpack directory
    if getattr(sys, 'frozen', False):
        # for onefile builds, sys.argv[0] points to the path of the original EXE invoked
        return os.path.dirname(os.path.abspath(sys.argv[0]))
    # when running as script, use module directory
    return os.path.dirname(os.path.abspath(__file__))

def get_data_path():
    """Directory where system JSON files live under data/missions/.../Terrain"""
    return os.path.join(get_base_path(), 'data', 'missions', 'Map Designer', 'Terrain')

# ─── Undo/Redo state ────────────────────────────────────────────────
undo_stack = []
redo_stack = []
current_sm = None    # holds the active SystemMap instance
sm_win = None        # editor window, used for bell()

def push_undo():
    # capture a deep copy of current data
    if current_sm is None:
        return
    undo_stack.append(copy.deepcopy(current_sm.data))

    # cap at 5
    if len(undo_stack) > 5:
        undo_stack.pop(0)
    # any new action invalidates redo history
    redo_stack.clear()

def do_undo():
    # Undo the last action
    if not undo_stack:
        sm_win.bell()
        return
    # Push current state onto redo
    redo_stack.append(copy.deepcopy(current_sm.data))
    # Pop the last undo state and restore it
    state = undo_stack.pop()
    current_sm.data = state
    _refresh_ui()

def do_redo():
    # Redo the last undone action
    if not redo_stack:
        sm_win.bell()
        return
    # Push current state back onto undo
    undo_stack.append(copy.deepcopy(current_sm.data))
    # Pop the last redo state and restore it
    state = redo_stack.pop()
    current_sm.data = state
    _refresh_ui()

def _refresh_ui():
    """Repopulate listboxes and redraw canvas from current_sm.data."""
    # Objects: update context list & listbox
    obj_names = current_sm.list_objects()
    g_ctx['objs'].clear()
    g_ctx['objs'].extend(obj_names)
    g_obj_lb.delete(0, 'end')
    for n in obj_names:
        g_obj_lb.insert('end', n)
    # Relays: update context list & listbox
    relay_names = list(current_sm.list_sensor_relays().keys())
    g_ctx['relay_order'].clear()
    g_ctx['relay_order'].extend(relay_names)
    g_relay_lb.delete(0, 'end')
    for r in relay_names:
        g_relay_lb.insert('end', r)
    # Terrain: update context list & listbox
    terrain_names = current_sm.list_terrain()
    g_ctx['terrain_keys'].clear()
    g_ctx['terrain_keys'].extend(terrain_names)
    g_ter_lb.delete(0, 'end')
    for t in terrain_names:
        g_ter_lb.insert('end', t)
    # clear side‐pane and redraw canvas
    clear_edit_pane()
    # redraw the canvas using the draw_map in our saved context
    g_ctx['draw_map'](g_ctx)
    # ─── Clear any stale drag/selection state ─────────────────────
    g_ctx['drag_data'].clear()
    current_selection['type'] = None
    current_selection['name'] = None


# Editor-only gridline modes
GRID_MODES = ['off', 'grid', 'sector', 'combined']
GRID_SPACING = {'grid': 20000, 'sector': 100000}

class SystemMap:
    """
    A class to load, edit, and save stellar system maps for StellarCartography.
    """
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.data: Dict[str, Any] = self._load()

    def _load(self) -> Dict[str, Any]:
        with open(self.file_path, 'r') as f:
            return json.load(f)

    def save(self, file_path: Optional[str] = None) -> None:
        target = file_path or self.file_path
        with open(target, 'w') as f:
            json.dump(self.data, f, indent=4)

    def list_sensor_relays(self) -> Dict[str, List[float]]:
        return self.data.get('sensor_relay', {})

    def list_objects(self) -> List[str]:
        return list(self.data.get('objects', {}).keys())

    def get_object(self, name: str) -> Dict[str, Any]:
        return self.data.get('objects', {}).get(name, {})

    def update_object_coordinate(self, name: str, coord: List[float]) -> bool:
        obj = self.data.get('objects', {}).get(name)
        if obj:
            obj['coordinate'] = coord
            return True
        return False

    def list_terrain(self) -> List[str]:
        return list(self.data.get('terrain', {}).keys())

    def get_terrain_feature(self, key: str) -> Dict[str, Any]:
        return self.data.get('terrain', {}).get(key, {})

    def update_terrain_feature(self, key: str, feature: Dict[str, Any]) -> bool:
        if key in self.data.get('terrain', {}):
            self.data['terrain'][key] = feature
            return True
        return False

    def get_system_map_coord(self) -> List[float]:
        return self.data.get('systemMapCoord', [])

    def set_system_map_coord(self, coord: List[float]) -> None:
        self.data['systemMapCoord'] = coord

    def get_alignment(self) -> Optional[str]:
        return self.data.get('alignment') or self.data.get('systemalignment')

    def set_alignment(self, alignment: str) -> None:
        if 'alignment' in self.data:
            self.data['alignment'] = alignment
        else:
            self.data['systemalignment'] = alignment

    def get_description(self) -> str:
        return self.data.get('metadata', {}).get('sysdescription', '')

    def set_description(self, description: str) -> None:
        md = self.data.setdefault('metadata', {})
        md['sysdescription'] = description


def open_system_editor(filename: str) -> None:
    # base for images, data_base for system JSON files
    base = get_base_path()
    data_base = get_data_path()
    file_path = os.path.join(data_base, filename)
    # Load ShipMap for valid hulls and sides
    # ─── Load Cargo/Teams presets and master lists from JSON ─────────────
    try:
        with open(os.path.join(base, 'cargo_teams.json'), 'r') as cf:
            ct_config = json.load(cf)
    except Exception:
        ct_config = {"cargo": [], "teams": [], "presets": {}, "skyboxes": []}
    try:
        with open(os.path.join(base, 'HTML', 'Images', 'Ships', 'ShipMap.json'), 'r') as sf:
            ship_entries = json.load(sf)
            valid_hulls = [entry['key'] for entry in ship_entries]
            # Extract unique sides for dropdown, excluding non-selectable ones
            invalid_sides = {'asteroid','cursor','generic','monster','pickup','wreck'}
            valid_sides = sorted(
                s for s in {entry.get('side','') for entry in ship_entries if entry.get('side')} 
                if s and s not in invalid_sides
            )
    except Exception:
        valid_hulls = []
        valid_sides = []
    # initialize system map
    
    try:
        global current_sm
        sm = SystemMap(file_path)
        current_sm = sm
        # ── Normalize old relay entries (bare lists) into dicts ───────────────
        sr = sm.data.get('sensor_relay', {})
        for key, val in list(sr.items()):
            if isinstance(val, list):
                sr[key] = {'coordinate': val}

        # ── Migrate legacy "jump_point" types to "jumpnode"/"jumppoint" ───
        migrated = False
        for obj_key, obj in sm.data.get('objects', {}).items():
            if obj.get('type') == 'jump_point':
                st = obj.get('state', '')
                # fix typo in state
                if st == 'Unteathered':
                    obj['state'] = 'Untethered'
                    st = 'Untethered'
        # map by state
                if st == 'Tethered':
                    obj['type'] = 'jumpnode'
                elif st == 'Untethered':
                    obj['type'] = 'jumppoint'
                migrated = True

        if migrated:
        # persist the silent migration immediately
            sm.save()

        # ── Sanitize all names: replace hyphens with spaces ─────────────
        renamed = False
        for category in ('objects', 'sensor_relay', 'terrain'):
            d = sm.data.get(category, {})
            for old in list(d.keys()):
                if '-' in old:
                    new = old.replace('-', ' ')
                    if new not in d:
                        d[new] = d.pop(old)
                        renamed = True
        if renamed:
            # write out the updated JSON silently
            sm.save()
        # ── Ensure asteroid fields have default composition ──────────────
        comp_changed = False
        for tkey, feat in sm.data.get('terrain', {}).items():
            if feat.get('type', '').lower() == 'asteroids':
            # if missing or empty, assign default composition
                if not feat.get('composition'):
                    feat['composition'] = ['Ast. Std Rand']
                    comp_changed = True
        if comp_changed:
        # silently persist the added compositions
            sm.save()

        push_undo()
        
    except Exception as e:
        messagebox.showerror("Error", f"Failed to load system map: {e}")
        return("Error", f"Failed to load system map: {e}")
        return

    global sm_win
    win = tk.Toplevel()
    sm_win = win
    # ── Skybox metadata dropdown ─────────────────────────────────────────
    # Values come from cargo-teams.json -> 'skyboxes'
    skybox_list = ct_config.get('skyboxes', [])
    # Ensure metadata dict exists
    md = sm.data.setdefault('metadata', {})
    # Helper to load icon buttons
    def load_icon_button(parent, relname, command):
        icon_img = None
        # Try standard and faction paths
        for relpath in [f'HTML/Images/{relname}', f'HTML/Images/Factions/{relname}']:
            candidate = os.path.join(base, *relpath.split('/'))
            print(f'Trying icon path: {candidate}')
            if os.path.exists(candidate):
                try:
                    pil_img = Image.open(candidate).resize((30,30), Image.LANCZOS)
                    icon_img = ImageTk.PhotoImage(pil_img)
                    break
                except Exception as e:
                    print(f'Icon load failed for {candidate}: {e}')
        if icon_img:
            btn = tk.Button(parent, image=icon_img, command=command, bg='#333333', activebackground='#333333')
            btn.image = icon_img
        else:
            btn = tk.Button(parent, text='', command=command, bg='#333333', activebackground='#333333')
        return btn
    win.title(f"System Editor - {filename}")
    frame = tk.Frame(win, padx=10, pady=10)
    # Control panel across top (pack to full width, then center buttons via grid)
    frame.pack(side=tk.TOP, fill=tk.X)

    # make columns 0 and 7 absorb all extra space, centering cols 1–6
    for col in range(0,8):
        frame.grid_columnconfigure(col, weight=0)
    frame.grid_columnconfigure(0, weight=1)
    frame.grid_columnconfigure(7, weight=1)

      # ─── System Details (collapsible) ─────────────────────────────────
    row = 0
    sysdet_header = tk.Label(
        frame,
        text = "▶ System Details",
        font = ('Arial', 10, 'bold'),
        cursor = 'hand2'
         )
    sysdet_header.grid(row=row, column=0, columnspan=8, sticky='w', pady=(5, 0))
    sysdet_frame = tk.Frame(frame)
    sysdet_frame.grid(row=row + 1, column=0, columnspan=8, sticky='ew', padx=10)
    for c in range(8):
        sysdet_frame.grid_columnconfigure(c, weight=1)
    sysdet_frame.grid_remove()

    def toggle_sysdet(event=None):

        if sysdet_frame.winfo_ismapped():
            sysdet_frame.grid_remove()
            sysdet_header.config(text="▶ System Details")
        else:
            sysdet_frame.grid()
            sysdet_header.config(text="▼ System Details")
    sysdet_header.bind("<Button-1>", toggle_sysdet)
    # direct metadata widgets into this frame
    md_parent = sysdet_frame
    row += 1

      # Metadata section (inside System Details)
    tk.Label(md_parent, text="Coordinates (X,Y,Z):").grid(row=row, column=0, sticky='w')
    coord_vars = []
    for i, val in enumerate(sm.get_system_map_coord()):
        var = tk.StringVar(value=str(val))
        coord_vars.append(var)
        tk.Entry(md_parent, textvariable=var, width=8).grid(row=row, column=i+1, padx=2)
    row += 1

    tk.Label(md_parent, text="Alignment:").grid(row=row, column=0, sticky='w')
    # Alignment dropdown with custom entry enabled
    align_var = tk.StringVar(value=sm.get_alignment() or '')
    align_cb = ttk.Combobox(md_parent, textvariable=align_var, values=valid_sides, state='normal')
    align_cb.grid(row=row, column=1, columnspan=1, sticky='w')

    # ── Skybox dropdown (read-only), sourced from cargo_teams.json
    skyboxes = ct_config.get('skyboxes', [])
    md = sm.data.setdefault('metadata', {})
    # Determine initial skybox: use existing metadata or default to first entry
    init_sky = md.get('skybox')

    if init_sky not in skyboxes and skyboxes:
        init_sky = skyboxes[0]
        md['skybox'] = init_sky
    skybox_var = tk.StringVar(value=init_sky or '')
    tk.Label(md_parent, text="Skybox:") \
        .grid(row=row, column=3, sticky='e', padx=(10, 0))
    skybox_cb = ttk.Combobox(
        md_parent,
        textvariable = skybox_var,
        values = skyboxes,
        state = 'readonly',
        width = 20
        )
    skybox_cb.grid(row=row, column=4, sticky='nsew', padx=(1,0))
    skybox_var.trace_add('write', lambda *a: md.__setitem__('skybox', skybox_var.get()))
  # Skybox preview (100×100px)
    preview_label = tk.Label(md_parent)




    row += 1

    #tk.Label(md_parent, text="Description:").grid(row=row, column=0, sticky='nw')

    tk.Label(md_parent, text="Description:").grid(row=row, column=0, sticky='nw')
    desc_text = tk.Text(md_parent, height=5, width=60)
    desc_text.insert('1.0', sm.get_description())
    desc_text.grid(row=row, column=1, columnspan=4, sticky='w')
    preview_label.grid(row=row, column=4, padx=(10, 0))
    def _update_sky_preview(*args):
        img_path = os.path.join(base, 'data', 'graphics', skybox_var.get())
        try:
            pil_img = Image.open(img_path).resize((100, 100), Image.LANCZOS)
            tk_img = ImageTk.PhotoImage(pil_img)
            preview_label.config(image=tk_img)
            preview_label.image = tk_img
        except Exception:
            preview_label.config(image='')
            preview_label.image = None
    _update_sky_preview()
    skybox_var.trace_add('write', _update_sky_preview)
    row += 1


    # ── Traffic controls: Commercial, Civilian, Security ────────────────
    traffic = sm.data.setdefault('traffic', {})
    levels = ['none', 'light', 'medium', 'heavy']
    # now inside the System Details pane
    tk.Label(md_parent, text="Traffic:") \
        .grid(row=row, column=0, sticky='e', pady=(1, 0))

    for i, cat in enumerate(('commercial', 'civilian', 'security')):
        tk.Label(md_parent, text=f"{cat.capitalize()}:") \
            .grid(row=row, column=1 + i , sticky='e', padx=(1, 0))
        var = tk.StringVar(value=traffic.get(cat, 'none'))
        cb = ttk.Combobox(
            md_parent,
            textvariable = var,
            values = levels,
            state = 'readonly',
            width = 8
        )
        cb.grid(row=row, column=2 + i , sticky='w', pady=(5, 2))
        var.trace_add(
            'write', lambda *a, c=cat, v=var: traffic.__setitem__(c, v.get())
        )
    row += 1


  # ─── Collapsible Map Elements section ──────────────────────────────
    mapel_header = tk.Label(
        frame, text="▶ Map Elements", font=('Arial', 10, 'bold'), cursor='hand2'
                            )
    mapel_header.grid(row=row, column=0, columnspan=8, sticky='w', pady=(10, 0))
    elems_frame = tk.Frame(frame)
  # center three columns with padding
    elems_frame.grid(row=row + 1, column=0, columnspan=8, sticky='ew', padx=10)
  # configure three equal columns (each ~200px wide), start collapsed

    for c in range(3):
        elems_frame.grid_columnconfigure(c, weight=1, minsize=200)
    elems_frame.grid_remove()

    def toggle_map_elements(event=None):
        if elems_frame.winfo_ismapped():
            elems_frame.grid_remove()

            mapel_header.config(text="▶ Map Elements")
        else:
            elems_frame.grid()
            mapel_header.config(text="▼ Map Elements")
    mapel_header.bind("<Button-1>", toggle_map_elements)
    # List sections
    def make_list(label_text, items, col, callback, parent=None):
        nonlocal row
        # Label above list
        p = parent or frame
        tk.Label(p, text=label_text).grid(row=row, column=col, sticky='n')
        lb = tk.Listbox(p, height=6, width=30)
        # Place list below its label, center with padding between columns
        lb.grid(row=row + 1, column=col, padx=10, pady=5)

        for it in items:
            lb.insert(tk.END, callback(it))
        return lb

    relays = sm.list_sensor_relays().items()
    objs = sm.list_objects()
    obj_lb = make_list("Objects:", objs, 0, lambda name: name, parent=elems_frame)
    obj_lb.bind('<<ListboxSelect>>', lambda e: show_object(objs[obj_lb.curselection()[0]]) if obj_lb.curselection() else None)
    # Relays list between Objects and Terrain
    relay_keys = list(sm.list_sensor_relays().keys())
    special = sorted([r for r in relay_keys if not (r.startswith('SR-') or r.startswith('Relay '))])
    standard = sorted([r for r in relay_keys if (r.startswith('SR-') or r.startswith('Relay '))])
    relay_order = special + standard
    relay_lb = make_list("Relays:", relay_order, 1, lambda r: r, parent=elems_frame)
    relay_lb.bind('<<ListboxSelect>>', lambda e: show_relay(relay_order[relay_lb.curselection()[0]]) if relay_lb.curselection() else None)
    # Define terrain list keys
    terrain_keys = sm.list_terrain()
    # Terrain list()
    ter_lb = make_list("Terrain:", terrain_keys, 2, lambda k: k, parent=elems_frame)  # column 4 for even spacing
    # Bind terrain list selection to display details
    ter_lb.bind('<<ListboxSelect>>', lambda e: show_terrain(terrain_keys[ter_lb.curselection()[0]]) if ter_lb.curselection() else None)

    # move past the two rows used by each list (label + listbox)
    row += 2

    global g_obj_lb, g_relay_lb, g_ter_lb, g_ctx
    g_obj_lb   = obj_lb
    g_relay_lb = relay_lb
    g_ter_lb   = ter_lb

    # Edit pane setup (sidebar on far right)
    edit_frame = tk.Frame(win, bd=1, relief=tk.SUNKEN, width=350)
    edit_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=10, pady=10)
    edit_frame.config(width=350)
    edit_frame.pack_propagate(False)
    # children use grid(); stop grid from resizing the frame
    edit_frame.grid_propagate(False)
    edit_title = tk.Label(edit_frame, text="Select item to edit", font=(None,12,'bold'))
    # Place title with grid so it’s always on row 0 above everything else
    edit_frame.grid_rowconfigure(0, weight=0)
    edit_frame.grid_columnconfigure(0, weight=1)
    edit_title.grid(row=0, column=0, columnspan=2, pady=5)

    global clear_edit_pane
    def clear_edit_pane():
        # before destroying widgets, commit any pending description safely
        global _last_desc_widget, _last_desc_obj
        if _last_desc_widget and _last_desc_obj:
            try:
                text = _last_desc_widget.get('1.0', 'end').strip()
                _last_desc_obj['description'] = text
            except tk.TclError:
        # widget no longer exists; skip saving
                pass
            finally:
            # clear references to avoid calling a destroyed widget again
                _last_desc_widget = None
                _last_desc_obj = None
          # now clear the pane

        for child in edit_frame.winfo_children():
            if child is not edit_title:
                child.destroy()
    # Generic builder for fields (Entry, Spinbox, Combobox) based on initial value
    def build_field(parent, initial, setter):
        # If it’s an integer, use IntVar + Spinbox
        if isinstance(initial, int):
            # integer field with immediate revert+bell on invalid input
            last_valid = {'val': initial}
            var = tk.StringVar(value=str(initial))
            # allow digits or blank (so you can delete all chars) :contentReference[oaicite:0]{index=0}
            vcmd = parent.register(lambda P: P.isdigit() or P == '')
            sb = tk.Spinbox(
                parent,
                from_=0,
                to=99999,
                textvariable=var,
                validate='key',
                validatecommand=(vcmd, '%P')
            )
            sb.pack(anchor='w', pady=2)

            def on_write(*_):
                txt = var.get()
                if txt.isdigit():
                    iv = int(txt)
                    setter(iv)
                    last_valid['val'] = iv
                elif txt == '':
                    # allow blank while typing
                    pass
                else:
                    parent.bell()         # invalid character
                    var.set(str(last_valid['val']))  # immediate revert

            var.trace_add('write', on_write)

            def on_focus_out(e):
                txt = var.get()
                # revert blank or any non-digit on blur
                if not txt.isdigit():
                    var.set(str(last_valid['val']))

            sb.bind('<FocusOut>', on_focus_out)
            return sb

        # If it’s a float, use DoubleVar + Entry
        elif isinstance(initial, float):
            var = tk.DoubleVar(value=initial)
            entry = tk.Entry(parent, textvariable=var)
            entry.pack(anchor='w', pady=2)
            var.trace_add('write', lambda *a: setter(var.get()))
            return entry

        # Otherwise treat it as a string
        else:
            var = tk.StringVar(value=str(initial))
            entry = tk.Entry(parent, textvariable=var)
            entry.pack(anchor='w', pady=2)
            var.trace_add('write', lambda *a: setter(var.get()))
            return entry

    def show_item(kind, key, fields, rename_fn, delete_fn):
        """
        Generic item display: fields may include optional fourth element 'text' to render a multi-line Text widget
        """
        clear_edit_pane()
        # Track selection type and name
        set_selection(kind.lower(), key)
        edit_title.config(text=f"{kind}: {key}")
        for field in fields:
            label_text, getter, setter = field[0], field[1], field[2]
            widget_type = field[3] if len(field) == 4 else 'entry'
            if widget_type == 'text':
                # multiline description
                tk.Label(edit_frame, text=label_text, wraplength=230, justify='left')\
                    .pack(anchor='w', pady=2)
                txt = tk.Text(edit_frame, height=4, width=30)
                txt.insert('1.0', getter())
                txt.pack(anchor='w', pady=2)
                txt.bind('<FocusOut>', lambda e, s=setter, t=txt: s(t.get('1.0', 'end').strip()))
            elif widget_type == 'check':
                # inline checkbox with label to the right
                var = tk.BooleanVar(value=getter())
                cb  = tk.Checkbutton(
                    edit_frame,
                    text=label_text,
                    variable=var,
                    anchor='w',
                    justify='left'
                )
                cb.pack(anchor='w', pady=2)
                # bind with defaults so setter/var are captured immediately
                var.trace_add(
                    'write',
            #        lambda *a, setter=setter, var=var: setter(var.get())
                )
            else:
               # default field type
                tk.Label(edit_frame, text=label_text, wraplength=230, justify='left')\
                    .pack(anchor='w', pady=2)
                build_field(edit_frame, getter(), setter)
        tk.Button(edit_frame, text="Rename", command=lambda: rename_fn(key)).pack(pady=5)
        tk.Button(edit_frame, text="Delete", fg="red", command=lambda: delete_fn(key)).pack(pady=5)
        # --- Selection Display Functions ---
    # Track current selection for Delete key support
    global current_selection
    current_selection = {'type': None, 'name': None}

    def set_selection(item_type, name):
        current_selection['type'] = item_type
        current_selection['name'] = name
    
    def on_delete_key(event=None):
        t = current_selection['type']
        n = current_selection['name']
        if not t or not n:
            return
        if t == 'object': delete_object(n)
        elif t == 'relay': delete_relay(n)
        elif t == 'terrain': delete_terrain(n)
    win.bind_all('<Delete>', on_delete_key)

    # Utility delete functions for objects, relays, and terrain
    def delete_object(obj_name):
        push_undo()
        idx = objs.index(obj_name)
        del sm.data['objects'][obj_name]
        objs.pop(idx)
        obj_lb.delete(idx)
        clear_edit_pane()
        draw_map(ctx)
        current_selection['type'] = None
        current_selection['name'] = None

    def delete_relay(relay_name):
        push_undo()
        idx = relay_order.index(relay_name)
        del sm.data['sensor_relay'][relay_name]
        relay_order.pop(idx)
        relay_lb.delete(idx)
        clear_edit_pane()
        draw_map(ctx)
        current_selection['type'] = None
        current_selection['name'] = None

    def delete_terrain(ter_name):
        push_undo()
        idx = terrain_keys.index(ter_name)
        del sm.data['terrain'][ter_name]
        terrain_keys.pop(idx)
        ter_lb.delete(idx)
        clear_edit_pane()
        draw_map(ctx)
        current_selection['type'] = None
        current_selection['name'] = None
    
    # Utility rename functions for objects, relays, and terrain
    def rename_object(name):
        new_name = simpledialog.askstring("Rename Object","New name:", initialvalue=name)
        # validate pattern and length
        if not new_name:
            return
        if not _VALID_NAME.match(new_name):
            sm_win.bell()
            return
        if new_name != name:
            push_undo()
            sm.data['objects'][new_name] = sm.data['objects'].pop(name)
            idx = objs.index(name)
            objs[idx] = new_name
            obj_lb.delete(idx)
            obj_lb.insert(idx, new_name)
            clear_edit_pane()
            draw_map(ctx)
            show_object(new_name)

    def rename_relay(name):
        new_name = simpledialog.askstring("Rename Relay","New name:", initialvalue=name)
        if not new_name:
            return
        if not _VALID_NAME.match(new_name):
            sm_win.bell()
            return
        if new_name != name:
            push_undo()
            sm.data['sensor_relay'][new_name] = sm.data['sensor_relay'].pop(name)
            idx = relay_order.index(name)
            relay_order[idx] = new_name
            relay_lb.delete(idx)
            relay_lb.insert(idx, new_name)
            clear_edit_pane()
            draw_map(ctx)
            show_relay(new_name)

    def set_facility(obj, facility, enabled):
        """Add or remove a facility name in obj['facilities'] (a list)."""
        facs = obj.get('facilities', [])
        if enabled and facility not in facs:
            facs.append(facility)
        elif not enabled and facility in facs:
            facs.remove(facility)
        obj['facilities'] = facs

    def rename_terrain(name):
        new_name = simpledialog.askstring("Rename Terrain","New name:", initialvalue=name)
        if not new_name:
            return
        if not _VALID_NAME.match(new_name):
            sm_win.bell()
            return
        if new_name != name:
            push_undo()
            sm.data['terrain'][new_name] = sm.data['terrain'].pop(name)
            idx = terrain_keys.index(name)
            terrain_keys[idx] = new_name
            ter_lb.delete(idx)
            ter_lb.insert(idx, new_name)
            clear_edit_pane()
            draw_map(ctx)
            show_terrain(new_name)
    # Adapter: show_object via generic helper
    def show_object(name: str):
        obj = sm.get_object(name)
        clear_edit_pane()
        edit_title.config(text=f"Station: {name}" if obj.get('type')=='station' else f"Object: {name}")
        # Bring title to front
        edit_title.lift()
        
        def open_cargo_teams_dialog(obj_name):
            obj = sm.get_object(obj_name)
            dlg = tk.Toplevel(win)
            dlg.title(f"Configure Cargo & Teams: {obj_name}")
            dlg.grab_set()

            # ——— Presets loaded from cargo_teams.json ———
            presets = ct_config.get('presets', {})
            preset_names = ["Custom"] + list(presets.keys())
            preset_var = tk.StringVar(value="Custom")
            tk.Label(dlg, text="Preset:").grid(row=0, column=0, padx=5, pady=5, sticky='w')
            preset_cb = ttk.Combobox(dlg, textvariable=preset_var,
                                     values=preset_names, state='readonly')
            preset_cb.grid(row=0, column=1, padx=5, pady=5, sticky='w')

            # ——— Randomize Button ———
            tk.Button(dlg, text="Randomize ±10%",
                      command=lambda: randomize()).grid(row=0, column=2, padx=5)

            # ——— Items Table ———
            table = tk.Frame(dlg)
            table.grid(row=1, column=0, columnspan=3, padx=5, pady=5, sticky='nsew')
            tk.Label(table, text="Item").grid(row=0, column=0, padx=5, pady=2)
            tk.Label(table, text="Quantity").grid(row=0, column=1, padx=5, pady=2)

            # master lists from JSON file: cargo (A–Z), then teams (A–Z)
            valid_items = sorted(ct_config.get('cargo', [])) + sorted(ct_config.get('teams', []))
            rows = []

            def refresh_dropdowns():
                """Rebuild each row’s combobox values to exclude selections in other rows."""
                # Collect all selected item names (non-blank)
                selected = [e['iv'].get().strip() for e in rows if e['iv'].get().strip()]
                for e in rows:
                    curr = e['iv'].get().strip()
                    # Allow blank plus any item not chosen by other rows (or this row’s current)
                    vals = [''] + [it for it in valid_items if it not in selected or it == curr]
                    e['cb']['values'] = vals
            def remove_row(idx):
                """Remove row at index `idx` and re-grid the rest."""
                entry = rows.pop(idx)
                # destroy widgets for this row
                for w in (entry['cb'], entry['sb'], entry['btn']):
                    w.destroy()
                # re-grid subsequent rows
                for j, e in enumerate(rows):
                    rn = j + 1
                    e['cb'].grid_configure(row=rn)
                    e['sb'].grid_configure(row=rn)
                    e['btn'].grid_configure(row=rn)
                # ensure there’s always one blank row available
                if not rows or rows[-1]['iv'].get().strip():
                    add_row()
                # and re-filter all dropdowns
                refresh_dropdowns()
                    
            def add_row(item="", qty=0):
                r = len(rows) + 1
                iv = tk.StringVar(value=item)
                qv = tk.IntVar(value=qty)
                # Item dropdown
                cb = ttk.Combobox(table, textvariable=iv,
                                  values=valid_items, state='readonly')
                cb.grid(row=r, column=0, padx=5, pady=2, sticky='w')
                # Quantity spinner
                sb = tk.Spinbox(table, from_=0, to=99999,
                                textvariable=qv, width=6)
                sb.grid(row=r, column=1, padx=5, pady=2, sticky='w')
                # Remove button
                def _remove_this():
                    remove_row(rows.index(entry))
                btn = tk.Button(table, text='X', command=_remove_this, width=2)
                btn.grid(row=r, column=2, padx=5, pady=2, sticky='w')
                # Track this row’s widgets and vars
                entry = {'iv': iv, 'qv': qv, 'cb': cb, 'sb': sb, 'btn': btn}
                rows.append(entry)

                # when last blank row gets a value, append another blank
                def on_change(*_):
                    # if this was the last blank row, add another
                    if rows and rows[-1]['iv'] is iv and iv.get().strip():
                        add_row()
                    # enforce uniqueness immediately
                    refresh_dropdowns()
                iv.trace_add('write', on_change)

            # populate existing cargo+teams
            existing = {}
            for k,v in (obj.get('cargo') or {}).items():
                existing[k] = int(v)
            for k,v in (obj.get('teams') or {}).items():
                existing[k] = int(v)
            for key,val in existing.items():
                add_row(key, val)
            add_row()  # always end with a blank row
            # initial filter
            refresh_dropdowns()

            # ——— Preset handler ———
            def apply_preset(_=None):
                name = preset_var.get()
                if name in presets:
                    # clear table
                    for w in table.winfo_children():
                        w.destroy()
                    rows.clear()
                    # header
                    tk.Label(table, text="Item").grid(row=0, column=0, padx=5, pady=2)
                    tk.Label(table, text="Quantity").grid(row=0, column=1, padx=5, pady=2)
                    cfg = presets[name]
                    for d in ('cargo','teams'):
                        for it,qt in cfg[d].items():
                            add_row(it, qt)
                    add_row()
            preset_cb.bind("<<ComboboxSelected>>", apply_preset)

            # ——— Randomize handler ———
            def randomize():
                for iv,qv in rows:
                    if iv.get().strip() and qv.get() > 0:
                        base = qv.get()
                        delta = max(1, int(base * 0.1))
                        qv.set(random.randint(base - delta, base + delta))

            # ——— Save & Cancel ———
            def save():
                cargo_keys = set(ct_config.get('cargo', []))
                cargo = {}
                teams = {}
                # each entry in rows is a dict with keys 'iv' and 'qv'
                for entry in rows:
                    iv = entry['iv']
                    qv = entry['qv']
                    name = iv.get().strip()
                    if not name:
                        continue
                    if name in cargo_keys:
                        cargo[name] = qv.get()
                    else:
                        teams[name] = qv.get()
                obj['cargo'] = cargo
                obj['teams'] = teams
                dlg.destroy()
                show_object(obj_name)

            tk.Button(dlg, text="Save",   command=save)\
              .grid(row=2, column=1, pady=5)
            tk.Button(dlg, text="Cancel", command=dlg.destroy)\
              .grid(row=2, column=2, pady=5)

            dlg.transient(win)
            dlg.wait_window()
        
        
        
        # ─── Platform‐type custom layout ──────────────────────────────
        if obj.get('type') == 'platform':
            edit_title.config(text=f"Platform: {name}")
            # Side dropdown
            tk.Label(edit_frame, text="Side:").pack(anchor='w', pady=2)
            side_var = tk.StringVar(value=obj.get('sides',[''])[0])
            side_cb = ttk.Combobox(
                edit_frame,
                textvariable=side_var,
                values=valid_sides,
                state='readonly'
            )
            side_cb.pack(anchor='w', pady=2)
            side_var.trace_add('write',
                lambda *a, v=side_var: obj.__setitem__('sides',[v.get()])
            )

            # Hull dropdown (include hulls with role 'platform' or 'defense')
            tk.Label(edit_frame, text="Hull:").pack(anchor='w', pady=2)
            hull_var = tk.StringVar(value=obj.get('hull',''))
            platform_hulls = [
                e['key'] for e in ship_entries
                if any(
                    role in ('platform', 'defense')
                    for role in (
                        e.get('roles')
                        if isinstance(e.get('roles'), list)
                        else [r.strip() for r in e.get('roles','').split(',')]
                    )
                )
            ]
            hull_cb = ttk.Combobox(
                edit_frame,
                textvariable=hull_var,
                values=sorted(platform_hulls),
                state='readonly'
            )
            hull_cb.pack(anchor='w', pady=2)
            hull_var.trace_add('write',
                lambda *a, v=hull_var: obj.__setitem__('hull', v.get())
            )

            # Rename & Delete buttons
            frm = tk.Frame(edit_frame)
            frm.pack(fill='x', pady=5)
            tk.Button(frm, text="Rename",
                      command=lambda: rename_object(name))\
              .pack(side='left', expand=True, padx=2)
            tk.Button(frm, text="Delete", fg='red',
                      command=lambda: delete_object(name))\
              .pack(side='left', expand=True, padx=2)

            # Hide on map
            hide_var = tk.BooleanVar(value=obj.get('hideonmap', False))
            tk.Checkbutton(
                edit_frame,
                text="Hide on map",
                variable=hide_var,
                command=lambda: obj.__setitem__('hideonmap', hide_var.get())
            ).pack(anchor='w', pady=2)
            return

    # ─── Custom Gate (“jumppoint”) Editor ────────────────────────────────
        if obj.get('type') in ('jumpnode', 'jumppoint'):
            # Name (+ rename)
            tk.Label(edit_frame, text="Name:").pack(anchor='w', pady=2)
            name_var = tk.StringVar(value=name)
            name_ent = tk.Entry(edit_frame, textvariable=name_var)
            name_ent.pack(anchor='w', pady=2)
        # inline rename handler for gates (old rename_object only takes 1 arg) :contentReference[oaicite:0]{index=0}:contentReference[oaicite:1]{index=1}
            def _rename_gate(event, old=name, var=name_var):
                new_name = var.get().strip()
                if new_name and new_name != old:
                    # mirror rename_object logic for objects
                    sm.data['objects'][new_name] = sm.data['objects'].pop(old)
                    idx = objs.index(old)
                    objs[idx] = new_name
                    obj_lb.delete(idx)
                    obj_lb.insert(idx, new_name)
                    clear_edit_pane()
                    draw_map(ctx)
                    show_object(new_name)
            name_ent.bind('<FocusOut>', _rename_gate)

            # ─── Rename & Delete buttons for jumpnode/jumppoint ───────────────
            btn_frame = tk.Frame(edit_frame)
            btn_frame.pack(fill='x', pady=5)
            tk.Button(btn_frame, text="Rename",
                command = lambda: rename_object(name)) \
                .pack(side='left', expand=True, padx=2)
            tk.Button(btn_frame, text="Delete", fg='red',
                command = lambda: delete_object(name)) \
                .pack(side='left', expand=True, padx=2)

            # Drift spinner
            tk.Label(edit_frame, text="Drift:").pack(anchor='w', pady=2)
            drift_var = tk.IntVar(value=obj.get('drift', 0))
            drift_sb = tk.Spinbox(edit_frame, from_=0, to=100000, textvariable=drift_var)
            drift_sb.pack(anchor='w', pady=2)
            drift_var.trace_add('write', lambda *a: obj.__setitem__('drift', drift_var.get()))

            # Type selector: switch between jumpnode (default) and jumppoint
            tk.Label(edit_frame, text="Type:") \
                .pack(anchor='w', pady=2)
            type_var = tk.StringVar(value=obj.get('type'))
            type_cb = ttk.Combobox(
                edit_frame,
                textvariable = type_var,
                values = ['jumpnode', 'jumppoint'],
                state = 'readonly',
                width = 12
                 )
            type_cb.pack(anchor='w', pady=2)
            type_var.trace_add('write',
            lambda *a, v=type_var: obj.__setitem__('type', v.get())
                 )

            # State dropdown
            tk.Label(edit_frame, text="State:").pack(anchor='w', pady=2)
            state_var = tk.StringVar(value=obj.get('state', 'Tethered'))
            state_cb = ttk.Combobox(
                edit_frame,
                textvariable=state_var,
                values=["Tethered","Unteathered","Disrupted"],
                state='readonly'
            )
            state_cb.pack(anchor='w', pady=2)
            state_var.trace_add('write', lambda *a: obj.__setitem__('state', state_var.get()))

            # Destinations table (System | Gate)
            table = tk.Frame(edit_frame)
            table.pack(anchor='w', pady=2)
            tk.Label(table, text="System").grid(row=0, column=0, padx=5)
            tk.Label(table, text="Gate").  grid(row=0, column=1, padx=5)

        # ─── System dropdown options: scan data folder ───────────────
            system_options = [''] + sorted(
            os.path.splitext(f)[0]
            for f in os.listdir(data_base)
            if f.endswith('.json')
               and f.lower() not in ('package.json', 'galmapinfo.json')
        )

            dest_vars = []
            items = list(obj.get('destinations', {}).items())
            for i in range(10):
                # prepare StringVars
                
                
                sv = tk.StringVar(value=items[i][1] if i < len(items) else "")
                gv = tk.StringVar(value=items[i][0] if i < len(items) else "")

                # system Combobox (editable)
                sys_cb = ttk.Combobox(
                    table, textvariable=sv,
                    values=system_options, state='normal'
                )
                sys_cb.grid(row=i+1, column=0, padx=5, pady=1)

                # gate Combobox, populated based on sv at startup
                gate_opts = []
                if sv.get():
                    try:
                        other_sm = SystemMap(os.path.join(data_base, sv.get()+'.json'))
                        gate_opts = sorted(
                            [k for k,v in other_sm.data.get('objects',{}).items()
                             if v.get('type')=='jump_point']
                        )
                    except:
                        pass
                gate_cb = ttk.Combobox(
                    table, textvariable=gv,
                    values=gate_opts, state='normal'
                )
                gate_cb.grid(row=i+1, column=1, padx=5, pady=1)

                dest_vars.append({'sv':sv, 'gv':gv, 'gate_cb':gate_cb})

            # update destinations dict any time Gate or System changes
            def _refresh_dest(*args):
                new = {}
                for d in dest_vars:
                    sys_name = d['sv'].get().strip()
                    gate_name= d['gv'].get().strip()
                    if gate_name and sys_name:
                        new[gate_name] = sys_name
                obj['destinations'] = new

            # when System changes, reload that row’s Gate options then refresh dests
            def _on_sys_change(idx, *args):
                d = dest_vars[idx]
                sys_name = d['sv'].get().strip()
                opts = []
                if sys_name:
                    try:
                        sm2 = SystemMap(os.path.join(data_base, sys_name + '.json'))
                        opts = sorted(
                            [k for k,v in sm2.data.get('objects',{}).items()
                             if v.get('type')=='jump_point']
                        )
                    except:
                        pass
                d['gate_cb']['values'] = opts
                _refresh_dest()

            # wire up traces
            for idx, d in enumerate(dest_vars):
                d['sv'].trace_add('write', lambda *a, i=idx: _on_sys_change(i))
                d['gv'].trace_add('write', _refresh_dest)
            # Hide on map
            hide_var = tk.BooleanVar(value=obj.get('hideonmap', False))
            tk.Checkbutton(
                edit_frame,
                text="Hide on map",
                variable=hide_var,
                anchor='w',
                justify='left'
            ).pack(anchor='w', pady=2)
            hide_var.trace_add('write', lambda *a: obj.__setitem__('hideonmap', hide_var.get()))

            return

        edit_title.config(text=f"Station: {name}" if obj.get('type')=='station' else f"Object: {name}")

        # ─── Station-only custom layout ────────────────────────────────
        if obj.get('type') == 'station':
            # Station pane now starts at row 1 (row 0 is the title)
            # Side dropdown
            tk.Label(edit_frame, text="Side:").grid(row=1, column=0, sticky='w')
            side_var = tk.StringVar(value=obj.get('sides',[''])[0])
            ttk.Combobox(edit_frame, textvariable=side_var,
                         values=valid_sides, state='readonly')\
                .grid(row=1, column=1, padx=5, pady=2, sticky='w')
            side_var.trace_add('write', lambda *a: obj.__setitem__('sides',[side_var.get()]))

            # Hull dropdown
            tk.Label(edit_frame, text="Hull:").grid(row=2, column=0, sticky='w')
            hull_var = tk.StringVar(value=obj.get('hull',''))
            hull_cb  = ttk.Combobox(
                edit_frame,
                textvariable=hull_var,
                values=valid_hulls,
                state='readonly'
            )
            hull_cb.grid(row=2, column=1, padx=5, pady=2, sticky='w')
            hull_var.trace_add('write', lambda *a: obj.__setitem__('hull', hull_var.get()))

            # Filter checkboxes
            side_filter = tk.BooleanVar(value=False)
            role_filter = tk.BooleanVar(value=False)
            def update_hulls():
                filtered = list(valid_hulls)
                if side_filter.get():
                    current = obj.get('sides',[''])[0]
                    filtered = [
                        h for h in filtered
                        if next((e for e in ship_entries if e['key']==h),{}).get('side','') == current
                    ]
                if role_filter.get():
                    newf = []
                    for h in filtered:
                        roles = next((e for e in ship_entries if e['key']==h),{}).get('roles',[])
                        if isinstance(roles,str):
                            roles = [r.strip() for r in roles.split(',') if r.strip()]
                        if 'station' in roles:
                            newf.append(h)
                    filtered = newf
                hull_cb['values'] = filtered
                if hull_var.get() not in filtered:
                    hull_var.set('')

            tk.Checkbutton(
                edit_frame, text="Match station side",
                variable=side_filter, command=update_hulls
            ).grid(row=3, column=0, sticky='w')
            tk.Checkbutton(
                edit_frame, text="Only roles=station",
                variable=role_filter, command=update_hulls
            ).grid(row=3, column=1, sticky='w')

            # ─── Facilities checkboxes ──────────────────────────────
            dock_var   = tk.BooleanVar(value="Docking" in obj.get('facilities', []))
            refuel_var = tk.BooleanVar(value="Refuel"  in obj.get('facilities', []))
            repair_var = tk.BooleanVar(value="Repair"  in obj.get('facilities', []))
            tk.Checkbutton(
                edit_frame, text="Docking",
                variable=dock_var,
                command=lambda v=dock_var: set_facility(obj, "Docking", v.get())
            ).grid(row=4, column=0, sticky='w')
            tk.Checkbutton(
                edit_frame, text="Refuel",
                variable=refuel_var,
                command=lambda v=refuel_var: set_facility(obj, "Refuel", v.get())
            ).grid(row=4, column=1, sticky='w')
            tk.Checkbutton(
                edit_frame, text="Repair",
                variable=repair_var,
                command=lambda v=repair_var: set_facility(obj, "Repair", v.get())
            ).grid(row=4, column=2, sticky='w')


            # Rename & Delete buttons on row 5
            tk.Button(edit_frame, text="Rename",
                      command=lambda: rename_object(name))\
                .grid(row=5, column=1, padx=2, pady=5, sticky='w')
            tk.Button(edit_frame, text="Delete",
                      command=lambda: delete_object(name))\
                .grid(row=5, column=2, padx=2, pady=5, sticky='w')

            # Description (multi-line) at row 6
            tk.Label(edit_frame, text="Description:") \
                .grid(row=6, column=0, sticky='nw', pady=(4, 0))
            desc_text = tk.Text(edit_frame, width=30, height=4, wrap='word')
            desc_text.grid(row=7, column=0, columnspan=2, padx=5, pady=2, sticky='w')
            desc_text.insert('1.0', obj.get('description', ''))
            # remember this widget & obj so clear_edit_pane() can commit edits

            global _last_desc_widget, _last_desc_obj
            _last_desc_widget = desc_text
            _last_desc_obj = obj

            # Hide on map at row 7
            hide_var = tk.BooleanVar(value=obj.get('hideonmap', False))
            tk.Checkbutton(edit_frame, text="Hide on map",
                           variable=hide_var,
                           command=lambda: obj.__setitem__('hideonmap', hide_var.get()))\
                .grid(row=8, column=0, columnspan=2, sticky='w', pady=2)

            # Edit Cargo/Teams at row 8
            tk.Button(edit_frame, text="Edit Cargo/Teams",
                      command=lambda n=name: open_cargo_teams_dialog(n))\
                .grid(row=5, column=0, columnspan=2, sticky='w', pady=2)
            return

        show_item("Object", name, fields, rename_object, delete_object)
                # Button to bring up Cargo/Teams editor
        tk.Button(
            edit_frame,
            text="Configure Cargo/Teams",
            command=lambda n=name: open_cargo_teams_dialog(n)
        ).pack(anchor='w', pady=2)

            
        # Hide on map checkbox for objects
        hide_var = tk.BooleanVar(value=obj.get('hideonmap', False))
        hide_chk = tk.Checkbutton(edit_frame,
                                  text="Hide on map",
                                  variable=hide_var,
                                  command=lambda: obj.__setitem__('hideonmap', hide_var.get()))
        hide_chk.pack(anchor='w', pady=2)
        # --- Hull selector with side/role filters ---
        # Holder frame
        hull_frame = tk.Frame(edit_frame)
        hull_frame.pack(anchor='w', pady=5, fill='x')
        tk.Label(hull_frame, text="Hull:").grid(row=0, column=0, sticky='w')
        hull_var = tk.StringVar(value=obj.get('hull',''))
        hull_cb = ttk.Combobox(hull_frame, textvariable=hull_var,
                               values=valid_hulls, state='readonly')
        hull_cb.grid(row=0, column=1, sticky='w', padx=5)

        # Filter checkboxes
        side_var = tk.BooleanVar(value=False)
        role_var = tk.BooleanVar(value=False)
        
        # ——— Side editable Combobox ———————————————————————
        tk.Label(edit_frame, text="Side:").pack(anchor='w', pady=2)
        side_var = tk.StringVar(value=obj.get('sides',[''])[0])
        side_cb  = ttk.Combobox(
            edit_frame,
            textvariable=side_var,
            values=valid_sides,  # from ShipMap.json loader :contentReference[oaicite:0]{index=0}
            state='normal'       # editable dropdown
        )
        side_cb.pack(anchor='w', pady=2)
        side_var.trace_add(
            'write',
            lambda *a, v=side_var: obj.__setitem__('sides',[v.get()])
        )
        def update_hulls():
            # start from all hull keys
            filtered = list(valid_hulls)
            # filter by matching side if requested
            if side_var.get():
                current_side = obj.get('sides',[''])[0]
                filtered = [
                    h for h in filtered
                    if next((e for e in ship_entries if e['key']==h), {}).get('side','') == current_side
                ]
            # filter by roles containing 'station'
            if role_var.get():
                new_filtered = []
                for h in filtered:
                    entry = next((e for e in ship_entries if e['key']==h), {})
                    roles = entry.get('roles', [])
                    # normalize to list
                    if isinstance(roles, str):
                        roles_list = [r.strip() for r in roles.split(',') if r.strip()]
                    else:
                        roles_list = roles
                    if 'station' in roles_list:
                        new_filtered.append(h)
                filtered = new_filtered

            hull_cb['values'] = filtered
            # clear selection if now invalid
            if hull_var.get() not in filtered:
                hull_var.set('')

        tk.Checkbutton(edit_frame,
                       text="Match station side",
                       variable=side_var,
                       command=update_hulls)\
            .pack(anchor='w')
        tk.Checkbutton(edit_frame,
                       text="Only roles=station",
                       variable=role_var,
                       command=update_hulls)\
            .pack(anchor='w', pady=(0,5))

        # write back to obj
        hull_var.trace_add('write', lambda *a: obj.__setitem__('hull', hull_var.get()))
# Adapter: show_terrain via generic helper with blackhole support
    def show_terrain(key: str):
        feat = sm.get_terrain_feature(key)
        ttype = feat.get('type','').lower()
        clear_edit_pane()
        edit_title.config(text=f"Terrain: {key}")

        if ttype == 'blackhole':
            coord = feat.get('coordinate',[0,0,0])
            fields = [
                ("X:", lambda: coord[0], lambda v: feat.__setitem__('coordinate',[v,coord[1],coord[2]])),
                ("Z:", lambda: coord[2], lambda v: feat.__setitem__('coordinate',[coord[0],coord[1],v])),
                ("Name:", lambda: feat.get('name', key), lambda v: feat.__setitem__('name',v)),
                ("Size:", lambda: feat.get('size',0), lambda v: feat.__setitem__('size',int(v))),
                ("Strength:", lambda: feat.get('strength',0), lambda v: feat.__setitem__('strength',int(v))),
                ("Description:", lambda: feat.get('description',''), lambda v: feat.__setitem__('description',v), 'text'),
            ]
            show_item("Blackhole", key, fields, rename_terrain, delete_terrain)
        else:
            fields = [
                ("Density:", lambda: feat.get('density',1), lambda v: feat.__setitem__('density',int(v))),
                ("Scatter:", lambda: feat.get('scatter',1), lambda v: feat.__setitem__('scatter',int(v))),
            ]
            show_item("Terrain", key, fields, rename_terrain, delete_terrain)

            # ── Composition dropdown for asteroid fields ─────────────────────────

            if ttype == 'asteroids':
                comp_list = ['Ast. Std Rand']
                init_comp = feat.get('composition', [comp_list[0]])[0]
                comp_var = tk.StringVar(value=init_comp)
                tk.Label(edit_frame, text="Composition:") \
                    .pack(anchor='w', pady=2)
                comp_cb = ttk.Combobox(
                    edit_frame, textvariable=comp_var,
                    values = comp_list, state = 'readonly'
                )
                comp_cb.pack(anchor='w', pady=2)
                comp_var.trace_add('write', lambda *a: feat.__setitem__('composition', [comp_var.get()]))

        # Hide on map checkbox (applies to all terrain types)
        hide_var = tk.BooleanVar(value=feat.get('hideonmap', False))
        hide_chk = tk.Checkbutton(edit_frame,
                                  text="Hide on map",
                                  variable=hide_var,
                                  command=lambda: feat.__setitem__('hideonmap', hide_var.get()))
        hide_chk.pack(anchor='w', pady=2)



    # Save All button
    def save_all():
        try:
            # Update in-memory state
            sm.set_system_map_coord([float(var.get()) for var in coord_vars])
            sm.set_alignment(align_var.get())
            sm.set_description(desc_text.get('1.0', tk.END).strip())
            # Persist to disk
            sm.save()
            # Inform user but do NOT close the window
            messagebox.showinfo("Saved", f"{filename} saved.")
        except Exception as e:
            messagebox.showerror("Error", f"Save failed: {e}")
    
   # ─── Reload button (clear & reload from disk) ──────────────────
    def reload_all():
        nonlocal sm
        try:
            # re-instantiate from file
            sm = SystemMap(file_path)
            # refresh metadata fields
            for var, val in zip(coord_vars, sm.get_system_map_coord()):
                var.set(str(val))
            align_var.set(sm.get_alignment() or '')
            desc_text.delete('1.0', tk.END)
            desc_text.insert('1.0', sm.get_description())

            # refresh Objects list
            obj_lb.delete(0, tk.END)
            objs[:] = sm.list_objects()
            for name in objs:
                obj_lb.insert(tk.END, name)

            # refresh Relays list
            relay_order.clear()
            relay_order.extend(sm.list_sensor_relays().keys())
            relay_lb.delete(0, tk.END)
            for name in relay_order:
                relay_lb.insert(tk.END, name)

            # refresh Terrain list
            terrain_keys.clear()
            terrain_keys.extend(sm.list_terrain())
            ter_lb.delete(0, tk.END)
            for key in terrain_keys:
                ter_lb.insert(tk.END, key)

            # update drawing context and redraw
            ctx['sm'] = sm
            draw_map(ctx)
        except Exception as e:
            messagebox.showerror("Error", f"Reload failed: {e}")

    # ─── Load Different System ────────────────────────────────────────────────
    def load_different_system():
        # Let the user pick another JSON (same initialdir/base as startup)
        newpath = filedialog.askopenfilename(
            title="Select System JSON",
            initialdir=data_base,
            filetypes=[("JSON Files", "*.json")]
        )
        if not newpath:
            return
        newfname = os.path.basename(newpath)
        if newfname == 'package.json':
            messagebox.showerror("Error", "Cannot open package.json")
            return
        # Close this editor window and open a fresh one
        win.destroy()
        open_system_editor(newfname)


    def show_info():
        info_win = tk.Toplevel(win)
        info_win.title("Help & Styling Guidelines")
        txt = tk.Text(info_win, wrap='word', width=60, height=20)
        txt.pack(expand=True, fill='both', padx=10, pady=10)
        help_content = (
            "Map Editor For TSN Sandbox by Fish\n"
            "For 1.0.6 of Cosmos and TSN Mod Acendence+\n\n"
            "Help & Styling Guidelines:\n\n"
            "- G will cycle grid options\n"
            "- Avoid special Charecters in names\n"
            "- Hide on Map Tickbox will stop that item from beeing shown\n"
            "- in the standard StellarCartography maps that players can access\n"
            "- Sensor Relays with non standard names (SR-<number>) Can be used as\n"
            "- Points of Intrest markers and Hazard Markers.\n"
            "\n\n"
            "Editorial Guidlines \n"
            "Maps should be designed with a handfull of easter eggs and hidden featuers\n"
            "Maps should not be exact replications of old maps - take advantage of the space\n"
            "use of the descriptions for stations and POI Sensor Relays is strongly recomended!\n"
            "Stations should be clustered with some exceptoions each cluster should be between 100k and 250K apart\n"
            "Sensor Relays will pass on sensor data to eachother - at current the pass on distance is 50K as such a string of sensors between Station islands and destinations is recomended  \n"
            "Only Stations on the TSN side (Command Stations, Armorys, Other Military facilites) should have docking permited by default (GM can allow/disable docking) a default load out for all stations is advised \n"
            "Some Stations are infact intended as submoduals for example - Storage facilites Theses should be in imediat proximity to a relivent station - Mining, Shipyard etc. the goal is to provide some lower risk stuff that can be blown up by eneimes with out large loss of life and allow some time for players to respond to the location \n"
            "Gates are not restricted to one destination, and can link to another gate in the same system they also dont have to be omni directional \n"
            
        )
        txt.insert("1.0", help_content)
        txt.config(state='disabled')

    # ─── Meta Ribbon ────────────────────────────────────────────────────
    button_frame = tk.Frame(frame)
    # span all columns and allow horizontal expansion
    button_frame.grid(row=row+2, column=0, columnspan=8, sticky='ew', pady=2)

    # define each action
    actions = [
        ("Save All Changes", save_all),
        ("Reload",           reload_all),
        ("Load Different System", load_different_system),
        ("Undo",             do_undo),
        ("Redo",             do_redo),
        ("Info",             show_info),
    ]
    # pack buttons side-by-side with minimal spacing
    for (label, cmd) in actions:
        tk.Button(button_frame, text=label, command=cmd)\
            .pack(side='left', padx=2, pady=2)

    # Toolbar: replace in-lined ribbon with external module
    toolbar_frame = tk.Frame(frame)
    toolbar_frame.grid(row=row+3, column=0, columnspan=5, pady=(5,0), sticky='we')
    # first create the map canvas,
    map_canvas = tk.Canvas(win, width=600, height=600, bg='black')
    map_canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=5)
    # Editor-only: grid mode cycling (press 'g' to toggle)
    grid_mode_index = 0
    def cycle_grid_mode(event=None):
        nonlocal grid_mode_index
        grid_mode_index = (grid_mode_index + 1) % len(GRID_MODES)
        mode = GRID_MODES[grid_mode_index]
        draw_map(ctx)
    map_canvas.bind_all('<g>', cycle_grid_mode)



    # now instantiate our refactored Toolbar
    base = get_base_path()
    toolbar = Toolbar(
        parent    = toolbar_frame,
        base_path = base,
        sm        = sm,
        relay_lb  = relay_lb,
        ter_lb    = ter_lb,
        map_canvas= map_canvas
    )

    # bind resize (unchanged)
    def on_canvas_resize(event):
        nonlocal map_scale, pan_x, pan_y
        width = event.width
        height = event.height
        map_scale = width / 500000.0
        pan_y    = height / 2
  
    map_canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=5)

    # Handle canvas resize to update map scale
    def on_canvas_resize(event):
        nonlocal map_scale, pan_x, pan_y
        width = event.width
        height = event.height
        # maintain full width representing 500000 units
        map_scale = width / 500000.0
        # recenter pan to middle
        pan_x = width / 2
        pan_y = height / 2
        draw_map(ctx)
    map_canvas.bind('<Configure>', on_canvas_resize)

    # Map controls
    map_scale = 600.0 / 500000.0  # 500k units span 600px
    pan_x, pan_y = 300.0, 300.0   # center origin
    drag_data = {'x': 0, 'y': 0, 'panning': False, 'obj': None, 'terrain': None, 'new_terrain': None}  # track dragging terrain points

    def coord_to_screen(x, z):
        sx = x * map_scale + pan_x
        sy = -z * map_scale + pan_y
        return sx, sy

    def screen_to_coord(sx, sy):
        x = (sx - pan_x) / map_scale
        z = -(sy - pan_y) / map_scale
        return x, z

    def draw_map(ctx):
        # Unpack pan/zoom state
        pan_x = ctx['pan_x']
        pan_y = ctx['pan_y']
        map_scale = ctx['map_scale']
        map_canvas = ctx['map_canvas']
        sm = ctx['sm']
        # Define local coordinate transforms to use updated pan/zoom
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
            # Support both list and dict entries for relays
            coord = entry.get('coordinate', entry) if isinstance(entry, dict) else entry
            sx, sy = coord_to_screen(coord[0], coord[2])
            rr = 5
            color = 'green' if (rname.startswith('SR-') or rname.startswith('Relay ')) else 'cyan'
            map_canvas.create_oval(sx-rr, sy-rr, sx+rr, sy+rr,
                fill=color, outline='', tags=('relay_pt', rname))
            if color == 'cyan':
                map_canvas.create_text(sx, sy-10,
                    text=rname, fill='cyan', font=('Arial',8), tags=('relay_pt', rname))
        # draw objects
        for name in objs:
            coord = sm.get_object(name).get('coordinate', [0,0,0])
            sx, sy = coord_to_screen(coord[0], coord[2])
            r = 5
            map_canvas.create_oval(sx-r, sy-r, sx+r, sy+r,
                fill='white', tags=('obj', name))
            map_canvas.create_text(sx, sy-10,
                text=name, fill='white', font=('Arial',8), tags=('obj', name))
        # draw terrain as boxes
        for key in terrain_keys:
            feat = sm.get_terrain_feature(key)
            # blackhole rendering: yellow dot with black center
            t_type = feat.get('type','').lower()
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
            map_canvas.create_polygon(
                pts, fill=color, outline='',
                tags=('terrain', key)
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
        map_canvas.tag_lower('terrain')
        map_canvas.tag_raise('relay_pt')
        map_canvas.tag_raise('obj')

    def on_canvas_release(event):
        # After drag, update sidebar
        if drag_data.get('relay'):
            show_relay(drag_data['relay'])
        elif drag_data.get('obj'):
            show_object(drag_data['obj'])
        elif drag_data.get('terrain'):
            key,_ = drag_data['terrain']
            show_terrain(key)
        # clear drag state
        drag_data['relay'] = None
        drag_data['obj'] = None
        drag_data['terrain'] = None
        if drag_data.get('obj'):
            show_object(drag_data['obj'])
        elif drag_data.get('terrain'):
            key, _ = drag_data['terrain']
            show_terrain(key)
        # Clear drag state
        drag_data['panning'] = False
        drag_data['obj'] = None
        drag_data['terrain'] = None

    # Zoom handler for canvas
    def on_map_zoom(event):
        nonlocal map_scale, pan_x, pan_y
        factor = 1.2 if event.delta > 0 else 1/1.2
        pan_x = event.x + factor * (pan_x - event.x)
        pan_y = event.y + factor * (pan_y - event.y)
        map_scale *= factor
        draw_map(ctx)



    # Adapter: show_relay via generic helper
    def show_relay(name: str):
        relay_data = sm.data.get('sensor_relay', {}).get(name)
        if isinstance(relay_data, dict):
            coord = relay_data.get('coordinate',[0,0,0])
        else:
            coord = sm.list_sensor_relays().get(name,[0,0,0])
            relay_data = {'coordinate': coord}
            sm.data['sensor_relay'][name] = relay_data
        clear_edit_pane()
        edit_title.config(text=f"Relay: {name}")
        fields = [
            ("X:",           lambda: relay_data['coordinate'][0], lambda v: relay_data['coordinate'].__setitem__(0,v)),
            ("Z:",           lambda: relay_data['coordinate'][2], lambda v: relay_data['coordinate'].__setitem__(2,v)),
            ("Description:", lambda: relay_data.get('description',''), lambda v: relay_data.__setitem__('description',v), 'text'),
        ]
        show_item("Relay", name, fields, rename_relay, delete_relay)
        # Hide on map checkbox for relays
        hide_var = tk.BooleanVar(value=relay_data.get('hideonmap', False))
        hide_chk = tk.Checkbutton(edit_frame,
                                  text="Hide on map",
                                  variable=hide_var,
                                  command=lambda: relay_data.__setitem__('hideonmap', hide_var.get()))
        hide_chk.pack(anchor='w', pady=2)

# Build context for canvas event handlers
    ctx = {
        'toolbar': toolbar,
        'map_canvas': map_canvas,
        'sm': sm,
        'ter_lb': ter_lb,
        'relay_order': relay_order,
        'relay_lb': relay_lb,
        'objs': objs,
        'obj_lb': obj_lb,
        'terrain_keys': terrain_keys,
        'valid_sides': valid_sides,
        'valid_hulls': valid_hulls,
        'align_var': align_var,
        'show_relay': show_relay,
        'show_object': show_object,
        'show_terrain': show_terrain,
        'draw_map': draw_map,
        'drag_data': drag_data,
        'screen_to_coord': screen_to_coord,
        'win': win,
        'pan_x': pan_x,
        'pan_y': pan_y,
        'map_scale': map_scale,
        'push_undo':  push_undo
    }
    map_canvas.bind('<ButtonPress-1>', lambda e, _ctx=ctx: SysMapCanvas.on_canvas_press(e, _ctx))
    map_canvas.bind('<B1-Motion>', lambda e, _ctx=ctx: SysMapCanvas.on_canvas_drag(e, _ctx))
    map_canvas.bind('<ButtonRelease-1>', on_canvas_release)
    map_canvas.bind('<MouseWheel>', lambda e, _ctx=ctx: SysMapCanvas.on_map_zoom(e, _ctx))
    map_canvas.bind('<Configure>', on_canvas_resize)
    draw_map(ctx)
    global g_ctx
    g_ctx = ctx    

if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()
    base = get_base_path()
    data_base = get_data_path()
    json_files = [f for f in os.listdir(data_base) if f.endswith('.json') and f != 'package.json']
    if not json_files:
        messagebox.showerror("Error", "No system JSON files found in:\n" + data_base)
        sys.exit()
    selected = filedialog.askopenfilename(
        title="Select System JSON",
        initialdir=data_base,
        filetypes=[("JSON Files", "*.json")]
    )
    if not selected:
        sys.exit()
    if os.path.basename(selected) == 'package.json':
        messagebox.showerror("Error", "Cannot open package.json")
        sys.exit()
    filename = os.path.basename(selected)
    root.deiconify()
    open_system_editor(filename)
    root.mainloop()
