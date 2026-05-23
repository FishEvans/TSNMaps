import os
import json
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import importlib.util
from PIL import Image, ImageTk
import math
import LocMapGen, GalMapGen, LibraryGen, ProductionFlowGen
import SystemEditor  # New module for dedicated system editing
import sys
import SystemTemplates
import copy
import re
import datetime
import webbrowser
from pathlib import Path
import SystemMetaOptions as smopts

# Helper to locate resources in bundled or source context
def get_base_path():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


STATION_OR_PLATFORM_TYPES = {"station", "platform"}
INCOMING_ONLY_GATES_KEY = "incomingOnlyGates"
INCOMING_ONLY_GATES_ALIASES = (INCOMING_ONLY_GATES_KEY, "incoming_only_gates")


def load_valid_hull_keys():
    shipmap_path = os.path.join(get_base_path(), "HTML", "Images", "Ships", "ShipMap.json")
    try:
        with open(shipmap_path, "r") as sf:
            ship_entries = json.load(sf)
    except (OSError, json.JSONDecodeError):
        return set()
    if not isinstance(ship_entries, list):
        return set()
    return {
        str(entry.get("key", "")).strip().casefold()
        for entry in ship_entries
        if isinstance(entry, dict) and str(entry.get("key", "")).strip()
    }


def object_has_blank_or_invalid_hull(obj, valid_hull_keys):
    if not isinstance(obj, dict):
        return False
    if str(obj.get("type", "")).strip().lower() not in STATION_OR_PLATFORM_TYPES:
        return False
    hull = str(obj.get("hull", "") or "").strip()
    if not hull:
        return True
    return bool(valid_hull_keys) and hull.casefold() not in valid_hull_keys


def system_has_blank_or_invalid_station_hull(data, valid_hull_keys):
    objects = data.get("objects", {}) if isinstance(data, dict) else {}
    if not isinstance(objects, dict):
        return False
    return any(object_has_blank_or_invalid_hull(obj, valid_hull_keys) for obj in objects.values())


def get_incoming_only_gate_names(data):
    meta = data.get("metadata", {}) if isinstance(data, dict) else {}
    if not isinstance(meta, dict):
        return set()

    names = set()
    for key in INCOMING_ONLY_GATES_ALIASES:
        raw_names = meta.get(key, [])
        if isinstance(raw_names, str):
            raw_names = [raw_names]
        if not isinstance(raw_names, (list, tuple, set)):
            continue
        for name in raw_names:
            cleaned = str(name or "").strip()
            if cleaned:
                names.add(cleaned.casefold())
    return names


def draw_red_cross(canvas, sx, sy, radius, width, tags):
    return [
        canvas.create_line(
            sx - radius, sy - radius, sx + radius, sy + radius,
            fill="red", width=width, tags=tags
        ),
        canvas.create_line(
            sx - radius, sy + radius, sx + radius, sy - radius,
            fill="red", width=width, tags=tags
        ),
    ]



class SystemMapEditor:
    INITIAL_SCALE = 10000
    ICON_RADIUS = 18000000  # half-size for click detection

    def _get_index_html_path(self):
        return Path(get_base_path()) / "HTML" / "index.html"

    def _get_ship_image_extractor_path(self):
        return Path(get_base_path()) / "scripts" / "ShipImageExtractor.py"

    def _run_generators(self):
        LocMapGen.main()
        GalMapGen.main()
        LibraryGen.main()
        ProductionFlowGen.main()

    def _open_index_html(self):
        index_path = self._get_index_html_path()
        if not index_path.exists():
            return False
        return webbrowser.open(index_path.resolve().as_uri())

    def open_or_generate_maps(self):
        index_path = self._get_index_html_path()
        if index_path.exists():
            opened = self._open_index_html()
            if not opened:
                messagebox.showerror("Open Map", f"Unable to open {index_path}.")
            return

        should_generate = messagebox.askyesno(
            "Open Map",
            "HTML/index.html was not found.\n\nGenerate the maps now and open the galactic map?",
        )
        if not should_generate:
            return

        try:
            self._run_generators()
        except Exception as exc:
            messagebox.showerror("Generate Maps", f"Error running generators:\n{exc}")
            return

        if not self._open_index_html():
            messagebox.showerror(
                "Open Map",
                f"Maps were generated, but {index_path} could not be opened.",
            )

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
    • Rename System – Edit the system name in System Properties
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

    def _load_cargo_teams(self):
        base = get_base_path()
        ct_path = os.path.join(base, "cargo_teams.json")
        try:
            with open(ct_path, "r") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _load_settings(self):
        base = get_base_path()
        settings_path = os.path.join(base, "Settings.json")
        try:
            with open(settings_path, "r") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _get_valid_alignments(self):
        settings = getattr(self, "settings_config", None) or {}
        ct = getattr(self, "ct_config", None) or {}
        factions = settings.get("Factions", []) or ct.get("Factions", []) or []
        races_map = settings.get("Races", {}) if isinstance(settings.get("Races", {}), dict) else ct.get("Races", {})
        races = list(races_map.keys()) if isinstance(races_map, dict) else []
        valid = sorted(set(factions) | set(races), key=str.casefold)
        if valid:
            return valid
        fallback = {s.get("alignment", "") for s in self.systems.values() if s.get("alignment")}
        fallback |= {"USFP", "TSN", "Arvonians", "Kralien", "Torgoth", "Ximni"}
        return sorted(fallback, key=str.casefold)

    def _get_skyboxes(self):
        ct = getattr(self, "ct_config", None) or {}
        skyboxes = ct.get("skyboxes", [])
        return skyboxes if isinstance(skyboxes, list) else []

    def _get_systems_dir(self):
        return os.path.join(get_base_path(), "data", "missions", "Map Designer", "Terrain")

    def _get_system_file_path(self, filename):
        return os.path.join(self._get_systems_dir(), filename)

    def _iter_system_filenames(self):
        systems_dir = self._get_systems_dir()
        for filename in os.listdir(systems_dir):
            if filename.endswith(".json") and filename != "package.json":
                yield filename

    def _load_system_json(self, filename):
        with open(self._get_system_file_path(filename), "r") as f:
            return json.load(f)

    def _write_system_json(self, filename, data):
        with open(self._get_system_file_path(filename), "w") as f:
            json.dump(data, f, indent=4)

    def _system_name_from_filename(self, filename):
        return os.path.splitext(os.path.basename(filename))[0]

    def _normalize_system_filename_from_input(self, system_name):
        cleaned = str(system_name or "").strip()
        if cleaned.lower().endswith(".json"):
            cleaned = cleaned[:-5].strip()
        if not cleaned:
            raise ValueError("System name cannot be empty.")
        if cleaned in (".", ".."):
            raise ValueError("System name cannot be '.' or '..'.")
        if cleaned.endswith(".") or cleaned.endswith(" "):
            raise ValueError("System name cannot end with a dot or space.")
        if any(ch in '<>:"/\\|?*' for ch in cleaned) or any(ord(ch) < 32 for ch in cleaned):
            raise ValueError('System name contains invalid filename characters: <>:"/\\|?*')
        reserved_names = {
            "CON", "PRN", "AUX", "NUL",
            "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
            "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
        }
        if cleaned.split(".")[0].upper() in reserved_names:
            raise ValueError("System name is reserved by Windows.")
        return f"{cleaned}.json"

    def _system_destination_key(self, value):
        key = str(value or "").strip().casefold()
        if key.endswith(".json"):
            key = key[:-5]
        return key

    def _renamed_destination_value(self, original_value, new_system_name):
        original = str(original_value or "").strip()
        if original.casefold().endswith(".json"):
            return f"{new_system_name}.json"
        return new_system_name

    def _rewrite_destination_system_names(self, data, old_system_name, new_system_name):
        objects = data.get("objects", {}) if isinstance(data, dict) else {}
        if not isinstance(objects, dict):
            return False

        old_key = old_system_name.casefold()
        changed = False
        for obj in objects.values():
            if not isinstance(obj, dict):
                continue
            if str(obj.get("type", "")).strip().lower() not in ("jumpnode", "jumppoint", "jump_point"):
                continue
            destinations = obj.get("destinations")
            if not isinstance(destinations, dict):
                continue
            for dest_gate_name, dest_system_name in list(destinations.items()):
                if self._system_destination_key(dest_system_name) != old_key:
                    continue
                destinations[dest_gate_name] = self._renamed_destination_value(dest_system_name, new_system_name)
                changed = True
        return changed

    def _rename_system_file(self, old_filename, new_filename):
        if old_filename == new_filename:
            return

        old_path = self._get_system_file_path(old_filename)
        new_path = self._get_system_file_path(new_filename)
        old_abs = os.path.abspath(old_path)
        new_abs = os.path.abspath(new_path)
        same_file = os.path.normcase(old_abs) == os.path.normcase(new_abs)

        if os.path.exists(new_path) and not same_file:
            raise FileExistsError(f"{new_filename} already exists.")
        if not os.path.exists(old_path):
            raise FileNotFoundError(old_path)

        if same_file:
            temp_filename = f".__rename_tmp__{os.getpid()}.json"
            temp_path = self._get_system_file_path(temp_filename)
            suffix = 1
            while os.path.exists(temp_path):
                temp_filename = f".__rename_tmp__{os.getpid()}_{suffix}.json"
                temp_path = self._get_system_file_path(temp_filename)
                suffix += 1
            os.replace(old_path, temp_path)
            os.replace(temp_path, new_path)
        else:
            os.replace(old_path, new_path)

    def rename_system(self, old_filename, new_system_name):
        new_filename = self._normalize_system_filename_from_input(new_system_name)
        old_system_name = self._system_name_from_filename(old_filename)
        new_system_name = self._system_name_from_filename(new_filename)
        if old_filename == new_filename:
            return old_filename

        self._rename_system_file(old_filename, new_filename)

        for filename in list(self._iter_system_filenames()):
            try:
                data = self._load_system_json(filename)
            except (OSError, json.JSONDecodeError):
                print(f"Warning: Could not parse {filename}, skipping destination rename.")
                continue
            if self._rewrite_destination_system_names(data, old_system_name, new_system_name):
                try:
                    self._write_system_json(filename, data)
                except OSError:
                    print(f"Failed to update destinations in {filename}")

        if old_filename in self.systems:
            self.systems[new_filename] = self.systems.pop(old_filename)

        for system in self.systems.values():
            cached_data = {"objects": {}}
            for jp in system.get("jump_points", []):
                if not isinstance(jp, dict):
                    continue
                jp_name = jp.get("name", "")
                cached_data["objects"][jp_name] = jp
            self._rewrite_destination_system_names(cached_data, old_system_name, new_system_name)

        self.clear_selection()
        self.redraw_map()
        return new_filename

    def _refresh_system_record_from_disk(self, filename):
        previous = self.systems.get(filename, {})
        try:
            data = self._load_system_json(filename)
        except (OSError, json.JSONDecodeError):
            return False

        fallback_author_meta = previous.get("author_meta", {}) if isinstance(previous, dict) else {}
        refreshed = self._normalize_system_record(data, fallback_author_meta=fallback_author_meta)
        if refreshed is None:
            return False

        if isinstance(previous, dict):
            for key in ("canvas_items", "link_lines", "incoming_lines"):
                refreshed[key] = previous.get(key, [])

        self.systems[filename] = refreshed
        return True

    def _build_author_meta(self, meta, fallback=None):
        if not isinstance(meta, dict):
            meta = {}
        if not isinstance(fallback, dict):
            fallback = {}
        all_authors = meta.get("all_authors", fallback.get("all_authors", []))
        if not isinstance(all_authors, list):
            all_authors = []
        return {
            "original_author": meta.get("original_author", fallback.get("original_author", "")),
            "last_revision_author": meta.get(
                "last_revision_author",
                meta.get("last_author", fallback.get("last_revision_author", "")),
            ),
            "revision_number": meta.get("revision_number", fallback.get("revision_number", 0)),
            "revision_date": meta.get("revision_date", fallback.get("revision_date", "")),
            "all_authors": list(all_authors),
        }

    def _normalize_system_record(self, data, fallback_author_meta=None):
        if not isinstance(data, dict) or "systemMapCoord" not in data:
            return None

        meta = data.get("metadata", {})
        if not isinstance(meta, dict):
            meta = {}

        objects = data.get("objects", {})
        if not isinstance(objects, dict):
            objects = {}

        jump_points = [
            {"name": key, **value}
            for key, value in objects.items()
            if isinstance(value, dict) and value.get("type") in ("jumpnode", "jumppoint")
        ]

        intel = meta.get("intel", {})
        if not isinstance(intel, dict):
            intel = {}

        traffic = data.get("traffic", {})
        if not isinstance(traffic, dict):
            traffic = {}

        coord = data.get("systemMapCoord", [0, 0, 0])
        if not isinstance(coord, list):
            coord = list(coord) if isinstance(coord, tuple) else [0, 0, 0]

        exports = meta.get("exports", [])
        if not isinstance(exports, list):
            exports = []

        return {
            "coord": list(coord),
            "alignment": data.get("systemalignment", "Unknown"),
            "description": meta.get("sysdescription", ""),
            "security": meta.get("security", "Neutral"),
            "exports": list(exports),
            "focus": meta.get("focus", ""),
            "intel": dict(intel),
            "development": meta.get("development", "Unclaimed"),
            "visible": meta.get("visible", True),
            "skybox": meta.get("skybox", ""),
            "traffic": dict(traffic),
            "author_meta": self._build_author_meta(meta, fallback_author_meta),
            "jump_points": jump_points,
            "incoming_only_gates": get_incoming_only_gate_names(data),
            "has_invalid_station_hull": system_has_blank_or_invalid_station_hull(
                data, getattr(self, "valid_hull_keys", set())
            ),
            "canvas_items": [],
            "link_lines": [],
            "incoming_lines": [],
        }

    def _build_author_source(self, data, author_meta):
        meta = data.get("metadata", {})
        if not isinstance(meta, dict):
            meta = {}

        author_source = dict(meta)
        if isinstance(author_meta, dict):
            for key, value in author_meta.items():
                if author_source.get(key) in (None, "", []):
                    author_source[key] = value

        for key in (
            "original_author",
            "last_revision_author",
            "last_author",
            "revision_number",
            "revision_date",
            "all_authors",
        ):
            if author_source.get(key) in (None, "", []):
                top_level_value = data.get(key)
                if top_level_value not in (None, "", []):
                    author_source[key] = top_level_value
        return author_source

    def _apply_system_record_to_data(self, data, system_data, coord_override=None):
        if not isinstance(data, dict):
            data = {}

        coord = coord_override if coord_override is not None else system_data.get("coord")
        if coord:
            data["systemMapCoord"] = coord

        data["systemalignment"] = system_data.get("alignment", data.get("systemalignment", ""))
        metadata = data.get("metadata", {})
        if not isinstance(metadata, dict):
            metadata = {}

        metadata.update({
            "sysdescription": system_data.get("description", ""),
            "security": system_data.get("security", "Neutral"),
            "exports": system_data.get("exports", []),
            "focus": system_data.get("focus", ""),
            "intel": system_data.get("intel", {}),
            "development": system_data.get("development", "Unclaimed"),
            "visible": system_data.get("visible", True),
            "skybox": system_data.get("skybox", metadata.get("skybox", "")),
        })

        author_meta = system_data.get("author_meta", {})
        if isinstance(author_meta, dict):
            metadata.update(author_meta)

        data["metadata"] = metadata

        traffic = system_data.get("traffic", {})
        if isinstance(traffic, dict):
            data["traffic"] = traffic

        return data

    def _save_system_record(self, filename, coord_override=None):
        data = self._load_system_json(filename)
        data = self._apply_system_record_to_data(data, self.systems[filename], coord_override=coord_override)
        self._write_system_json(filename, data)

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
            incoming_only_gates = get_incoming_only_gate_names(data)
            current_system = filename[:-5]
            current_system_lower = current_system.lower()
            for gate_name, gate_data in objects.items():
                if not isinstance(gate_data, dict):
                    continue
                if gate_data.get("type") not in ("jumpnode", "jumppoint"):
                    continue
                if str(gate_name).strip().casefold() in incoming_only_gates:
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
        self.valid_hull_keys = load_valid_hull_keys()
        self.load_systems()
        self.clear_selection()
        self.redraw_map()
        self.draw_scale()
        print("Systems reloaded.")

    def regenerate_ship_data(self):
        should_proceed = messagebox.askyesno(
            "Re-generate Ship Data",
            "Caution this script will delete old data and regenerate new do you wish to proceed?",
        )
        if not should_proceed:
            return

        executable_path = filedialog.askopenfilename(
            title="Select Game Executable",
            initialdir=get_base_path(),
            filetypes=[
                ("Executable files", "*.exe"),
                ("All files", "*.*"),
            ],
        )
        if not executable_path:
            return

        script_path = self._get_ship_image_extractor_path()
        if not script_path.exists():
            messagebox.showerror(
                "Re-generate Ship Data",
                f"Ship image extractor script was not found:\n{script_path}",
            )
            return

        validation_error_cls = None
        try:
            spec = importlib.util.spec_from_file_location("ShipImageExtractor", script_path)
            if spec is None or spec.loader is None:
                raise ImportError(f"Unable to load module spec from {script_path}")

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            validation_error_cls = getattr(module, "ValidationError", None)
            if not hasattr(module, "main"):
                raise AttributeError("ShipImageExtractor.py does not define a main() function.")

            prev_cwd = os.getcwd()
            try:
                os.chdir(get_base_path())
                module.main(executable_path)
                LibraryGen.main()
            finally:
                os.chdir(prev_cwd)
        except Exception as exc:
            if validation_error_cls and isinstance(exc, validation_error_cls):
                messagebox.showwarning(
                    "Re-generate Ship Data",
                    f"Ship data regeneration was aborted:\n{exc}",
                )
                return
            messagebox.showerror(
                "Re-generate Ship Data",
                f"Failed to re-generate ship data:\n{exc}",
            )
            return

        messagebox.showinfo(
            "Re-generate Ship Data",
            "Ship data re-generation completed.",
        )
        self.valid_hull_keys = load_valid_hull_keys()
        self.reload_systems_data()

    def create_new_system(self):
        top = tk.Toplevel(self.root)
        top.title("Create New System")

        tk.Label(top, text="System Name:").pack()
        name_entry = tk.Entry(top)
        name_entry.pack(fill=tk.X, padx=5)

        tk.Label(top, text="Alignment:").pack()
        alignments = self._get_valid_alignments()
        default_align = "USFP" if "USFP" in alignments else (alignments[0] if alignments else "")
        align_var = tk.StringVar(value=default_align)
        align_cb = ttk.Combobox(top, textvariable=align_var, values=alignments, state="normal")
        align_cb.pack(fill=tk.X, padx=5)

        def add_system():
            name = name_entry.get().strip()
            if not name:
                messagebox.showerror("Invalid Input", "System name cannot be empty.")
                return
            filename = f"{name}.json"
            file_path = self._get_system_file_path(filename)
            if os.path.exists(file_path):
                messagebox.showerror("File Exists", f"{filename} already exists.")
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
            self._write_system_json(filename, template)

            # Add to in-memory system list
            self.systems[filename] = self._normalize_system_record(template)

            self.redraw_map()
            editor_window = SystemEditor.open_system_editor(file_path)
            if editor_window is not None:
                def _refresh_after_editor_close(close_event, target=filename, window=editor_window):
                    if close_event.widget is not window:
                        return
                    if self._refresh_system_record_from_disk(target):
                        self.redraw_map()

                editor_window.bind("<Destroy>", _refresh_after_editor_close, add="+")
            top.destroy()

        tk.Button(top, text="Add", command=add_system).pack(pady=10)

    def __init__(self, root):
        self.root = root
        self.root.title("Stellar Cartography")
        self.ct_config = self._load_cargo_teams()
        self.settings_config = self._load_settings()
        control_frame = tk.Frame(root)
        control_frame.pack(side=tk.TOP, fill=tk.X)
        open_map_button = tk.Button(control_frame, text="Open Map", command=self.open_or_generate_maps)
        open_map_button.pack(side=tk.LEFT)
        auto_link_button = tk.Button(control_frame, text="Auto Link Gates", command=self.auto_link_gates)
        auto_link_button.pack(side=tk.LEFT)
        reload_button = tk.Button(control_frame, text="Reload Systems", command=self.reload_systems_data)
        reload_button.pack(side=tk.LEFT)
        regenerate_ship_data_button = tk.Button(
            control_frame,
            text="Re-generate Ship Data",
            command=self.regenerate_ship_data,
        )
        regenerate_ship_data_button.pack(side=tk.LEFT)
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

        self.drag_data = {
            "item": None,
            "x": 0,
            "y": 0,
            "panning": False,
            "dragged": False,
            "press_x": 0,
            "press_y": 0,
            "drag_distance": 0.0,
            "system_start_coord": None,
            "system_start_fname": None,
        }
        # Selection state
        self.selected_type = None
        self.selected_id = None

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
        self.valid_hull_keys = load_valid_hull_keys()
        self.pan_offset_x = 600
        self.pan_offset_y = 400
        # Initialize SCALE to sweet spot selected by user
        self.SCALE = 0.7053834425211398
        self.min_zoom_scale = self.SCALE
        self.scale_indicator = None
        self.icon_cache = {}
        self.icon_base_images = {}

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
        for filename in self._iter_system_filenames():
            try:
                data = self._load_system_json(filename)
                system_record = self._normalize_system_record(data)
                if system_record is not None:
                    self.systems[filename] = system_record
            except (OSError, json.JSONDecodeError):
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
        canvas_w, canvas_h = self._get_canvas_size()

        # Find the best scale to fit everything
        if spread_x == 0: spread_x = 1
        if spread_y == 0: spread_y = 1
        scale_x = canvas_w / (spread_x + 1000)  # Add small padding
        scale_y = canvas_h / (spread_y + 1000)
        self.SCALE = min(scale_x, scale_y)
        self.min_zoom_scale = self.SCALE

        # Center the map
        screen_cx = canvas_w / 2
        screen_cy = canvas_h / 2
        self.pan_offset_x = screen_cx - center_x * self.SCALE
        self.pan_offset_y = screen_cy - center_y * self.SCALE

    def _get_canvas_size(self):
        self.root.update_idletasks()
        canvas_w = self.canvas.winfo_width()
        canvas_h = self.canvas.winfo_height()
        if canvas_w < 100:
            canvas_w = int(self.canvas.cget("width"))
        if canvas_h < 100:
            canvas_h = int(self.canvas.cget("height"))
        return canvas_w, canvas_h

    def _get_icon_image(self, alignment, size):
        cache_key = (alignment, size)
        cached = self.icon_cache.get(cache_key)
        if cached:
            return cached
        base = get_base_path()
        icon_path = os.path.join(base, "HTML", "Images", "Factions", f"{alignment}.png")
        if not os.path.exists(icon_path):
            return None
        base_img = self.icon_base_images.get(alignment)
        if base_img is None:
            try:
                with Image.open(icon_path) as img:
                    base_img = img.convert("RGBA")
                self.icon_base_images[alignment] = base_img
            except OSError:
                return None
        resized = base_img.resize((size, size), Image.LANCZOS)
        tk_img = ImageTk.PhotoImage(resized)
        self.icon_cache[cache_key] = tk_img
        return tk_img

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
        incoming_only_gates = system.get("incoming_only_gates", set())
        for jp in system.get("jump_points", []):
            if jp.get("type") not in ("jumpnode", "jumppoint"):
                continue
            if str(jp.get("name", "")).strip().casefold() in incoming_only_gates:
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
        canvas_w, _ = self._get_canvas_size()
        max_scale = canvas_w / 1000.0
        size = max(70, int(160 * (self.SCALE / max_scale)))
        half = size // 2
        for filename, system in self.systems.items():
            x, _, y = system["coord"]
            sx, sy = self.coord_to_screen(x, y)

            # Dynamic icon size: 80px at max zoom in, scales proportionally
            # Compute max_scale from current canvas width (1000 units spans canvas width at max zoom)
            tk_img = self._get_icon_image(system["alignment"], size)
            if tk_img:
                system["icon"] = tk_img
                img_id = self.canvas.create_image(sx, sy, image=tk_img, tags=("map",))
            else:
                img_id = self.canvas.create_oval(sx-half, sy-half, sx+half, sy+half, fill="grey", tags=("map",))

            indicator_items = []
            if self.system_has_invalid_destination(filename, gate_index, system_name_map):
                ring_r = half + 6
                ring_id = self.canvas.create_oval(
                    sx - ring_r, sy - ring_r, sx + ring_r, sy + ring_r,
                    outline="yellow", width=3, tags=("map",)
                )
                indicator_items.append(ring_id)

            if system.get("has_invalid_station_hull"):
                cross_r = max(18, int(half * 0.72))
                cross_w = max(3, int(size / 28))
                indicator_items.extend(
                    draw_red_cross(self.canvas, sx, sy, cross_r, cross_w, ("map",))
                )

            # Position label below icon
            text_y = sy + half + 5
            text_id = self.canvas.create_text(sx, text_y, text=filename.replace(".json", ""), fill="white", tags=("map",))

            # Store canvas items for dragging
            system["canvas_items"] = [img_id, *indicator_items, text_id]

    def draw_jump_links(self):
        system_names = {filename.replace(".json", "").lower(): filename for filename in self.systems.keys()}
        for system in self.systems.values():
            system["link_lines"].clear()
            system["incoming_lines"].clear()
        # Collect all jump lines by src/dest pair for offsetting
        links = []

        for src_filename, system in self.systems.items():
            incoming_only_gates = system.get("incoming_only_gates", set())
            for jp in system["jump_points"]:
                if jp.get("type") not in ["jumppoint", "jumpnode"]:
                    continue
                if str(jp.get("name", "")).strip().casefold() in incoming_only_gates:
                    continue
                destinations = jp.get("destinations", {})
                for dest_system in destinations.values():
                    dest_key = str(dest_system).lower()
                    if dest_key.endswith(".json"):
                        dest_key = dest_key[:-5]
                    dest_file = system_names.get(dest_key)
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

            src_system["link_lines"].append({"line_id": line_id, "dest": dest, "offset": (offset_x, offset_y)})
            self.systems[dest]["incoming_lines"].append({"line_id": line_id, "src": src, "offset": (offset_x, offset_y)})

    def coord_to_screen(self, x, y):
        return (x * self.SCALE + self.pan_offset_x, y * self.SCALE + self.pan_offset_y)

    def screen_to_coord(self, x, y):
        return ((x - self.pan_offset_x) / self.SCALE, 0, (y - self.pan_offset_y) / self.SCALE)

    def find_nearest_border_node(self, x, y, radius=40):
        hit = self._find_border_node_hit(x, y, radius)
        if hit is None:
            return None
        return (hit["border_index"], hit["point_index"])

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
        self.draw_scale()
        # Redraw icons at new size
        self.redraw_map()

    def zoom_out(self, center_x=600, center_y=400):
        """Zoom out, capped at the initial auto-fit scale."""
        factor = 1 / 1.3
        min_scale = getattr(self, "min_zoom_scale", self.SCALE)
        target_scale = max(self.SCALE * factor, min_scale)
        if target_scale < self.SCALE:
            applied_factor = target_scale / self.SCALE
            self.canvas.scale("map", center_x, center_y, applied_factor, applied_factor)
            self.canvas.scale("hover", center_x, center_y, applied_factor, applied_factor)
            self.canvas.scale("selection", center_x, center_y, applied_factor, applied_factor)
            self.pan_offset_x = center_x + applied_factor * (self.pan_offset_x - center_x)
            self.pan_offset_y = center_y + applied_factor * (self.pan_offset_y - center_y)
            self.SCALE = target_scale
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

    def _find_system_hit(self, x, y, radius=30):
        radius_sq = radius ** 2
        closest_fname = None
        closest_pos = None
        min_dist_sq = float("inf")
        for fname, system in self.systems.items():
            if not system.get("canvas_items"):
                continue
            coords = self.canvas.coords(system["canvas_items"][0])
            if not coords:
                continue
            sx, sy = coords[0], coords[1]
            dist_sq = (x - sx) ** 2 + (y - sy) ** 2
            if dist_sq < radius_sq and dist_sq < min_dist_sq:
                min_dist_sq = dist_sq
                closest_fname = fname
                closest_pos = (sx, sy)
        if closest_fname is None:
            return None
        return {"filename": closest_fname, "position": closest_pos, "distance_sq": min_dist_sq}

    def _get_text_node_center(self, index):
        items = self.canvas.find_withtag("text_node")
        if index >= len(items):
            return None
        coords = self.canvas.coords(items[index])
        if len(coords) < 4:
            return None
        return (coords[0] + coords[2]) / 2, (coords[1] + coords[3]) / 2

    def _find_text_node_hit(self, x, y, radius):
        radius_sq = radius ** 2
        closest_index = None
        closest_pos = None
        min_dist_sq = float("inf")
        for idx in range(len(self.canvas.find_withtag("text_node"))):
            center = self._get_text_node_center(idx)
            if center is None:
                continue
            cx, cy = center
            dist_sq = (x - cx) ** 2 + (y - cy) ** 2
            if dist_sq < radius_sq and dist_sq < min_dist_sq:
                min_dist_sq = dist_sq
                closest_index = idx
                closest_pos = center
        if closest_index is None:
            return None
        return {"index": closest_index, "position": closest_pos, "distance_sq": min_dist_sq}

    def _find_text_item_hit(self, x, y):
        for idx, item in enumerate(self.canvas.find_withtag("text")):
            bbox = self.canvas.bbox(item)
            if bbox and bbox[0] <= x <= bbox[2] and bbox[1] <= y <= bbox[3]:
                return idx
        return None

    def _find_border_node_hit(self, x, y, radius=40):
        closest = None
        min_distance = float("inf")
        for border_index, border in enumerate(self.borders):
            for point_index, point in enumerate(border.get("points", [])):
                screen_x, screen_y = self.coord_to_screen(point[0], point[1])
                distance = math.hypot(screen_x - x, screen_y - y)
                if distance <= radius and distance < min_distance:
                    min_distance = distance
                    closest = {
                        "border_index": border_index,
                        "point_index": point_index,
                        "position": (screen_x, screen_y),
                        "distance": distance,
                    }
        return closest

    def get_clicked_system(self, event, radius=30):
        hit = self._find_system_hit(event.x, event.y, radius)
        return hit["filename"] if hit else None


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
        candidates = []

        system_hit = self._find_system_hit(event.x, event.y, radius=30)
        if system_hit:
            candidates.append((math.sqrt(system_hit["distance_sq"]), system_hit["position"], 30))

        text_hit = self._find_text_node_hit(event.x, event.y, radius=13)
        if text_hit:
            candidates.append((math.sqrt(text_hit["distance_sq"]), text_hit["position"], 13))

        border_hit = self._find_border_node_hit(event.x, event.y, radius=13)
        if border_hit:
            candidates.append((border_hit["distance"], border_hit["position"], 13))

        if candidates:
            _, (x, y), r = min(candidates, key=lambda item: item[0])
            self.canvas.create_oval(x - r, y - r, x + r, y + r, outline="cyan", width=2, tags="hover")

    # Selection utility methods
    def clear_selection(self):
        """Clears any persistent selection highlights"""
        self.canvas.delete("selection")
        self.selected_type = None
        self.selected_id = None

    def select_text(self, index):
        """Highlights a text node"""
        center = self._get_text_node_center(index)
        if center:
            cx, cy = center
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
        # Ignore if this was a drag (thresholded)
        drag_distance = self.drag_data.get("drag_distance")
        if drag_distance is None:
            px = self.drag_data.get("press_x", event.x)
            py = self.drag_data.get("press_y", event.y)
            drag_distance = math.hypot(event.x - px, event.y - py)
        if drag_distance > 10:
            return

        # If we nudged a system less than the threshold, restore its original coord
        start_fname = self.drag_data.get("system_start_fname")
        start_coord = self.drag_data.get("system_start_coord")
        if start_fname and start_coord:
            self.systems[start_fname]["coord"] = start_coord
            self.redraw_map()
        # Left-click on a system opens the system editor
        system_hit = self._find_system_hit(event.x, event.y, radius=30)
        if system_hit:
            file_path = self._get_system_file_path(system_hit["filename"])
            editor_window = SystemEditor.open_system_editor(file_path)
            if editor_window is not None:
                target = system_hit["filename"]

                def _refresh_after_editor_close(close_event, filename=target, window=editor_window):
                    if close_event.widget is not window:
                        return
                    if self._refresh_system_record_from_disk(filename):
                        self.redraw_map()

                editor_window.bind("<Destroy>", _refresh_after_editor_close, add="+")
            return
        # Select text node
        text_hit = self._find_text_node_hit(event.x, event.y, radius=60)
        if text_hit:
            self.clear_selection()
            self.select_text(text_hit["index"])
            return
        # Select border node
        border_hit = self._find_border_node_hit(event.x, event.y, radius=40)
        if border_hit:
            self.clear_selection()
            self.select_border(border_hit["border_index"])
            return
        # Empty space click
        self.clear_selection()

    def start_pan(self, event):
        """Begin panning or item dragging"""
        x, y = event.x, event.y
        self.drag_data["dragged"] = False
        self.drag_data["press_x"], self.drag_data["press_y"] = x, y
        self.drag_data["drag_distance"] = 0.0
        self.drag_data["system_start_coord"] = None
        self.drag_data["system_start_fname"] = None
        # Detect system under pointer for dragging
        system_hit = self._find_system_hit(x, y, radius=30)
        if system_hit:
            fname = system_hit["filename"]
            self.drag_data["item"] = ("system", fname)
            self.drag_data["x"], self.drag_data["y"] = x, y
            self.drag_data["system_start_coord"] = list(self.systems[fname].get("coord", [0, 0, 0]))
            self.drag_data["system_start_fname"] = fname
            return
        # Detect text node under pointer
        text_hit = self._find_text_node_hit(x, y, radius=10 * self.SCALE / self.INITIAL_SCALE + 5)
        if text_hit:
            self.drag_data["item"] = ("text", text_hit["index"])
            self.drag_data["x"], self.drag_data["y"] = x, y
            return
        # Detect border node under pointer
        border_hit = self._find_border_node_hit(x, y, radius=40)
        if border_hit:
            self.drag_data["item"] = ("border", (border_hit["border_index"], border_hit["point_index"]))
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
        if dx or dy:
            self.drag_data["dragged"] = True
        px = self.drag_data.get("press_x", x)
        py = self.drag_data.get("press_y", y)
        self.drag_data["drag_distance"] = math.hypot(x - px, y - py)
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
                for link in self.systems[fname]["link_lines"]:
                    line_id = link["line_id"]
                    dest = link["dest"]
                    offset_x, offset_y = link["offset"]
                    srcx, srcy = self.coord_to_screen(nx, ny)
                    dest_coord = self.systems[dest]["coord"]
                    dx_s, dy_s = self.coord_to_screen(dest_coord[0], dest_coord[2])
                    self.canvas.coords(line_id, srcx + offset_x, srcy + offset_y, dx_s + offset_x, dy_s + offset_y)
                # Update incoming jump lines
                for link in self.systems[fname]["incoming_lines"]:
                    line_id = link["line_id"]
                    src = link["src"]
                    offset_x, offset_y = link["offset"]
                    src_coord = self.systems[src]["coord"]
                    sx_s, sy_s = self.coord_to_screen(src_coord[0], src_coord[2])
                    dstx, dsty = self.coord_to_screen(nx, ny)
                    self.canvas.coords(line_id, sx_s + offset_x, sy_s + offset_y, dstx + offset_x, dsty + offset_y)
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
        item = self.drag_data.get("item")
        dist = self.drag_data.get("drag_distance", 0.0)
        if item and item[0] == "system" and dist <= 10:
            fname = self.drag_data.get("system_start_fname")
            start_coord = self.drag_data.get("system_start_coord")
            if fname and start_coord is not None:
                self.systems[fname]["coord"] = start_coord
                self.redraw_map()
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

        for fn in list(self.systems.keys()):
            if not self._refresh_system_record_from_disk(fn):
                print(f"Failed to reload {fn}; using cached data.")
            sys_data = self.systems.get(fn, {})
            coords = self.canvas.coords(sys_data["canvas_items"][0])
            coord_override = None
            if coords:
                nx, _, ny = self.screen_to_coord(coords[0], coords[1])
                coord_override = [nx, 0, ny]
            try:
                self._save_system_record(fn, coord_override=coord_override)
            except (OSError, json.JSONDecodeError):
                print(f"Failed to write {fn}")
        print("Changes saved.")
        # Invoke integrated map generator modules
        try:
            self._run_generators()
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
            file_path = self._get_system_file_path(fname)
            editor_window = SystemEditor.open_system_editor(file_path)
            if editor_window is not None:
                def _refresh_after_editor_close(close_event, target=fname, window=editor_window):
                    if close_event.widget is not window:
                        return
                    if self._refresh_system_record_from_disk(target):
                        self.redraw_map()

                editor_window.bind("<Destroy>", _refresh_after_editor_close, add="+")
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
        text_index = self._find_text_item_hit(event.x, event.y)
        if text_index is not None:
            self.edit_text_properties(text_index)
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
        prev_system = system if isinstance(system, dict) else {}
        try:
            data = self._load_system_json(filename)
        except Exception as e:
            print(f"Failed to load system metadata from {self._get_system_file_path(filename)}: {e}")
            return

        # Fully reload this system's data from disk
        prev_author_meta = prev_system.get("author_meta", {}) if isinstance(prev_system, dict) else {}
        meta = data.get("metadata", {})
        if not isinstance(meta, dict):
            meta = {}
        self.systems[filename] = self._normalize_system_record(data, fallback_author_meta=prev_author_meta)
        system = self.systems[filename]
        author_source = self._build_author_source(data, system.get("author_meta", {}))
        self.root.after(100, self.redraw_map)
        top = tk.Toplevel(self.root)
        top.title(f"Edit System: {filename}")

        # System name / file rename
        tk.Label(top, text="System Name:").pack(anchor="w")
        name_frame = tk.Frame(top)
        name_frame.pack(fill=tk.X)
        system_name_var = tk.StringVar(value=self._system_name_from_filename(filename))
        tk.Entry(name_frame, textvariable=system_name_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

        def rename_current_system(show_message=True):
            nonlocal filename, system
            old_filename = filename
            try:
                new_filename = self.rename_system(filename, system_name_var.get())
            except (ValueError, FileExistsError, FileNotFoundError, OSError) as exc:
                messagebox.showerror("Rename System", str(exc), parent=top)
                system_name_var.set(self._system_name_from_filename(filename))
                return False

            filename = new_filename
            system = self.systems[filename]
            system_name_var.set(self._system_name_from_filename(filename))
            top.title(f"Edit System: {filename}")
            if show_message and new_filename != old_filename:
                try:
                    top.bell()
                except tk.TclError:
                    pass
            return True

        tk.Button(name_frame, text="Rename", command=rename_current_system).pack(side=tk.LEFT)

        # Coordinates
        tk.Label(top, text="Coordinates (X,Y,Z):").pack(anchor="w")
        coord_frame = tk.Frame(top)
        coord_frame.pack(fill=tk.X)
        coord_vals = list(system.get("coord", [0, 0, 0]))
        while len(coord_vals) < 3:
            coord_vals.append(0)
        coord_vals = coord_vals[:3]
        coord_vars = []
        for val in coord_vals:
            var = tk.StringVar(value=str(val))
            coord_vars.append(var)
            tk.Entry(coord_frame, textvariable=var, width=10).pack(side=tk.LEFT, padx=2)

        # Description
        tk.Label(top, text="Description:").pack(anchor="w")
        desc_text = tk.Text(top, height=5)
        desc_text.insert("1.0", system.get("description",""))
        desc_text.pack(fill=tk.X)

        # Alignment selection (editable combobox)
        tk.Label(top, text="Alignment:").pack(anchor="w", pady=(10,0))
        alignments = self._get_valid_alignments()
        align_var = tk.StringVar(value=system.get("alignment",""))
        align_cb = ttk.Combobox(top, textvariable=align_var, values=alignments)
        align_cb.pack(fill=tk.X)

        # Skybox
        skyboxes = self._get_skyboxes()
        skybox_val = system.get("skybox", "")
        if skyboxes and skybox_val not in skyboxes:
            skybox_val = skyboxes[0]
        skybox_var = tk.StringVar(value=skybox_val)
        tk.Label(top, text="Skybox:").pack(anchor="w", pady=(10, 0))
        skybox_state = "readonly" if skyboxes else "normal"
        skybox_cb = ttk.Combobox(top, textvariable=skybox_var, values=skyboxes, state=skybox_state)
        skybox_cb.pack(fill=tk.X)

        intel = system.get("intel", {})
        if not isinstance(intel, dict):
            intel = {}

        # Dropdowns row
        dd_frame = tk.Frame(top)
        dd_frame.pack(fill=tk.X, pady=(5,5))
        # Security
        tk.Label(dd_frame, text="Security Level:").grid(row=0, column=0, sticky="w")
        sec_var = tk.StringVar(value=system.get("security","Neutral"))
        sec_menu = tk.OptionMenu(dd_frame, sec_var, *smopts.SECURITY_LEVELS)
        sec_menu.grid(row=0, column=1, sticky="w", padx=5)
        # Pirate
        tk.Label(dd_frame, text="Pirate Activity:").grid(row=0, column=2, sticky="w")
        pirate_var = tk.StringVar(value=intel.get("pirate","Low"))
        pirate_menu = tk.OptionMenu(dd_frame, pirate_var, *smopts.PIRATE_LEVELS)
        pirate_menu.grid(row=0, column=3, sticky="w", padx=5)
        # Enemy
        tk.Label(dd_frame, text="Enemy Strength:").grid(row=0, column=4, sticky="w")
        enemy_var = tk.StringVar(value=intel.get("enemy","Low"))
        enemy_menu = tk.OptionMenu(dd_frame, enemy_var, *smopts.ENEMY_LEVELS)
        enemy_menu.grid(row=0, column=5, sticky="w", padx=5)
        # Development
        tk.Label(dd_frame, text="Development Stage:").grid(row=0, column=6, sticky="w")
        dev_var = tk.StringVar(value=system.get("development","Unclaimed"))
        dev_menu = tk.OptionMenu(dd_frame, dev_var, *smopts.DEVELOPMENT_STAGES)
        dev_menu.grid(row=0, column=7, sticky="w", padx=5)

        # Traffic
        traffic = system.get("traffic", {})
        if not isinstance(traffic, dict):
            traffic = {}
        traffic_frame = tk.Frame(top)
        traffic_frame.pack(fill=tk.X, pady=(5, 5))
        tk.Label(traffic_frame, text="Traffic:").grid(row=0, column=0, sticky="w")
        traffic_vars = {}
        for i, cat in enumerate(("commercial", "civilian", "security")):
            tk.Label(traffic_frame, text=f"{cat.capitalize()}:").grid(row=0, column=1 + i * 2, sticky="w")
            var = tk.StringVar(value=traffic.get(cat, "none"))
            cb = ttk.Combobox(
                traffic_frame, textvariable=var,
                values=smopts.TRAFFIC_LEVELS, state="readonly", width=8
            )
            cb.grid(row=0, column=2 + i * 2, sticky="w", padx=5)
            traffic_vars[cat] = var

        # Strategic Assets
        tk.Label(top, text="Strategic Assets:").pack(anchor="w", pady=(10, 0))
        assets_vars = {}
        assets_opts = smopts.ASSET_OPTIONS
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
        export_opts = [(v, v) for v in smopts.EXPORT_OPTIONS]
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
        focus_opts = smopts.FOCUS_OPTIONS
        focus_cb = ttk.Combobox(top, textvariable=focus_var, values=focus_opts)
        focus_cb.pack(fill=tk.X)

        # Display on Galactic Map
        tk.Label(top, text="Display on Galactic Map:").pack(anchor="w", pady=(10, 0))
        vis_var = tk.StringVar(value="Show" if system.get("visible", True) else "Hide")
        vis_frame = tk.Frame(top)
        vis_frame.pack(fill=tk.X)
        tk.Radiobutton(vis_frame, text="Show System on Galactic Map", variable=vis_var, value="Show").grid(row=0, column=0, sticky="w", padx=5)
        tk.Radiobutton(vis_frame, text="Hide System on Galactic Map", variable=vis_var, value="Hide").grid(row=0, column=1, sticky="w", padx=5)

        # Author & Revision Metadata
        editor_settings = {}
        try:
            editor_settings = SystemEditor.load_editor_settings()
        except Exception:
            editor_settings = {}
        current_author_default = str(editor_settings.get("author", "") or "").strip()
        if not current_author_default:
            current_author_default = str(author_source.get("last_revision_author", "") or author_source.get("last_author", "") or "").strip()
        if not current_author_default:
            current_author_default = str(author_source.get("original_author", "") or "").strip()

        tk.Label(top, text="Author (current):").pack(anchor="w", pady=(10, 0))
        author_var = tk.StringVar(value=current_author_default)
        author_entry = tk.Entry(top, textvariable=author_var)
        author_entry.pack(fill=tk.X)

        orig_author_var = tk.StringVar(value=str(author_source.get("original_author", "") or ""))
        last_author_var = tk.StringVar(value=str(author_source.get("last_revision_author", "") or author_source.get("last_author", "") or ""))
        rev_num_var = tk.StringVar(value=str(SystemEditor._coerce_revision_number(author_source.get("revision_number", 0))))
        rev_date_var = tk.StringVar(value=str(author_source.get("revision_date", "") or ""))
        all_authors_raw = author_source.get("all_authors", [])
        all_authors_var = tk.StringVar(value=", ".join(SystemEditor._normalize_author_list(all_authors_raw)))
        # Keep readonly vars alive for the life of the dialog (avoid GC clearing ttk.Entry values)
        top._author_vars = {
            "orig_author": orig_author_var,
            "last_author": last_author_var,
            "rev_num": rev_num_var,
            "rev_date": rev_date_var,
            "all_authors": all_authors_var,
        }

        meta_frame = tk.Frame(top)
        meta_frame.pack(fill=tk.X, pady=(5, 0))
        tk.Label(meta_frame, text="Original Author:").grid(row=0, column=0, sticky="w")
        ttk.Entry(meta_frame, textvariable=orig_author_var, state="readonly", width=25).grid(row=0, column=1, sticky="w", padx=5)
        tk.Label(meta_frame, text="Last Revision Author:").grid(row=0, column=2, sticky="w")
        ttk.Entry(meta_frame, textvariable=last_author_var, state="readonly", width=25).grid(row=0, column=3, sticky="w", padx=5)
        tk.Label(meta_frame, text="Revision #:").grid(row=1, column=0, sticky="w")
        ttk.Entry(meta_frame, textvariable=rev_num_var, state="readonly", width=10).grid(row=1, column=1, sticky="w", padx=5)
        tk.Label(meta_frame, text="Revision Date:").grid(row=1, column=2, sticky="w")
        ttk.Entry(meta_frame, textvariable=rev_date_var, state="readonly", width=15).grid(row=1, column=3, sticky="w", padx=5)
        tk.Label(meta_frame, text="All Authors:").grid(row=2, column=0, sticky="nw")
        ttk.Entry(meta_frame, textvariable=all_authors_var, state="readonly", width=60).grid(row=2, column=1, columnspan=3, sticky="w", padx=5)

        def save_system_changes():
            if not rename_current_system(show_message=False):
                return

            def _merge_with_extras(selected, existing, known):
                extras = [x for x in (existing or []) if x not in known]
                for x in extras:
                    if x not in selected:
                        selected.append(x)
                return selected

            # Save coordinates
            try:
                new_coord = [float(v.get()) for v in coord_vars]
            except ValueError:
                new_coord = system.get("coord", [0, 0, 0])
            system["coord"] = new_coord

            system["description"] = desc_text.get("1.0", tk.END).strip()
            # Save alignment
            system["alignment"] = align_var.get()
            # Save security and intel
            system["security"] = sec_var.get()
            intel_data = system.get("intel", {})
            if not isinstance(intel_data, dict):
                intel_data = {}
            intel_assets = [k for k, v in assets_vars.items() if v.get()]
            intel_data["pirate"] = pirate_var.get()
            intel_data["enemy"] = enemy_var.get()
            intel_data["assets"] = _merge_with_extras(intel_assets, intel_data.get("assets", []), assets_opts)
            system["intel"] = intel_data
            # Save development stage
            system["development"] = dev_var.get()
            # Save exports
            selected_exports = [k for k, v in export_vars.items() if v.get()]
            system["exports"] = _merge_with_extras(selected_exports, system.get("exports", []), smopts.EXPORT_OPTIONS)
            # Save primary focus
            system["focus"] = focus_var.get()
            # Save visibility preference
            system["visible"] = True if vis_var.get() == "Show" else False
            # Save skybox
            system["skybox"] = skybox_var.get()
            # Save traffic
            system["traffic"] = {k: v.get() for k, v in traffic_vars.items()}

            # Save author settings
            current_author = author_var.get().strip()
            if current_author:
                editor_settings["author"] = current_author
                try:
                    SystemEditor.save_editor_settings(editor_settings)
                except Exception:
                    pass
            author_meta = system.get("author_meta", {})
            if not isinstance(author_meta, dict):
                author_meta = {}
            authors = SystemEditor._normalize_author_list(author_meta.get("all_authors") or meta.get("all_authors"))
            if current_author:
                if not any(a.casefold() == current_author.casefold() for a in authors):
                    authors.append(current_author)
                if not str(author_meta.get("original_author") or meta.get("original_author", "") or "").strip():
                    author_meta["original_author"] = current_author
                author_meta["last_revision_author"] = current_author
            if authors:
                author_meta["all_authors"] = authors
            rev_num = SystemEditor._coerce_revision_number(author_meta.get("revision_number", meta.get("revision_number", 0)))
            author_meta["revision_number"] = rev_num + 1
            author_meta["revision_date"] = datetime.date.today().isoformat()
            system["author_meta"] = author_meta

            # Persist all changes
            self.save_system_properties(filename)
            top.destroy()
            self.redraw_map()

        tk.Button(top, text="Save", command=save_system_changes).pack(pady=10)

    def save_system_properties(self, filename):
        self._save_system_record(filename)

if __name__ == "__main__":
    root = tk.Tk()
    app = SystemMapEditor(root)
    try:
        root.mainloop()
    except KeyboardInterrupt:
        try:
            root.destroy()
        except tk.TclError:
            pass
