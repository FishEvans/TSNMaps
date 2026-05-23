#import os
import os
import argparse
import sys
import json
import datetime
import ast
from pathlib import Path
#import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
from typing import Any, Dict, List, Optional, Tuple
from Toolbar import *
import SysMapCanvas
import math
from math import hypot
import random
import copy
from PIL import Image, ImageTk
import re
import SystemMetaOptions as smopts

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
    "Data Chip",
    "Data Core",
    "Vaccine",
    "Virus",
    "Virus Sample",
}
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


STATION_OR_PLATFORM_TYPES = {"station", "platform"}
INCOMING_ONLY_GATES_KEY = "incomingOnlyGates"
INCOMING_ONLY_GATES_ALIASES = (INCOMING_ONLY_GATES_KEY, "incoming_only_gates")


def object_has_blank_or_invalid_hull(obj: Any, valid_hull_keys: set) -> bool:
    if not isinstance(obj, dict):
        return False
    if str(obj.get("type", "")).strip().lower() not in STATION_OR_PLATFORM_TYPES:
        return False
    hull = str(obj.get("hull", "") or "").strip()
    if not hull:
        return True
    return bool(valid_hull_keys) and hull.casefold() not in valid_hull_keys


def draw_red_cross(canvas, sx, sy, radius=8, width=3, tags=()):
    canvas.create_line(
        sx - radius, sy - radius, sx + radius, sy + radius,
        fill="red", width=width, tags=tags
    )
    canvas.create_line(
        sx - radius, sy + radius, sx + radius, sy - radius,
        fill="red", width=width, tags=tags
    )


def get_incoming_only_gate_list(data: Any) -> List[str]:
    meta = data.get("metadata", {}) if isinstance(data, dict) else {}
    if not isinstance(meta, dict):
        return []

    cleaned = []
    seen = set()
    for key in INCOMING_ONLY_GATES_ALIASES:
        raw_names = meta.get(key, [])
        if isinstance(raw_names, str):
            raw_names = [raw_names]
        if not isinstance(raw_names, (list, tuple, set)):
            continue
        for name in raw_names:
            gate_name = str(name or "").strip()
            gate_key = gate_name.casefold()
            if not gate_name or gate_key in seen:
                continue
            cleaned.append(gate_name)
            seen.add(gate_key)
    return cleaned


def get_incoming_only_gate_names(data: Any) -> set:
    return {name.casefold() for name in get_incoming_only_gate_list(data)}


def set_incoming_only_gate(data: Dict[str, Any], gate_name: str, enabled: bool) -> None:
    md = data.setdefault("metadata", {})
    if not isinstance(md, dict):
        md = {}
        data["metadata"] = md

    cleaned_name = str(gate_name or "").strip()
    existing = get_incoming_only_gate_list(data)
    existing_keys = {name.casefold() for name in existing}
    gate_key = cleaned_name.casefold()

    if enabled and cleaned_name and gate_key not in existing_keys:
        existing.append(cleaned_name)
    elif not enabled:
        existing = [name for name in existing if name.casefold() != gate_key]

    for key in INCOMING_ONLY_GATES_ALIASES:
        md.pop(key, None)
    if existing:
        md[INCOMING_ONLY_GATES_KEY] = existing


def rename_incoming_only_gate(data: Dict[str, Any], old_name: str, new_name: str) -> None:
    cleaned_new = str(new_name or "").strip()
    old_key = str(old_name or "").strip().casefold()
    if not old_key or not cleaned_new:
        return

    existing = get_incoming_only_gate_list(data)
    changed = False
    renamed = []
    seen = set()
    for name in existing:
        candidate = cleaned_new if name.casefold() == old_key else name
        candidate_key = candidate.casefold()
        if candidate_key in seen:
            changed = True
            continue
        renamed.append(candidate)
        seen.add(candidate_key)
        changed = changed or candidate != name

    if changed:
        md = data.setdefault("metadata", {})
        if isinstance(md, dict):
            for key in INCOMING_ONLY_GATES_ALIASES:
                md.pop(key, None)
            if renamed:
                md[INCOMING_ONLY_GATES_KEY] = renamed


def remove_incoming_only_gate(data: Dict[str, Any], gate_name: str) -> None:
    set_incoming_only_gate(data, gate_name, False)


def draw_blue_gate_ring(canvas, sx, sy, radius=14, width=2, tags=()):
    canvas.create_oval(
        sx - radius, sy - radius, sx + radius, sy + radius,
        outline="#3aa7ff", width=width, tags=tags
    )


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

def distance_to_spine(px, pz, ax, az, bx, bz):
    abx = bx - ax
    abz = bz - az
    apx = px - ax
    apz = pz - az

    ab_len_sq = abx * abx + abz * abz
    if ab_len_sq == 0:
        return math.hypot(apx, apz)

    # NOTE: no clamping → ends fade naturally
    t = (apx * abx + apz * abz) / ab_len_sq
    cx = ax + t * abx
    cz = az + t * abz

    return math.hypot(px - cx, pz - cz)


def influence(dist, radius):
    if dist >= radius:
        return 0.0
    x = 1.0 - (dist / radius)
    return x * x


def generate_line_coords(start, end, count, radius, seed=None, y_range=(-600, 600),
                         clumps=(), voids=()):
    # Match the reference TerrainHandling.generateLineCoords placement so the
    # editor preview uses the same asteroid/nebula dot distribution as runtime.
    rng = random.Random(seed)
    coords = []

    dx = end[0] - start[0]
    dz = end[2] - start[2]
    length = math.hypot(dx, dz)

    if length == 0:
        return []

    for _ in range(count):
        # Position uniformly along the terrain spine.
        t = rng.random()
        cx = start[0] + t * dx
        cz = start[2] + t * dz

        # Scatter with the same Gaussian-style radial falloff as the reference.
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


def distance_sq_2d(ax, az, bx, bz):
    dx = ax - bx
    dz = az - bz
    return dx * dx + dz * dz


def percentile_value(values, percentile):
    if not values:
        return 0.0
    pct = max(0.0, min(100.0, float(percentile)))
    ordered = sorted(float(v) for v in values)
    if len(ordered) == 1:
        return ordered[0]
    index = int((len(ordered) - 1) * (pct / 100.0))
    index = max(0, min(len(ordered) - 1, index))
    return ordered[index]


def jittered_fcs_spacing(candidate, base_spacing, jitter_ratio=DEFAULT_FCS_SPACING_JITTER):
    """
    Return a deterministic spacing value for a candidate so repeated runs stay stable.
    """
    base_spacing = max(1.0, float(base_spacing))
    jitter_ratio = max(0.0, float(jitter_ratio))
    key = f"{candidate['source']}|{float(candidate['x']):.3f}|{float(candidate['z']):.3f}"
    rng = random.Random(key)
    factor = 1.0 + rng.uniform(-jitter_ratio, jitter_ratio)
    return base_spacing * max(0.01, factor)


def collect_nebula_points_for_fcs(terrain_data, cache=None):
    nebula_points = []
    if not isinstance(terrain_data, dict):
        return nebula_points

    cache_dict = cache if isinstance(cache, dict) else None

    for key, feat in terrain_data.items():
        if not isinstance(feat, dict):
            continue
        if str(feat.get("type", "")).strip().lower() != "nebulas":
            continue

        start = feat.get("start", [0, 0, 0])
        end = feat.get("end", [0, 0, 0])
        density = int(feat.get("density", 0) or 0)
        scatter = float(feat.get("scatter", 0) or 0)
        seed = feat.get("seed")
        hide_on_map = bool(feat.get("hideonmap", False))

        if density <= 0 or scatter <= 0:
            continue
        if not (isinstance(start, (list, tuple)) and isinstance(end, (list, tuple))):
            continue
        if len(start) < 3 or len(end) < 3:
            continue

        cache_key = (
            "nebulas",
            tuple(start),
            tuple(end),
            float(scatter),
            int(density),
            seed,
        )
        cache_token = (key, cache_key)
        coords = cache_dict.get(cache_token) if cache_dict is not None else None
        if coords is None:
            coords = generate_line_coords(start, end, density, scatter, seed=seed)
            if cache_dict is not None:
                cache_dict[cache_token] = coords

        for gx, _, gz in coords:
            nebula_points.append((float(gx), float(gz), key, hide_on_map))

    return nebula_points


def collect_fcs_blocked_centers(system_data, replace_existing=False):
    blocked = []
    if not isinstance(system_data, dict):
        return blocked

    if replace_existing:
        return blocked

    objects = system_data.get("objects", {})
    if isinstance(objects, dict):
        for obj in objects.values():
            if not isinstance(obj, dict):
                continue
            if str(obj.get("type", "")).strip().lower() != FCS_ZONE_TYPE:
                continue
            coord = obj.get("coordinate")
            if isinstance(coord, (list, tuple)) and len(coord) >= 3:
                blocked.append((float(coord[0]), float(coord[2])))

    terrain_data = system_data.get("terrain", {})
    if isinstance(terrain_data, dict):
        for feat in terrain_data.values():
            if not isinstance(feat, dict):
                continue
            if str(feat.get("type", "")).strip().lower() != FCS_ZONE_TYPE:
                continue
            coord = feat.get("coordinate")
            if isinstance(coord, (list, tuple)) and len(coord) >= 3:
                blocked.append((float(coord[0]), float(coord[2])))

    return blocked


def generate_zone_name(existing_objects, zone_type=FCS_ZONE_TYPE):
    prefix = "ZONE"
    zone_key = str(zone_type or "").strip().lower()
    if zone_key == FCS_ZONE_TYPE:
        prefix = "FCS"
    elif zone_key.endswith("_zone"):
        candidate_prefix = zone_key[:-5].replace("_", "").upper()
        if candidate_prefix:
            prefix = candidate_prefix

    if isinstance(existing_objects, dict):
        existing_names = {str(name) for name in existing_objects.keys()}
    else:
        existing_names = {str(name) for name in (existing_objects or [])}

    pattern = re.compile(rf'^{re.escape(prefix)}\s*(\d+)$', re.IGNORECASE)
    used_numbers = []
    for name in existing_names:
        match = pattern.match(name.strip())
        if not match:
            continue
        try:
            used_numbers.append(int(match.group(1)))
        except ValueError:
            continue

    next_value = (max(used_numbers) + 1) if used_numbers else 1
    candidate = f"{prefix}{next_value}"
    while candidate in existing_names:
        next_value += 1
        candidate = f"{prefix}{next_value}"
    return candidate


def select_fcs_zone_centers(points, min_spacing=DEFAULT_FCS_MIN_SPACING,
                            density_radius=DEFAULT_FCS_DENSITY_RADIUS,
                            percentile=DEFAULT_FCS_DENSITY_PERCENTILE,
                            min_score=DEFAULT_FCS_MIN_SCORE,
                            blocked_centers=()):
    """
    Pick zone centers from nebula dots using local point density.

    Points are scored by nearby dot concentration, then greedily selected with a
    minimum center-to-center spacing so zones track dense clusters without
    piling into the same pocket.
    """
    if not points:
        return []

    min_spacing = max(1.0, float(min_spacing))
    density_radius = max(1.0, float(density_radius))
    cell_size = density_radius
    radius_sq = density_radius * density_radius
    min_spacing_sq = min_spacing * min_spacing

    grid = {}
    for idx, (x, z, source_key, source_hidden) in enumerate(points):
        cell_key = (int(math.floor(x / cell_size)), int(math.floor(z / cell_size)))
        grid.setdefault(cell_key, []).append(idx)

    candidates = []
    raw_scores = []

    for idx, (x, z, source_key, source_hidden) in enumerate(points):
        gx = int(math.floor(x / cell_size))
        gz = int(math.floor(z / cell_size))
        score = 0.0
        weighted_x = 0.0
        weighted_z = 0.0

        for dx in (-1, 0, 1):
            for dz in (-1, 0, 1):
                for other_idx in grid.get((gx + dx, gz + dz), []):
                    ox, oz, _, _ = points[other_idx]
                    dist_sq = distance_sq_2d(x, z, ox, oz)
                    if dist_sq > radius_sq:
                        continue
                    weight = 1.0 - (dist_sq / radius_sq)
                    score += weight
                    weighted_x += ox * weight
                    weighted_z += oz * weight

        if score <= 0:
            continue

        raw_scores.append(score)
        candidates.append({
            "score": float(score),
            "x": float(weighted_x / score),
            "z": float(weighted_z / score),
            "source": source_key,
            "hideonmap": bool(source_hidden),
        })

    if not candidates:
        return []

    threshold = max(float(min_score), percentile_value(raw_scores, percentile))
    blocked = [
        {"x": float(x), "z": float(z), "spacing": float(min_spacing)}
        for x, z in blocked_centers
    ]
    selected = []
    selected_signatures = set()

    def _candidate_signature(candidate):
        return (
            candidate["source"],
            round(float(candidate["x"]), 6),
            round(float(candidate["z"]), 6),
        )

    def _try_select_candidate(candidate):
        cx = float(candidate["x"])
        cz = float(candidate["z"])
        candidate_spacing = jittered_fcs_spacing(candidate, min_spacing)
        for blocked_item in blocked:
            bx = float(blocked_item["x"])
            bz = float(blocked_item["z"])
            blocked_spacing = float(blocked_item.get("spacing", min_spacing))
            required_spacing = (candidate_spacing + blocked_spacing) / 2.0
            if distance_sq_2d(cx, cz, bx, bz) < required_spacing * required_spacing:
                return False
        selected.append({
            "x": cx,
            "z": cz,
            "score": float(candidate["score"]),
            "source": candidate["source"],
            "hideonmap": bool(candidate["hideonmap"]),
        })
        blocked.append({
            "x": cx,
            "z": cz,
            "spacing": candidate_spacing,
        })
        selected_signatures.add(_candidate_signature(candidate))
        return True

    candidates_by_source = {}
    for candidate in candidates:
        candidates_by_source.setdefault(candidate["source"], []).append(candidate)

    # Pass 1: try to guarantee one zone per nebula field, unless spacing blocks it.
    source_priority = sorted(
        (
            max(source_candidates, key=lambda item: item["score"])
            for source_candidates in candidates_by_source.values()
        ),
        key=lambda item: item["score"],
        reverse=True,
    )

    for source_head in source_priority:
        source_candidates = sorted(
            candidates_by_source.get(source_head["source"], []),
            key=lambda item: item["score"],
            reverse=True,
        )
        for candidate in source_candidates:
            if _try_select_candidate(candidate):
                break

    # Pass 2: add extra zones only for stronger dense pockets.
    for candidate in sorted(candidates, key=lambda item: item["score"], reverse=True):
        if candidate["score"] < threshold:
            break
        if _candidate_signature(candidate) in selected_signatures:
            continue
        _try_select_candidate(candidate)

    return selected

# valid names: letters, digits, dot, space; 1–20 chars
_VALID_NAME = re.compile(r'^[A-Za-z0-9. ]{1,20}$')
DEFAULT_PLANET_CLASS = 'EarthLike'
RELAY_TYPE_SENSOR = 'Sensor Relay'
RELAY_TYPE_WARNING_BUOY = 'Warning Buoy'
RELAY_TYPE_OPTIONS = [RELAY_TYPE_SENSOR, RELAY_TYPE_WARNING_BUOY]
WARNING_BUOY_DEFAULT_PING = 2
WARNING_BUOY_DEFAULT_RANGE = 15000

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

def get_settings_path():
    base = get_base_path()
    settings_path = os.path.join(base, 'Settings.json')
    try:
        if os.path.isdir(base) and os.access(base, os.W_OK):
            return settings_path
    except Exception:
        pass
    home = os.path.expanduser('~')
    return os.path.join(home, '.tsnmaps', 'Settings.json')

def _load_settings_file(path: str) -> Dict[str, Any]:
    try:
        with open(path, 'r') as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}

def load_editor_settings():
    base_path = os.path.join(get_base_path(), 'Settings.json')
    settings = _load_settings_file(base_path)
    user_path = get_settings_path()
    if os.path.abspath(user_path) != os.path.abspath(base_path):
        user_settings = _load_settings_file(user_path)
        settings.update(user_settings)
    return settings

def save_editor_settings(settings: Dict[str, Any]) -> None:
    path = get_settings_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
    except Exception:
        pass

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
    try:
        with open(path, 'w') as f:
            json.dump(settings, f, indent=4)
    except Exception:
        pass

def _normalize_author_list(value: Any) -> List[str]:
    if value is None:
        return []
    items = []
    if isinstance(value, str):
        items = [x.strip() for x in value.split(',')]
    elif isinstance(value, list):
        items = [str(x).strip() for x in value]
    else:
        return []
    cleaned = []
    seen = set()
    for item in items:
        if not item:
            continue
        key = item.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(item)
    return cleaned

def _coerce_revision_number(value: Any) -> int:
    try:
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str):
            return int(value.strip() or 0)
    except Exception:
        return 0
    return 0

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

def build_gate_index_for_systems(data_base: str, current_filename: str):
    system_files = {}
    other_gate_index = {}
    try:
        filenames = os.listdir(data_base)
    except Exception:
        return system_files, other_gate_index

    for filename in filenames:
        if not filename.endswith('.json'):
            continue
        lowered = filename.lower()
        if lowered in ('package.json', 'galmapinfo.json'):
            continue
        system_name = os.path.splitext(filename)[0]
        system_files[system_name.lower()] = filename
        if current_filename and lowered == current_filename.lower():
            continue
        path = os.path.join(data_base, filename)
        try:
            with open(path, 'r') as f:
                data = json.load(f)
        except Exception:
            continue
        objects = data.get('objects', {})
        if not isinstance(objects, dict):
            continue
        gate_names = set()
        for name, obj in objects.items():
            if not isinstance(obj, dict):
                continue
            otype = str(obj.get('type', '')).lower()
            if otype in ('jumpnode', 'jumppoint', 'jump_point'):
                gate_names.add(name.lower())
        other_gate_index[filename] = gate_names

    if current_filename:
        current_name = os.path.splitext(current_filename)[0]
        system_files.setdefault(current_name.lower(), current_filename)

    return system_files, other_gate_index

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
    undo_stack = []
    redo_stack = []
    current_selection = {'type': None, 'name': None}
    last_desc_widget = None
    last_desc_obj = None
    pending_text_widgets = []
    text_dirty = False
    copy_state = {'source_name': None, 'source_obj': None}
    session_revision_bumped = False
    # base for images, data_base for system JSON files
    base = get_base_path()
    data_base = get_data_path()
    file_path = os.path.join(data_base, filename)
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

    def has_unsaved_changes():
        try:
            return bool(undo_stack) or text_dirty
        except Exception:
            return bool(text_dirty)
    # Load ShipMap for valid hulls and sides
    # ─── Load Cargo/Teams presets and master lists from JSON ─────────────
    try:
        with open(os.path.join(base, 'cargo_teams.json'), 'r') as cf:
            ct_config = json.load(cf)
    except Exception:
        ct_config = {"cargo": [], "teams": [], "presets": {}, "skyboxes": []}
    
    # ─── Load item metadata for icons from tsn_databases.py ─────────────
    try:
        db_path = Path(base) / DATABASE_SOURCE
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
                        if category == 'objects':
                            rename_incoming_only_gate(sm.data, old, new)
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
        # Do NOT push an initial undo state here; we only mark undo after the first real edit.

        # ── Silent side fixes + validation for stations/platforms/static ─────────────
        def validate_and_fix_sides_on_load(_sm: SystemMap):
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
            for obj_name in _sm.list_objects():
                obj = _sm.get_object(obj_name)
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
                _sm.save()
            if issues:
                # inform user once after load
                msg = "Objects with invalid side values:\n\n" + "\n".join(issues)
                try:
                    messagebox.showwarning("Side Validation", msg)
                except Exception:
                    print(msg)

        def validate_and_fix_planet_classes_on_load(_sm: SystemMap):
            valid_class_set = set(valid_planet_classes)
            changed = False
            issues = []
            for terrain_key, feat in _sm.data.get('terrain', {}).items():
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
                _sm.save()
            if issues:
                msg = "Planets with invalid class values:\n\n" + "\n".join(issues)
                try:
                    messagebox.showwarning("Planet Class Validation", msg)
                except Exception:
                    print(msg)

        validate_and_fix_planet_classes_on_load(sm)
        validate_and_fix_sides_on_load(sm)
        system_files, other_gate_index = build_gate_index_for_systems(data_base, filename)

    except Exception as e:
        messagebox.showerror("Error", f"Failed to load system map: {e}")
        return("Error", f"Failed to load system map: {e}")
        return

    def push_undo():
        if sm is None:
            return
        undo_stack.append(copy.deepcopy(sm.data))
        # cap at 5
        if len(undo_stack) > 5:
            undo_stack.pop(0)
        # any new action invalidates redo history
        redo_stack.clear()

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
    skybox_var.trace_add('write', lambda *a: md.__setitem__('skybox', skybox_var.get()))
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
        try:
            entered = simpledialog.askstring(
                "Author",
                "Enter your author name for this session:",
                parent=win
            )
        except Exception:
            entered = None
        if entered is not None:
            author_var.set(entered.strip())
            persist_author_setting()

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
            'write', lambda *a, c=cat, v=var: traffic.__setitem__(c, v.get())
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
    def _az09_key(name: str):
        if name is None:
            return (1, "")
        s = str(name)
        return (1 if (s[:1].isdigit()) else 0, s.casefold())

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

    def do_undo():
        if not undo_stack:
            win.bell()
            return
        redo_stack.append(copy.deepcopy(sm.data))
        state = undo_stack.pop()
        sm.data = state
        _refresh_ui()

    def do_redo():
        if not redo_stack:
            win.bell()
            return
        undo_stack.append(copy.deepcopy(sm.data))
        state = redo_stack.pop()
        sm.data = state
        _refresh_ui()

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
        # Track selection type and name
        set_selection(kind.lower(), key)
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
        remove_incoming_only_gate(sm.data, obj_name)
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
            win.bell()
            return
        if new_name != name:
            push_undo()
            sm.data['objects'][new_name] = sm.data['objects'].pop(name)
            rename_incoming_only_gate(sm.data, name, new_name)
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
                with open(os.path.join(base, 'cargo_teams.json'), 'w', encoding='utf-8') as cf:
                    json.dump(ct_config, cf, indent=4)
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
    # Adapter: show_object via generic helper
    def arm_copy_object(name: str, obj: Dict[str, Any]) -> None:
        copy_state['source_name'] = name
        copy_state['source_obj'] = copy.deepcopy(obj)

    def show_object(name: str):
        nonlocal last_desc_widget, last_desc_obj
        obj = sm.get_object(name)
        if not win.winfo_exists():
            return
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
            edit_title.config(text=f"Platform: {name}")
            side_var, _, _ = _build_faction_side_controls(edit_frame, obj, layout='pack')

            # Hull dropdown (include hulls with role 'platform' or 'defense')
            tk.Label(edit_frame, text="Hull:").pack(anchor='w', pady=2)
            hull_var = tk.StringVar(value=obj.get('hull',''))
            platform_hulls = SysMapCanvas._filter_hulls_by_roles(
                valid_hulls, {'platform', 'static', 'defense'}, hull_role_map, hull_category_map
            )
            hull_cb = ttk.Combobox(
                edit_frame,
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
                edit_frame, text="Show all hulls",
                variable=show_all_var
            ).pack(anchor='w', pady=(2, 0))
            tk.Checkbutton(
                edit_frame, text="Relax role filter",
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
            frm = tk.Frame(edit_frame)
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
            sm.set_system_map_coord([float(var.get()) for var in coord_vars])
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
            # Persist to disk
            sm.save()
            if bumped_this_save:
                session_revision_bumped = True
            refresh_author_metadata_display(md)
            # Mark as clean (no unsaved changes)
            # Using the project's definition: "unsaved" ≙ undo list has entries.
            # After a successful save, clear undo/redo so close won't warn.
            try:
                undo_stack.clear()
                redo_stack.clear()
            except Exception:
                pass
            text_dirty = False
            # Inform user with a sound only (no popup)
            try:
                win.bell()
            except Exception:
                pass
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

   # ─── Reload button (clear & reload from disk) ──────────────────
    def reload_all():
        nonlocal sm, text_dirty
        try:
            clear_edit_pane()
            # re-instantiate from file
            sm = SystemMap(file_path)
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
            skybox_var.set(md.get('skybox', '') or skybox_var.get())

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
            draw_map(ctx)
            text_dirty = False
        except Exception as e:
            messagebox.showerror("Error", f"Reload failed: {e}")
            return
        # Re-run validation after a reload
        validate_and_report()
        validate_and_fix_planet_classes_on_load(sm)
        validate_and_fix_sides_on_load(sm)
        # Refresh object list ordering/coloring after reload

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

    def collect_cargo_team_validation_issues():
        cargo_set = set(ct_config.get('cargo', []))
        team_set  = set(ct_config.get('teams', []))
        issues    = []
        # Nothing to validate against? Skip quietly.
        if not cargo_set and not team_set:
            return issues
        objects = sm.data.get('objects', {})
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
        errors = []
        warnings = []

        try:
            encoded = json.dumps(sm.data, indent=4, allow_nan=False)
            decoded = json.loads(encoded)
            if not isinstance(decoded, dict):
                errors.append("JSON round-trip did not produce an object at the root.")
        except Exception as exc:
            errors.append(f"Current system data cannot be serialized as valid JSON: {exc}")
            show_validation_results("Verify System", errors, warnings)
            return

        if not isinstance(sm.data, dict):
            errors.append("System root must be a JSON object.")
            show_validation_results("Verify System", errors, warnings)
            return

        system_coord = sm.data.get('systemMapCoord')
        validate_coordinate_value(system_coord, "systemMapCoord", errors)

        metadata = sm.data.get('metadata', {})
        if metadata is not None and not isinstance(metadata, dict):
            errors.append("metadata must be a JSON object when present.")

        objects = sm.data.get('objects', {})
        if not isinstance(objects, dict):
            errors.append("objects must be a JSON object.")
            objects = {}

        terrain_data = sm.data.get('terrain', {})
        if not isinstance(terrain_data, dict):
            errors.append("terrain must be a JSON object.")
            terrain_data = {}

        relay_data = sm.data.get('sensor_relay', {})
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
        incoming_only_gate_list = get_incoming_only_gate_list(sm.data)
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

        warnings.extend(collect_cargo_team_validation_issues())
        show_validation_results("Verify System", errors, warnings)

    def show_station_list():
        list_win = tk.Toplevel(win)
        list_win.title("Stations Overview")
        list_win.transient(win)

        tk.Label(list_win, text="Click a station name to edit cargo/teams.").pack(anchor='w', padx=8, pady=(8, 0))

        container = tk.Frame(list_win)
        container.pack(fill='both', expand=True, padx=8, pady=8)

        canvas = tk.Canvas(container, highlightthickness=0)
        vsb = ttk.Scrollbar(container, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        canvas.grid(row=0, column=0, sticky='nsew')
        vsb.grid(row=0, column=1, sticky='ns')
        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)

        rows_frame = tk.Frame(canvas)
        rows_id = canvas.create_window((0, 0), window=rows_frame, anchor='nw')

        def _sync_scrollregion(event=None):
            canvas.configure(scrollregion=canvas.bbox('all'))

        def _sync_width(event):
            canvas.itemconfigure(rows_id, width=event.width)

        rows_frame.bind("<Configure>", _sync_scrollregion)
        canvas.bind("<Configure>", _sync_width)

        type_values = ['station', 'platform']
        platform_hulls = [
            e['key'] for e in ship_entries
            if any(
                role in ('platform', 'defense')
                for role in (
                    e.get('roles')
                    if isinstance(e.get('roles'), list)
                    else [r.strip() for r in e.get('roles', '').split(',') if r.strip()]
                )
            )
        ]
        platform_hulls = sorted(platform_hulls)

        def has_cargo(obj):
            cargo = obj.get('cargo') or {}
            for qty in cargo.values():
                try:
                    if int(qty) > 0:
                        return True
                except Exception:
                    if qty:
                        return True
            return False

        def open_ct_dialog(obj_name):
            open_cargo_teams_dialog(obj_name)
            build_rows()
            refresh_objects_list()

        def build_rows():
            for child in rows_frame.winfo_children():
                child.destroy()

            for idx, minsize in enumerate((200, 110, 180, 280, 120)):
                rows_frame.grid_columnconfigure(idx, minsize=minsize, weight=0)
            rows_frame.grid_columnconfigure(0, weight=1)
            rows_frame.grid_columnconfigure(3, weight=1)

            tk.Label(rows_frame, text="Name", font=('Arial', 9, 'bold')).grid(row=0, column=0, sticky='w', padx=2, pady=(0, 4))
            tk.Label(rows_frame, text="Type", font=('Arial', 9, 'bold')).grid(row=0, column=1, sticky='w', padx=2, pady=(0, 4))
            tk.Label(rows_frame, text="Hull", font=('Arial', 9, 'bold')).grid(row=0, column=2, sticky='w', padx=2, pady=(0, 4))
            tk.Label(rows_frame, text="Facilities", font=('Arial', 9, 'bold')).grid(row=0, column=3, sticky='w', padx=2, pady=(0, 4))
            tk.Label(rows_frame, text="Cargo/Teams", font=('Arial', 9, 'bold')).grid(row=0, column=4, sticky='w', padx=2, pady=(0, 4))

            entries = []
            for obj_name in sm.list_objects():
                obj = sm.get_object(obj_name)
                otype = str(obj.get('type', '')).lower()
                if otype not in ('station', 'platform'):
                    continue
                entries.append((obj_name, obj))
            entries.sort(key=lambda item: _az09_key(item[0]))

            if not entries:
                tk.Label(rows_frame, text="No stations or platforms found.").grid(row=1, column=0, columnspan=5, sticky='w', padx=2, pady=4)
                return

            row = 1
            for obj_name, obj in entries:
                otype = str(obj.get('type', '')).lower()
                if otype not in ('station', 'platform'):
                    otype = 'station'

                name_lbl = tk.Label(rows_frame, text=obj_name, cursor='hand2')
                if not has_cargo(obj):
                    name_lbl.configure(fg='red')
                name_lbl.grid(row=row, column=0, sticky='w', padx=2, pady=2)
                name_lbl.bind("<Button-1>", lambda e, n=obj_name: open_ct_dialog(n))

                type_var = tk.StringVar(value=otype)
                type_cb = ttk.Combobox(rows_frame, textvariable=type_var, values=type_values, state='readonly', width=10)
                type_cb.grid(row=row, column=1, sticky='w', padx=2, pady=2)

                hull_var = tk.StringVar(value=obj.get('hull', ''))
                hull_vals = platform_hulls if type_var.get() == 'platform' else valid_hulls
                hull_cb = ttk.Combobox(rows_frame, textvariable=hull_var, values=hull_vals, state='readonly', width=16)
                hull_cb.grid(row=row, column=2, sticky='w', padx=2, pady=2)

                def apply_overview_hull(*_, o=obj, v=hull_var):
                    o['hull'] = v.get()
                    draw_map(ctx)

                hull_var.trace_add('write', apply_overview_hull)

                fac_frame = tk.Frame(rows_frame)
                fac_frame.grid(row=row, column=3, sticky='w', padx=2, pady=2)
                facs = obj.get('facilities', [])
                dock_var = tk.BooleanVar(value="Docking" in facs)
                refuel_var = tk.BooleanVar(value="Refuel" in facs)
                repair_var = tk.BooleanVar(value="Repair" in facs)

                def apply_facilities(o=obj, dv=dock_var, rv=refuel_var, pv=repair_var):
                    new_list = []
                    if dv.get():
                        new_list.append("Docking")
                    if rv.get():
                        new_list.append("Refuel")
                    if pv.get():
                        new_list.append("Repair")
                    o['facilities'] = new_list

                dock_cb = tk.Checkbutton(fac_frame, text="Docking", variable=dock_var, command=apply_facilities)
                refuel_cb = tk.Checkbutton(fac_frame, text="Refuel", variable=refuel_var, command=apply_facilities)
                repair_cb = tk.Checkbutton(fac_frame, text="Repair", variable=repair_var, command=apply_facilities)
                dock_cb.pack(side='left')
                refuel_cb.pack(side='left')
                repair_cb.pack(side='left')

                def set_facility_state(enabled, dcb=dock_cb, rcb=refuel_cb, pcb=repair_cb):
                    state = 'normal' if enabled else 'disabled'
                    dcb.configure(state=state)
                    rcb.configure(state=state)
                    pcb.configure(state=state)

                def on_type_change(*_, o=obj, tv=type_var, hv=hull_var, hcb=hull_cb, sfs=set_facility_state):
                    new_type = tv.get()
                    o['type'] = new_type
                    if new_type == 'platform':
                        vals = list(platform_hulls)
                        curr = hv.get()
                        if curr and curr not in vals:
                            vals = [curr] + vals
                        hcb['values'] = vals
                        sfs(False)
                    else:
                        vals = list(valid_hulls)
                        curr = hv.get()
                        if curr and curr not in vals:
                            vals = [curr] + vals
                        hcb['values'] = vals
                        sfs(True)
                    refresh_objects_list()
                    draw_map(ctx)

                type_var.trace_add('write', on_type_change)
                set_facility_state(type_var.get() == 'station')

                tk.Button(rows_frame, text="Edit", command=lambda n=obj_name: open_ct_dialog(n)).grid(
                    row=row, column=4, sticky='w', padx=2, pady=2
                )

                row += 1

        build_rows()

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

    def generate_terrain():
        scripts_dir = os.path.join(base, 'scripts')
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        try:
            import generate_system_terrain as gst
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
        """
        Intercept window close. If there are unsaved changes
        (defined as undo_stack having entries), ask the user:
        - Yes   → Save changes and exit
        - No    → Discard changes and exit
        - Cancel→ Do not close
        """
        has_unsaved = has_unsaved_changes()
        if not has_unsaved:
            win.destroy()
            return
        resp = messagebox.askyesnocancel(
            "Unsaved changes",
            "You have unsaved changes.\n"
            "Save changes before closing?\n\n"
            "Yes = Save & Exit\nNo = Discard Changes\nCancel = Keep Editing"
        )
        if resp is None:
            # Cancel
            return
        if resp:
            # Yes → Save then close (only if save succeeds)
            save_all()
        # For No or after successful save, close the window
        win.destroy()

    # Toolbar: replace in-lined ribbon with external module
    toolbar_frame = tk.Frame(frame)
    toolbar_frame.grid(row=row+3, column=0, columnspan=5, pady=(5,0), sticky='we')
    # first create the map canvas,
    map_canvas = tk.Canvas(win, width=600, height=600, bg='black')
    map_canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=5)
    # Editor-only: grid mode cycling (press 'g' to toggle)
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
        system_files = ctx.get('system_files', {})
        other_gate_index = ctx.get('other_gate_index', {})
        current_filename = ctx.get('current_system_filename', '')
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


    map_canvas.bind('<ButtonPress-1>', lambda e, _ctx=ctx: SysMapCanvas.on_canvas_press(e, _ctx))
    map_canvas.bind('<ButtonPress-3>', lambda e, _ctx=ctx: SysMapCanvas.on_canvas_press(e, _ctx))
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

    # Run validation once the editor window is up
    validate_and_report()
    refresh_objects_list()
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
