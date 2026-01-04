import os
import json
import tkinter as tk
from tkinter import filedialog, Menu, ttk
from PIL import Image, ImageTk
import math
import LocMapGen, GalMapGen
import SystemEditor  # New module for dedicated system editing
import sys
import SystemTemplates
import copy
import re

# Helper to locate resources in bundled or source context
def get_base_path():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))



class SystemMapEditor:
    INITIAL_SCALE = 10000
    ICON_RADIUS = 18000000  # half-size for click detection

    def show_help(self):
        help_text = """
    Stellar Cartography – Help & Controls

    Mouse Controls:
    • Left Click & Drag – Move systems and text nodes
    • Scroll Wheel – Zoom in/out centered at mouse
    • Right Click – Edit system or text properties
    • Left Click (on system) – Open System Editor
    • Shift + Left Click – Open system details / add point to selected border
    • Shift + Right Click – 
       - On a system: open detailed System Editor
       - On empty space: create new text node
       - On border point: remove nearest point

    UI Buttons:
    • Save Changes – Writes all system edits and regenerates maps
    • Zoom In / Out – Adjust zoom level
    • New System – Create a new system at the current view center
    • Help – Show this dialog

    System Editor:
    • Modify alignment, description, exports, threats, assets, etc.
    • Visibility toggle controls map appearance
    """

        top = tk.Toplevel(self.root)
        top.title("Help")
        top.geometry("600x500")

        text = tk.Text(top, wrap="word", bg="black", fg="white", font=("Courier", 10))
        text.insert("1.0", help_text.strip())
        text.config(state="disabled")
        text.pack(expand=True, fill=tk.BOTH)

        tk.Button(top, text="Close", command=top.destroy).pack(pady=5)

    def auto_link_gates(self):
        base = get_base_path()
        systems_dir = os.path.join(base, "data", "missions", "Map Designer", "Terrain")
        if not os.path.isdir(systems_dir):
            print(f"Systems directory not found: {systems_dir}")
            return

        system_files = {}
        system_paths = {}
        for filename in os.listdir(systems_dir):
            if not filename.endswith(".json") or filename == "package.json":
                continue
            system_name = filename[:-5]
            system_files[system_name.lower()] = filename
            system_paths[filename] = os.path.join(systems_dir, filename)

        system_data = {}
        for filename, path in system_paths.items():
            try:
                with open(path, "r") as f:
                    system_data[filename] = json.load(f)
            except (IOError, json.JSONDecodeError):
                print(f"Warning: Could not parse {filename}, skipping.")

        updates = {}
        for filename, data in system_data.items():
            objects = data.get("objects", {})
            if not isinstance(objects, dict):
                continue
            current_system = filename[:-5]
            current_system_lower = current_system.lower()
            for gate_name, gate_data in objects.items():
                if not isinstance(gate_data, dict):
                    continue
                if gate_data.get("type") not in ("jumpnode", "jumppoint"):
                    continue
                destinations = gate_data.get("destinations")
                if isinstance(destinations, dict) and destinations:
                    continue
                words = re.findall(r"[A-Za-z0-9]+", gate_name)
                if not words:
                    continue
                matched = False
                fallback_system = None
                for word in words:
                    candidate_file = system_files.get(word.lower())
                    if not candidate_file:
                        continue
                    if candidate_file.lower() == filename.lower():
                        continue
                    if fallback_system is None:
                        fallback_system = candidate_file
                    candidate_data = system_data.get(candidate_file)
                    if not isinstance(candidate_data, dict):
                        continue
                    candidate_objects = candidate_data.get("objects", {})
                    if not isinstance(candidate_objects, dict):
                        continue
                    for candidate_gate_name, candidate_gate_data in candidate_objects.items():
                        if not isinstance(candidate_gate_data, dict):
                            continue
                        if candidate_gate_data.get("type") not in ("jumpnode", "jumppoint"):
                            continue
                        if current_system_lower in candidate_gate_name.lower():
                            dest_system_name = candidate_file[:-5]
                            gate_data["destinations"] = {candidate_gate_name: dest_system_name}
                            updates.setdefault(filename, []).append(
                                (gate_name, candidate_gate_name, dest_system_name)
                            )
                            matched = True
                            break
                    if matched:
                        break
                if not matched and fallback_system:
                    dest_system_name = fallback_system[:-5]
                    gate_data["destinations"] = {gate_name: dest_system_name}
                    updates.setdefault(filename, []).append(
                        (gate_name, gate_name, dest_system_name)
                    )

        if not updates:
            print("Auto Link Gates: no missing destinations matched.")
            return

        for filename in updates:
            path = system_paths.get(filename)
            if not path:
                continue
            try:
                with open(path, "w") as f:
                    json.dump(system_data[filename], f, indent=4)
            except IOError:
                print(f"Failed to write {filename}")

        for filename, changes in updates.items():
            if filename not in self.systems:
                continue
            jump_points = self.systems[filename].get("jump_points", [])
            for gate_name, dest_gate_name, dest_system_name in changes:
                for jp in jump_points:
                    if jp.get("name") == gate_name:
                        jp["destinations"] = {dest_gate_name: dest_system_name}
                        break

        self.redraw_map()
        total = sum(len(changes) for changes in updates.values())
        print(f"Auto Link Gates: updated {total} gate(s).")

    def reload_systems_data(self):
        self.systems = {}
        self.load_systems()
        self.clear_selection()
        self.redraw_map()
        self.draw_scale()
        print("Systems reloaded.")

    def create_new_system(self):
        top = tk.Toplevel(self.root)
        top.title("Create New System")

        tk.Label(top, text="System Name:").pack()
        name_entry = tk.Entry(top)
        name_entry.pack(fill=tk.X, padx=5)

        tk.Label(top, text="Alignment:").pack()
        align_var = tk.StringVar(value="USFP")
        alignments = sorted({s.get("alignment", "Unknown") for s in self.systems.values()} | {"USFP", "TSN", "Arvonians", "Kraliens", "Torgoth", "Ximni"})
        align_cb = ttk.Combobox(top, textvariable=align_var, values=alignments)
        align_cb.pack(fill=tk.X, padx=5)

        def add_system():
            name = name_entry.get().strip()
            if not name:
                tk.messagebox.showerror("Invalid Input", "System name cannot be empty.")
                return
            filename = f"{name}.json"
            systems_dir = os.path.join(get_base_path(), "data/missions/Map Designer/Terrain")
            file_path = os.path.join(systems_dir, filename)
            if os.path.exists(file_path):
                tk.messagebox.showerror("File Exists", f"{filename} already exists.")
                return

            # Copy and modify template
            template = copy.deepcopy(SystemTemplates.new_system_template)
            template["systemalignment"] = align_var.get()

            # Calculate placement at center of view
            self.root.update_idletasks()
            canvas_w = self.canvas.winfo_width()
            canvas_h = self.canvas.winfo_height()
            screen_x = canvas_w / 2
            screen_y = canvas_h / 2
            nx, _, ny = self.screen_to_coord(screen_x, screen_y)
            template["systemMapCoord"] = [nx, 0, ny]

            # Save new file
            with open(file_path, 'w') as f:
                json.dump(template, f, indent=4)

            # Add to in-memory system list
            self.systems[filename] = {
                "coord": [nx, 0, ny],
                "alignment": template["systemalignment"],
                "description": "",
                "security": "Neutral",
                "exports": [],
                "focus": "",
                "intel": {},
                "development": "Unclaimed",
                "visible": True,
                "jump_points": [],
                "canvas_items": [],
                "warning_circle": None,
                "link_lines": [],
                "incoming_lines": []
            }

            self.redraw_map()
            SystemEditor.open_system_editor(file_path)
            top.destroy()

        tk.Button(top, text="Add", command=add_system).pack(pady=10)

    def __init__(self, root):
        self.root = root
        self.root.title("Stellar Cartography")
        control_frame = tk.Frame(root)
        control_frame.pack(side=tk.TOP, fill=tk.X)
        self.selected_text = None
        self.selected_text_index = None
        auto_link_button = tk.Button(control_frame, text="Auto Link Gates", command=self.auto_link_gates)
        auto_link_button.pack(side=tk.LEFT)
        reload_button = tk.Button(control_frame, text="Reload Systems", command=self.reload_systems_data)
        reload_button.pack(side=tk.LEFT)
        save_button = tk.Button(control_frame, text="Save Changes", command=self.save_changes)
        save_button.pack(side=tk.LEFT)

        zoom_in_button = tk.Button(control_frame, text="Zoom In", command=self.zoom_in)
        zoom_in_button.pack(side=tk.LEFT)

        zoom_out_button = tk.Button(control_frame, text="Zoom Out", command=self.zoom_out)
        zoom_out_button.pack(side=tk.LEFT)
        
        new_button = tk.Button(control_frame, text="New System", command=self.create_new_system)
        new_button.pack(side=tk.LEFT)

        help_button = tk.Button(control_frame, text="Help", command=self.show_help)
        help_button.pack(side=tk.LEFT)

        self.drag_data = {"item": None, "x": 0, "y": 0, "panning": False, "dragged": False}
        # Selection state
        self.selected_type = None
        self.selected_id = None
        self.selected_border = None
        self.selected_point_index = None

        self.canvas = tk.Canvas(root, bg="black", width=1200, height=800)
        self.canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self.canvas.bind("<ButtonPress-1>", self.start_pan)
        self.canvas.bind("<B1-Motion>", self.do_pan)
        self.canvas.bind("<ButtonRelease-1>", self.end_pan)
        self.canvas.bind("<MouseWheel>", self.mouse_zoom)
        self.canvas.bind("<Motion>", self.hover_highlight)
        # Shift-click to add/remove border points
        self.canvas.bind("<Shift-Button-1>", self.on_shift_left)
        self.canvas.bind("<Shift-Button-3>", self.on_shift_right)  # right-click
        # Left-click selection handler
        self.canvas.bind("<ButtonRelease-1>", self.on_left_click, add='+')
        # Right-click to edit properties
        self.canvas.bind("<Button-3>", self.on_right_click)  # context edit

        self.systems = {}
        self.borders = []
        self.texts = []
        self.pan_offset_x = 600
        self.pan_offset_y = 400
        # Initialize SCALE to sweet spot selected by user
        self.SCALE = 0.7053834425211398
        self.scale_indicator = None

        self.load_galmapinfo()
        self.load_systems()
        self.auto_center_and_zoom()
        self.draw_systems()
        self.draw_jump_links()
        self.draw_borders()
        self.draw_texts()
        self.draw_scale()

    def load_galmapinfo(self):
        """Load borders and texts metadata from GalMapInfo.json"""
        base = get_base_path()
        galinfo_path = os.path.join(base, "GalMapInfo.json")
        if os.path.exists(galinfo_path):
            try:
                with open(galinfo_path, 'r') as f:
                    data = json.load(f)
                self.borders = data.get("borders", [])
                self.texts = data.get("texts", [])
            except json.JSONDecodeError:
                print("Warning: Could not parse GalMapInfo.json, skipping.")

    def load_systems(self):
        """Load system JSON files and cache their data for rendering."""
        base = get_base_path()
        systems_dir = os.path.join(get_base_path(), "data/missions/Map Designer/Terrain")
        for filename in os.listdir(systems_dir):
            if not filename.endswith(".json") or filename == "package.json":
                continue
            file_path = os.path.join(systems_dir, filename)
            try:
                with open(file_path, 'r') as f:
                    data = json.load(f)
                if isinstance(data, dict) and "systemMapCoord" in data:
                    coord = data.get("systemMapCoord", [0, 0, 0])
                    align = data.get("systemalignment", "Unknown")
                    objects = data.get("objects", {})
                    jump_points = [
                        {"name": key, **value}
                        for key, value in objects.items()
                        if value.get("type") in ("jumpnode", "jumppoint")
                    ]
                    meta = data.get("metadata", {})
                    self.systems[filename] = {
                        "coord": coord,
                        "alignment": align,
                        "description": meta.get("sysdescription", ""),
                        "security": meta.get("security", "Neutral"),
                        "exports": meta.get("exports", []),
                        "focus": meta.get("focus", ""),
                        "intel": meta.get("intel", {}),
                        "development": meta.get("development", "Unclaimed"),
                        "visible": meta.get("visible", True),
                        "jump_points": jump_points,
                        "canvas_items": [],
                        "warning_circle": None,
                        "link_lines": [],
                        "incoming_lines": []
                    }
            except json.JSONDecodeError:
                print(f"Warning: Could not parse {filename}, skipping.")

    def auto_center_and_zoom(self):
        if not self.systems:
            return

        xs = [s["coord"][0] for s in self.systems.values()]
        ys = [s["coord"][2] for s in self.systems.values()]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        center_x = (min_x + max_x) / 2
        center_y = (min_y + max_y) / 2
        spread_x = max_x - min_x
        spread_y = max_y - min_y

        # Size of canvas in pixels
        self.root.update_idletasks()
        canvas_w = self.canvas.winfo_width()
        canvas_h = self.canvas.winfo_height()
        if canvas_w < 100:
            canvas_w = int(self.canvas.cget("width"))
        if canvas_h < 100:
            canvas_h = int(self.canvas.cget("height"))

        # Find the best scale to fit everything
        if spread_x == 0: spread_x = 1
        if spread_y == 0: spread_y = 1
        scale_x = canvas_w / (spread_x + 1000)  # Add small padding
        scale_y = canvas_h / (spread_y + 1000)
        self.SCALE = min(scale_x, scale_y)

        # Center the map
        screen_cx = canvas_w / 2
        screen_cy = canvas_h / 2
        self.pan_offset_x = screen_cx - center_x * self.SCALE
        self.pan_offset_y = screen_cy - center_y * self.SCALE

    def build_gate_index(self):
        gate_index = {}
        for filename, system in self.systems.items():
            names = set()
            for jp in system.get("jump_points", []):
                if jp.get("type") not in ("jumpnode", "jumppoint"):
                    continue
                name = jp.get("name")
                if name:
                    names.add(name.lower())
            gate_index[filename] = names
        return gate_index

    def system_has_invalid_destination(self, filename, gate_index, system_name_map):
        system = self.systems.get(filename, {})
        for jp in system.get("jump_points", []):
            if jp.get("type") not in ("jumpnode", "jumppoint"):
                continue
            destinations = jp.get("destinations")
            if not isinstance(destinations, dict) or not destinations:
                return True
            for dest_gate_name, dest_system_name in destinations.items():
                if not dest_gate_name or not dest_system_name:
                    return True
                dest_system_key = str(dest_system_name).lower()
                if dest_system_key.endswith(".json"):
                    dest_system_key = dest_system_key[:-5]
                dest_filename = system_name_map.get(dest_system_key)
                if not dest_filename:
                    return True
                if dest_gate_name.lower() not in gate_index.get(dest_filename, set()):
                    return True
        return False

    def draw_systems(self):
        """Draw each system with dynamic icon sizing based on current SCALE"""
        gate_index = self.build_gate_index()
        system_name_map = {filename.replace(".json", "").lower(): filename for filename in self.systems.keys()}
        for filename, system in self.systems.items():
            x, _, y = system["coord"]
            sx, sy = self.coord_to_screen(x, y)

            # Dynamic icon size: 80px at max zoom in, scales proportionally
            # Compute max_scale from current canvas width (1000 units spans canvas width at max zoom)
            # Ensure canvas is rendered to get correct width
            self.root.update_idletasks()
            canvas_w = self.canvas.winfo_width()
            # Fallback to configured width if not yet mapped
            if canvas_w < 100:
                canvas_w = int(self.canvas.cget('width'))
            max_scale = canvas_w / 1000.0
            # At max_scale, size should be 160; scale linearly with current SCALE
            size = max(70, int(160 * (self.SCALE / max_scale)))
            half = size // 2

            icon_path = f"HTML/Images/Factions/{system['alignment']}.png"
            # Determine full path for bundled resources
            base = get_base_path()
            icon_full = os.path.join(base, icon_path)
            if os.path.exists(icon_full):
                img = Image.open(icon_full).resize((size, size))
                tk_img = ImageTk.PhotoImage(img)
                system["icon"] = tk_img
                img_id = self.canvas.create_image(sx, sy, image=tk_img, tags=("map",))
            else:
                img_id = self.canvas.create_oval(sx-half, sy-half, sx+half, sy+half, fill="grey", tags=("map",))

            if self.system_has_invalid_destination(filename, gate_index, system_name_map):
                ring_r = half + 6
                self.canvas.create_oval(
                    sx - ring_r, sy - ring_r, sx + ring_r, sy + ring_r,
                    outline="yellow", width=3, tags=("map",)
                )

            # Position label below icon
            text_y = sy + half + 5
            text_id = self.canvas.create_text(sx, text_y, text=filename.replace(".json", ""), fill="white", tags=("map",))

            # Store canvas items for dragging
            system["canvas_items"] = [img_id, text_id]

    def draw_jump_links(self):
        system_names = {filename.replace(".json", ""): filename for filename in self.systems.keys()}
        # Collect all jump lines by src/dest pair for offsetting
        links = []

        for src_filename, system in self.systems.items():
            for jp in system["jump_points"]:
                if jp.get("type") not in ["jumppoint", "jumpnode"]:
                    continue
                destinations = jp.get("destinations", {})
                for dest_system in destinations.values():
                    dest_file = system_names.get(dest_system)
                    if not dest_file:
                        continue
                    links.append((src_filename, dest_file, jp))
        # Count links per pair
        from collections import defaultdict
        pair_counts = defaultdict(int)
        for src, dest, _ in links:
            pair_counts[(src, dest)] += 1

        # Track offsets per pair
        pair_offsets = defaultdict(int)
        OFFSET_AMOUNT = 10

        for src, dest, jp in links:
            src_system = self.systems[src]
            dest_system = self.systems[dest]
            jp_coord = jp.get("coordinate")
            src_x, _, src_y = src_system["coord"]

            dest_x, _, dest_y = dest_system["coord"]
            src_screen_x, src_screen_y = self.coord_to_screen(src_x, src_y)
            dest_screen_x, dest_screen_y = self.coord_to_screen(dest_x, dest_y)

            # Compute perpendicular offset
            dx = dest_screen_x - src_screen_x
            dy = dest_screen_y - src_screen_y
            dist = math.hypot(dx, dy)
            if dist == 0:
                dist = 1
            norm_dx = -dy / dist
            norm_dy = dx / dist

            count = pair_counts[(src, dest)]
            offset_index = pair_offsets[(src, dest)]
            offset_value = (offset_index - (count - 1) / 2) * OFFSET_AMOUNT
            pair_offsets[(src, dest)] += 1

            offset_x = norm_dx * offset_value
            offset_y = norm_dy * offset_value

            # Color and style
            is_hidden = jp.get("hideonmap", False)
            line_color = "#66ccff" if is_hidden else "white"
            dash_style = (4, 2) if is_hidden else None

            line_id = self.canvas.create_line(
                src_screen_x + offset_x, src_screen_y + offset_y,
                dest_screen_x + offset_x, dest_screen_y + offset_y,
                 fill = line_color,
                 arrow = tk.LAST,
                 arrowshape = (16, 20, 6),
                 dash = dash_style,
                 tags = ("map",)
            )

            src_system["link_lines"].append((line_id, dest))
            self.systems[dest]["incoming_lines"].append((line_id, src))

    def coord_to_screen(self, x, y):
        return (x * self.SCALE + self.pan_offset_x, y * self.SCALE + self.pan_offset_y)

    def screen_to_coord(self, x, y):
        return ((x - self.pan_offset_x) / self.SCALE, 0, (y - self.pan_offset_y) / self.SCALE)

    def find_nearest_border_node(self, x, y, radius=40):
        for i, border in enumerate(self.borders):
            for j, point in enumerate(border.get("points", [])):
                screen_x, screen_y = self.coord_to_screen(point[0], point[1])
                if math.hypot(screen_x - x, screen_y - y) <= radius:
                    return (i, j)
        return None

    def point_near_line(self, px, py, x1, y1, x2, y2, tolerance):
        if x1 == x2 and y1 == y2:
            return math.hypot(px - x1, py - y1) <= tolerance

        length_sq = (x2 - x1) ** 2 + (y2 - y1) ** 2
        if length_sq == 0:
            return False

        t = max(0, min(1, ((px - x1) * (x2 - x1) + (py - y1) * (y2 - y1)) / length_sq))
        proj_x = x1 + t * (x2 - x1)
        proj_y = y1 + t * (y2 - y1)
        return math.hypot(px - proj_x, py - proj_y) <= tolerance

    def zoom_in(self, center_x=600, center_y=400):
        """Zoom in, capped so 1000 units span no more than canvas width"""
        factor = 1.3
        max_scale = self.canvas.winfo_width() / 1500.0
        if self.SCALE * factor <= max_scale:
            # Scale all map and selection items
            self.canvas.scale("map", center_x, center_y, factor, factor)
            self.canvas.scale("hover", center_x, center_y, factor, factor)
            self.canvas.scale("selection", center_x, center_y, factor, factor)
            # Adjust pan offset
            self.pan_offset_x = center_x + factor * (self.pan_offset_x - center_x)
            self.pan_offset_y = center_y + factor * (self.pan_offset_y - center_y)
            self.SCALE *= factor
            print(f"Scale: {self.SCALE}")
        self.draw_scale()
        # Redraw icons at new size
        self.redraw_map()

    def zoom_out(self, center_x=600, center_y=400):
        """Zoom out, capped so 1000 units cover at least 25% of canvas width"""
        factor = 1 / 1.3
        min_scale = self.canvas.winfo_width() * 0.05 / 1500.0
        if self.SCALE * factor >= min_scale:
            self.canvas.scale("map", center_x, center_y, factor, factor)
            self.canvas.scale("hover", center_x, center_y, factor, factor)
            self.canvas.scale("selection", center_x, center_y, factor, factor)
            self.pan_offset_x = center_x + factor * (self.pan_offset_x - center_x)
            self.pan_offset_y = center_y + factor * (self.pan_offset_y - center_y)
            self.SCALE *= factor
        self.draw_scale()
        # Redraw icons at new size
        self.redraw_map()

    def mouse_zoom(self, event):
        if event.delta > 0:
            self.zoom_in(event.x, event.y)
        else:
            self.zoom_out(event.x, event.y)

    def redraw_map(self):
        """Clear and redraw all map elements based on current SCALE and pan."""
        # Remove all items with "map" tag
        self.canvas.delete("map")
        # Redraw everything
        self.draw_systems()
        self.draw_jump_links()
        self.draw_borders()
        self.draw_texts()

    def get_clicked_system(self, event, radius=30):
        closest_fname = None
        min_dist = float('inf')
        for fname, system in self.systems.items():
            coords = self.canvas.coords(system["canvas_items"][0])
            if coords:
                sx, sy = coords[0], coords[1]
                dist = (event.x - sx) ** 2 + (event.y - sy) ** 2
                if dist < radius ** 2 and dist < min_dist:
                    min_dist = dist
                    closest_fname = fname
        return closest_fname


    def save_galmapinfo(self):
        # Remove any borders with fewer than 2 points before saving
        valid_borders = [b for b in self.borders if isinstance(b.get("points"), list) and len(b.get("points")) >= 2]
        data = {"borders": valid_borders, "texts": self.texts}
        base = get_base_path()
        galinfo_path = os.path.join(base, "GalMapInfo.json")
        with open(galinfo_path, 'w') as f:
            json.dump(data, f, indent=4)

    def draw_borders(self):
        self.canvas.delete("border")
        for border in self.borders:
            points = border.get("points", [])
            if len(points) < 2:
                continue
            color = border.get("color", "white")
            width = border.get("width", 2)
            screen_points = []
            for px, py in points:
                sx, sy = self.coord_to_screen(px, py)
                screen_points.extend([sx, sy])
            self.canvas.create_line(screen_points, fill=color, width=width, tags=("border", "map"))
            hover_text = border.get("hover_text", "")
            if hover_text:
                sx, sy = self.coord_to_screen(points[0][0], points[0][1])
                self.canvas.create_text(sx, sy-10, text=hover_text, fill=color, tags=("border", "map"))

    def draw_texts(self):
        self.canvas.delete("text")
        self.canvas.delete("text_node")
        for idx, text in enumerate(self.texts):
            lines = text.get("lines", [])
            if not lines:
                continue
            color = text.get("color", "white")
            size = text.get("size", 12)
            pos = text.get("position", [0, 0])
            sx, sy = self.coord_to_screen(pos[0], pos[1])
            combined = "\n".join(lines)
            self.canvas.create_text(sx, sy, text=combined, fill=color, font=("Arial", size), justify="center", tags=("text", "map"))
            r = 10 * self.SCALE / self.INITIAL_SCALE
            self.canvas.create_oval(sx-r, sy-r, sx+r, sy+r, outline="cyan", width=1, tags=("text_node", "map"))

    def hover_highlight(self, event):
        """Highlights nearest system, text node, or border node with appropriate radius matching interaction zone"""
        self.canvas.delete("hover")
        closest = None
        min_distance = float('inf')
        # Interaction radii
        system_radius = 30
        text_radius = 13
        border_radius = 13
        closest_radius = 13

        # Check systems
        for system in self.systems.values():
            coords = self.canvas.coords(system["canvas_items"][0])
            if not coords:
                continue
            x, y = coords[0], coords[1]
            dist = math.hypot(event.x - x, event.y - y)
            if dist < system_radius and dist < min_distance:
                closest, min_distance, closest_radius = (x, y), dist, system_radius

        # Check text nodes
        for item in self.canvas.find_withtag("text_node"):
            coords = self.canvas.coords(item)
            if len(coords) >= 4:
                cx = (coords[0] + coords[2]) / 2
                cy = (coords[1] + coords[3]) / 2
                dist = math.hypot(event.x - cx, event.y - cy)
                if dist < text_radius and dist < min_distance:
                    closest, min_distance, closest_radius = (cx, cy), dist, text_radius

        # Check border nodes
        for border in self.borders:
            for px, py in border.get("points", []):
                sx, sy = self.coord_to_screen(px, py)
                dist = math.hypot(event.x - sx, event.y - sy)
                if dist < border_radius and dist < min_distance:
                    closest, min_distance, closest_radius = (sx, sy), dist, border_radius

        # Draw highlight if something is close enough
        if closest:
            x, y = closest
            r = closest_radius
            self.canvas.create_oval(x - r, y - r, x + r, y + r, outline="cyan", width=2, tags="hover")

    # Selection utility methods
    def clear_selection(self):
        """Clears any persistent selection highlights"""
        self.canvas.delete("selection")
        self.selected_type = None
        self.selected_id = None

    def select_system(self, filename):
        """Highlights a system"""
        coords = self.canvas.coords(self.systems[filename]["canvas_items"][0])
        if coords:
            x, y = coords[0], coords[1]
            r = 25
            self.canvas.create_oval(x-r, y-r, x+r, y+r, outline="white", width=2, tags=("selection","map"))
            self.selected_type = "system"
            self.selected_id = filename

    def select_text(self, index):
        """Highlights a text node"""
        items = self.canvas.find_withtag("text_node")
        if index < len(items):
            coords = self.canvas.coords(items[index])
            if len(coords) >= 4:
                cx = (coords[0] + coords[2]) / 2
                cy = (coords[1] + coords[3]) / 2
                r = 10 * self.SCALE / self.INITIAL_SCALE + 5
                self.canvas.create_oval(cx-r, cy-r, cx+r, cy+r, outline="white", width=2, tags=("selection","map"))
                self.selected_type = "text"
                self.selected_id = index

    def select_border(self, border_index):
        """Highlights all points of a border"""
        for px, py in self.borders[border_index].get("points", []):
            sx, sy = self.coord_to_screen(px, py)
            r = 40
            self.canvas.create_oval(sx-r, sy-r, sx+r, sy+r, outline="white", width=2, tags=("selection","map"))
        self.selected_type = "border"
        self.selected_id = border_index

    def on_left_click(self, event):
        """Handles left-click selection"""
        # Ignore if this was a drag
        if self.drag_data.get("dragged"):
            self.drag_data["dragged"] = False
            return
        # Only treat as click if minimal movement
        if abs(event.x - self.drag_data.get("x", 0)) > 5 or abs(event.y - self.drag_data.get("y", 0)) > 5:
            return
        # Left-click on a system opens the system editor
        fname = self.get_clicked_system(event, radius=30)
        if fname:
            systems_dir = os.path.join(get_base_path(), "data/missions/Map Designer/Terrain")
            file_path = os.path.join(systems_dir, fname)
            SystemEditor.open_system_editor(file_path)
            return
        # Select text node
        items = self.canvas.find_withtag("text_node")
        for idx, item in enumerate(items):
            coords = self.canvas.coords(item)
            if len(coords) >= 4:
                cx = (coords[0] + coords[2]) / 2
                cy = (coords[1] + coords[3]) / 2
                if (event.x - cx)**2 + (event.y - cy)**2 < 60**2:
                    self.clear_selection()
                    self.select_text(idx)
                    return
        # Select border node
        node = self.find_nearest_border_node(event.x, event.y, radius=40)
        if node:
            self.clear_selection()
            self.select_border(node[0])
            return
        # Empty space click
        self.clear_selection()
    def start_pan(self, event):
        """Begin panning or item dragging"""
        x, y = event.x, event.y
        # Detect system under pointer for dragging
        for fname, system in self.systems.items():
            coords = self.canvas.coords(system["canvas_items"][0])
            if coords:
                sx, sy = coords[0], coords[1]
                if (x - sx)**2 + (y - sy)**2 < 30**2:
                    self.drag_data["item"] = ("system", fname)
                    self.drag_data["x"], self.drag_data["y"] = x, y
                    return
        # Detect text node under pointer
        items = self.canvas.find_withtag("text_node")
        for idx, item in enumerate(items):
            coords = self.canvas.coords(item)
            if len(coords) >= 4:
                cx = (coords[0] + coords[2]) / 2
                cy = (coords[1] + coords[3]) / 2
                if (x - cx)**2 + (y - cy)**2 < (10 * self.SCALE / self.INITIAL_SCALE + 5)**2:
                    self.drag_data["item"] = ("text", idx)
                    self.drag_data["x"], self.drag_data["y"] = x, y
                    return
        # Detect border node under pointer
        node = self.find_nearest_border_node(x, y, radius=40)
        if node:
            self.drag_data["item"] = ("border", node)
            self.drag_data["x"], self.drag_data["y"] = x, y
            return
        # Otherwise start panning
        self.drag_data["panning"] = True
        self.drag_data["x"], self.drag_data["y"] = x, y

    def do_pan(self, event):
        """Handle dragging of items or panning"""
        x, y = event.x, event.y
        dx = x - self.drag_data.get("x", 0)
        dy = y - self.drag_data.get("y", 0)
        # Drag a selected item
        item = self.drag_data.get("item")
        if item:
            item_type, info = item
            if item_type == "system":
                fname = info
                for cid in self.systems[fname]["canvas_items"]:
                    self.canvas.move(cid, dx, dy)
                new_x, new_y = self.canvas.coords(self.systems[fname]["canvas_items"][0])
                nx, _, ny = self.screen_to_coord(new_x, new_y)
                self.systems[fname]["coord"] = [nx, 0, ny]
                                # Update outgoing jump lines
                for line_id, dest in self.systems[fname]["link_lines"]:
                    srcx, srcy = self.coord_to_screen(nx, ny)
                    dest_coord = self.systems[dest]["coord"]
                    dx_s, dy_s = self.coord_to_screen(dest_coord[0], dest_coord[2])
                    self.canvas.coords(line_id, srcx, srcy, dx_s, dy_s)
                # Update incoming jump lines
                for line_id, src in self.systems[fname]["incoming_lines"]:
                    src_coord = self.systems[src]["coord"]
                    sx_s, sy_s = self.coord_to_screen(src_coord[0], src_coord[2])
                    dstx, dsty = self.coord_to_screen(nx, ny)
                    self.canvas.coords(line_id, sx_s, sy_s, dstx, dsty)
            elif item_type == "text":
                idx = info
                text_id = self.canvas.find_withtag("text")[idx]
                node_id = self.canvas.find_withtag("text_node")[idx]
                self.canvas.move(text_id, dx, dy)
                self.canvas.move(node_id, dx, dy)
                coords = self.canvas.coords(text_id)
                nx, _, ny = self.screen_to_coord(coords[0], coords[1])
                self.texts[idx]["position"] = [nx, ny]
            elif item_type == "border":
                bidx, pidx = info
                nx, _, ny = self.screen_to_coord(x, y)
                self.borders[bidx]["points"][pidx] = [nx, ny]
                self.draw_borders()
        # Pan the map if no item is being dragged
        elif self.drag_data.get("panning"):
            self.canvas.move("map", dx, dy)
            self.canvas.move("hover", dx, dy)
            self.canvas.move("selection", dx, dy)
            self.pan_offset_x += dx
            self.pan_offset_y += dy
        # Always update drag_data for both panning and item dragging
        self.drag_data["x"], self.drag_data["y"] = x, y

    def end_pan(self, event):
        # End dragging or panning
        self.drag_data["panning"] = False
        self.drag_data["item"] = None

    def draw_scale(self):
        if self.scale_indicator:
            self.canvas.delete(self.scale_indicator)
        if hasattr(self, "scale_text"):
            self.canvas.delete(self.scale_text)

        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()
        x0, y0 = 20, height - 30
        length = 1000 * self.SCALE  # increased to 1000 units
        self.scale_indicator = self.canvas.create_line(x0, y0, x0 + length, y0, fill="white", width=3, tags="scale")
        self.scale_text = self.canvas.create_text(x0 + length / 2, y0 - 15, text="1000 units", fill="white", tags="scale")

    def edit_text_properties(self, idx):
        text = self.texts[idx]
        top = tk.Toplevel(self.root)
        top.title("Edit Text")

        tk.Label(top, text="Color:").pack()
        color_entry = tk.Entry(top)
        color_entry.insert(0, text.get("color", "white"))
        color_entry.pack()

        tk.Label(top, text="Size:").pack()
        size_entry = tk.Entry(top)
        size_entry.insert(0, str(text.get("size", 12)))
        size_entry.pack()

        tk.Label(top, text="Lines (separate with newlines):").pack()
        lines_text = tk.Text(top, height=5)
        lines_text.insert("1.0", "\n".join(text.get("lines", [])))
        lines_text.pack()

        def save_changes():
            text["color"] = color_entry.get()
            text["size"] = int(size_entry.get())
            text["lines"] = lines_text.get("1.0", tk.END).strip().split("\n")
            self.draw_texts()
            top.destroy()

        tk.Button(top, text="Save", command=save_changes).pack()
        # Delete button to remove this text node
        def delete_text():
            del self.texts[idx]
            self.draw_texts()
            top.destroy()

        tk.Button(top, text="Delete", command=delete_text).pack()
    
    #Main App Save changes 
  
    def save_changes(self):
        """Save galmap info and persist system property and coordinate changes to each system JSON file"""
        # Save borders and texts
        self.save_galmapinfo()
        base = get_base_path()
        # Define keys to sync other properties between memory and JSON
        props = ["security", "exports", "focus", "intel", "development", "visible"]

        for fn, sys_data in self.systems.items():
            file_path = os.path.join(base, "data", "missions", "Map Designer", "Terrain", fn)
            # Load existing JSON
            try:
                with open(file_path, 'r') as f:
                    orig_data = json.load(f)
            except (IOError, json.JSONDecodeError):
                continue

            coords = self.canvas.coords(sys_data["canvas_items"][0])
            if coords:
                nx, _, ny = self.screen_to_coord(coords[0], coords[1])
                orig_data["systemMapCoord"] = [nx, 0, ny]

            orig_data["systemalignment"] = sys_data.get("alignment", orig_data.get("systemalignment", ""))

            # Update metadata block without affecting other data
            if "metadata" not in orig_data:
                orig_data["metadata"] = {}

            orig_data["metadata"].update({
                "sysdescription": sys_data.get("description", ""),
                "security": sys_data.get("security", "Neutral"),
                "exports": sys_data.get("exports", []),
                "focus": sys_data.get("focus", ""),
                "intel": sys_data.get("intel", {}),
                "development": sys_data.get("development", "Unclaimed"),
                "visible": sys_data.get("visible", True)
            })
            try:
                with open(file_path, 'w') as f:
                    json.dump(orig_data, f, indent=4)
            except IOError:
                print(f"Failed to write {fn}")
        print("Changes saved.")
        # Invoke integrated map generator modules
        try:
            LocMapGen.main()
            GalMapGen.main()
            print("Generators ran successfully.")
        except Exception as e:
            print(f"Error running generators: {e}")

    def add_border_point_at(self, x, y):
        """Adds a new point to the selected border or starts a new border if none is selected"""
        bx, _, by = self.screen_to_coord(x, y)
        # Start a new border if none selected
        if self.selected_type != "border" or self.selected_id is None:
            new_border = {"points": [[bx, by]], "color": "white", "width": 2, "hover_text": ""}
            self.borders.append(new_border)
            self.selected_type = "border"
            self.selected_id = len(self.borders) - 1
        else:
            # Add point to existing border
            self.borders[self.selected_id]["points"].append([bx, by])
        self.draw_borders()

    def on_shift_left(self, event):
        """Shift+Left-click: open system details if on a system; otherwise add border point"""
        fname = self.get_clicked_system(event, radius=30)
        if fname:
            self.edit_system_properties(fname)
            return
        self.add_border_point_at(event.x, event.y)
      
    def on_shift_right(self, event):
        """Shift+Right-click: open system editor if on a system, otherwise handle text/border edits"""
        # Check for shift+right-click on a system icon using closest match
        fname = self.get_clicked_system(event, radius=100)
        if fname:
            systems_dir = os.path.join(get_base_path(), "data/missions/Map Designer/Terrain")
            file_path = os.path.join(systems_dir, fname)
            SystemEditor.open_system_editor(file_path)
            return
        # Fallback: original behavior
        """Removes nearest point from selected border, or creates a new text node if nothing is selected"""
        # Determine action: if nothing selected, create new text node
        if self.selected_type not in ("border", "text") or self.selected_id is None:
            bx, _, by = self.screen_to_coord(event.x, event.y)
            new_text = {"lines": ["New text"], "color": "white", "size": 12, "position": [bx, by]}
            self.texts.append(new_text)
            self.selected_type = "text"
            self.selected_id = len(self.texts) - 1
            self.draw_texts()
            # Open editor for new text
            self.edit_text_properties(self.selected_id)
            return
        # Otherwise, if a border is selected, remove nearest point
        if self.selected_type == "border" and self.selected_id is not None:
            # Use reduced radius matching hover/select radius
            node = self.find_nearest_border_node(event.x, event.y, radius=13)
            if node and node[0] == self.selected_id:
                _, idx = node
                pts = self.borders[self.selected_id]["points"]
                if 0 <= idx < len(pts):
                    pts.pop(idx)
                    self.draw_borders()
                  
    def on_right_click(self, event):
        """Handle right-click to edit system, text, or border properties"""
        # Check if clicked on a system
        fname = self.get_clicked_system(event, radius=100)
        if fname:
            self.edit_system_properties(fname)
            return
        # Existing text edit
        items = self.canvas.find_withtag("text")
        for idx, item in enumerate(items):
            bbox = self.canvas.bbox(item)
            if bbox and bbox[0] <= event.x <= bbox[2] and bbox[1] <= event.y <= bbox[3]:
                self.edit_text_properties(idx)
                return
        # Check if clicked near a border line point
        node = self.find_nearest_border_node(event.x, event.y, radius=100)
        if node:
            self.edit_border_properties(node[0])
            return
        return
        # Check if clicked near a border line point
        node = self.find_nearest_border_node(event.x, event.y, radius=100)
        if node:
            self.edit_border_properties(node[0])
            return

    def edit_border_properties(self, idx):
        """Opens a dialog to edit border color, width, and hover text"""
        border = self.borders[idx]
        top = tk.Toplevel(self.root)
        top.title("Edit Border Properties")

        tk.Label(top, text="Color:").pack()
        color_entry = tk.Entry(top)
        color_entry.insert(0, border.get("color", "white"))
        color_entry.pack()

        tk.Label(top, text="Width:").pack()
        width_entry = tk.Entry(top)
        width_entry.insert(0, str(border.get("width", 2)))
        width_entry.pack()

        tk.Label(top, text="Hover Text:").pack()
        hover_entry = tk.Entry(top)
        hover_entry.insert(0, border.get("hover_text", ""))
        hover_entry.pack()

        def save_border_changes():
            border["color"] = color_entry.get()
            try:
                border["width"] = int(width_entry.get())
            except ValueError:
                border["width"] = 2
            border["hover_text"] = hover_entry.get()
            self.draw_borders()
            top.destroy()

        tk.Button(top, text="Save", command=save_border_changes).pack()

    # Edit system properties
    def edit_system_properties(self, filename):
        system = self.systems[filename]
        meta = {}  # default empty metadata
        systems_dir = os.path.join(get_base_path(), "data/missions/Map Designer/Terrain")
        file_path = os.path.join(systems_dir, filename)
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
                meta = data.get("metadata", {})
        except Exception as e:
            print(f"Failed to load system metadata from {file_path}: {e}")

        # Fully reload this system's data from disk
        objects = data.get("objects", {})
        jump_points = [
            {"name": key, **value}
            for key, value in objects.items()
            if value.get("type") in ("jumppoint", "jumpnode")
        ]
        meta = data.get("metadata", {})
        self.systems[filename] = {
            "coord": data.get("systemMapCoord", [0, 0, 0]),
            "alignment": data.get("systemalignment", "Unknown"),
            "description": meta.get("sysdescription", ""),
            "security": meta.get("security", "Neutral"),
            "exports": meta.get("exports", []),
            "focus": meta.get("focus", ""),
            "intel": meta.get("intel", {}),
            "development": meta.get("development", "Unclaimed"),
            "visible": meta.get("visible", True),
            "jump_points": jump_points,
            "canvas_items": [],
            "warning_circle": None,
            "link_lines": [],
            "incoming_lines": []
        }
        system = self.systems[filename]
        self.root.after(100, self.redraw_map)
        top = tk.Toplevel(self.root)
        top.title(f"Edit System: {filename}")

        # Description
        tk.Label(top, text="Description:").pack(anchor="w")
        desc_text = tk.Text(top, height=5)
        desc_text.insert("1.0", system.get("description",""))
        desc_text.pack(fill=tk.X)

        # Alignment selection (editable combobox)
        tk.Label(top, text="Alignment:").pack(anchor="w", pady=(10,0))
        alignments = sorted({s.get("alignment","") for s in self.systems.values()})
        align_var = tk.StringVar(value=system.get("alignment",""))
        align_cb = ttk.Combobox(top, textvariable=align_var, values=alignments)
        align_cb.pack(fill=tk.X)

        intel = system.get("intel", {})

        # Dropdowns row
        dd_frame = tk.Frame(top)
        dd_frame.pack(fill=tk.X, pady=(5,5))
        # Security
        tk.Label(dd_frame, text="Security Level:").grid(row=0, column=0, sticky="w")
        sec_var = tk.StringVar(value=system.get("security","Neutral"))
        sec_menu = tk.OptionMenu(dd_frame, sec_var, *["None","Neutral","Low","Normal","High"])
        sec_menu.grid(row=0, column=1, sticky="w", padx=5)
        # Pirate
        tk.Label(dd_frame, text="Pirate Activity:").grid(row=0, column=2, sticky="w")
        pirate_var = tk.StringVar(value=intel.get("pirate","Low"))
        pirate_menu = tk.OptionMenu(dd_frame, pirate_var, *["None","Low","Mid","High"])
        pirate_menu.grid(row=0, column=3, sticky="w", padx=5)
        # Enemy
        tk.Label(dd_frame, text="Enemy Strength:").grid(row=0, column=4, sticky="w")
        enemy_var = tk.StringVar(value=intel.get("enemy","Low"))
        enemy_menu = tk.OptionMenu(dd_frame, enemy_var, *["None","Low","Mid","High"])
        enemy_menu.grid(row=0, column=5, sticky="w", padx=5)
        # Development
        tk.Label(dd_frame, text="Development Stage:").grid(row=0, column=6, sticky="w")
        dev_var = tk.StringVar(value=system.get("development","Unclaimed"))
        dev_menu = tk.OptionMenu(dd_frame, dev_var, *["Unclaimed","Uninhabited","Outpost","Colony","Administrative Center","Regional Capital"])
        dev_menu.grid(row=0, column=7, sticky="w", padx=5)

                # Strategic Assets
        tk.Label(top, text="Strategic Assets:").pack(anchor="w", pady=(10, 0))
        assets_vars = {}
        assets_opts = ["Armory", "Shipyard", "Slingshot", "Listening Post", "Fortification"]
        sa_frame = tk.Frame(top)
        sa_frame.pack(fill=tk.X)
        for i, opt in enumerate(assets_opts):
            var = tk.BooleanVar(value=opt in intel.get("assets", []))
            cb = tk.Checkbutton(sa_frame, text=opt, variable=var)
            cb.grid(row=0, column=i, sticky="w", padx=5)
            assets_vars[opt] = var

        # Exports
        tk.Label(top, text="Exports:").pack(anchor="w", pady=(10, 0))
        export_vars = {}
        export_opts = [("Oil", "Oil"), ("Agriculture", "Agriculture"), ("Mining", "Mining"), ("Industry", "Industry"), ("Research", "Research")]
        ex_frame = tk.Frame(top)
        ex_frame.pack(fill=tk.X)
        for idx, (label, val) in enumerate(export_opts):
            var = tk.BooleanVar(value=val in system.get("exports", []))
            cb = tk.Checkbutton(ex_frame, text=label, variable=var)
            cb.grid(row=idx//4, column=idx%4, sticky="w", padx=5, pady=2)
            export_vars[val] = var

        # Primary Focus
        tk.Label(top, text="Primary Focus:").pack(anchor="w", pady=(10, 0))
        focus_var = tk.StringVar(value=system.get("focus", ""))
        focus_opts = ["Research", "Agriculture", "Mining", "Industry", "Military"]
        pf_frame = tk.Frame(top)
        pf_frame.pack(fill=tk.X)
        for i, opt in enumerate(focus_opts):
            rb = tk.Radiobutton(pf_frame, text=opt, variable=focus_var, value=opt)
            rb.grid(row=0, column=i, sticky="w", padx=5)

        # Display on Galactic Map
        tk.Label(top, text="Display on Galactic Map:").pack(anchor="w", pady=(10, 0))
        vis_var = tk.StringVar(value="Show" if system.get("visible", True) else "Hide")
        vis_frame = tk.Frame(top)
        vis_frame.pack(fill=tk.X)
        tk.Radiobutton(vis_frame, text="Show System on Galactic Map", variable=vis_var, value="Show").grid(row=0, column=0, sticky="w", padx=5)
        tk.Radiobutton(vis_frame, text="Hide System on Galactic Map", variable=vis_var, value="Hide").grid(row=0, column=1, sticky="w", padx=5)

        def save_system_changes():
            system["description"] = desc_text.get("1.0", tk.END).strip()
            # Save alignment
            system["alignment"] = align_var.get()
            # Save security and intel
            system["security"] = sec_var.get()
            system["intel"] = {
                "pirate": pirate_var.get(),
                "enemy": enemy_var.get(),
                "assets": [k for k, v in assets_vars.items() if v.get()]
            }
            # Save development stage
            system["development"] = dev_var.get()
            # Save exports
            system["exports"] = [k for k, v in export_vars.items() if v.get()]
            # Save primary focus
            system["focus"] = focus_var.get()
            # Save visibility preference
            system["visible"] = True if vis_var.get() == "Show" else False
            # Persist all changes
            self.save_system_properties(filename)
            top.destroy()
            self.redraw_map()

        tk.Button(top, text="Save", command=save_system_changes).pack(pady=10)

    def save_system_properties(self, filename):
        systems_dir = os.path.join(get_base_path(), "data/missions/Map Designer/Terrain")
        file_path = os.path.join(systems_dir, filename)
        with open(file_path,'r') as f:
            data = json.load(f)
        # Copy properties
        data["systemalignment"] = self.systems[filename].get("alignment", data.get("systemalignment", ""))
        if "metadata" not in data:
            data["metadata"] = {}

        data["metadata"].update({
            "sysdescription": self.systems[filename].get("description", ""),
            "security": self.systems[filename].get("security", "Neutral"),
            "exports": self.systems[filename].get("exports", []),
            "focus": self.systems[filename].get("focus", ""),
            "intel": self.systems[filename].get("intel", {}),
            "development": self.systems[filename].get("development", "Unclaimed"),
            "visible": self.systems[filename].get("visible", True)
        })
        with open(file_path,'w') as f:
            json.dump(data,f,indent=4)

if __name__ == "__main__":
    root = tk.Tk()
    app = SystemMapEditor(root)
    root.mainloop()
