import os
import argparse
import sys
import json
import datetime
import ast
from pathlib import Path
from tkinter import ttk, messagebox, filedialog, simpledialog
from typing import Any, Dict, List, Optional
import tkinter as tk
from Toolbar import Toolbar
import SysMapCanvas
import random
import copy
from PIL import Image, ImageTk
import re
import SystemMetaOptions as smopts
from JsonStorage import atomic_write_json
# Re-export established helpers for compatibility with external scripts.
# New code should import their owning modules directly (see ARCHITECTURE.md).
from MapTypes import (
    ZONE_STYLE_MAP, DEFAULT_ZONE_STYLE, FCS_ZONE_TYPE,
    DEFAULT_FCS_ZONE_RADIUS, DEFAULT_FCS_MIN_SPACING, DEFAULT_FCS_DENSITY_RADIUS,
    DEFAULT_FCS_DENSITY_PERCENTILE, DEFAULT_FCS_MIN_SCORE, DEFAULT_FCS_SPACING_JITTER,
    DEFAULT_FCS_DESCRIPTION, STATION_OR_PLATFORM_TYPES, DEFAULT_PLANET_CLASS,
    RELAY_TYPE_SENSOR, RELAY_TYPE_WARNING_BUOY, RELAY_TYPE_OPTIONS,
    WARNING_BUOY_DEFAULT_PING, WARNING_BUOY_DEFAULT_RANGE, GRID_MODES,
    GRID_SPACING, get_zone_style, is_zone_type,
    object_has_blank_or_invalid_hull, _normalize_roles, normalize_relay_type,
    ensure_relay_dict
)
from MapMetadata import (
    INCOMING_ONLY_GATES_KEY, INCOMING_ONLY_GATES_ALIASES, get_incoming_only_gate_list,
    get_incoming_only_gate_names, set_incoming_only_gate, rename_incoming_only_gate,
    remove_incoming_only_gate, _normalize_author_list, _coerce_revision_number,
    build_gate_index_for_systems
)
from EditorSettings import (
    get_data_path, get_default_data_path, get_default_html_path,
    resolve_configured_path, get_html_output_path, get_settings_path,
    _load_settings_file, load_editor_settings, save_editor_settings
)
from StationOverview import open_station_overview
from SystemValidation import (is_number_like, validate_coordinate_value,
    collect_cargo_team_validation_issues as collect_cargo_issues, verify_system_data as verify_map_data)
from SystemMigrations import migrate_legacy_structure, migrate_sides, migrate_planet_classes
from SystemMap import SystemMap
from TerrainGeometry import (
    distance_to_spine, influence, generate_line_coords,
    distance_sq_2d, percentile_value, jittered_fcs_spacing,
    collect_nebula_points_for_fcs, collect_fcs_blocked_centers, generate_zone_name,
    select_fcs_zone_centers
)
from SystemMapRenderer import (
    draw_red_cross, _normalise_side_key, get_object_primary_side,
    get_station_side_colour, draw_station_side_colour_legend, draw_blue_gate_ring,
    draw_system_map
)

from MapConsistency import is_gate, parse_map_coordinate_fields, rewrite_gate_references

# Icon display constants (from ProductionFlowGen.py)
SPRITE_COLUMNS = 20
SPRITE_ROWS = 20
SPRITE_SOURCE = Path("HTML") / "Images" / "Production" / "grid-icon-sheet2.png"
DATABASE_SOURCE = Path("scripts") / "Referance" / "tsn_databases.py"
CARGO_ITEM_CATEGORY_ORDER = (
    "team",
    "usable_deployable",
    "intel_special",
    "ship_items",
    "ordnance",
    "commodity",
    "raw",
)
CARGO_ITEM_CATEGORY_LABELS = {
    "team": "Team",
    "usable_deployable": "Useable/Deployable",
    "intel_special": "Intel/Special",
    "ship_items": "Ship Items",
    "ordnance": "Ordnance",
    "commodity": "Commodity",
    "raw": "Raw Material",
}
CARGO_ITEM_CATEGORY_COLORS = {
    "team": "darkblue",
    "usable_deployable": "#006b8f",
    "intel_special": "#d56b00",
    "ship_items": "#6a2c91",
    "ordnance": "#b00020",
    "commodity": "#0b7d26",
    "raw": "#7a4a12",
}
CARGO_ITEM_CATEGORY_RANK = {
    category: index for index, category in enumerate(CARGO_ITEM_CATEGORY_ORDER)
}
TARGET_ASSIGNMENTS = {
    "rawMaterials",
    "shipItems", 
    "commoditiesDatabase",
    "intelfragmentsDatabase",
    "ordnanceDatabase",
}
TEAM_ICON_META = {
    # Team names are stored in cargo_teams.json, not the TSN item database.
    "DamCon": {"icon": 168, "colour": "#8bd6ff", "category": "team"},
    "Medics": {"icon": 170, "colour": "#71d983", "category": "team"},
    "Marines": {"icon": 360, "colour": "#b8c4d6", "category": "team"},
    "Combat Engineers": {"icon": 166, "colour": "#f1c46a", "category": "team"},
    "Evacuees": {"icon": 366, "colour": "#a7d8ff", "category": "team"},
    "Diplomats": {"icon": 368, "colour": "#d6c2ff", "category": "team"},
}
USABLE_DEPLOYABLE_ITEMS = {
    # Manual category override list for cargo/team dropdown grouping.
    "Comms Relay",
    "Coolant",
    "Fuel Cell 100",
    "Fuel Cell 200",
    "Fuel Cell 400",
    "Sensor Relay",
    "Warning Beacon",
    "Warning Buoy",
    "Warp Inhibitor",
}
INTEL_SPECIAL_ITEMS = {
    # Manual category override list for cargo/team dropdown grouping.
    "Vaccine",
    "Virus",
    "Virus Sample",
}


def parse_database_snapshot(path):
    source = path.read_text(encoding="utf-8")
    module = ast.parse(source, filename=str(path))
    snapshot = {}

    for node in module.body:
        if not isinstance(node, ast.Assign):
            continue
        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            continue

        name = node.targets[0].id
        if name not in TARGET_ASSIGNMENTS:
            continue

        try:
            snapshot[name] = ast.literal_eval(node.value)
        except Exception as exc:
            raise ValueError(f"Could not parse {name} from {path}: {exc}") from exc

    return snapshot

def build_item_meta(snapshot):
    meta_sources = (
        (snapshot["rawMaterials"], "raw"),
        (snapshot["shipItems"], "ship_items"),
        (snapshot["commoditiesDatabase"], "commodity"),
        (snapshot["intelfragmentsDatabase"], "commodity"),
        (snapshot["ordnanceDatabase"], "ordnance"),
    )

    item_meta = {}
    for source, category in meta_sources:
        for item, data in source.items():
            if not isinstance(data, dict):
                continue
            item_meta[str(item).strip()] = {
                "icon": data.get("icon"),
                "colour": data.get("colour", "#5f86a8"),
                "size": data.get("size"),
                "signatures": data.get("signatures", data.get("signature")),
                "category": category,
            }
    return item_meta

class CategorizedItemDropdown(tk.Button):
    def __init__(self, parent, variable, category_lookup, width=28):
        super().__init__(
            parent,
            textvariable=variable,
            command=self.show_dropdown,
            relief='sunken',
            borderwidth=1,
            anchor='w',
            width=width,
            padx=4,
            bg='white',
        )
        self.variable = variable
        self.category_lookup = category_lookup
        self.dropdown = None
        self.has_blank = False
        self.category_items = {category: [] for category in CARGO_ITEM_CATEGORY_ORDER}
        self.variable.trace_add('write', lambda *_: self._sync_foreground())
        self._sync_foreground()

    def set_values(self, values):
        seen = set()
        unique_values = []
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            unique_values.append(value)

        self.has_blank = '' in unique_values
        grouped = {category: [] for category in CARGO_ITEM_CATEGORY_ORDER}
        for value in unique_values:
            if not value:
                continue
            category = self.category_lookup(value)
            grouped.setdefault(category, []).append(value)

        self.category_items = {
            category: sorted(grouped.get(category, []), key=lambda item: item.casefold())
            for category in CARGO_ITEM_CATEGORY_ORDER
        }
        self._sync_foreground()

    def show_dropdown(self):
        if self.dropdown and self.dropdown.winfo_exists():
            try:
                self.dropdown.grab_release()
            except tk.TclError:
                pass
            self.dropdown.destroy()
            return

        self.update_idletasks()
        parent_window = self.winfo_toplevel()
        parent_window.update_idletasks()

        categories = [
            category for category in CARGO_ITEM_CATEGORY_ORDER
            if self.category_items.get(category)
        ]
        if not categories and not self.has_blank:
            return

        self.dropdown = tk.Toplevel(parent_window)
        self.dropdown.withdraw()
        self.dropdown.transient(parent_window)
        self.dropdown.title("Select Item")
        self.dropdown.resizable(False, False)

        x = self.winfo_rootx()
        y = self.winfo_rooty() + self.winfo_height()
        width = max(self.winfo_width(), 500)
        visible_rows = min(
            max((len(items) for items in self.category_items.values()), default=1),
            14
        )
        visible_rows = max(visible_rows, min(len(categories), 5), 5)
        height = visible_rows * 22 + 64
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        x = max(0, min(x, screen_w - width))
        if y + height > screen_h:
            y = max(0, self.winfo_rooty() - height)
        self.dropdown.geometry(f"{width}x{height}+{x}+{y}")

        frame = tk.Frame(self.dropdown, borderwidth=1, relief='solid', bg='white')
        frame.pack(fill='both', expand=True)

        if self.has_blank:
            clear_btn = tk.Button(
                frame,
                text="Clear selection",
                command=lambda: (self.variable.set(''), close_dropdown()),
                anchor='w'
            )
            clear_btn.grid(row=0, column=0, columnspan=3, sticky='ew', padx=4, pady=(4, 2))

        tk.Label(frame, text="Category", bg='white', anchor='w').grid(
            row=1, column=0, sticky='ew', padx=(4, 2)
        )
        tk.Label(frame, text="Item", bg='white', anchor='w').grid(
            row=1, column=1, columnspan=2, sticky='ew', padx=(2, 4)
        )

        category_list = tk.Listbox(
            frame,
            activestyle='none',
            exportselection=False,
            height=visible_rows,
            width=20,
            selectbackground='#d9e8ff',
            selectforeground='black',
        )
        item_scrollbar = tk.Scrollbar(frame, orient='vertical')
        item_list = tk.Listbox(
            frame,
            activestyle='none',
            exportselection=False,
            height=visible_rows,
            width=34,
            selectbackground='#d9e8ff',
            selectforeground='black',
            yscrollcommand=item_scrollbar.set,
        )
        item_scrollbar.config(command=item_list.yview)

        category_list.grid(row=2, column=0, sticky='ns', padx=(4, 2), pady=(0, 4))
        item_list.grid(row=2, column=1, sticky='nsew', padx=(2, 0), pady=(0, 4))
        item_scrollbar.grid(row=2, column=2, sticky='ns', padx=(0, 4), pady=(0, 4))
        frame.grid_columnconfigure(1, weight=1)
        frame.grid_rowconfigure(2, weight=1)

        current = self.variable.get().strip()
        current_category = self.category_lookup(current) if current else None
        if current_category not in categories:
            current_category = categories[0] if categories else None

        for index, category in enumerate(categories):
            category_list.insert('end', CARGO_ITEM_CATEGORY_LABELS.get(category, category.title()))
            color = CARGO_ITEM_CATEGORY_COLORS.get(category, 'black')
            category_list.itemconfig(index, foreground=color)
            if category == current_category:
                category_list.selection_set(index)
                category_list.see(index)

        def selected_category():
            selection = category_list.curselection()
            if not selection:
                return current_category
            return categories[selection[0]]

        def render_items(event=None):
            category = selected_category()
            item_list.delete(0, 'end')
            if not category:
                return
            color = CARGO_ITEM_CATEGORY_COLORS.get(category, 'black')
            selected_item_index = None
            for index, item in enumerate(self.category_items.get(category, [])):
                item_list.insert('end', item)
                item_list.itemconfig(index, foreground=color)
                if item == current:
                    selected_item_index = index
            if selected_item_index is not None:
                item_list.selection_set(selected_item_index)
                item_list.see(selected_item_index)

        def choose_current(event=None):
            selection = item_list.curselection()
            if not selection:
                return "break"
            category = selected_category()
            if not category:
                return "break"
            items = self.category_items.get(category, [])
            if selection[0] >= len(items):
                return "break"
            self.variable.set(items[selection[0]])
            return close_dropdown()

        def close_dropdown(event=None):
            if self.dropdown and self.dropdown.winfo_exists():
                try:
                    self.dropdown.grab_release()
                except tk.TclError:
                    pass
                self.dropdown.destroy()
            return "break"

        def close_if_outside(event=None):
            if not (self.dropdown and self.dropdown.winfo_exists() and event):
                return
            x = event.x_root
            y = event.y_root
            left = self.dropdown.winfo_rootx()
            top = self.dropdown.winfo_rooty()
            right = left + self.dropdown.winfo_width()
            bottom = top + self.dropdown.winfo_height()
            if not (left <= x <= right and top <= y <= bottom):
                close_dropdown()

        category_list.bind('<<ListboxSelect>>', render_items)
        category_list.bind('<Return>', lambda event: item_list.focus_set())
        category_list.bind('<Escape>', close_dropdown)
        item_list.bind('<Double-Button-1>', choose_current)
        item_list.bind('<Return>', choose_current)
        item_list.bind('<Escape>', close_dropdown)
        item_list.bind('<ButtonRelease-1>', choose_current)
        self.dropdown.bind('<ButtonPress-1>', close_if_outside, add='+')
        self.dropdown.protocol("WM_DELETE_WINDOW", close_dropdown)
        render_items()
        self.dropdown.grab_set()
        self.dropdown.deiconify()
        self.dropdown.lift(parent_window)
        self.dropdown.focus_force()
        category_list.focus_set()

    def _sync_foreground(self):
        value = self.variable.get().strip()
        category = self.category_lookup(value) if value else ''
        color = CARGO_ITEM_CATEGORY_COLORS.get(category, 'black')
        self.configure(fg=color, activeforeground=color)


# valid names: letters, digits, dot, space; 1–20 chars
_VALID_NAME = re.compile(r'^[A-Za-z0-9. ]{1,20}$')


from AppPaths import get_base_path, get_resource_path


def _parse_multiline_values(value: str) -> List[str]:
    values = []
    seen = set()
    for raw in re.split(r'[\n,]+', value or ''):
        item = raw.strip()
        if not item:
            continue
        key = item.casefold()
        if key in seen:
            continue
        seen.add(key)
        values.append(item)
    return values


def prompt_for_author(parent, settings: Optional[Dict[str, Any]] = None) -> Optional[str]:
    settings = settings if isinstance(settings, dict) else load_editor_settings()
    result = {'author': None}

    dlg = tk.Toplevel(parent)
    dlg.title("Author")
    dlg.transient(parent)
    dlg.grab_set()
    dlg.resizable(False, False)

    tk.Label(dlg, text="Enter your author name for this session:").grid(
        row=0, column=0, columnspan=2, sticky='w', padx=12, pady=(12, 6)
    )
    author_var = tk.StringVar()
    entry = ttk.Entry(dlg, textvariable=author_var, width=36)
    entry.grid(row=1, column=0, columnspan=2, sticky='ew', padx=12)

    save_var = tk.BooleanVar(value=False)
    ttk.Checkbutton(
        dlg,
        text="Save this author to Settings.json",
        variable=save_var,
    ).grid(row=2, column=0, columnspan=2, sticky='w', padx=12, pady=(8, 10))

    buttons = ttk.Frame(dlg)
    buttons.grid(row=3, column=0, columnspan=2, sticky='e', padx=12, pady=(0, 12))

    def accept():
        author = author_var.get().strip()
        if not author:
            messagebox.showwarning("Author", "Enter an author name or cancel.", parent=dlg)
            return
        result['author'] = author
        if save_var.get():
            settings['author'] = author
            save_editor_settings(settings)
        dlg.destroy()

    def cancel():
        dlg.destroy()

    ttk.Button(buttons, text="OK", command=accept).pack(side=tk.LEFT, padx=(0, 6))
    ttk.Button(buttons, text="Cancel", command=cancel).pack(side=tk.LEFT)
    dlg.bind('<Return>', lambda _event: accept())
    dlg.bind('<Escape>', lambda _event: cancel())
    entry.focus_set()
    dlg.wait_window()
    return result['author']


def open_settings_editor(parent=None, on_save=None):
    settings = load_editor_settings()
    if not isinstance(settings, dict):
        settings = {}

    dlg = tk.Toplevel(parent) if parent is not None else tk.Toplevel()
    dlg.title("Settings")
    dlg.geometry("720x560")
    if parent is not None:
        dlg.transient(parent)
    dlg.grab_set()

    notebook = ttk.Notebook(dlg)
    notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

    general = ttk.Frame(notebook)
    races_tab = ttk.Frame(notebook)
    advanced = ttk.Frame(notebook)
    notebook.add(general, text="General")
    notebook.add(races_tab, text="Races")
    notebook.add(advanced, text="Advanced JSON")

    author_var = tk.StringVar(value=str(settings.get('author', '') or ''))
    ttk.Label(general, text="Author").grid(row=0, column=0, sticky='w', padx=8, pady=(8, 2))
    ttk.Entry(general, textvariable=author_var, width=48).grid(row=1, column=0, sticky='ew', padx=8)
    general.columnconfigure(0, weight=1)

    factions_value = settings.get('Factions', [])
    if not isinstance(factions_value, list):
        factions_value = []
    paths_frame = ttk.LabelFrame(general, text="Map folders")
    paths_frame.grid(row=2, column=0, sticky='ew', padx=8, pady=(12, 2))
    paths_frame.columnconfigure(1, weight=1)

    system_maps_var = tk.StringVar(value=str(settings.get('systemMapsPath', '') or ''))
    html_output_var = tk.StringVar(value=str(settings.get('htmlOutputPath', '') or ''))

    def browse_directory(var, title, fallback):
        initial = str(resolve_configured_path(var.get(), fallback))
        if not os.path.isdir(initial):
            initial = fallback
        selected = filedialog.askdirectory(parent=dlg, title=title, initialdir=initial)
        if selected:
            var.set(selected)

    ttk.Label(paths_frame, text="Read/save system maps").grid(row=0, column=0, sticky='w', padx=8, pady=(8, 2))
    ttk.Entry(paths_frame, textvariable=system_maps_var, width=56).grid(row=0, column=1, sticky='ew', padx=(0, 6), pady=(8, 2))
    ttk.Button(
        paths_frame,
        text="Browse",
        command=lambda: browse_directory(system_maps_var, "System map folder", get_default_data_path()),
    ).grid(row=0, column=2, sticky='e', padx=(0, 8), pady=(8, 2))
    ttk.Label(paths_frame, text="Save generated HTML").grid(row=1, column=0, sticky='w', padx=8, pady=(2, 8))
    ttk.Entry(paths_frame, textvariable=html_output_var, width=56).grid(row=1, column=1, sticky='ew', padx=(0, 6), pady=(2, 8))
    ttk.Button(
        paths_frame,
        text="Browse",
        command=lambda: browse_directory(html_output_var, "Generated HTML folder", get_default_html_path()),
    ).grid(row=1, column=2, sticky='e', padx=(0, 8), pady=(2, 8))

    ttk.Label(general, text="Factions (one per line)").grid(row=3, column=0, sticky='w', padx=8, pady=(12, 2))
    factions_text = tk.Text(general, height=10, wrap='none')
    factions_text.grid(row=4, column=0, sticky='nsew', padx=8, pady=(0, 8))
    factions_text.insert('1.0', "\n".join(str(item) for item in factions_value))
    general.rowconfigure(4, weight=1)

    races_tab.columnconfigure(0, weight=1)
    races_tab.rowconfigure(0, weight=1)
    races_frame = ttk.Frame(races_tab)
    races_frame.grid(row=0, column=0, sticky='nsew', padx=8, pady=8)
    races_frame.columnconfigure(0, weight=1)
    races_frame.rowconfigure(0, weight=1)

    races_tree = ttk.Treeview(races_frame, columns=('race', 'faction'), show='headings', selectmode='browse')
    races_tree.heading('race', text='Race')
    races_tree.heading('faction', text='Faction')
    races_tree.column('race', width=260, stretch=True)
    races_tree.column('faction', width=220, stretch=True)
    races_tree.grid(row=0, column=0, sticky='nsew')
    races_scroll = ttk.Scrollbar(races_frame, orient='vertical', command=races_tree.yview)
    races_scroll.grid(row=0, column=1, sticky='ns')
    races_tree.configure(yscrollcommand=races_scroll.set)

    races_map = settings.get('Races', {})
    if not isinstance(races_map, dict):
        races_map = {}
    for race, info in sorted(races_map.items(), key=lambda item: str(item[0]).casefold()):
        faction = info.get('Faction', '') if isinstance(info, dict) else ''
        races_tree.insert('', 'end', values=(str(race), str(faction or '')))

    race_edit = ttk.Frame(races_tab)
    race_edit.grid(row=1, column=0, sticky='ew', padx=8, pady=(0, 8))
    race_edit.columnconfigure(1, weight=1)
    race_edit.columnconfigure(3, weight=1)
    race_var = tk.StringVar()
    faction_var = tk.StringVar()
    ttk.Label(race_edit, text="Race").grid(row=0, column=0, sticky='w')
    ttk.Entry(race_edit, textvariable=race_var).grid(row=0, column=1, sticky='ew', padx=(4, 8))
    ttk.Label(race_edit, text="Faction").grid(row=0, column=2, sticky='w')
    ttk.Entry(race_edit, textvariable=faction_var).grid(row=0, column=3, sticky='ew', padx=(4, 0))

    race_buttons = ttk.Frame(races_tab)
    race_buttons.grid(row=2, column=0, sticky='e', padx=8, pady=(0, 8))

    def on_race_select(_event=None):
        selected = races_tree.selection()
        if not selected:
            return
        race, faction = races_tree.item(selected[0], 'values')
        race_var.set(race)
        faction_var.set(faction)

    def add_or_update_race():
        race = race_var.get().strip()
        faction = faction_var.get().strip()
        if not race:
            messagebox.showwarning("Settings", "Enter a race name.", parent=dlg)
            return
        selected = races_tree.selection()
        target = selected[0] if selected else None
        if target is None:
            for item in races_tree.get_children():
                existing = races_tree.item(item, 'values')[0]
                if existing.casefold() == race.casefold():
                    target = item
                    break
        if target is None:
            races_tree.insert('', 'end', values=(race, faction))
        else:
            races_tree.item(target, values=(race, faction))
        race_var.set('')
        faction_var.set('')

    def delete_race():
        for item in races_tree.selection():
            races_tree.delete(item)
        race_var.set('')
        faction_var.set('')

    races_tree.bind('<<TreeviewSelect>>', on_race_select)
    ttk.Button(race_buttons, text="Add/Update", command=add_or_update_race).pack(side=tk.LEFT, padx=(0, 6))
    ttk.Button(race_buttons, text="Delete", command=delete_race).pack(side=tk.LEFT)

    known_keys = {'author', 'Factions', 'Races', 'systemMapsPath', 'htmlOutputPath'}
    extra_settings = {k: v for k, v in settings.items() if k not in known_keys}
    ttk.Label(advanced, text="Additional Settings JSON").pack(anchor='w', padx=8, pady=(8, 2))
    extra_text = tk.Text(advanced, wrap='none')
    extra_text.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))
    extra_text.insert('1.0', json.dumps(extra_settings, indent=4))

    button_row = ttk.Frame(dlg)
    button_row.pack(fill=tk.X, padx=10, pady=(0, 10))

    def save():
        try:
            extra = json.loads(extra_text.get('1.0', 'end').strip() or '{}')
            if not isinstance(extra, dict):
                raise ValueError("Additional settings must be a JSON object.")
        except Exception as exc:
            messagebox.showerror("Settings", f"Invalid Additional Settings JSON:\n{exc}", parent=dlg)
            notebook.select(advanced)
            return

        new_settings = dict(extra)
        new_settings['Factions'] = _parse_multiline_values(factions_text.get('1.0', 'end'))
        new_settings['Races'] = {}
        for item in races_tree.get_children():
            race, faction = races_tree.item(item, 'values')
            race = str(race).strip()
            if race:
                new_settings['Races'][race] = {'Faction': str(faction).strip()}
        new_settings['author'] = author_var.get().strip()
        system_maps_path = system_maps_var.get().strip()
        html_output_path = html_output_var.get().strip()
        for label, value, default_path in (
            ("System map folder", system_maps_path, get_default_data_path()),
            ("Generated HTML folder", html_output_path, get_default_html_path()),
        ):
            target = resolve_configured_path(value, default_path)
            try:
                target.mkdir(parents=True, exist_ok=True)
            except Exception as exc:
                messagebox.showerror("Settings", f"{label} could not be created:\n{target}\n\n{exc}", parent=dlg)
                notebook.select(general)
                return
            if not target.is_dir():
                messagebox.showerror("Settings", f"{label} is not a directory:\n{target}", parent=dlg)
                notebook.select(general)
                return
        if system_maps_path:
            new_settings['systemMapsPath'] = system_maps_path
        if html_output_path:
            new_settings['htmlOutputPath'] = html_output_path
        save_editor_settings(new_settings)
        if callable(on_save):
            on_save(new_settings)
        dlg.destroy()

    ttk.Button(button_row, text="Save", command=save).pack(side=tk.RIGHT, padx=(6, 0))
    ttk.Button(button_row, text="Cancel", command=dlg.destroy).pack(side=tk.RIGHT)
    return dlg


def open_system_editor(filename: str) -> None:
    undo_stack = []
    redo_stack = []
    current_selection = {'type': None, 'name': None}
    last_desc_widget = None
    last_desc_obj = None
    pending_text_widgets = []
    text_dirty = False
    copy_state = {'source_name': None, 'source_obj': None}
    session_revision_bumped = False
    saved_state = None
    # base for images, data_base for system JSON files
    base = get_base_path()
    data_base = get_data_path()
    file_path = os.path.abspath(os.path.join(data_base, filename))
    data_base = os.path.dirname(file_path)
    filename = os.path.basename(file_path)
    editor_settings = load_editor_settings()
    if not isinstance(editor_settings, dict):
        editor_settings = {}

    def _commit_text_widget(widget, setter):
        try:
            setter(widget.get('1.0', 'end').strip())
            return True
        except tk.TclError:
            return False

    def flush_pending_text_widgets():
        alive = []
        for widget, setter in pending_text_widgets:
            try:
                if not widget.winfo_exists():
                    continue
            except tk.TclError:
                continue
            if _commit_text_widget(widget, setter):
                alive.append((widget, setter))
        pending_text_widgets[:] = alive

    def register_text_widget(widget, setter):
        pending_text_widgets.append((widget, setter))

        def _on_modified(event=None, w=widget):
            nonlocal text_dirty
            try:
                if w.edit_modified():
                    text_dirty = True
                    w.edit_modified(False)
            except tk.TclError:
                pass

        widget.bind('<FocusOut>', lambda e, w=widget, s=setter: _commit_text_widget(w, s), add='+')
        widget.bind('<<Modified>>', _on_modified, add='+')
        try:
            widget.edit_modified(False)
        except tk.TclError:
            pass

    def capture_edit_state():
        # Include controls committed only on Save and direct model edits.
        variables = [*coord_vars, align_var, author_var, sec_var, pirate_var,
                     enemy_var, dev_var, focus_var, vis_var, skybox_var,
                     *export_vars.values(), *assets_vars.values(),
                     *traffic_vars.values()]
        return copy.deepcopy(sm.data), tuple(var.get() for var in variables)

    def has_unsaved_changes():
        flush_pending_text_widgets()
        return saved_state != capture_edit_state()

    def mark_saved():
        nonlocal saved_state, text_dirty
        flush_pending_text_widgets()
        saved_state = capture_edit_state()
        text_dirty = False

    def confirm_pending_changes(action):
        if not has_unsaved_changes():
            return True
        response = messagebox.askyesnocancel(
            "Unsaved changes",
            f"Save changes before {action}?\n\n"
            "Yes = Save\nNo = Discard Changes\nCancel = Keep Editing",
            parent=win,
        )
        if response is None:
            return False
        return save_all() if response else True

    # Load ShipMap for valid hulls and sides
    # ─── Load Cargo/Teams presets and master lists from JSON ─────────────
    try:
        with open(os.path.join(base, 'cargo_teams.json'), 'r') as cf:
            ct_config = json.load(cf)
    except Exception:
        ct_config = {"cargo": [], "teams": [], "presets": {}, "skyboxes": []}
    
    # ─── Load item metadata for icons from tsn_databases.py ─────────────
    try:
        db_path = get_resource_path(DATABASE_SOURCE)
        snapshot = parse_database_snapshot(db_path)
        item_meta = build_item_meta(snapshot)
    except Exception as e:
        print(f"Warning: Could not load item metadata: {e}")
        item_meta = {}
    for team_name, team_meta in TEAM_ICON_META.items():
        item_meta.setdefault(team_name, team_meta)
    sprite_sheet_cache = {"path": None, "image": None, "tile_size": None}
    
    def resolve_icon_style(item_name):
        meta = item_meta.get(item_name, {})
        icon = meta.get("icon")
        accent = str(meta.get("colour", "#5f86a8"))

        if not isinstance(icon, int) or icon < 0 or icon >= SPRITE_COLUMNS * SPRITE_ROWS:
            return "", accent

        col = icon % SPRITE_COLUMNS
        row = icon // SPRITE_COLUMNS
        style = f'--icon-col:{col}; --icon-row:{row}; --item-accent:{accent};'
        return style, accent
    
    def create_icon_label(parent, item_name, size=20):
        """Create a tkinter Label with the item's icon from the sprite sheet."""
        from PIL import Image, ImageTk
        
        style, accent = resolve_icon_style(item_name)
        
        # Create a label for the icon
        icon_label = tk.Label(parent, width=size, height=size)
        
        if style:
            try:
                # Parse the style to get icon position
                style_parts = style.split(';')
                col = None
                row = None
                for part in style_parts:
                    part = part.strip()
                    if part.startswith('--icon-col:'):
                        col = int(part.split(':')[1])
                    elif part.startswith('--icon-row:'):
                        row = int(part.split(':')[1])
                
                if col is not None and row is not None:
                    # Load the sprite sheet
                    sprite_path = Path(base) / SPRITE_SOURCE
                    if sprite_path.exists():
                        if sprite_sheet_cache["path"] != sprite_path:
                            with Image.open(str(sprite_path)) as img:
                                sprite_sheet_cache["image"] = img.convert("RGBA")
                            sprite_sheet_cache["path"] = sprite_path
                            sheet = sprite_sheet_cache["image"]
                            tile_w = sheet.width // SPRITE_COLUMNS
                            tile_h = sheet.height // SPRITE_ROWS
                            sprite_sheet_cache["tile_size"] = (tile_w, tile_h)

                        sprite_sheet = sprite_sheet_cache["image"]
                        tile_w, tile_h = sprite_sheet_cache["tile_size"]
                        if tile_w <= 0 or tile_h <= 0:
                            raise ValueError(f"Invalid sprite sheet tile size for {sprite_path}")

                        x = col * tile_w
                        y = row * tile_h
                        
                        # Extract the sprite
                        sprite = sprite_sheet.crop((x, y, x + tile_w, y + tile_h))
                        
                        # Resize to desired size
                        sprite = sprite.resize((size, size), Image.Resampling.LANCZOS)
                        
                        # Convert to PhotoImage for tkinter
                        photo = ImageTk.PhotoImage(sprite)
                        icon_label.config(image=photo)
                        icon_label.image = photo  # Keep reference
                        return icon_label
            except Exception as e:
                print(f"Error loading icon for {item_name}: {e}")
        
        # Fallback: show colored square with first letter
        fallback = item_name[:1].upper() or "?"
        color = accent if accent.startswith('#') else '#5f86a8'
        
        # Create a small canvas for the fallback
        canvas = tk.Canvas(icon_label, width=size, height=size, highlightthickness=0)
        canvas.pack()
        canvas.create_rectangle(0, 0, size, size, fill=color, outline=color)
        canvas.create_text(size//2, size//2, text=fallback, 
                          fill='white', font=("Arial", 10, "bold"))
        
        return icon_label
    
    try:
        with open(os.path.join(base, 'HTML', 'Images', 'Ships', 'ShipMap.json'), 'r') as sf:
            ship_entries = json.load(sf)
            valid_hulls = [entry['key'] for entry in ship_entries]
            valid_hull_keys = {
                str(hull).strip().casefold()
                for hull in valid_hulls
                if str(hull).strip()
            }
            valid_planet_classes = sorted(
                [
                    str(entry.get('key')).strip()
                    for entry in ship_entries
                    if (
                        isinstance(entry, dict)
                        and str(entry.get('key', '')).strip()
                        and 'planet' in _normalize_roles(entry)
                    )
                ],
                key=str.casefold
            )
            # Extract unique sides from ShipMap as a fallback only
            ship_sides = sorted(
                {
                    entry.get('side', '')
                    for entry in ship_entries
                    if isinstance(entry, dict) and entry.get('side')
                },
                key=str.casefold
            )
            # Map hull key -> (BRange, DRange); default to 0 if not present
            hull_ranges = {
                entry.get('key'): (
                    entry.get('BRange', 0) or 0,
                    entry.get('DRange', 0) or 0
                )
                for entry in ship_entries if isinstance(entry, dict)
            }
            # Map hull key -> side string; default '' if not present
            hull_side_map = {
                entry.get('key'): entry.get('side', '') or ''
                for entry in ship_entries if isinstance(entry, dict)
            }
            # Map hull key -> role (e.g., 'station', 'static')
            hull_role_map = {
                entry.get('key'): (entry.get('role', '') or '').lower()
                for entry in ship_entries if isinstance(entry, dict)
            }
            # Map hull key -> category/tags set (e.g., contains 'defence' or 'industrial' if present)
            hull_category_map = {}
            for entry in ship_entries:
                if not isinstance(entry, dict):
                    continue
                key = entry.get('key')
                cats = set()
                # try several common fields that may describe categories/tags
                for fld in ('categories', 'tags', 'roleTags', 'roles'):
                    v = entry.get(fld, [])
                    if isinstance(v, str):
                        if fld == 'roles':
                            cats.update(r.strip().lower() for r in v.split(',') if r.strip())
                        else:
                            cats.add(v.strip().lower())
                    elif isinstance(v, list):
                        cats.update(str(x).strip().lower() for x in v)
                # single-value hints
                for fld in ('role_detail', 'subrole', 'function'):
                    v = entry.get(fld)
                    if isinstance(v, str) and v.strip():
                        cats.add(v.strip().lower())
                hull_category_map[key] = cats
    except Exception:
        ship_entries = []
        valid_hulls = []
        valid_hull_keys = set()
        valid_planet_classes = [DEFAULT_PLANET_CLASS]
        ship_sides = []
        hull_ranges = {}
        hull_side_map = {}
        hull_role_map = {}
        hull_category_map = {}
    if not valid_planet_classes:
        valid_planet_classes = [DEFAULT_PLANET_CLASS]

    # ── Valid factions/races: prefer Settings.json; fallback to cargo_teams.json or ShipMap.json ──
    settings_factions = editor_settings.get('Factions', []) if isinstance(editor_settings, dict) else []
    factions = settings_factions or (ct_config.get('Factions', []) or [])
    valid_factions = sorted(factions, key=str.casefold) if factions else []
    settings_races = editor_settings.get('Races') if isinstance(editor_settings, dict) else None
    races_map = settings_races if isinstance(settings_races, dict) else (ct_config.get('Races') or {}) if isinstance(ct_config, dict) else {}
    valid_races = sorted(list(races_map.keys()), key=str.casefold) if races_map else []
    # Fallback to ShipMap.json sides if Settings/cargo_teams are missing/empty.
    if not valid_races and ship_sides:
        valid_races = list(ship_sides)
    valid_sides = list(valid_races)
    # For Alignment specifically, allow either a Faction or any Race name
    valid_alignments = sorted(set(valid_factions) | set(valid_races), key=str.casefold)

    faction_name_by_cf = {str(f).casefold(): str(f) for f in valid_factions}
    race_to_faction_cf = {
        str(race).casefold(): str(info.get('Faction', '')).casefold()
        for race, info in (races_map or {}).items()
        if isinstance(info, dict)
    }

    def _races_for_faction(faction_val: str) -> List[str]:
        if not faction_val:
            return list(valid_races)
        f_cf = str(faction_val).casefold()
        matches = [
            str(race) for race, info in (races_map or {}).items()
            if isinstance(info, dict) and str(info.get('Faction', '')).casefold() == f_cf
        ]
        return sorted(matches, key=str.casefold)

    def _init_faction_for_side(side_val: str) -> str:
        fac_cf = race_to_faction_cf.get(str(side_val).casefold(), '')
        return faction_name_by_cf.get(fac_cf, '')

    def _build_faction_side_controls(parent, obj, *, layout: str = 'pack', row: int = 1):
        side_val = ''
        sides = obj.get('sides')
        if isinstance(sides, list) and sides:
            side_val = str(sides[0])
        side_var = tk.StringVar(value=side_val)
        faction_var = tk.StringVar(value=_init_faction_for_side(side_val))

        if layout == 'grid':
            tk.Label(parent, text="Faction:").grid(row=row, column=0, sticky='w')
            faction_cb = ttk.Combobox(parent, textvariable=faction_var,
                                      values=valid_factions, state='readonly')
            faction_cb.grid(row=row, column=1, padx=5, pady=2, sticky='w')
            tk.Label(parent, text="Side:").grid(row=row + 1, column=0, sticky='w')
            side_cb = ttk.Combobox(parent, textvariable=side_var,
                                   values=valid_races, state='readonly')
            side_cb.grid(row=row + 1, column=1, padx=5, pady=2, sticky='w')
        else:
            tk.Label(parent, text="Faction:").pack(anchor='w', pady=2)
            faction_cb = ttk.Combobox(parent, textvariable=faction_var,
                                      values=valid_factions, state='readonly')
            faction_cb.pack(anchor='w', pady=2)
            tk.Label(parent, text="Side:").pack(anchor='w', pady=2)
            side_cb = ttk.Combobox(parent, textvariable=side_var,
                                   values=valid_races, state='readonly')
            side_cb.pack(anchor='w', pady=2)

        def _update_side_values_from_faction(*_):
            vals = _races_for_faction(faction_var.get())
            current = side_var.get().strip()
            if current and current not in vals:
                vals = [current] + vals
            side_cb['values'] = vals

        def _update_faction_from_side(*_):
            side_cf = side_var.get().strip().casefold()
            fac_cf = race_to_faction_cf.get(side_cf, '')
            fac_display = faction_name_by_cf.get(fac_cf, '')
            if fac_display and faction_var.get() != fac_display:
                faction_var.set(fac_display)

        def _on_side_change(*_):
            obj.__setitem__('sides', [side_var.get()])
            _update_faction_from_side()

        side_var.trace_add('write', _on_side_change)
        faction_var.trace_add('write', _update_side_values_from_faction)
        _update_side_values_from_faction()
        return side_var, faction_var, side_cb
    # initialize system map
    
    try:
        sm = SystemMap(file_path)
        # Required silent main-game compatibility migration; keep on load.
        sm.migrate_names()
        migrate_legacy_structure(sm)
        # Do NOT push an initial undo state here; we only mark undo after the first real edit.

        # ── Silent side fixes + validation for stations/platforms/static ─────────────
        def validate_and_fix_sides_on_load(_sm):
            issues = migrate_sides(_sm, valid_sides)
            if issues:
                messagebox.showwarning("Side Validation", "Objects with invalid side values:\n\n" + "\n".join(issues))

        def validate_and_fix_planet_classes_on_load(_sm):
            issues = migrate_planet_classes(_sm, valid_planet_classes)
            if issues:
                messagebox.showwarning("Planet Class Validation", "Planets with invalid class values:\n\n" + "\n".join(issues))

        validate_and_fix_planet_classes_on_load(sm)
        validate_and_fix_sides_on_load(sm)
        system_files, other_gate_index = build_gate_index_for_systems(data_base, filename)

    except Exception as e:
        messagebox.showerror("Error", f"Failed to load system map: {e}")
        return None

    gate_origins = {name: name for name, obj in sm.data.get('objects', {}).items() if is_gate(obj)}

    def history_snapshot():
        return copy.deepcopy((sm.data, gate_origins))

    def push_undo():
        if sm is None:
            return
        undo_stack.append(history_snapshot())
        # cap at 10
        if len(undo_stack) > 10:
            undo_stack.pop(0)
        # any new action invalidates redo history
        redo_stack.clear()

    win = tk.Toplevel()

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
    # Alignment dropdown with custom entry enabled — can be any Faction or Race
    align_var = tk.StringVar(value=sm.get_alignment() or '')
    align_cb = ttk.Combobox(md_parent, textvariable=align_var, values=valid_alignments, state='normal')
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
    skybox_var.trace_add('write', lambda *a: sm.data.setdefault('metadata', {}).__setitem__('skybox', skybox_var.get()))
  # Skybox preview (100×100px)
    preview_label = tk.Label(md_parent)


    row += 1

    #tk.Label(md_parent, text="Description:").grid(row=row, column=0, sticky='nw')

    tk.Label(md_parent, text="Description:").grid(row=row, column=0, sticky='nw')
    desc_text = tk.Text(md_parent, height=5, width=60)
    desc_text.insert('1.0', sm.get_description())
    desc_text.grid(row=row, column=1, columnspan=4, sticky='w')
    register_text_widget(desc_text, lambda value: sm.set_description(value))
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

    # ── Author & Revision Metadata ──────────────────────────────────────
    tk.Label(md_parent, text="Author (current):").grid(row=row, column=0, sticky='w')
    author_var = tk.StringVar(value=str(editor_settings.get('author', '') or ''))
    author_entry = tk.Entry(md_parent, textvariable=author_var, width=30)
    author_entry.grid(row=row, column=1, columnspan=2, sticky='w')

    def persist_author_setting(*_):
        editor_settings['author'] = author_var.get().strip()
        save_editor_settings(editor_settings)

    if not author_var.get().strip():
        entered = prompt_for_author(win, editor_settings)
        if entered is not None:
            author_var.set(entered.strip())

    author_entry.bind('<FocusOut>', persist_author_setting)
    author_entry.bind('<Return>', persist_author_setting)
    row += 1

    orig_author_var = tk.StringVar()
    last_author_var = tk.StringVar()
    rev_num_var = tk.StringVar()
    rev_date_var = tk.StringVar()
    all_authors_var = tk.StringVar()

    def refresh_author_metadata_display(metadata: Optional[Dict[str, Any]] = None):
        data = metadata if isinstance(metadata, dict) else sm.data.get('metadata', {})
        orig_author_var.set(str(data.get('original_author', '') or ''))
        last_author_var.set(str(data.get('last_revision_author', data.get('last_author', '')) or ''))
        rev_num_var.set(str(_coerce_revision_number(data.get('revision_number', 0))))
        rev_date_var.set(str(data.get('revision_date', '') or ''))
        all_authors_var.set(", ".join(_normalize_author_list(data.get('all_authors'))))

    tk.Label(md_parent, text="Original Author:").grid(row=row, column=0, sticky='w')
    ttk.Entry(md_parent, textvariable=orig_author_var, state='readonly', width=28)\
        .grid(row=row, column=1, columnspan=2, sticky='w', padx=(0, 5))
    tk.Label(md_parent, text="Last Revision Author:").grid(row=row, column=3, sticky='w')
    ttk.Entry(md_parent, textvariable=last_author_var, state='readonly', width=28)\
        .grid(row=row, column=4, columnspan=2, sticky='w')
    row += 1

    tk.Label(md_parent, text="Revision #:").grid(row=row, column=0, sticky='w')
    ttk.Entry(md_parent, textvariable=rev_num_var, state='readonly', width=8)\
        .grid(row=row, column=1, sticky='w')
    tk.Label(md_parent, text="Revision Date:").grid(row=row, column=3, sticky='w')
    ttk.Entry(md_parent, textvariable=rev_date_var, state='readonly', width=16)\
        .grid(row=row, column=4, columnspan=2, sticky='w')
    row += 1

    tk.Label(md_parent, text="All Authors:").grid(row=row, column=0, sticky='nw')
    ttk.Entry(md_parent, textvariable=all_authors_var, state='readonly', width=60)\
        .grid(row=row, column=1, columnspan=6, sticky='w')
    refresh_author_metadata_display(md)
    row += 1


    # ── Traffic controls: Commercial, Civilian, Security ────────────────
    traffic = sm.data.setdefault('traffic', {})
    levels = smopts.TRAFFIC_LEVELS
    traffic_vars = {}
    # now inside the System Details pane
    tk.Label(md_parent, text="Traffic:") \
        .grid(row=row, column=0, sticky='e', pady=(1, 0))

    for i, cat in enumerate(('commercial', 'civilian', 'security')):
        tk.Label(md_parent, text=f"{cat.capitalize()}:") \
            .grid(row=row, column=1 + i , sticky='e', padx=(1, 0))
        var = tk.StringVar(value=traffic.get(cat, 'none'))
        traffic_vars[cat] = var
        cb = ttk.Combobox(
            md_parent,
            textvariable = var,
            values = levels,
            state = 'readonly',
            width = 8
        )
        cb.grid(row=row, column=2 + i , sticky='w', pady=(5, 2))
        var.trace_add(
            'write', lambda *a, c=cat, v=var: sm.data.setdefault('traffic', {}).__setitem__(c, v.get())
        )
    row += 1

    # ── System intel & development ─────────────────────────────────────
    intel = md.get('intel', {})
    if not isinstance(intel, dict):
        intel = {}
    sec_val = md.get('security', 'Neutral')
    if sec_val not in smopts.SECURITY_LEVELS:
        sec_val = 'Neutral'
    pirate_val = intel.get('pirate', 'Low')
    if pirate_val not in smopts.PIRATE_LEVELS:
        pirate_val = 'Low'
    enemy_val = intel.get('enemy', 'Low')
    if enemy_val not in smopts.ENEMY_LEVELS:
        enemy_val = 'Low'
    dev_val = md.get('development', 'Unclaimed')
    if dev_val not in smopts.DEVELOPMENT_STAGES:
        dev_val = 'Unclaimed'

    dd_frame = tk.Frame(md_parent)
    dd_frame.grid(row=row, column=0, columnspan=8, sticky='w', pady=(4, 2))
    tk.Label(dd_frame, text="Security Level:").grid(row=0, column=0, sticky='w')
    sec_var = tk.StringVar(value=sec_val)
    sec_cb = ttk.Combobox(
        dd_frame, textvariable=sec_var,
        values=smopts.SECURITY_LEVELS, state='readonly', width=10
    )
    sec_cb.grid(row=0, column=1, sticky='w', padx=5)
    tk.Label(dd_frame, text="Pirate Activity:").grid(row=0, column=2, sticky='w')
    pirate_var = tk.StringVar(value=pirate_val)
    pirate_cb = ttk.Combobox(
        dd_frame, textvariable=pirate_var,
        values=smopts.PIRATE_LEVELS, state='readonly', width=8
    )
    pirate_cb.grid(row=0, column=3, sticky='w', padx=5)
    tk.Label(dd_frame, text="Enemy Strength:").grid(row=0, column=4, sticky='w')
    enemy_var = tk.StringVar(value=enemy_val)
    enemy_cb = ttk.Combobox(
        dd_frame, textvariable=enemy_var,
        values=smopts.ENEMY_LEVELS, state='readonly', width=8
    )
    enemy_cb.grid(row=0, column=5, sticky='w', padx=5)
    tk.Label(dd_frame, text="Development Stage:").grid(row=0, column=6, sticky='w')
    dev_var = tk.StringVar(value=dev_val)
    dev_cb = ttk.Combobox(
        dd_frame, textvariable=dev_var,
        values=smopts.DEVELOPMENT_STAGES, state='readonly', width=18
    )
    dev_cb.grid(row=0, column=7, sticky='w', padx=5)
    row += 1

    # Strategic Assets
    assets_frame = tk.Frame(md_parent)
    assets_frame.grid(row=row, column=0, columnspan=8, sticky='w', pady=(2, 0))
    tk.Label(assets_frame, text="Strategic Assets:").grid(row=0, column=0, sticky='w')
    assets_vars = {}
    assets_current = set(intel.get('assets', []) or [])
    for i, opt in enumerate(smopts.ASSET_OPTIONS):
        var = tk.BooleanVar(value=opt in assets_current)
        cb = tk.Checkbutton(assets_frame, text=opt, variable=var)
        cb.grid(row=0, column=i + 1, sticky='w', padx=5)
        assets_vars[opt] = var
    row += 1

    # Exports
    tk.Label(md_parent, text="Exports:").grid(row=row, column=0, sticky='nw', pady=(2, 0))
    export_vars = {}
    exports_frame = tk.Frame(md_parent)
    exports_frame.grid(row=row, column=1, columnspan=7, sticky='w')
    exports_current = set(md.get('exports', []) or [])
    for idx, val in enumerate(smopts.EXPORT_OPTIONS):
        var = tk.BooleanVar(value=val in exports_current)
        cb = tk.Checkbutton(exports_frame, text=val, variable=var)
        cb.grid(row=idx // 4, column=idx % 4, sticky='w', padx=5, pady=2)
        export_vars[val] = var
    row += 1

    # Primary Focus
    tk.Label(md_parent, text="Primary Focus:").grid(row=row, column=0, sticky='w', pady=(2, 0))
    focus_var = tk.StringVar(value=md.get('focus', ''))
    focus_cb = ttk.Combobox(
        md_parent, textvariable=focus_var,
        values=smopts.FOCUS_OPTIONS, state='normal', width=28
    )
    focus_cb.grid(row=row, column=1, columnspan=3, sticky='w')
    row += 1

    # Display on Galactic Map
    tk.Label(md_parent, text="Display on Galactic Map:").grid(row=row, column=0, sticky='w', pady=(2, 0))
    vis_var = tk.StringVar(value="Show" if md.get('visible', True) else "Hide")
    vis_frame = tk.Frame(md_parent)
    vis_frame.grid(row=row, column=1, columnspan=4, sticky='w')
    tk.Radiobutton(
        vis_frame, text="Show System on Galactic Map",
        variable=vis_var, value="Show"
    ).grid(row=0, column=0, sticky='w', padx=5)
    tk.Radiobutton(
        vis_frame, text="Hide System on Galactic Map",
        variable=vis_var, value="Hide"
    ).grid(row=0, column=1, sticky='w', padx=5)
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

    # Ordering helper: sort A–Z before 0–9, case-insensitive

    # Find stations that have cargo/team validation errors
    def _stations_with_cargo_errors():
        cargo_set = set(ct_config.get('cargo', []))
        team_set  = set(ct_config.get('teams', []))
        bad = set()
        if not (cargo_set or team_set):
            return bad
        for obj_name in sm.list_objects():
            obj = sm.get_object(obj_name)
            if obj.get('type', '').lower() != 'station':
                continue
            carg = obj.get('cargo') or {}
            tms  = obj.get('teams') or {}
            for item, qty in carg.items():
                if (item in team_set) or (item not in cargo_set) or (not isinstance(qty, int)) or (qty < 0):
                    bad.add(obj_name); break
            if obj_name in bad:
                continue
            for item, qty in tms.items():
                if (item in cargo_set) or (item not in team_set) or (not isinstance(qty, int)) or (qty < 0):
                    bad.add(obj_name); break
        return bad

    # Ordering helper: sort A–Z before 0–9, case-insensitive
    def _az09_key(name: str):
        if name is None:
            return (1, "")
        s = str(name)
        return (1 if (s[:1].isdigit()) else 0, s.casefold())
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

    # We’ll populate the Objects list dynamically so we can bubble up
    # stations with cargo errors and color them red.
    objs = []  # will be filled by refresh_objects_list()
    obj_lb = make_list("Objects:", objs, 0, lambda name: name, parent=elems_frame)

    def refresh_objects_list():
        """Rebuild the Objects list with stations that have cargo errors at the top (in red)."""
        nonlocal objs
        err_stations = _stations_with_cargo_errors()
        all_objs = list(sm.list_objects())
        top  = sorted([n for n in all_objs if n in err_stations], key=_az09_key)
        rest = sorted([n for n in all_objs if n not in err_stations], key=_az09_key)
        # IMPORTANT: mutate the existing list so any closures keep seeing updates
        objs[:] = top + rest
        obj_lb.delete(0, tk.END)
        for name in objs:
            obj_lb.insert(tk.END, name)
        # color/embolden error stations
        for idx, name in enumerate(objs):
            if name in err_stations:
                try:
                    obj_lb.itemconfig(idx, fg='red', font=('Arial', 9, 'bold'))
                except Exception:
                    # itemconfig might not support font on some Tk variants; ensure at least red
                    obj_lb.itemconfig(idx, fg='red')

    # initial populate
    refresh_objects_list()
    obj_lb.selection_clear(0, tk.END)

    obj_lb.bind('<<ListboxSelect>>', lambda e: show_object(objs[obj_lb.curselection()[0]]) if obj_lb.curselection() else None)
    # Relays list between Objects and Terrain
    relay_order = sorted(list(sm.list_sensor_relays().keys()), key=_az09_key)
    relay_lb = make_list("Relays:", relay_order, 1, lambda r: r, parent=elems_frame)
    relay_lb.bind('<<ListboxSelect>>', lambda e: show_relay(relay_order[relay_lb.curselection()[0]]) if relay_lb.curselection() else None)
    # Define terrain list keys
    terrain_keys = sorted(sm.list_terrain(), key=_az09_key)
    # Terrain list()
    ter_lb = make_list("Terrain:", terrain_keys, 2, lambda k: k, parent=elems_frame)  # column 4 for even spacing
    # Bind terrain list selection to display details
    ter_lb.bind('<<ListboxSelect>>', lambda e: show_terrain(terrain_keys[ter_lb.curselection()[0]]) if ter_lb.curselection() else None)

    coord_label_var = tk.StringVar(value="Coordinates (X,Y,Z):")
    coord_val_var = tk.StringVar(value="")
    coord_frame = tk.Frame(elems_frame)
    coord_frame.grid(row=row + 2, column=0, columnspan=3, sticky='w', padx=10, pady=(2, 0))
    tk.Label(coord_frame, textvariable=coord_label_var).pack(side='left')
    coord_entry = tk.Entry(coord_frame, textvariable=coord_val_var, width=40, state='readonly')
    coord_entry.pack(side='left', padx=4)

    def copy_coords():
        val = coord_val_var.get()
        if not val:
            win.bell()
            return
        win.clipboard_clear()
        win.clipboard_append(val)

    tk.Button(coord_frame, text="Copy", command=copy_coords).pack(side='left')

    def _format_coord_value(val):
        try:
            fval = float(val)
        except Exception:
            return str(val)
        if fval.is_integer():
            return str(int(fval))
        return f"{fval:.2f}".rstrip('0').rstrip('.')

    def update_coord_display(coord, is_center=False):
        label = "Center (X,Y,Z):" if is_center else "Coordinates (X,Y,Z):"
        coord_label_var.set(label)
        if not isinstance(coord, (list, tuple)) or len(coord) < 3:
            coord_val_var.set("")
            return
        coord_val_var.set(
            f"{_format_coord_value(coord[0])}, {_format_coord_value(coord[1])}, {_format_coord_value(coord[2])}"
        )

    # move past the two rows used by each list (label + listbox)
    row += 2

    overview_refreshers = {}

    def refresh_overviews():
        for refresh in list(overview_refreshers.values()):
            refresh()

    def _refresh_ui():
        obj_names = sm.list_objects()
        objs.clear()
        objs.extend(obj_names)
        obj_lb.delete(0, tk.END)
        for n in obj_names:
            obj_lb.insert(tk.END, n)
        relay_names = list(sm.list_sensor_relays().keys())
        relay_order.clear()
        relay_order.extend(relay_names)
        relay_lb.delete(0, tk.END)
        for r in relay_names:
            relay_lb.insert(tk.END, r)
        terrain_names = sm.list_terrain()
        terrain_keys.clear()
        terrain_keys.extend(terrain_names)
        ter_lb.delete(0, tk.END)
        for t in terrain_names:
            ter_lb.insert(tk.END, t)
        clear_edit_pane()
        draw_map(ctx)
        drag_data.clear()
        current_selection['type'] = None
        current_selection['name'] = None
        refresh_overviews()

    def do_undo():
        if not undo_stack:
            win.bell()
            return
        redo_stack.append(history_snapshot())
        sm.data, origins = undo_stack.pop()
        gate_origins.clear()
        gate_origins.update(origins)
        _refresh_ui()

    def do_redo():
        if not redo_stack:
            win.bell()
            return
        undo_stack.append(history_snapshot())
        sm.data, origins = redo_stack.pop()
        gate_origins.clear()
        gate_origins.update(origins)
        _refresh_ui()

    def bind_history_shortcuts(window):
        # Precede widget class bindings: Ctrl+X must not also cut text.
        tag = f"SystemHistory{window}"
        def invoke(action):
            flush_pending_text_widgets()
            action()
            return 'break'
        for sequence, action in (('<Control-z>', do_undo), ('<Control-x>', do_redo)):
            window.bind_class(tag, sequence, lambda event, fn=action: invoke(fn))
        def attach(widget):
            tags = widget.bindtags()
            if tag not in tags:
                widget.bindtags((tag,) + tags)
            for child in widget.winfo_children():
                if child.winfo_toplevel() == window:
                    attach(child)
        window.bind('<Map>', lambda event: attach(event.widget), add='+')
        attach(window)

    bind_history_shortcuts(win)

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

    def clear_edit_pane():
        # before destroying widgets, commit any pending description safely
        nonlocal last_desc_widget, last_desc_obj
        flush_pending_text_widgets()
        last_desc_widget = None
        last_desc_obj = None
        # now clear the pane

        if not edit_frame.winfo_exists():
            return
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
        Generic item display.
        Optional field elements:
        - 4th element: widget type ('text', 'check', 'combo')
        - 5th element: widget options for combo fields
        """
        clear_edit_pane()
        edit_title.config(text=f"{kind}: {key}")
        for field in fields:
            label_text, getter, setter = field[0], field[1], field[2]
            widget_type = field[3] if len(field) >= 4 else 'entry'
            widget_options = field[4] if len(field) >= 5 else []
            if widget_type == 'text':
                # multiline description
                tk.Label(edit_frame, text=label_text, wraplength=230, justify='left')\
                    .pack(anchor='w', pady=2)
                txt = tk.Text(edit_frame, height=4, width=30)
                txt.insert('1.0', getter())
                txt.pack(anchor='w', pady=2)
                register_text_widget(txt, setter)
            elif widget_type == 'combo':
                tk.Label(edit_frame, text=label_text, wraplength=230, justify='left')\
                    .pack(anchor='w', pady=2)
                initial = str(getter())
                values = list(widget_options or [])
                if initial and initial not in values:
                    values.append(initial)
                var = tk.StringVar(value=initial)
                cb = ttk.Combobox(edit_frame, textvariable=var, values=values, state='readonly')
                cb.pack(anchor='w', pady=2)
                var.trace_add('write', lambda *a, s=setter, v=var: s(v.get()))
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

    def set_selection(item_type, name):
        current_selection['type'] = item_type
        current_selection['name'] = name
    
    def on_delete_key(event=None):
        if event is not None:
            try:
                if event.widget.winfo_toplevel() != win:
                    return
            except Exception:
                return
            # Preserve the normal Delete-key behaviour while editing text or
            # choosing a combobox value. Map-item deletion is intended for the
            # lists, canvas, and other non-editable editor controls.
            if isinstance(event.widget, (tk.Entry, tk.Text, tk.Spinbox, ttk.Entry, ttk.Combobox)):
                return
        t = current_selection['type']
        n = current_selection['name']
        if not t or not n:
            return
        if t == 'object' and n in sm.data.get('objects', {}):
            delete_object(n)
        elif t == 'relay' and n in sm.data.get('sensor_relay', {}):
            delete_relay(n)
        elif t == 'terrain' and n in sm.data.get('terrain', {}):
            delete_terrain(n)
        else:
            return
        return 'break'
    win.bind('<Delete>', on_delete_key)

    # Utility delete functions for objects, relays, and terrain
    def delete_object(obj_name):
        push_undo()
        idx = objs.index(obj_name)
        remove_incoming_only_gate(sm.data, obj_name)
        del sm.data['objects'][obj_name]
        gate_origins.pop(obj_name, None)
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
            win.bell()
            return
        if new_name != name:
            if any(other != name and other.casefold() == new_name.casefold() for other in sm.data['objects']):
                messagebox.showerror("Rename Object", "An object with that name already exists.", parent=win)
                return
            flush_pending_text_widgets()
            renamed_data = copy.deepcopy(sm.data)
            obj = renamed_data['objects'].pop(name)
            renamed_data['objects'][new_name] = obj
            try:
                if is_gate(obj):
                    rewrite_gate_references(renamed_data, Path(file_path).stem, {name: new_name})
                rename_incoming_only_gate(renamed_data, name, new_name)
            except ValueError as exc:
                messagebox.showerror("Rename Object", str(exc), parent=win)
                return
            push_undo()
            sm.data = renamed_data
            if name in gate_origins:
                gate_origins[new_name] = gate_origins.pop(name)
            idx = objs.index(name)
            objs[idx] = new_name
            obj_lb.delete(idx)
            obj_lb.insert(idx, new_name)
            clear_edit_pane()
            draw_map(ctx)
            show_object(new_name)
            refresh_overviews()

    def rename_relay(name):
        new_name = simpledialog.askstring("Rename Relay","New name:", initialvalue=name)
        if not new_name:
            return
        if not _VALID_NAME.match(new_name):
            win.bell()
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
            win.bell()
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

    def open_cargo_teams_dialog(obj_name):
        obj = sm.get_object(obj_name)
        dlg = tk.Toplevel(win)
        dlg.title(f"Configure Cargo & Teams: {obj_name}")
        dlg.grab_set()

        # --- Presets loaded from cargo_teams.json ---
        presets = ct_config.setdefault('presets', {})
        if not isinstance(presets, dict):
            presets = {}
            ct_config['presets'] = presets
        preset_names = ["Custom"] + list(presets.keys())
        preset_var = tk.StringVar(value="Custom")
        tk.Label(dlg, text="Preset:").grid(row=0, column=0, padx=5, pady=5, sticky='w')
        preset_cb = ttk.Combobox(dlg, textvariable=preset_var,
                                 values=preset_names, state='readonly')
        preset_cb.grid(row=0, column=1, padx=5, pady=5, sticky='w')

        # --- Randomize Button ---
        tk.Button(dlg, text="Randomize ņ10%",
                  command=lambda: randomize()).grid(row=0, column=2, padx=5)

        # --- Items Table ---
        table = tk.Frame(dlg)
        table.grid(row=1, column=0, columnspan=4, padx=5, pady=5, sticky='nsew')
        tk.Label(table, text="Icon").grid(row=0, column=0, padx=5, pady=2)
        tk.Label(table, text="Item").grid(row=0, column=1, padx=5, pady=2)
        tk.Label(table, text="Quantity").grid(row=0, column=2, padx=5, pady=2)

        cargo_keys = set(ct_config.get('cargo', []))
        team_keys = set(ct_config.get('teams', []))

        def item_category(item_name):
            if item_name in team_keys:
                return "team"
            if item_name in USABLE_DEPLOYABLE_ITEMS:
                return "usable_deployable"
            if item_name in INTEL_SPECIAL_ITEMS:
                return "intel_special"
            category = item_meta.get(item_name, {}).get("category")
            if category in CARGO_ITEM_CATEGORY_RANK:
                return category
            return "commodity"

        def item_sort_key(item_name):
            category = item_category(item_name)
            return (CARGO_ITEM_CATEGORY_RANK.get(category, 99), item_name.casefold())

        valid_items = sorted(cargo_keys | team_keys, key=item_sort_key)
        rows = []

        def refresh_dropdowns():
            """Rebuild each row's combobox values to exclude selections in other rows."""
            # Collect all selected item names (non-blank)
            selected = [e['iv'].get().strip() for e in rows if e['iv'].get().strip()]
            for e in rows:
                curr = e['iv'].get().strip()
                # Allow blank plus any item not chosen by other rows (or this row's current)
                vals = [''] + [it for it in valid_items if it not in selected or it == curr]
                e['cb'].set_values(vals)
        def remove_row(idx):
            """Remove row at index `idx` and re-grid the rest."""
            entry = rows.pop(idx)
            # destroy widgets for this row
            for w in (entry['icon'], entry['cb'], entry['sb'], entry['btn']):
                w.destroy()
            # re-grid subsequent rows
            for j, e in enumerate(rows):
                rn = j + 1
                e['icon'].grid_configure(row=rn)
                e['cb'].grid_configure(row=rn)
                e['sb'].grid_configure(row=rn)
                e['btn'].grid_configure(row=rn)
            # ensure there's always one blank row available
            if not rows or rows[-1]['iv'].get().strip():
                add_row()
            # and re-filter all dropdowns
            refresh_dropdowns()
                
        def add_row(item="", qty=0):
            r = len(rows) + 1
            iv = tk.StringVar(value=item)
            qv = tk.IntVar(value=qty)
            
            # Icon label
            icon_label = create_icon_label(table, item)
            icon_label.grid(row=r, column=0, padx=2, pady=2)
            
            # Item dropdown
            cb = CategorizedItemDropdown(table, iv, item_category)
            cb.set_values(valid_items)
            cb.grid(row=r, column=1, padx=5, pady=2, sticky='w')
            # Quantity spinner
            sb = tk.Spinbox(table, from_=0, to=99999,
                            textvariable=qv, width=6)
            sb.grid(row=r, column=2, padx=5, pady=2, sticky='w')
            # Remove button
            def _remove_this():
                remove_row(rows.index(entry))
            btn = tk.Button(table, text='X', command=_remove_this, width=2)
            btn.grid(row=r, column=3, padx=5, pady=2, sticky='w')
            # Track this row's widgets and vars
            entry = {'iv': iv, 'qv': qv, 'cb': cb, 'sb': sb, 'btn': btn, 'icon': icon_label}
            rows.append(entry)

            # when last blank row gets a value, append another blank
            def on_change(*_):
                # Update icon when item changes
                selected_item = iv.get().strip()
                # Remove old icon and create new one
                entry['icon'].destroy()
                entry['icon'] = create_icon_label(table, selected_item)
                try:
                    row_number = rows.index(entry) + 1
                except ValueError:
                    row_number = r
                entry['icon'].grid(row=row_number, column=0, padx=2, pady=2)
                
                # if this was the last blank row, add another
                if rows and rows[-1]['iv'] is iv and iv.get().strip():
                    add_row()
                # enforce uniqueness immediately
                refresh_dropdowns()
            iv.trace_add('write', on_change)

        def refresh_preset_selector(select_name=None):
            names = ["Custom"] + list(presets.keys())
            preset_cb['values'] = names
            if select_name and select_name in presets:
                preset_var.set(select_name)
            elif preset_var.get() not in names:
                preset_var.set("Custom")

        def save_cargo_team_config():
            try:
                atomic_write_json(os.path.join(base, 'cargo_teams.json'), ct_config)
                return True
            except Exception as exc:
                messagebox.showerror(
                    "Preset Editor",
                    f"Could not save cargo_teams.json:\n{exc}",
                    parent=dlg
                )
                return False

        def open_preset_editor():
            editor = tk.Toplevel(dlg)
            editor.title("Edit Cargo/Teams Presets")
            editor.transient(dlg)
            editor.grab_set()

            current = {'name': None}
            preset_rows = []

            left = tk.Frame(editor)
            left.grid(row=0, column=0, rowspan=3, sticky='ns', padx=6, pady=6)
            right = tk.Frame(editor)
            right.grid(row=0, column=1, sticky='nsew', padx=6, pady=6)
            buttons = tk.Frame(editor)
            buttons.grid(row=2, column=1, sticky='e', padx=6, pady=6)
            editor.grid_columnconfigure(1, weight=1)
            editor.grid_rowconfigure(0, weight=1)

            tk.Label(left, text="Presets").pack(anchor='w')
            preset_list_frame = tk.Frame(left)
            preset_list_frame.pack(fill='both', expand=True)
            preset_scroll = tk.Scrollbar(preset_list_frame, orient='vertical')
            preset_lb = tk.Listbox(
                preset_list_frame,
                height=14,
                width=24,
                exportselection=False,
                yscrollcommand=preset_scroll.set
            )
            preset_scroll.config(command=preset_lb.yview)
            preset_lb.pack(side='left', fill='both', expand=True)
            preset_scroll.pack(side='right', fill='y')

            name_var = tk.StringVar()
            tk.Label(right, text="Preset Name:").grid(row=0, column=0, sticky='w', padx=2, pady=2)
            tk.Entry(right, textvariable=name_var, width=32).grid(row=0, column=1, sticky='w', padx=2, pady=2)

            preset_table = tk.Frame(right)
            preset_table.grid(row=1, column=0, columnspan=3, sticky='nsew', pady=(6, 0))
            right.grid_rowconfigure(1, weight=1)
            right.grid_columnconfigure(1, weight=1)

            def build_preset_headers():
                tk.Label(preset_table, text="Icon").grid(row=0, column=0, padx=5, pady=2)
                tk.Label(preset_table, text="Item").grid(row=0, column=1, padx=5, pady=2)
                tk.Label(preset_table, text="Quantity").grid(row=0, column=2, padx=5, pady=2)

            def refresh_preset_dropdowns():
                selected = [e['iv'].get().strip() for e in preset_rows if e['iv'].get().strip()]
                for e in preset_rows:
                    curr = e['iv'].get().strip()
                    vals = [''] + [it for it in valid_items if it not in selected or it == curr]
                    e['cb'].set_values(vals)

            def remove_preset_row(idx):
                entry = preset_rows.pop(idx)
                for w in (entry['icon'], entry['cb'], entry['sb'], entry['btn']):
                    w.destroy()
                for j, e in enumerate(preset_rows):
                    rn = j + 1
                    e['icon'].grid_configure(row=rn)
                    e['cb'].grid_configure(row=rn)
                    e['sb'].grid_configure(row=rn)
                    e['btn'].grid_configure(row=rn)
                if not preset_rows or preset_rows[-1]['iv'].get().strip():
                    add_preset_row()
                refresh_preset_dropdowns()

            def add_preset_row(item="", qty=0):
                r = len(preset_rows) + 1
                iv = tk.StringVar(value=item)
                qv = tk.IntVar(value=qty)
                icon_label = create_icon_label(preset_table, item)
                icon_label.grid(row=r, column=0, padx=2, pady=2)
                cb = CategorizedItemDropdown(preset_table, iv, item_category)
                cb.set_values(valid_items)
                cb.grid(row=r, column=1, padx=5, pady=2, sticky='w')
                sb = tk.Spinbox(preset_table, from_=0, to=99999, textvariable=qv, width=6)
                sb.grid(row=r, column=2, padx=5, pady=2, sticky='w')

                def _remove_this():
                    remove_preset_row(preset_rows.index(entry))

                btn = tk.Button(preset_table, text='X', command=_remove_this, width=2)
                btn.grid(row=r, column=3, padx=5, pady=2, sticky='w')
                entry = {'iv': iv, 'qv': qv, 'cb': cb, 'sb': sb, 'btn': btn, 'icon': icon_label}
                preset_rows.append(entry)

                def on_change(*_):
                    selected_item = iv.get().strip()
                    entry['icon'].destroy()
                    entry['icon'] = create_icon_label(preset_table, selected_item)
                    try:
                        row_number = preset_rows.index(entry) + 1
                    except ValueError:
                        row_number = r
                    entry['icon'].grid(row=row_number, column=0, padx=2, pady=2)
                    if preset_rows and preset_rows[-1]['iv'] is iv and selected_item:
                        add_preset_row()
                    refresh_preset_dropdowns()

                iv.trace_add('write', on_change)

            def clear_preset_table():
                for widget in preset_table.winfo_children():
                    widget.destroy()
                preset_rows.clear()
                build_preset_headers()

            def preset_row_data():
                cargo = {}
                teams = {}
                for entry in preset_rows:
                    name = entry['iv'].get().strip()
                    if not name:
                        continue
                    qty = entry['qv'].get()
                    if name in cargo_keys:
                        cargo[name] = qty
                    else:
                        teams[name] = qty
                return {"cargo": cargo, "teams": teams}

            def load_preset(name):
                current['name'] = name
                name_var.set(name)
                clear_preset_table()
                cfg = presets.get(name, {"cargo": {}, "teams": {}})
                preset_items = []
                for section in ('cargo', 'teams'):
                    preset_items.extend((it, qt) for it, qt in cfg.get(section, {}).items())
                for item, qty in sorted(preset_items, key=lambda entry: item_sort_key(entry[0])):
                    add_preset_row(item, qty)
                add_preset_row()
                refresh_preset_dropdowns()

            def refresh_preset_list(select_name=None):
                preset_lb.delete(0, 'end')
                names = list(presets.keys())
                for name in names:
                    preset_lb.insert('end', name)
                if not names:
                    current['name'] = None
                    name_var.set('')
                    clear_preset_table()
                    add_preset_row()
                    return
                if select_name not in presets:
                    select_name = names[0]
                idx = names.index(select_name)
                preset_lb.selection_clear(0, 'end')
                preset_lb.selection_set(idx)
                preset_lb.see(idx)
                load_preset(select_name)

            def selected_preset_name():
                sel = preset_lb.curselection()
                if not sel:
                    return None
                return preset_lb.get(sel[0])

            def save_current_preset():
                old_name = current.get('name')
                new_name = name_var.get().strip()
                if not old_name:
                    messagebox.showwarning("Preset Editor", "Select or add a preset first.", parent=editor)
                    return False
                if not new_name:
                    messagebox.showwarning("Preset Editor", "Preset name cannot be blank.", parent=editor)
                    return False
                if new_name != old_name and new_name in presets:
                    messagebox.showwarning("Preset Editor", f"Preset '{new_name}' already exists.", parent=editor)
                    return False
                data = preset_row_data()
                if new_name != old_name:
                    presets[new_name] = presets.pop(old_name)
                    current['name'] = new_name
                presets[new_name] = data
                refresh_preset_list(new_name)
                refresh_preset_selector(new_name)
                return True

            def add_preset():
                name = simpledialog.askstring("Add Preset", "Preset name:", parent=editor)
                if not name:
                    return
                name = name.strip()
                if not name:
                    return
                if name in presets:
                    messagebox.showwarning("Preset Editor", f"Preset '{name}' already exists.", parent=editor)
                    return
                presets[name] = {"cargo": {}, "teams": {}}
                refresh_preset_list(name)
                refresh_preset_selector(name)

            def delete_preset():
                name = selected_preset_name()
                if not name:
                    return
                if not messagebox.askyesno("Delete Preset", f"Delete preset '{name}'?", parent=editor):
                    return
                presets.pop(name, None)
                refresh_preset_list()
                refresh_preset_selector()

            def on_preset_select(event=None):
                name = selected_preset_name()
                old_name = current.get('name')
                if old_name and old_name in presets and name != old_name:
                    presets[old_name] = preset_row_data()
                if name:
                    load_preset(name)

            def save_and_close():
                if current.get('name') and not save_current_preset():
                    return
                if save_cargo_team_config():
                    editor.destroy()

            preset_lb.bind('<<ListboxSelect>>', on_preset_select)

            tk.Button(left, text="Add", command=add_preset).pack(fill='x', pady=(6, 2))
            tk.Button(left, text="Delete", command=delete_preset).pack(fill='x', pady=2)
            tk.Button(buttons, text="Save Preset", command=lambda: save_current_preset() and save_cargo_team_config())\
              .pack(side='left', padx=4)
            tk.Button(buttons, text="Save & Close", command=save_and_close).pack(side='left', padx=4)
            tk.Button(buttons, text="Close", command=editor.destroy).pack(side='left', padx=4)

            refresh_preset_list()
            editor.wait_window()

        # populate existing cargo+teams
        existing = {}
        for k,v in (obj.get('cargo') or {}).items():
            existing[k] = int(v)
        for k,v in (obj.get('teams') or {}).items():
            existing[k] = int(v)
        for key,val in sorted(existing.items(), key=lambda entry: item_sort_key(entry[0])):
            add_row(key, val)
        add_row()  # always end with a blank row
        # initial filter
        refresh_dropdowns()

        # --- Preset handler ---
        def apply_preset(_=None):
            name = preset_var.get()
            if name in presets:
                # clear table
                for w in table.winfo_children():
                    w.destroy()
                rows.clear()
                # header
                tk.Label(table, text="Icon").grid(row=0, column=0, padx=5, pady=2)
                tk.Label(table, text="Item").grid(row=0, column=1, padx=5, pady=2)
                tk.Label(table, text="Quantity").grid(row=0, column=2, padx=5, pady=2)
                cfg = presets[name]
                preset_items = []
                for d in ('cargo','teams'):
                    preset_items.extend((it, qt) for it, qt in cfg.get(d, {}).items())
                for it, qt in sorted(preset_items, key=lambda entry: item_sort_key(entry[0])):
                    add_row(it, qt)
                add_row()
        preset_cb.bind("<<ComboboxSelected>>", apply_preset)
        tk.Button(dlg, text="Edit Presets", command=open_preset_editor)\
          .grid(row=0, column=3, padx=5)

        # --- Randomize handler ---
        def randomize():
            # Randomize each row's quantity by с10%
            for entry in rows:
                iv = entry.get('iv')
                qv = entry.get('qv')
                if iv and qv and iv.get().strip() and qv.get() > 0:
                    base = qv.get()
                    delta = max(1, int(base * 0.1))
                    qv.set(random.randint(base - delta, base + delta))

        # --- Save & Cancel ---
        def save():
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
            if obj.get('cargo') != cargo or obj.get('teams') != teams:
                push_undo()
            obj['cargo'] = cargo
            obj['teams'] = teams
            dlg.destroy()
            show_object(obj_name)
            refresh_overviews()

        tk.Button(dlg, text="Save",   command=save)\
          .grid(row=2, column=1, pady=5)
        tk.Button(dlg, text="Cancel", command=dlg.destroy)\
          .grid(row=2, column=2, pady=5)

        dlg.transient(win)
        dlg.wait_window()
    # Adapter: show_object via generic helper
    def arm_copy_object(name: str, obj: Dict[str, Any]) -> None:
        copy_state['source_name'] = name
        copy_state['source_obj'] = copy.deepcopy(obj)

    def convert_station_type(name, new_type):
        obj = sm.get_object(name)
        if obj.get('type') not in STATION_OR_PLATFORM_TYPES or new_type not in STATION_OR_PLATFORM_TYPES:
            return
        if obj['type'] == new_type:
            return
        flush_pending_text_widgets()
        push_undo()
        # Retain hull, cargo, facilities, coordinates and other metadata.
        obj['type'] = new_type
        show_object(name)
        refresh_objects_list()
        draw_map(ctx)
        refresh_overviews()

    def show_object(name: str):
        nonlocal last_desc_widget, last_desc_obj
        obj = sm.get_object(name)
        if not win.winfo_exists():
            return
        set_selection('object', name)
        update_coord_display(obj.get('coordinate'), False)
        clear_edit_pane()
        edit_title.config(text=f"Station: {name}" if obj.get('type')=='station' else f"Object: {name}")
        # Bring title to front
        edit_title.lift()

        zone_style = get_zone_style(obj.get('type'))
        if zone_style is not None:
            coord = obj.get('coordinate', [0,0,0])
            zone_types = sorted(ZONE_STYLE_MAP.keys())

            def _set_zone_type(value):
                obj['type'] = value
                draw_map(ctx)

            fields = [
                ("Type:", lambda: obj.get('type', ''), _set_zone_type, 'combo', zone_types),
                ("X:", lambda: coord[0], lambda v: obj.__setitem__('coordinate', [v, coord[1], coord[2]])),
                ("Z:", lambda: coord[2], lambda v: obj.__setitem__('coordinate', [coord[0], coord[1], v])),
                ("Radius:", lambda: obj.get('radius', 5000), lambda v: obj.__setitem__('radius', int(v))),
                ("Description:", lambda: obj.get('description', ''), lambda v: obj.__setitem__('description', v), 'text'),
            ]
            show_item(zone_style['label'], name, fields, rename_object, delete_object)
            set_selection('object', name)
            edit_title.config(text=f"{zone_style['label']}: {name}")
            hide_var = tk.BooleanVar(value=obj.get('hideonmap', False))
            tk.Checkbutton(
                edit_frame,
                text="Hide on map",
                variable=hide_var,
                command=lambda: obj.__setitem__('hideonmap', hide_var.get())
            ).pack(anchor='w', pady=2)
            return
        
        # ─── Platform‐type custom layout ──────────────────────────────
        if obj.get('type') == 'platform':
            platform_frame = tk.Frame(edit_frame)
            platform_frame.grid(row=1, column=0, columnspan=2, sticky='nsew')
            edit_title.config(text=f"Platform: {name}")
            tk.Button(platform_frame, text="Convert to Station",
                      command=lambda: convert_station_type(name, 'station')).pack(anchor='w', pady=2)
            side_var, _, _ = _build_faction_side_controls(platform_frame, obj, layout='pack')

            # Hull dropdown (include hulls with role 'platform' or 'defense')
            tk.Label(platform_frame, text="Hull:").pack(anchor='w', pady=2)
            hull_var = tk.StringVar(value=obj.get('hull',''))
            platform_hulls = SysMapCanvas._filter_hulls_by_roles(
                valid_hulls, {'platform', 'static', 'defense'}, hull_role_map, hull_category_map
            )
            hull_cb = ttk.Combobox(
                platform_frame,
                textvariable=hull_var,
                values=sorted(platform_hulls),
                state='readonly'
            )
            hull_cb.pack(anchor='w', pady=2)
            hull_cb.bind("<Button-1>", lambda e, cb=hull_cb: SysMapCanvas._schedule_combobox_colors(cb), add="+")
            SysMapCanvas._ensure_hull_color_binding(hull_cb)

            def apply_platform_hull(*_, v=hull_var):
                obj['hull'] = v.get()
                draw_map(ctx)

            hull_var.trace_add('write', apply_platform_hull)

            show_all_var = tk.BooleanVar(value=False)
            relax_role_var = tk.BooleanVar(value=False)
            tk.Checkbutton(
                platform_frame, text="Show all hulls",
                variable=show_all_var
            ).pack(anchor='w', pady=(2, 0))
            tk.Checkbutton(
                platform_frame, text="Relax role filter",
                variable=relax_role_var
            ).pack(anchor='w', pady=(0, 2))

            def update_platform_hulls(*_):
                base_pool = valid_hulls if relax_role_var.get() else platform_hulls
                opts, green_count = SysMapCanvas._build_hull_options(
                    base_pool, side_var.get(), hull_side_map, toolbar, include_others=show_all_var.get()
                )
                current = hull_var.get()
                if current and current not in opts:
                    opts = opts + [current]
                hull_cb['values'] = opts
                hull_cb._green_count = green_count
                SysMapCanvas._schedule_combobox_colors(hull_cb)
                current = hull_var.get().strip()
                if current and current not in opts and opts:
                    hull_var.set(opts[0])

            side_var.trace_add('write', update_platform_hulls)
            show_all_var.trace_add('write', update_platform_hulls)
            relax_role_var.trace_add('write', update_platform_hulls)
            update_platform_hulls()

            # Rename & Delete buttons
            frm = tk.Frame(platform_frame)
            frm.pack(fill='x', pady=5)
            tk.Button(frm, text="Copy",
                      command=lambda n=name, o=obj: arm_copy_object(n, o))\
              .pack(side='left', expand=True, padx=2)
            tk.Button(frm, text="Rename",
                      command=lambda: rename_object(name))\
              .pack(side='left', expand=True, padx=2)
            tk.Button(frm, text="Delete", fg='red',
                      command=lambda: delete_object(name))\
              .pack(side='left', expand=True, padx=2)

            # Hide on map
            hide_var = tk.BooleanVar(value=obj.get('hideonmap', False))
            tk.Checkbutton(
                platform_frame,
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
                    push_undo()
                    # mirror rename_object logic for objects
                    sm.data['objects'][new_name] = sm.data['objects'].pop(old)
                    rename_incoming_only_gate(sm.data, old, new_name)
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

            incoming_only_var = tk.BooleanVar(
                value=name.casefold() in get_incoming_only_gate_names(sm.data)
            )

            def apply_incoming_only():
                push_undo()
                set_incoming_only_gate(sm.data, name, incoming_only_var.get())
                draw_map(ctx)

            tk.Checkbutton(
                edit_frame,
                text="Incoming only",
                variable=incoming_only_var,
                command=apply_incoming_only,
                anchor='w',
                justify='left'
            ).pack(anchor='w', pady=2)

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
                             if v.get('type') in ('jumpnode','jumppoint')]
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
                             if v.get('type') in ('jumpnode','jumppoint')]
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
            tk.Button(edit_frame, text="Convert to Platform",
                      command=lambda: convert_station_type(name, 'platform')).grid(
                          row=12, column=0, columnspan=2, sticky='w', pady=2)
            # Station pane now starts at row 1 (row 0 is the title)
            side_var, _, _ = _build_faction_side_controls(edit_frame, obj, layout='grid', row=1)

            # Hull dropdown
            tk.Label(edit_frame, text="Hull:").grid(row=3, column=0, sticky='w')
            hull_var = tk.StringVar(value=obj.get('hull',''))
            hull_cb  = ttk.Combobox(
                edit_frame,
                textvariable=hull_var,
                values=valid_hulls,
                state='readonly'
            )
            hull_cb.grid(row=3, column=1, padx=5, pady=2, sticky='w')
            hull_cb.bind("<Button-1>", lambda e, cb=hull_cb: SysMapCanvas._schedule_combobox_colors(cb), add="+")
            SysMapCanvas._ensure_hull_color_binding(hull_cb)

            def apply_station_hull(*_):
                obj['hull'] = hull_var.get()
                draw_map(ctx)

            hull_var.trace_add('write', apply_station_hull)

            show_all_var = tk.BooleanVar(value=False)
            relax_role_var = tk.BooleanVar(value=False)
            tk.Checkbutton(
                edit_frame, text="Show all hulls",
                variable=show_all_var
            ).grid(row=4, column=0, columnspan=2, sticky='w')
            tk.Checkbutton(
                edit_frame, text="Relax role filter",
                variable=relax_role_var
            ).grid(row=5, column=0, columnspan=2, sticky='w')

            station_hulls = SysMapCanvas._filter_hulls_by_roles(
                valid_hulls, {'station'}, hull_role_map, hull_category_map
            )
            def update_hulls(*_):
                hull_pool = valid_hulls if relax_role_var.get() else station_hulls
                opts, green_count = SysMapCanvas._build_hull_options(
                    hull_pool, side_var.get(), hull_side_map, toolbar, include_others=show_all_var.get()
                )
                current = hull_var.get()
                if current and current not in opts:
                    opts = opts + [current]
                hull_cb['values'] = opts
                hull_cb._green_count = green_count
                SysMapCanvas._schedule_combobox_colors(hull_cb)
                current = hull_var.get().strip()
                if current and current not in opts and opts:
                    hull_var.set(opts[0])

            side_var.trace_add('write', update_hulls)
            show_all_var.trace_add('write', update_hulls)
            relax_role_var.trace_add('write', update_hulls)
            update_hulls()

            # ─── Facilities checkboxes ──────────────────────────────
            dock_var   = tk.BooleanVar(value="Docking" in obj.get('facilities', []))
            refuel_var = tk.BooleanVar(value="Refuel"  in obj.get('facilities', []))
            repair_var = tk.BooleanVar(value="Repair"  in obj.get('facilities', []))
            tk.Checkbutton(
                edit_frame, text="Docking",
                variable=dock_var,
                command=lambda v=dock_var: set_facility(obj, "Docking", v.get())
            ).grid(row=6, column=0, sticky='w')
            tk.Checkbutton(
                edit_frame, text="Refuel",
                variable=refuel_var,
                command=lambda v=refuel_var: set_facility(obj, "Refuel", v.get())
            ).grid(row=6, column=1, sticky='w')
            tk.Checkbutton(
                edit_frame, text="Repair",
                variable=repair_var,
                command=lambda v=repair_var: set_facility(obj, "Repair", v.get())
            ).grid(row=6, column=2, sticky='w')


            # Rename & Delete buttons on row 5
            tk.Button(edit_frame, text="Copy",
                      command=lambda n=name, o=obj: arm_copy_object(n, o))\
                .grid(row=8, column=0, padx=2, pady=5, sticky='w')
            tk.Button(edit_frame, text="Rename",
                      command=lambda: rename_object(name))\
                .grid(row=8, column=1, padx=2, pady=5, sticky='w')
            tk.Button(edit_frame, text="Delete",
                      command=lambda: delete_object(name))\
                .grid(row=8, column=2, padx=2, pady=5, sticky='w')

            # Description (multi-line) at row 6
            tk.Label(edit_frame, text="Description:") \
                .grid(row=9, column=0, sticky='nw', pady=(4, 0))
            desc_text = tk.Text(edit_frame, width=30, height=4, wrap='word')
            desc_text.grid(row=10, column=0, columnspan=2, padx=5, pady=2, sticky='w')
            desc_text.insert('1.0', obj.get('description', ''))
            # remember this widget & obj so clear_edit_pane() can commit edits

            last_desc_widget = desc_text
            last_desc_obj = obj
            register_text_widget(
                desc_text,
                lambda value, target=obj: target.__setitem__('description', value)
            )

            # Hide on map at row 7
            hide_var = tk.BooleanVar(value=obj.get('hideonmap', False))
            tk.Checkbutton(edit_frame, text="Hide on map",
                           variable=hide_var,
                           command=lambda: obj.__setitem__('hideonmap', hide_var.get()))\
                .grid(row=11, column=0, columnspan=2, sticky='w', pady=2)

            # Edit Cargo/Teams at row 8
            tk.Button(edit_frame, text="Edit Cargo/Teams",
                      command=lambda n=name: open_cargo_teams_dialog(n))\
                .grid(row=7, column=0, columnspan=2, sticky='w', pady=2)
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

        side_var, _, _ = _build_faction_side_controls(edit_frame, obj, layout='pack')

        # Filter checkboxes
        side_filter_var = tk.BooleanVar(value=False)
        role_filter_var = tk.BooleanVar(value=False)
        def update_hulls():
            # start from all hull keys
            filtered = list(valid_hulls)
            # filter by matching side if requested
            if side_filter_var.get():
                current_side = side_var.get()
                current_cf = str(current_side).casefold()
                # Build casefolded Race→Faction and Faction→Races maps from Settings.json
                races_map_local = races_map if isinstance(races_map, dict) else {}
                race_to_faction_cf = {str(r).casefold(): str(v.get('Faction','')).casefold()
                                      for r, v in races_map_local.items()
                                      if isinstance(v, dict)}
                faction_to_races_cf = {}
                for r_cf, f_cf in race_to_faction_cf.items():
                    faction_to_races_cf.setdefault(f_cf, set()).add(r_cf)
                # Allowed sides: selected + its faction + all races in that faction
                allowed = {current_cf}
                if current_cf in race_to_faction_cf:
                    fac_cf = race_to_faction_cf[current_cf]
                    allowed.add(fac_cf)
                    allowed |= faction_to_races_cf.get(fac_cf, set())
                if current_cf in faction_to_races_cf:
                    allowed |= faction_to_races_cf.get(current_cf, set())
                # Filter by allowed sides
                filtered = [
                    h for h in filtered
                    if str(
                        next((e for e in ship_entries if e['key']==h), {}).get('side','')
                    ).casefold() in allowed
                ]
            # filter by roles containing 'station'
            if role_filter_var.get():
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
                       variable=side_filter_var,
                       command=update_hulls)\
            .pack(anchor='w')
        tk.Checkbutton(edit_frame,
                       text="Only roles=station",
                       variable=role_filter_var,
                       command=update_hulls)\
            .pack(anchor='w', pady=(0,5))

        # write back to obj
        hull_var.trace_add('write', lambda *a: obj.__setitem__('hull', hull_var.get()))
# Adapter: show_terrain via generic helper with blackhole support
    def show_terrain(key: str):
        feat = sm.get_terrain_feature(key)
        set_selection('terrain', key)
        ttype = feat.get('type','').lower()
        coord = None
        is_center = False
        start = feat.get('start')
        end = feat.get('end')
        if isinstance(start, (list, tuple)) and isinstance(end, (list, tuple)) and len(start) >= 3 and len(end) >= 3:
            coord = [
                (start[0] + end[0]) / 2,
                (start[1] + end[1]) / 2,
                (start[2] + end[2]) / 2
            ]
            is_center = True
        elif isinstance(feat.get('coordinate'), (list, tuple)):
            coord = feat.get('coordinate')
            if ttype in ('blackhole', 'planet', 'debris_field', 'hidden_minefield', 'minefield') or is_zone_type(ttype):
                is_center = True
        update_coord_display(coord, is_center)
        clear_edit_pane()
        edit_title.config(text=f"Terrain: {key}")

        if ttype == 'blackhole':
            coord = feat.get('coordinate',[0,0,0])
            fields = [
                ("X:", lambda: coord[0], lambda v: feat.__setitem__('coordinate',[v,coord[1],coord[2]])),
                ("Z:", lambda: coord[2], lambda v: feat.__setitem__('coordinate',[coord[0],coord[1],v])),
                ("Name:", lambda: feat.get('name', key), lambda v: feat.__setitem__('name',v)),
                ("Size:", lambda: feat.get('size',500), lambda v: feat.__setitem__('size',int(v))),
                ("Gravity Radius:", lambda: feat.get('GravityRadius',5000), lambda v: feat.__setitem__('GravityRadius',int(v))),
                ("Strength:", lambda: feat.get('strength',10), lambda v: feat.__setitem__('strength',int(v))),
                ("Turbulence Strength:", lambda: feat.get('turbulence_strength',2), lambda v: feat.__setitem__('turbulence_strength',int(v))),
                ("Description:", lambda: feat.get('description',''), lambda v: feat.__setitem__('description',v), 'text'),
            ]
            show_item("Blackhole", key, fields, rename_terrain, delete_terrain)
        elif ttype == 'planet':
            coord = feat.get('coordinate',[0,0,0])
            fields = [
                ("X:",      lambda: coord[0], lambda v: feat.__setitem__('coordinate',[v,coord[1],coord[2]])),
                ("Z:",      lambda: coord[2], lambda v: feat.__setitem__('coordinate',[coord[0],coord[1],v])),
                ("Name:",   lambda: feat.get('name', key), lambda v: feat.__setitem__('name', v)),
                (
                    "Class:",
                    lambda: feat.get('class', DEFAULT_PLANET_CLASS),
                    lambda v: feat.__setitem__('class', v),
                    'combo',
                    valid_planet_classes,
                ),
                # Size is fixed visually (15,000 units); no size field in JSON by design
                ("Description:", lambda: feat.get('description',''),
                    lambda v: feat.__setitem__('description', v), 'text'),
            ]
            show_item("Planet", key, fields, rename_terrain, delete_terrain)
        elif ttype == 'debris_field':
            coord = feat.get('coordinate', [0,0,0])
            # Basic fields for debris field (circular)
            fields = [
                ("X:", lambda: coord[0], lambda v: feat.__setitem__('coordinate', [v, coord[1], coord[2]])),
                ("Z:", lambda: coord[2], lambda v: feat.__setitem__('coordinate', [coord[0], coord[1], v])),
                ("Density:", lambda: feat.get('density',30), lambda v: feat.__setitem__('density', int(v))),
                ("Scatter (radius):", lambda: feat.get('scatter',10000), lambda v: feat.__setitem__('scatter', int(v))),
            ]
            # Include seed if present
            if 'seed' in feat:
                fields.append(("Seed:", lambda: feat.get('seed',2010), lambda v: feat.__setitem__('seed', int(v))))
            show_item("Debris Field", key, fields, rename_terrain, delete_terrain)
        elif ttype in ('hidden_minefield', 'minefield'):
            coord = feat.get('coordinate', [0,0,0])
            def _set_minefield_type(value):
                feat['type'] = value
                feat['hideonmap'] = (value == 'hidden_minefield')
                draw_map(ctx)
            fields = [
                (
                    "Type:",
                    lambda: feat.get('type', 'hidden_minefield'),
                    _set_minefield_type,
                    'combo',
                    ['hidden_minefield', 'minefield'],
                ),
                ("X:", lambda: coord[0], lambda v: feat.__setitem__('coordinate', [v, coord[1], coord[2]])),
                ("Z:", lambda: coord[2], lambda v: feat.__setitem__('coordinate', [coord[0], coord[1], v])),
                ("Width:", lambda: feat.get('width', 15000), lambda v: feat.__setitem__('width', int(v))),
                ("Height:", lambda: feat.get('height', 15000), lambda v: feat.__setitem__('height', int(v))),
                ("Density:", lambda: feat.get('density', 70), lambda v: feat.__setitem__('density', int(v))),
            ]
            show_item("Hidden Mine Field" if ttype == 'hidden_minefield' else "Mine Field", key, fields, rename_terrain, delete_terrain)
        elif is_zone_type(ttype):
            coord = feat.get('coordinate', [0,0,0])
            zone_style = get_zone_style(ttype) or DEFAULT_ZONE_STYLE
            zone_types = sorted(ZONE_STYLE_MAP.keys())

            def _set_zone_type(value):
                feat['type'] = value
                draw_map(ctx)

            fields = [
                ("Type:", lambda: feat.get('type', ttype), _set_zone_type, 'combo', zone_types),
                ("X:", lambda: coord[0], lambda v: feat.__setitem__('coordinate', [v, coord[1], coord[2]])),
                ("Z:", lambda: coord[2], lambda v: feat.__setitem__('coordinate', [coord[0], coord[1], v])),
                ("Radius:", lambda: feat.get('radius', 5000), lambda v: feat.__setitem__('radius', int(v))),
                ("Description:", lambda: feat.get('description', ''), lambda v: feat.__setitem__('description', v), 'text'),
            ]
            show_item(zone_style['label'], key, fields, rename_terrain, delete_terrain)
            set_selection('terrain', key)
            edit_title.config(text=f"{zone_style['label']}: {key}")
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
        nonlocal session_revision_bumped, text_dirty
        old_md = {}
        try:
            flush_pending_text_widgets()
            # Update in-memory state
            sm.set_system_map_coord(parse_map_coordinate_fields(
                [var.get() for var in coord_vars], sm.get_system_map_coord()))
            sm.set_alignment(align_var.get())
            sm.set_description(desc_text.get('1.0', tk.END).strip())
            persist_author_setting()

            md = sm.data.setdefault('metadata', {})
            def _merge_with_extras(selected, existing, known):
                extras = [x for x in (existing or []) if x not in known]
                for x in extras:
                    if x not in selected:
                        selected.append(x)
                return selected

            md['security'] = sec_var.get()
            selected_exports = [k for k, v in export_vars.items() if v.get()]
            md['exports'] = _merge_with_extras(selected_exports, md.get('exports', []), smopts.EXPORT_OPTIONS)
            md['focus'] = focus_var.get()
            md['development'] = dev_var.get()
            md['visible'] = True if vis_var.get() == "Show" else False
            md['skybox'] = skybox_var.get()

            intel_data = md.get('intel', {})
            if not isinstance(intel_data, dict):
                intel_data = {}
            intel_data['pirate'] = pirate_var.get()
            intel_data['enemy'] = enemy_var.get()
            selected_assets = [k for k, v in assets_vars.items() if v.get()]
            intel_data['assets'] = _merge_with_extras(selected_assets, intel_data.get('assets', []), smopts.ASSET_OPTIONS)
            md['intel'] = intel_data

            current_author = author_var.get().strip()
            old_md = {}
            for key in ('original_author', 'last_revision_author', 'revision_number', 'revision_date', 'all_authors'):
                if key in md:
                    old_md[key] = (True, md.get(key))
                else:
                    old_md[key] = (False, None)

            authors = _normalize_author_list(md.get('all_authors'))
            if current_author:
                if not any(a.casefold() == current_author.casefold() for a in authors):
                    authors.append(current_author)
                if not str(md.get('original_author', '') or '').strip():
                    md['original_author'] = current_author
                md['last_revision_author'] = current_author
            if authors:
                md['all_authors'] = authors

            bumped_this_save = False
            if not session_revision_bumped:
                rev_num = _coerce_revision_number(md.get('revision_number', 0))
                md['revision_number'] = rev_num + 1
                md['revision_date'] = datetime.date.today().isoformat()
                bumped_this_save = True
            # Update incoming gate references with the system save, so rename
            # remains undoable until Save and cannot partially update the map.
            renames = {original: current for current, original in gate_origins.items()
                       if current != original and is_gate(sm.get_object(current))}
            sm.save(gate_renames=renames)
            gate_origins.clear()
            gate_origins.update({name: name for name, obj in sm.data.get('objects', {}).items() if is_gate(obj)})
            if bumped_this_save:
                session_revision_bumped = True
            refresh_author_metadata_display(md)
            # Mark as clean (no unsaved changes)
            # Reset history and the baseline only after a successful write.
            try:
                undo_stack.clear()
                redo_stack.clear()
            except Exception:
                pass
            mark_saved()
            # Inform user with a sound only (no popup)
            try:
                win.bell()
            except Exception:
                pass
            return True
        except Exception as e:
            # Restore metadata on failure to avoid false revision bumps
            try:
                md = sm.data.setdefault('metadata', {})
                for key, (exists, val) in old_md.items():
                    if exists:
                        md[key] = val
                    else:
                        md.pop(key, None)
                refresh_author_metadata_display(md)
            except Exception:
                pass
            messagebox.showerror("Error", f"Save failed: {e}")
            return False

   # ─── Reload button (clear & reload from disk) ──────────────────
    def reload_all():
        nonlocal text_dirty, session_revision_bumped
        if not confirm_pending_changes("reloading"):
            return False
        try:
            # Read first so a failed read leaves the current session intact.
            reloaded = SystemMap(file_path)
            # Reload may encounter newly imported legacy names; apply the same
            # compatibility migration as initial opening before refreshing UI.
            reloaded.migrate_names()
            validate_and_fix_planet_classes_on_load(reloaded)
            validate_and_fix_sides_on_load(reloaded)
            clear_edit_pane()
            sm.data = reloaded.data
            sm.disk_bytes = reloaded.disk_bytes
            gate_origins.clear()
            gate_origins.update({name: name for name, obj in sm.data.get('objects', {}).items() if is_gate(obj)})
            # refresh metadata fields
            for var, val in zip(coord_vars, sm.get_system_map_coord()):
                var.set(str(val))
            align_var.set(sm.get_alignment() or '')
            desc_text.delete('1.0', tk.END)
            desc_text.insert('1.0', sm.get_description())
            try:
                desc_text.edit_modified(False)
            except tk.TclError:
                pass
            refresh_author_metadata_display(sm.data.get('metadata', {}))

            md = sm.data.setdefault('metadata', {})
            intel = md.get('intel', {})
            if not isinstance(intel, dict):
                intel = {}
            sec_val = md.get('security', 'Neutral')
            if sec_val not in smopts.SECURITY_LEVELS:
                sec_val = 'Neutral'
            pirate_val = intel.get('pirate', 'Low')
            if pirate_val not in smopts.PIRATE_LEVELS:
                pirate_val = 'Low'
            enemy_val = intel.get('enemy', 'Low')
            if enemy_val not in smopts.ENEMY_LEVELS:
                enemy_val = 'Low'
            dev_val = md.get('development', 'Unclaimed')
            if dev_val not in smopts.DEVELOPMENT_STAGES:
                dev_val = 'Unclaimed'

            sec_var.set(sec_val)
            pirate_var.set(pirate_val)
            enemy_var.set(enemy_val)
            dev_var.set(dev_val)

            assets_current = set(intel.get('assets', []) or [])
            for opt, var in assets_vars.items():
                var.set(opt in assets_current)

            exports_current = set(md.get('exports', []) or [])
            for opt, var in export_vars.items():
                var.set(opt in exports_current)

            focus_var.set(md.get('focus', ''))
            vis_var.set("Show" if md.get('visible', True) else "Hide")
            skybox_var.set(md.get('skybox', ''))

            traffic = sm.data.get('traffic', {})
            if not isinstance(traffic, dict):
                traffic = {}
            for cat, var in traffic_vars.items():
                var.set(traffic.get(cat, 'none'))

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
            undo_stack.clear()
            redo_stack.clear()
            copy_state.update(source_name=None, source_obj=None)
            session_revision_bumped = False
            _refresh_ui()
            refresh_objects_list()
            mark_saved()
        except Exception as e:
            messagebox.showerror("Error", f"Reload failed: {e}")
            return False
        # Re-run validation after a reload
        validate_and_report()
        return True

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
        if not confirm_pending_changes("opening another system"):
            return
        # Preserve this session if the selected file cannot be opened.
        replacement = open_system_editor(newpath)
        if isinstance(replacement, tk.Toplevel):
            win.destroy()


    def collect_cargo_team_validation_issues():
        return collect_cargo_issues(sm.data, ct_config)

    # ─── Validation: Cargo & Teams against cargo_teams.json ─────────────
    def validate_and_report(show_success=False):
        """
        Validate every object's cargo and teams against cargo_teams.json.
        - Flags unknown item names.
        - Flags items placed under the wrong section (cargo vs teams).
        - Flags non-integer or negative quantities.
        Shows a summary warning on problems; silent if all OK unless requested.
        """
        issues = collect_cargo_team_validation_issues()
        if issues:
            # If message too long for a messagebox, print full list and summarize.
            report = "\n".join(issues)
            if len(report) > 1800:
                print("Cargo/Teams validation issues:\n" + report)
                messagebox.showwarning(
                    "Cargo/Teams Validation",
                    f"{len(issues)} issues found. Full list printed to console."
                )
            else:
                messagebox.showwarning("Cargo/Teams Validation", "Issues found:\n\n" + report)
        else:
            print("Cargo/Teams validation: OK")
            if show_success:
                messagebox.showinfo("Cargo/Teams Validation", "No cargo or team issues were found.")

    def show_validation_results(title, errors, warnings):
        if not errors and not warnings:
            messagebox.showinfo(title, "No malformed JSON or structural issues were found.")
            return

        dlg = tk.Toplevel(win)
        dlg.title(title)
        dlg.transient(win)
        dlg.resizable(True, True)
        dlg.geometry("780x520")

        body = tk.Frame(dlg, padx=10, pady=10)
        body.pack(fill='both', expand=True)

        summary_parts = []
        if errors:
            summary_parts.append(f"{len(errors)} error(s)")
        if warnings:
            summary_parts.append(f"{len(warnings)} warning(s)")
        summary_text = ", ".join(summary_parts) if summary_parts else "No issues found"

        tk.Label(
            body,
            text=summary_text,
            font=('Arial', 10, 'bold'),
            anchor='w',
            justify='left',
        ).pack(fill='x', pady=(0, 8))

        text_frame = tk.Frame(body)
        text_frame.pack(fill='both', expand=True)

        report_text = tk.Text(text_frame, wrap='word', width=100, height=24)
        report_text.pack(side='left', fill='both', expand=True)
        scroll = ttk.Scrollbar(text_frame, orient='vertical', command=report_text.yview)
        scroll.pack(side='right', fill='y')
        report_text.configure(yscrollcommand=scroll.set)

        if errors:
            report_text.insert('end', "Errors\n")
            report_text.insert('end', "======\n")
            for item in errors:
                report_text.insert('end', f"- {item}\n")
        if warnings:
            if errors:
                report_text.insert('end', "\n")
            report_text.insert('end', "Warnings\n")
            report_text.insert('end', "========\n")
            for item in warnings:
                report_text.insert('end', f"- {item}\n")
        report_text.configure(state='disabled')

        footer = tk.Frame(dlg, padx=10, pady=10)
        footer.pack(fill='x')
        tk.Button(footer, text="Close", width=12, command=dlg.destroy).pack(side='right')

        dlg.update_idletasks()
        dlg.lift()
        try:
            dlg.focus_force()
        except Exception:
            dlg.focus_set()

    def verify_system_data():
        errors, warnings = verify_map_data(
            sm.data, filename=filename, system_files=system_files,
            other_gate_index=other_gate_index, ct_config=ct_config,
        )
        show_validation_results("Verify System", errors, warnings)

    def show_station_list():
        return open_station_overview(
            win=win,
            bind_history_shortcuts=bind_history_shortcuts,
            valid_sides=valid_sides,
            ship_entries=ship_entries,
            overview_refreshers=overview_refreshers,
            sm=sm,
            refresh_objects_list=refresh_objects_list,
            _az09_key=_az09_key,
            valid_hulls=valid_hulls,
            convert_station_type=convert_station_type,
            open_cargo_teams_dialog=open_cargo_teams_dialog,
            push_undo=push_undo,
            flush_pending_text_widgets=flush_pending_text_widgets,
            ctx=ctx,
            _refresh_ui=_refresh_ui,
            draw_map=draw_map,
        )

    def show_info():
        info_win = tk.Toplevel(win)
        info_win.title("Help & Styling Guidelines")
        txt = tk.Text(info_win, wrap='word', width=60, height=20)
        txt.pack(expand=True, fill='both', padx=10, pady=10)
        help_content = (
            "Map Editor For TSN Sandbox by Fish\n"
            "For 1.0.6 of Cosmos and TSN Mod Acendence+\n\n"
            "Help & Styling Guidelines:\n\n"
            "- Ctrl+Z: Undo; Ctrl+X: Redo (up to 10 actions)\n"
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

    def generate_terrain():
        try:
            from scripts import generate_system_terrain as gst
        except Exception as exc:
            messagebox.showerror("Generate Terrain", f"Failed to load generator:\n{exc}")
            return

        defaults = argparse.Namespace(
            size="medium",
            radius=None,
            asteroids=getattr(gst, "DEFAULT_ASTEROIDS", 12),
            nebulas=getattr(gst, "DEFAULT_NEBULAS", 8),
            debris=6,
            density_min=100,
            density_max=300,
            debris_density=130,
            seed=None,
            pattern_ratio=0.7,
            track_min=4,
            track_max=9,
            arc_angle_min=20.0,
            arc_angle_max=45.0,
            max_circle_sides=24,
            path_turn=40.0,
            segment_overlap=0.15,
            segment_swing=0.15,
            min_gap=None,
            input=None,
            out=None,
            mode="append",
        )

        try:
            args = gst.interactive_prompt(defaults, parent=win, show_io=False)
        except SystemExit as exc:
            if "canceled" in str(exc).lower():
                return
            messagebox.showerror("Generate Terrain", str(exc))
            return
        except Exception as exc:
            messagebox.showerror("Generate Terrain", f"Failed to open generator:\n{exc}")
            return

        try:
            radius = args.radius if args.radius else gst.SIZE_TO_RADIUS[args.size]
        except Exception:
            messagebox.showerror("Generate Terrain", "Invalid size selection.")
            return

        min_gap = args.min_gap if args.min_gap is not None else max(20000.0, radius * 0.08)
        counts_custom = getattr(args, "_counts_custom", False)
        if not counts_custom:
            if args.size == "medium":
                args.asteroids *= 2
                args.nebulas *= 2
            elif args.size == "large":
                args.asteroids *= 4
                args.nebulas *= 4

        rng = random.Random(args.seed)
        terrain_data = sm.data.setdefault("terrain", {})
        used_names = set(terrain_data.keys()) if args.mode == "append" else set()

        try:
            new_terrain = gst.build_terrain(
                radius,
                args.asteroids,
                args.nebulas,
                args.debris,
                rng,
                args.pattern_ratio,
                min_gap,
                used_names,
                args.track_min,
                args.track_max,
                args.max_circle_sides,
                args.path_turn,
                args.segment_overlap,
                args.density_min,
                args.density_max,
                args.segment_swing,
                args.debris_density,
                args.arc_angle_min,
                args.arc_angle_max,
            )
        except Exception as exc:
            messagebox.showerror("Generate Terrain", f"Generation failed:\n{exc}")
            return

        if not new_terrain:
            messagebox.showinfo("Generate Terrain", "No terrain was generated.")
            return

        push_undo()
        if args.mode == "append":
            terrain_data.update(new_terrain)
        else:
            sm.data["terrain"] = new_terrain
        _refresh_ui()

    def generate_fcs_zones():
        terrain_data = sm.data.get("terrain", {})
        cache = ctx.setdefault("terrain_points_cache", {})
        nebula_points = collect_nebula_points_for_fcs(terrain_data, cache=cache)

        if not nebula_points:
            messagebox.showinfo(
                "Generate FCS Zones",
                "No nebula dots are available in this system."
            )
            return

        existing_objects = sm.data.get("objects", {})
        if existing_objects is None:
            existing_objects = {}
        if not isinstance(existing_objects, dict):
            messagebox.showerror("Generate FCS Zones", "objects must be a JSON object.")
            return
        terrain_store = sm.data.setdefault("terrain", {})
        if not isinstance(terrain_store, dict):
            messagebox.showerror("Generate FCS Zones", "terrain must be a JSON object.")
            return
        existing_fcs_objects = {
            name: obj for name, obj in existing_objects.items()
            if isinstance(obj, dict)
            and str(obj.get("type", "")).strip().lower() == FCS_ZONE_TYPE
        }
        existing_fcs_terrain = {
            name: feat for name, feat in terrain_store.items()
            if isinstance(feat, dict)
            and str(feat.get("type", "")).strip().lower() == FCS_ZONE_TYPE
        }
        existing_fcs_count = len(existing_fcs_objects) + len(existing_fcs_terrain)

        dlg, body, footer = toolbar.make_dialog("Generate Fuel Collection Zones", near="toolbar")

        zone_radius_var = tk.IntVar(value=DEFAULT_FCS_ZONE_RADIUS)
        spacing_var = tk.IntVar(value=DEFAULT_FCS_MIN_SPACING)
        density_radius_var = tk.IntVar(value=DEFAULT_FCS_DENSITY_RADIUS)
        percentile_var = tk.IntVar(value=DEFAULT_FCS_DENSITY_PERCENTILE)
        replace_var = tk.BooleanVar(value=bool(existing_fcs_count))

        tk.Label(
            body,
            text=f"Nebula dots available: {len(nebula_points)}"
        ).grid(row=0, column=0, columnspan=2, padx=6, pady=(2, 2), sticky="w")
        tk.Label(
            body,
            text=f"Existing FCS zones: {existing_fcs_count}"
        ).grid(row=1, column=0, columnspan=2, padx=6, pady=(0, 6), sticky="w")

        toolbar.labeled_spinbox(body, "Zone Radius:", zone_radius_var,
                                frm=1, to=1000000, width=10, row=2, col=0)
        toolbar.labeled_spinbox(body, "Min Spacing:", spacing_var,
                                frm=1000, to=1000000, width=10, row=3, col=0)
        toolbar.labeled_spinbox(body, "Density Radius:", density_radius_var,
                                frm=1000, to=1000000, width=10, row=4, col=0)
        toolbar.labeled_spinbox(body, "Density Percentile:", percentile_var,
                                frm=0, to=100, width=10, row=5, col=0)

        tk.Checkbutton(
            body,
            text="Replace existing FCS zones",
            variable=replace_var
        ).grid(row=6, column=0, columnspan=2, padx=6, pady=(2, 4), sticky="w")

        tk.Label(
            body,
            text="Higher percentile favors tighter nebula clusters.",
            fg="#3a86ff"
        ).grid(row=7, column=0, columnspan=2, padx=6, pady=(0, 6), sticky="w")

        def _apply():
            try:
                zone_radius = max(1, int(zone_radius_var.get() or DEFAULT_FCS_ZONE_RADIUS))
                min_spacing = max(1, int(spacing_var.get() or DEFAULT_FCS_MIN_SPACING))
                density_radius = max(1, int(density_radius_var.get() or DEFAULT_FCS_DENSITY_RADIUS))
                percentile = max(0, min(100, int(percentile_var.get() or DEFAULT_FCS_DENSITY_PERCENTILE)))
            except Exception:
                messagebox.showerror("Generate FCS Zones", "Invalid FCS zone settings.")
                return

            replace_existing = bool(replace_var.get())
            blocked_centers = collect_fcs_blocked_centers(sm.data, replace_existing=replace_existing)
            selected = select_fcs_zone_centers(
                nebula_points,
                min_spacing=min_spacing,
                density_radius=density_radius,
                percentile=percentile,
                min_score=DEFAULT_FCS_MIN_SCORE,
                blocked_centers=blocked_centers,
            )

            if not selected:
                messagebox.showinfo(
                    "Generate FCS Zones",
                    "No fuel collection zones met the current density settings."
                )
                return

            push_undo()
            removed = 0

            if replace_existing:
                for name in list(existing_objects.keys()):
                    obj = existing_objects.get(name, {})
                    if str(obj.get("type", "")).strip().lower() != FCS_ZONE_TYPE:
                        continue
                    del existing_objects[name]
                    removed += 1
                for name in list(terrain_store.keys()):
                    feat = terrain_store.get(name, {})
                    if not isinstance(feat, dict):
                        continue
                    if str(feat.get("type", "")).strip().lower() != FCS_ZONE_TYPE:
                        continue
                    del terrain_store[name]
                    removed += 1

            created = []
            used_names = set(existing_objects.keys()) | set(terrain_store.keys())
            for zone in selected:
                name = generate_zone_name(used_names, FCS_ZONE_TYPE)
                terrain_store[name] = {
                    "type": FCS_ZONE_TYPE,
                    "coordinate": [zone["x"], 0, zone["z"]],
                    "radius": zone_radius,
                    "description": DEFAULT_FCS_DESCRIPTION,
                    "hideonmap": bool(zone.get("hideonmap", False)),
                }
                used_names.add(name)
                created.append(name)

            dlg.destroy()
            _refresh_ui()

        def _cancel():
            dlg.destroy()

        toolbar.footer_buttons(
            footer,
            [
                ("Generate", _apply, {"width": 12}),
                ("Cancel", _cancel, {"width": 12}),
            ]
        )
        dlg.protocol("WM_DELETE_WINDOW", _cancel)

    # ─── Meta Ribbon ────────────────────────────────────────────────────
    button_frame = tk.Frame(frame)
    # span all columns and allow horizontal expansion
    button_frame.grid(row=row+2, column=0, columnspan=8, sticky='ew', pady=2)
    side_colour_view_var = tk.BooleanVar(value=False)

    def toggle_side_colour_view():
        try:
            draw_map(ctx)
        except NameError:
            pass

    # define each action
    actions = [
        ("Save All Changes", save_all),
        ("Reload",           reload_all),
        ("Load Different System", load_different_system),
        ("Undo",             do_undo),
        ("Redo",             do_redo),
        ("Verify System",    verify_system_data),
        ("Generate Terrain", generate_terrain),
        ("Generate FCS Zones", generate_fcs_zones),
        ("Stations Overview", show_station_list),
        ("Info",             show_info),
    ]
    # pack buttons side-by-side with minimal spacing
    for (label, cmd) in actions:
        tk.Button(button_frame, text=label, command=cmd)\
            .pack(side='left', padx=2, pady=2)

    # ─── Close/Exit handling with unsaved-changes prompt ─────────────────────
    # ─── Close/Exit handling with unsaved-changes prompt ─────────────────────
    def on_close():
        if confirm_pending_changes("closing"):
            win.destroy()

    # Toolbar: replace in-lined ribbon with external module
    toolbar_frame = tk.Frame(frame)
    toolbar_frame.grid(row=row+3, column=0, columnspan=5, pady=(5,0), sticky='we')
    # first create the map canvas,
    map_canvas = tk.Canvas(win, width=600, height=600, bg='black')
    map_canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=5)
    # Editor-only: grid mode cycling (press 'g' while the map has focus)
    grid_mode_index = 0
    def cycle_grid_mode(event=None):
        if event is not None:
            try:
                if event.widget.winfo_toplevel() != win:
                    return
            except Exception:
                return
        nonlocal grid_mode_index
        grid_mode_index = (grid_mode_index + 1) % len(GRID_MODES)
        mode = GRID_MODES[grid_mode_index]
        draw_map(ctx)
    map_canvas.bind('<g>', cycle_grid_mode)


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
    tk.Checkbutton(
        toolbar_frame,
        text="Side Colours",
        variable=side_colour_view_var,
        command=toggle_side_colour_view,
    ).pack(side=tk.LEFT, padx=(10, 2), pady=2)

    # bind resize (unchanged)

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
        return draw_system_map(
            ctx, side_colour_view_var=side_colour_view_var,
            grid_mode_index=grid_mode_index, race_to_faction_cf=race_to_faction_cf,
            valid_hull_keys=valid_hull_keys, terrain_keys=terrain_keys,
        )

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
        relay_store = sm.data.setdefault('sensor_relay', {})
        relay_data = ensure_relay_dict(relay_store.get(name))
        relay_store[name] = relay_data
        set_selection('relay', name)
        coord = relay_data.get('coordinate', [0, 0, 0])
        update_coord_display(coord, False)
        clear_edit_pane()
        edit_title.config(text=f"Relay: {name}")

        tk.Label(edit_frame, text="X:", wraplength=230, justify='left').pack(anchor='w', pady=2)
        build_field(edit_frame, relay_data['coordinate'][0], lambda v: relay_data['coordinate'].__setitem__(0, v))
        tk.Label(edit_frame, text="Z:", wraplength=230, justify='left').pack(anchor='w', pady=2)
        build_field(edit_frame, relay_data['coordinate'][2], lambda v: relay_data['coordinate'].__setitem__(2, v))

        tk.Label(edit_frame, text="Type:", wraplength=230, justify='left').pack(anchor='w', pady=2)
        relay_type_var = tk.StringVar(value=normalize_relay_type(relay_data.get('type')))
        type_cb = ttk.Combobox(
            edit_frame,
            textvariable=relay_type_var,
            values=RELAY_TYPE_OPTIONS,
            state='readonly'
        )
        type_cb.pack(anchor='w', pady=2)

        warning_frame = tk.Frame(edit_frame)
        warning_frame.pack(anchor='w', fill='x')

        def render_warning_fields():
            for child in warning_frame.winfo_children():
                child.destroy()
            if relay_data.get('type') != RELAY_TYPE_WARNING_BUOY:
                return
            tk.Label(warning_frame, text="Broadcast:", wraplength=230, justify='left').pack(anchor='w', pady=2)
            build_field(warning_frame, relay_data.get('broadcast', ''), lambda v: relay_data.__setitem__('broadcast', v))
            tk.Label(warning_frame, text="Ping:", wraplength=230, justify='left').pack(anchor='w', pady=2)
            build_field(
                warning_frame,
                int(relay_data.get('ping', WARNING_BUOY_DEFAULT_PING)),
                lambda v: relay_data.__setitem__('ping', int(v))
            )
            tk.Label(warning_frame, text="Range:", wraplength=230, justify='left').pack(anchor='w', pady=2)
            build_field(
                warning_frame,
                int(relay_data.get('range', WARNING_BUOY_DEFAULT_RANGE)),
                lambda v: relay_data.__setitem__('range', int(v))
            )

        def apply_relay_type(*_):
            relay_type = normalize_relay_type(relay_type_var.get())
            relay_data['type'] = relay_type
            if relay_type == RELAY_TYPE_WARNING_BUOY:
                relay_data.setdefault('broadcast', '')
                relay_data.setdefault('ping', WARNING_BUOY_DEFAULT_PING)
                relay_data.setdefault('range', WARNING_BUOY_DEFAULT_RANGE)
            else:
                relay_data.pop('broadcast', None)
                relay_data.pop('ping', None)
                relay_data.pop('range', None)
            render_warning_fields()

        relay_type_var.trace_add('write', apply_relay_type)
        apply_relay_type()

        tk.Label(edit_frame, text="Description:", wraplength=230, justify='left').pack(anchor='w', pady=2)
        desc_text = tk.Text(edit_frame, height=4, width=30)
        desc_text.insert('1.0', relay_data.get('description', ''))
        desc_text.pack(anchor='w', pady=2)
        register_text_widget(desc_text, lambda value: relay_data.__setitem__('description', value))

        tk.Button(edit_frame, text="Rename", command=lambda: rename_relay(name)).pack(pady=5)
        tk.Button(edit_frame, text="Delete", fg="red", command=lambda: delete_relay(name)).pack(pady=5)

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
        'side_colour_view_var': side_colour_view_var,
        'valid_hulls': valid_hulls,
        'valid_planet_classes': valid_planet_classes,
        'hull_ranges': hull_ranges,
        'hull_side_map': hull_side_map,
        'hull_role_map': hull_role_map,
        'hull_category_map': hull_category_map,
        'align_var': align_var,
        'show_relay': show_relay,
        'show_object': show_object,
        'show_terrain': show_terrain,
        'draw_map': draw_map,
        'drag_data': drag_data,
        'system_files': system_files,
        'other_gate_index': other_gate_index,
        'current_system_filename': filename,
        # placeholders; filled just below with closures bound to this ctx
        'screen_to_coord': None,
        'coord_to_screen': None,
        'win': win,
        'pan_x': pan_x,
        'pan_y': pan_y,
        'map_scale': map_scale,
        'push_undo':  push_undo,
        'copy_state': copy_state
    }

    # Create transform functions that always read the *current* pan/zoom from ctx.
    # Using closures here avoids the default-arg capture bug that set _ctx=None.
    def _make_transforms(_ctx):
        def coord_to_screen(x, z):
            return (
                x * _ctx['map_scale'] + _ctx['pan_x'],
               -z * _ctx['map_scale'] + _ctx['pan_y']
            )
        def screen_to_coord(sx, sy):
            return (
                (sx - _ctx['pan_x']) / _ctx['map_scale'],
               -(sy - _ctx['pan_y']) / _ctx['map_scale']
            )
        return coord_to_screen, screen_to_coord
    _cts, _stc = _make_transforms(ctx)
    ctx['coord_to_screen'], ctx['screen_to_coord'] = _cts, _stc

    _orig_push_undo = ctx['push_undo']
    def _guarded_push_undo():
        if ctx.get('undo_enabled', False):
            _orig_push_undo()
    ctx['push_undo'] = _guarded_push_undo
    ctx['undo_enabled'] = False


    def on_map_press(event):
        map_canvas.focus_set()
        SysMapCanvas.on_canvas_press(event, ctx)

    map_canvas.bind('<ButtonPress-1>', on_map_press)
    map_canvas.bind('<ButtonPress-3>', on_map_press)
    map_canvas.bind('<B1-Motion>', lambda e, _ctx=ctx: SysMapCanvas.on_canvas_drag(e, _ctx))
    map_canvas.bind('<ButtonRelease-1>', on_canvas_release)
    map_canvas.bind('<MouseWheel>', lambda e, _ctx=ctx: SysMapCanvas.on_map_zoom(e, _ctx))
    map_canvas.bind('<Configure>', on_canvas_resize)
    draw_map(ctx)


    # Now that the initial draw & UI wiring are complete, enable undo.
    # Also ensure stacks are pristine so close dialog won't trigger until a real edit.
    try:
        undo_stack.clear()
    except Exception:
        pass
    try:
        redo_stack.clear()
    except Exception:
        pass
    ctx['undo_enabled'] = True

    # (Optional) clear any selection in the objects list after first draw
    try: obj_lb.selection_clear(0, tk.END)
    except Exception: pass
    # Hook window-close protocol
    win.protocol("WM_DELETE_WINDOW", on_close)
    win.confirm_pending_changes = confirm_pending_changes
    win.system_file_path = str(Path(file_path).resolve())

    # Run validation once the editor window is up
    validate_and_report()
    refresh_objects_list()
    mark_saved()
    return win
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
