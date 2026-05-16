import os
import tkinter as tk
from tkinter import ttk
from tkinter import messagebox
import re

import CenteringTool
import ResizeTool
from PIL import Image, ImageTk
import random
import math
from tkinter import messagebox

RELAY_TYPE_SENSOR = "Sensor Relay"
RELAY_TYPE_WARNING_BUOY = "Warning Buoy"
RELAY_TYPE_OPTIONS = [RELAY_TYPE_SENSOR, RELAY_TYPE_WARNING_BUOY]
RELAY_NUMBERING_ORDERED = "Ordered"
RELAY_NUMBERING_RANDOM = "Random"
RELAY_NUMBERING_OPTIONS = [RELAY_NUMBERING_ORDERED, RELAY_NUMBERING_RANDOM]
WARNING_BUOY_DEFAULT_BROADCAST = "Keep Clear"
WARNING_BUOY_DEFAULT_PING = 2
WARNING_BUOY_DEFAULT_RANGE = 12000
ZONE_TYPE_FCS = "fcs_zone"
ZONE_TYPE_OPTIONS = [ZONE_TYPE_FCS]
ZONE_TYPE_PREFIXES = {
    ZONE_TYPE_FCS: "FCS",
}

class Toolbar:
    def __init__(self, parent, base_path, sm, relay_lb, ter_lb, map_canvas):
        self.base = base_path
        self.sm = sm
        self.relay_lb = relay_lb
        self.ter_lb = ter_lb
        self.map_canvas = map_canvas

        # Mode flags
        self.station_mode = False
        self.sensor_mode = False
        self.multi_mode = False
        self.asteroid_mode = False
        self.nebula_mode = False
        self.blackhole_mode = False
        self.debris_mode = False
        self.minefield_mode = False
        self.planet_mode = False
        self.zone_mode = False
        self.debris_pending = None  # holds {'density': int, 'scatter': int, 'seed': int} when armed
        self.minefield_pending = None  # holds {'name': str, 'type': str, 'width': int, 'height': int, 'density': int} when armed
        self.zone_pending = None  # holds {'name': str, 'type': str, 'radius': int} when armed
        self.gate_mode        = False
        self.platform_mode    = False

        # Multi relay configuration
        self.multi_config = {}

        # Toolbar frame
        self.frame = parent

        # Buttons: station, single relay, batch relay, asteroid, nebula, blackhole, plus our new Center/Scale tool
        icons = [
            'Station.png','Relay.png','RelayP.png','Asteroid.png',
            'Nebular.png','Blackhole.png','Planet.png','Debris.png','mine.png','ring.png','Platform.png','Gate.png',
            'Center.png'
        ]
        cmds  = [
            self.toggle_station_mode,self.toggle_sensor_mode,self.configure_multi_relay,
            self.toggle_asteroid_mode,self.toggle_nebula_mode,self.toggle_blackhole_mode,
            self.toggle_planet_mode, self.open_debris_dialog, self.open_minefield_dialog, self.open_zone_dialog,
            self.toggle_platform_mode,self.toggle_gate_mode,
            self.open_center_dialog
        ]
        refs  = [
            'station_btn','sensor_btn','multi_btn','asteroid_btn',
            'nebula_btn','blackhole_btn','planet_btn','debris_btn','minefield_btn','zone_btn','platform_btn','gate_btn',
            'center_btn'
        ]
        for icon, cmd, ref in zip(icons, cmds, refs):
            container = tk.Frame(self.frame, width=35, height=35)
            container.pack(side=tk.LEFT, padx=5)
            container.pack_propagate(False)
            btn = self.load_icon_button(container, icon, cmd)
            setattr(self, ref, btn)
            btn.pack(fill=tk.BOTH, expand=True)

    # ───────────────────────────────────────────────────────────────────────────
    # Consistent dialog helpers (styling & layout)
    # ───────────────────────────────────────────────────────────────────────────
    def make_dialog(self, title: str, near: str = "toolbar"):
        """
        Create a consistently styled dialog with a body and footer.
        Returns (dlg, body_frame, footer_frame).
        near: "toolbar" (center around toolbar) or "pointer" (center around mouse).
        """
        dlg = tk.Toplevel(self.frame)
        dlg.title(title)
        # Base container with padding
        container = tk.Frame(dlg, padx=10, pady=10)
        container.grid(row=0, column=0, sticky='nsew')
        dlg.grid_rowconfigure(0, weight=1)
        dlg.grid_columnconfigure(0, weight=1)
        # Body (form area)
        body = tk.Frame(container)
        body.grid(row=0, column=0, sticky='nsew')
        # Footer (buttons)
        footer = tk.Frame(container)
        footer.grid(row=1, column=0, sticky='e', pady=(8, 0))
        # Position
        dlg.update_idletasks()
        if near == "pointer":
            px = dlg.winfo_pointerx()
            py = dlg.winfo_pointery()
            w, h = dlg.winfo_width(), dlg.winfo_height()
            dlg.geometry(f"+{px - w//2}+{py - h//2}")
        else:
            w, h = dlg.winfo_width(), dlg.winfo_height()
            px = self.frame.winfo_rootx() + self.frame.winfo_width() // 2
            py = self.frame.winfo_rooty() + self.frame.winfo_height() // 2
            dlg.geometry(f"+{px - w//2}+{py - h//2}")
        return dlg, body, footer

    def labeled_entry(self, parent, label: str, textvariable, width: int = 22, row: int = 0, col: int = 0):
        tk.Label(parent, text=label).grid(row=row, column=col, padx=6, pady=4, sticky='e')
        ent = tk.Entry(parent, textvariable=textvariable, width=width)
        ent.grid(row=row, column=col+1, padx=6, pady=4, sticky='w')
        return ent

    def labeled_spinbox(self, parent, label: str, var, frm=0, to=9999999, width: int = 10, row: int = 0, col: int = 0):
        tk.Label(parent, text=label).grid(row=row, column=col, padx=6, pady=4, sticky='e')
        sb = tk.Spinbox(parent, from_=frm, to=to, textvariable=var, width=width)
        sb.grid(row=row, column=col+1, padx=6, pady=4, sticky='w')
        return sb

    def labeled_combo(self, parent, label: str, var, values, width: int = 18, row: int = 0, col: int = 0):
        tk.Label(parent, text=label).grid(row=row, column=col, padx=6, pady=4, sticky='e')
        cb = ttk.Combobox(parent, textvariable=var, values=list(values), state='readonly', width=width)
        cb.grid(row=row, column=col+1, padx=6, pady=4, sticky='w')
        return cb

    def footer_buttons(self, footer, buttons):
        """
        Create a right-aligned row of buttons.
        buttons: list of tuples (label, command, kwargs_optional)
        """
        for i, b in enumerate(buttons):
            if len(b) == 2:
                text, cmd = b
                kw = {}
            else:
                text, cmd, kw = b
            tk.Button(footer, text=text, command=cmd, **kw).pack(side=tk.LEFT, padx=5)

    def load_icon_button(self, parent, relname, command):
        icon_img = None
        for relpath in [f'HTML/Images/{relname}', f'HTML/Images/Factions/{relname}']:
            candidate = os.path.join(self.base, *relpath.split('/'))
            if os.path.exists(candidate):
                try:
                    pil_img = Image.open(candidate).resize((30,30), Image.LANCZOS)
                    icon_img = ImageTk.PhotoImage(pil_img)
                    break
                except Exception:
                    pass
        if not icon_img:
            # fallback to a blank image if not found
            try:
                blank = Image.new('RGBA', (30, 30), (0, 0, 0, 0))
                icon_img = ImageTk.PhotoImage(blank)
            except Exception:
                icon_img = None
        if icon_img:
            btn = tk.Button(parent, image=icon_img, command=command, bg='#333333', activebackground='#333333')
            btn.image = icon_img
        else:
            btn = tk.Button(parent, text='', command=command, bg='#333333', activebackground='#333333')
        return btn

    def open_center_dialog(self):
        # Consistent dialog for centering and optional scaling
        dlg, body, footer = self.make_dialog("Center and Scale System", near="toolbar")
        # input
        scale_var = tk.DoubleVar(value=1.0)
        self.labeled_entry(body, "Scale multiplier:", scale_var, width=12, row=0, col=0)

        def center_only():
            try:
                CenteringTool.shift_coordinates(self.sm.file_path)
            except Exception as e:
                tk.messagebox.showerror("Center Error", f"Failed to center system:\n{e}")
            finally:
                dlg.destroy()

        def center_and_resize():
            try:
                # Center first
                CenteringTool.shift_coordinates(self.sm.file_path)
                # Then resize (stubbed)
                ResizeTool.scale_system(self.sm.file_path, scale_var.get())
            except Exception as e:
                tk.messagebox.showerror("Center/Resize Error", f"Failed to center/resize system:\n{e}")
            finally:
                dlg.destroy()

        # buttons
        self.footer_buttons(
            footer,
            [
                ("Center Only", center_only, {"width": 14}),
                ("Center & Resize", center_and_resize, {"width": 14})
            ]
        )

    def gen_platform_name(self):
        """Produce a unique WP## name for platforms."""
        existing = set(self.sm.list_objects())
        for _ in range(100):
            name = f"WP {random.randint(1,99)}"
            if name not in existing:
                return name
        return f"WP {random.randint(100,999)}"

    def gen_relay_name(self):
        return self.build_unique_relay_name()

    def default_relay_prefix(self, relay_type: str) -> str:
        if str(relay_type or "").strip() == RELAY_TYPE_WARNING_BUOY:
            return "NAV HAZ"
        return "SR"

    def build_unique_relay_name(self, prefix: str = "SR", numbering: str = RELAY_NUMBERING_RANDOM) -> str:
        prefix = str(prefix or "").strip() or "SR"
        numbering = str(numbering or RELAY_NUMBERING_RANDOM).strip()
        existing = {str(name) for name in self.sm.list_sensor_relays().keys()}
        pattern = re.compile(rf'^{re.escape(prefix)}\s+(\d+)$', re.IGNORECASE)
        matches = []
        width = 3
        for name in existing:
            match = pattern.match(name)
            if not match:
                continue
            digits = match.group(1)
            try:
                matches.append(int(digits))
                width = max(width, len(digits))
            except ValueError:
                continue

        if numbering == RELAY_NUMBERING_ORDERED:
            next_value = (max(matches) + 1) if matches else 1
            width = max(width, len(str(next_value)))
            candidate = f"{prefix} {next_value:0{width}d}"
            while candidate in existing:
                next_value += 1
                width = max(width, len(str(next_value)))
                candidate = f"{prefix} {next_value:0{width}d}"
            return candidate

        max_value = (10 ** width) - 1
        for _ in range(300):
            value = random.randint(1, max_value)
            candidate = f"{prefix} {value:0{width}d}"
            if candidate not in existing:
                return candidate

        width += 1
        next_value = 1
        candidate = f"{prefix} {next_value:0{width}d}"
        while candidate in existing:
            next_value += 1
            candidate = f"{prefix} {next_value:0{width}d}"
        return candidate

    def build_relay_payload(
        self,
        coordinate,
        relay_type: str = RELAY_TYPE_SENSOR,
        broadcast: str = "",
        ping: int = WARNING_BUOY_DEFAULT_PING,
        range_value: int = WARNING_BUOY_DEFAULT_RANGE,
    ):
        payload = {
            "coordinate": [coordinate[0], coordinate[1], coordinate[2]],
            "type": relay_type,
        }
        if relay_type == RELAY_TYPE_WARNING_BUOY:
            payload["broadcast"] = str(broadcast or "")
            payload["ping"] = int(ping)
            payload["range"] = int(range_value)
        return payload

    def gen_station_name(self):
        existing = set(self.sm.list_objects())
        for _ in range(100):
            name = f"DS {random.randint(10,99)}"
            if name not in existing:
                return name
        return f"DS {random.randint(100,999)}"

    def gen_minefield_name(self):
        """Produce a unique Hidden Mine Field X name for terrain."""
        existing = set(self.sm.list_terrain())
        for i in range(1, 1000):
            name = f"Hidden Mine Field {i}"
            if name not in existing:
                return name
        return f"Hidden Mine Field {random.randint(1000,9999)}"

    def default_zone_prefix(self, zone_type: str) -> str:
        zone_key = str(zone_type or "").strip().lower()
        if zone_key in ZONE_TYPE_PREFIXES:
            return ZONE_TYPE_PREFIXES[zone_key]
        if zone_key.endswith("_zone"):
            prefix = zone_key[:-5].replace("_", "").upper()
            if prefix:
                return prefix
        return "ZONE"

    def gen_zone_name(self, zone_type: str = ZONE_TYPE_FCS) -> str:
        existing = {str(name) for name in self.sm.list_objects()}
        prefix = self.default_zone_prefix(zone_type)
        pattern = re.compile(rf'^{re.escape(prefix)}\s*(\d+)$', re.IGNORECASE)
        used_numbers = []
        for name in existing:
            match = pattern.match(name.strip())
            if not match:
                continue
            try:
                used_numbers.append(int(match.group(1)))
            except ValueError:
                continue

        next_value = (max(used_numbers) + 1) if used_numbers else 1
        candidate = f"{prefix}{next_value}"
        while candidate in existing:
            next_value += 1
            candidate = f"{prefix}{next_value}"
        return candidate

    def toggle_station_mode(self):
        self.station_mode = not self.station_mode
        self.sensor_mode = self.multi_mode = self.asteroid_mode = self.nebula_mode = self.blackhole_mode = False
        self.planet_mode = self.debris_mode = self.minefield_mode = self.zone_mode = self.platform_mode = self.gate_mode = False
        if self.station_btn:
            self.station_btn.config(relief=tk.SUNKEN if self.station_mode else tk.RAISED,
                                     bg='#666666' if self.station_mode else '#333333',
                                     activebackground='#666666' if self.station_mode else '#333333')
        for btn in (self.sensor_btn, self.multi_btn, self.asteroid_btn, self.nebula_btn, self.blackhole_btn,
                    self.planet_btn, self.debris_btn, self.minefield_btn, self.zone_btn, self.platform_btn, self.gate_btn):
            if btn:
                btn.config(relief=tk.RAISED, bg='#333333', activebackground='#333333')

    def toggle_sensor_mode(self):
        self.sensor_mode = not self.sensor_mode
        self.station_mode = self.multi_mode = self.asteroid_mode = self.nebula_mode = self.blackhole_mode = False
        self.planet_mode = self.debris_mode = self.minefield_mode = self.zone_mode = self.platform_mode = self.gate_mode = False
        if self.sensor_btn:
            self.sensor_btn.config(relief=tk.SUNKEN if self.sensor_mode else tk.RAISED,
                                    bg='#666666' if self.sensor_mode else '#333333',
                                    activebackground='#666666' if self.sensor_mode else '#333333')
        for btn in (self.station_btn, self.multi_btn, self.asteroid_btn, self.nebula_btn, self.blackhole_btn,
                    self.planet_btn, self.debris_btn, self.minefield_btn, self.zone_btn, self.platform_btn, self.gate_btn):
            if btn:
                btn.config(relief=tk.RAISED, bg='#333333', activebackground='#333333')

    def toggle_asteroid_mode(self):
        self.asteroid_mode = not self.asteroid_mode
        self.station_mode = self.sensor_mode = self.multi_mode = self.nebula_mode = self.blackhole_mode = False
        self.planet_mode = self.debris_mode = self.minefield_mode = self.zone_mode = self.platform_mode = self.gate_mode = False
        if self.asteroid_btn:
            self.asteroid_btn.config(relief=tk.SUNKEN if self.asteroid_mode else tk.RAISED,
                                     bg='#666666' if self.asteroid_mode else '#333333',
                                     activebackground='#666666' if self.asteroid_mode else '#333333')
        for btn in (self.station_btn, self.sensor_btn, self.multi_btn, self.nebula_btn, self.blackhole_btn,
                    self.planet_btn, self.debris_btn, self.minefield_btn, self.zone_btn, self.platform_btn, self.gate_btn):
            if btn:
                btn.config(relief=tk.RAISED, bg='#333333', activebackground='#333333')

    def toggle_planet_mode(self):
        """Arm/disarm Planet placement mode (single-point terrain)."""
        self.planet_mode = not self.planet_mode
        # reset others
        (self.station_mode, self.sensor_mode, self.multi_mode,
         self.asteroid_mode, self.nebula_mode, self.blackhole_mode,
         self.debris_mode, self.minefield_mode, self.zone_mode, self.platform_mode, self.gate_mode) = (False,)*11
        # highlight our button
        if getattr(self, 'planet_btn', None):
            self.planet_btn.config(
                relief=tk.SUNKEN if self.planet_mode else tk.RAISED,
                bg    = '#666666' if self.planet_mode else '#333333',
                activebackground = '#666666' if self.planet_mode else '#333333'
            )
        # reset others' buttons
        for btn in (self.station_btn, self.sensor_btn, self.multi_btn, self.asteroid_btn, self.nebula_btn,
                    self.blackhole_btn, self.debris_btn, self.minefield_btn, self.zone_btn, self.platform_btn, self.gate_btn):
            if btn: btn.config(relief=tk.RAISED, bg='#333333', activebackground='#333333')

    def toggle_nebula_mode(self):
        self.nebula_mode = not self.nebula_mode
        self.station_mode = self.sensor_mode = self.multi_mode = self.asteroid_mode = self.blackhole_mode = self.planet_mode = False
        self.debris_mode = self.minefield_mode = self.zone_mode = self.platform_mode = self.gate_mode = False
        if self.nebula_btn:
            self.nebula_btn.config(relief=tk.SUNKEN if self.nebula_mode else tk.RAISED,
                                    bg='#666666' if self.nebula_mode else '#333333',
                                    activebackground='#666666' if self.nebula_mode else '#333333')
        for btn in (self.station_btn, self.sensor_btn, self.multi_btn, self.asteroid_btn, self.blackhole_btn,
                    self.planet_btn, self.debris_btn, self.minefield_btn, self.zone_btn, self.platform_btn, self.gate_btn):
            if btn:
                btn.config(relief=tk.RAISED, bg='#333333', activebackground='#333333')

    def toggle_blackhole_mode(self):
        self.blackhole_mode = not self.blackhole_mode
        # reset all other modes
        self.station_mode = self.sensor_mode = self.multi_mode = self.asteroid_mode = self.nebula_mode = self.planet_mode = False
        self.debris_mode = self.minefield_mode = self.zone_mode = self.platform_mode = self.gate_mode = False
        # update button relief/colors
        if self.blackhole_btn:
            self.blackhole_btn.config(
                relief=tk.SUNKEN if self.blackhole_mode else tk.RAISED,
                bg    = '#666666' if self.blackhole_mode else '#333333',
                activebackground = '#666666' if self.blackhole_mode else '#333333'
            )
        for btn in (self.station_btn, self.sensor_btn, self.multi_btn, self.asteroid_btn, self.nebula_btn,
                    self.planet_btn, self.debris_btn, self.minefield_btn, self.zone_btn, self.platform_btn, self.gate_btn):
            if btn:
                btn.config(relief=tk.RAISED, bg='#333333', activebackground='#333333')

    def toggle_platform_mode(self):
        """Arm/disarm Platform‐placement mode."""
        self.platform_mode = not self.platform_mode
        # turn off all other modes
        (self.station_mode, self.sensor_mode, self.multi_mode,
         self.asteroid_mode, self.nebula_mode, self.blackhole_mode,
         self.planet_mode, self.debris_mode, self.minefield_mode, self.zone_mode, self.gate_mode) = (False,)*11
        # update button reliefs
        if self.platform_btn:
            self.platform_btn.config(
                relief=tk.SUNKEN if self.platform_mode else tk.RAISED,
                bg    = '#666666'    if self.platform_mode else '#333333',
                activebackground = '#666666' if self.platform_mode else '#333333'
            )
        # reset others
        for btn in (self.station_btn, self.sensor_btn, self.multi_btn,
                    self.asteroid_btn, self.nebula_btn, self.blackhole_btn,
                    self.planet_btn, self.debris_btn, self.minefield_btn, self.zone_btn, self.gate_btn):
            if btn:
                btn.config(relief=tk.RAISED, bg='#333333', activebackground='#333333')

    def toggle_debris_mode(self):
        """Arm/disarm Debris‐field placement mode."""
        self.debris_mode = not self.debris_mode
        # reset all other modes
        (self.station_mode, self.sensor_mode, self.multi_mode, self.planet_mode,
         self.asteroid_mode, self.nebula_mode, self.blackhole_mode,
         self.platform_mode, self.minefield_mode, self.zone_mode, self.gate_mode) = (False,)*11
        # update button states
        if getattr(self, 'debris_btn', None):
            self.debris_btn.config(
                relief=tk.SUNKEN if self.debris_mode else tk.RAISED,
                bg    = '#666666' if self.debris_mode else '#333333',
                activebackground = '#666666' if self.debris_mode else '#333333'
            )
        for btn in (self.station_btn, self.sensor_btn, self.multi_btn, self.asteroid_btn,
                    self.nebula_btn, self.blackhole_btn, self.platform_btn, self.gate_btn, self.minefield_btn, self.zone_btn):
            if btn: btn.config(relief=tk.RAISED, bg='#333333', activebackground='#333333')

    # ───────────────────────────────────────────────────────────────────────────
    # Debris field: dialog-first flow, then place on next click
    # ───────────────────────────────────────────────────────────────────────────
    def open_debris_dialog(self):
        """
        Show a small dialog to configure a Debris Field (density, scatter/radius, seed).
        Pressing 'Add' will ARM placement: the next left-click on the map will create
        the debris_field at the clicked location using these settings.
        """
        # Reset other modes but keep our button highlighted only after arming
        (self.station_mode, self.sensor_mode, self.multi_mode, self.planet_mode,
         self.asteroid_mode, self.nebula_mode, self.blackhole_mode,
         self.platform_mode, self.minefield_mode, self.zone_mode, self.gate_mode) = (False,)*11
        self.zone_pending = None
        if getattr(self, 'zone_btn', None):
            self.zone_btn.config(relief=tk.RAISED, bg='#333333', activebackground='#333333')

        dlg, body, footer = self.make_dialog('New Debris Field', near="toolbar")
        dens_var = tk.IntVar(value=30)
        self.labeled_spinbox(body, 'Density:', dens_var, frm=1, to=100000, width=10, row=0, col=0)
        scat_var = tk.IntVar(value=10000)
        self.labeled_spinbox(body, 'Scatter (radius):', scat_var, frm=1, to=1000000, width=10, row=1, col=0)
        seed_var = tk.IntVar(value=2010)
        self.labeled_spinbox(body, 'Seed:', seed_var, frm=0, to=9999999, width=10, row=2, col=0)

        tk.Label(body, text="Click 'Add', then click on the map to place.", fg='#3a86ff')\
          .grid(row=3, column=0, columnspan=2, padx=6, pady=(2, 6), sticky='w')

        def _arm():
            d = max(1, int(dens_var.get() or 1))
            s = max(1, int(scat_var.get() or 1))
            z = int(seed_var.get() or 0)
            # store config and arm placement
            self.debris_pending = {'density': d, 'scatter': s, 'seed': z}
            self.debris_mode = True
            # visually arm the button
            if getattr(self, 'debris_btn', None):
                self.debris_btn.config(relief=tk.SUNKEN, bg='#666666', activebackground='#666666')
            dlg.destroy()

        def _cancel():
            self.debris_pending = None
            self.debris_mode = False
            if getattr(self, 'debris_btn', None):
                self.debris_btn.config(relief=tk.RAISED, bg='#333333', activebackground='#333333')
            dlg.destroy()

        btn_row = tk.Frame(dlg)
        btn_row.grid(row=4, column=0, columnspan=2, pady=6)
        tk.Button(btn_row, text='Add', width=12, command=_arm).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_row, text='Cancel', width=12, command=_cancel).pack(side=tk.LEFT, padx=5)
        dlg.protocol("WM_DELETE_WINDOW", _cancel)

        # Center the dialog near the toolbar
        dlg.update_idletasks()
        w = dlg.winfo_width(); h = dlg.winfo_height()
        px = self.frame.winfo_rootx() + self.frame.winfo_width() // 2
        py = self.frame.winfo_rooty() + self.frame.winfo_height() // 2
        dlg.geometry(f"+{px - w//2}+{py - h//2}")

    # ───────────────────────────────────────────────────────────────────────────
    # Minefield: dialog-first flow, then place on next click
    # ───────────────────────────────────────────────────────────────────────────
    def open_minefield_dialog(self):
        """
        Configure a Mine Field (name, type, width, height, density).
        Pressing 'Add' will ARM placement: the next left-click on the map will create
        the selected minefield type at the clicked location using these settings.
        """
        # Reset other modes but keep our button highlighted only after arming
        (self.station_mode, self.sensor_mode, self.multi_mode, self.planet_mode,
         self.asteroid_mode, self.nebula_mode, self.blackhole_mode,
         self.platform_mode, self.debris_mode, self.zone_mode, self.gate_mode) = (False,)*11
        self.zone_pending = None
        if getattr(self, 'zone_btn', None):
            self.zone_btn.config(relief=tk.RAISED, bg='#333333', activebackground='#333333')

        dlg, body, footer = self.make_dialog('New Mine Field', near="toolbar")
        name_var = tk.StringVar(value=self.gen_minefield_name())
        self.labeled_entry(body, 'Name:', name_var, width=22, row=0, col=0)
        type_var = tk.StringVar(value='hidden_minefield')
        self.labeled_combo(body, 'Type:', type_var, ['hidden_minefield', 'minefield'], width=18, row=1, col=0)
        width_var = tk.IntVar(value=15000)
        self.labeled_spinbox(body, 'Width:', width_var, frm=1, to=1000000, width=10, row=2, col=0)
        height_var = tk.IntVar(value=15000)
        self.labeled_spinbox(body, 'Height:', height_var, frm=1, to=1000000, width=10, row=3, col=0)
        dens_var = tk.IntVar(value=70)
        self.labeled_spinbox(body, 'Density:', dens_var, frm=1, to=100000, width=10, row=4, col=0)

        tk.Label(body, text="Click 'Add', then click on the map to place.", fg='#3a86ff')\
          .grid(row=5, column=0, columnspan=2, padx=6, pady=(2, 6), sticky='w')

        def _arm():
            name = (name_var.get() or '').strip()
            if not name:
                name = self.gen_minefield_name()
            minefield_type = (type_var.get() or 'hidden_minefield').strip()
            if minefield_type not in ('hidden_minefield', 'minefield'):
                minefield_type = 'hidden_minefield'
            # store config and arm placement
            self.minefield_pending = {
                'name': name,
                'type': minefield_type,
                'width': max(1, int(width_var.get() or 1)),
                'height': max(1, int(height_var.get() or 1)),
                'density': max(1, int(dens_var.get() or 1))
            }
            self.minefield_mode = True
            if getattr(self, 'minefield_btn', None):
                self.minefield_btn.config(relief=tk.SUNKEN, bg='#666666', activebackground='#666666')
            dlg.destroy()

        def _cancel():
            self.minefield_pending = None
            self.minefield_mode = False
            if getattr(self, 'minefield_btn', None):
                self.minefield_btn.config(relief=tk.RAISED, bg='#333333', activebackground='#333333')
            dlg.destroy()

        btn_row = tk.Frame(dlg)
        btn_row.grid(row=6, column=0, columnspan=2, pady=6)
        tk.Button(btn_row, text='Add', width=12, command=_arm).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_row, text='Cancel', width=12, command=_cancel).pack(side=tk.LEFT, padx=5)
        dlg.protocol("WM_DELETE_WINDOW", _cancel)

        dlg.update_idletasks()
        w = dlg.winfo_width(); h = dlg.winfo_height()
        px = self.frame.winfo_rootx() + self.frame.winfo_width() // 2
        py = self.frame.winfo_rooty() + self.frame.winfo_height() // 2
        dlg.geometry(f"+{px - w//2}+{py - h//2}")

    def open_zone_dialog(self):
        """
        Configure a circular zone placement.
        Pressing 'Add' arms placement so the next left-click on the map will create
        the configured zone centered on that click.
        """
        (self.station_mode, self.sensor_mode, self.multi_mode, self.planet_mode,
         self.asteroid_mode, self.nebula_mode, self.blackhole_mode,
         self.platform_mode, self.debris_mode, self.minefield_mode, self.gate_mode) = (False,) * 11
        self.zone_mode = False
        self.zone_pending = None

        for btn in (
            getattr(self, 'station_btn', None),
            getattr(self, 'sensor_btn', None),
            getattr(self, 'multi_btn', None),
            getattr(self, 'asteroid_btn', None),
            getattr(self, 'nebula_btn', None),
            getattr(self, 'blackhole_btn', None),
            getattr(self, 'planet_btn', None),
            getattr(self, 'debris_btn', None),
            getattr(self, 'minefield_btn', None),
            getattr(self, 'zone_btn', None),
            getattr(self, 'platform_btn', None),
            getattr(self, 'gate_btn', None),
        ):
            if btn:
                btn.config(relief=tk.RAISED, bg='#333333', activebackground='#333333')

        dlg, body, footer = self.make_dialog('New Zone', near="toolbar")
        type_var = tk.StringVar(value=ZONE_TYPE_OPTIONS[0])
        name_var = tk.StringVar(value=self.gen_zone_name(type_var.get()))
        radius_var = tk.IntVar(value=5000)

        self.labeled_combo(body, 'Type:', type_var, ZONE_TYPE_OPTIONS, width=18, row=0, col=0)
        self.labeled_entry(body, 'Name:', name_var, width=22, row=1, col=0)
        self.labeled_spinbox(body, 'Radius:', radius_var, frm=1, to=1000000, width=10, row=2, col=0)

        tk.Label(body, text="Click 'Add', then click on the map to place.", fg='#3a86ff')\
            .grid(row=3, column=0, columnspan=2, padx=6, pady=(2, 6), sticky='w')

        last_generated = {'value': name_var.get()}

        def sync_name(*_):
            suggested = self.gen_zone_name(type_var.get())
            current = name_var.get().strip()
            if not current or current == last_generated['value']:
                name_var.set(suggested)
            last_generated['value'] = suggested

        type_var.trace_add('write', sync_name)

        def _arm():
            zone_type = (type_var.get() or ZONE_TYPE_OPTIONS[0]).strip().lower()
            if zone_type not in ZONE_TYPE_OPTIONS:
                zone_type = ZONE_TYPE_OPTIONS[0]
            name = (name_var.get() or '').strip() or self.gen_zone_name(zone_type)
            self.zone_pending = {
                'name': name,
                'type': zone_type,
                'radius': max(1, int(radius_var.get() or 1)),
            }
            self.zone_mode = True
            if getattr(self, 'zone_btn', None):
                self.zone_btn.config(relief=tk.SUNKEN, bg='#666666', activebackground='#666666')
            dlg.destroy()

        def _cancel():
            self.zone_pending = None
            self.zone_mode = False
            if getattr(self, 'zone_btn', None):
                self.zone_btn.config(relief=tk.RAISED, bg='#333333', activebackground='#333333')
            dlg.destroy()

        self.footer_buttons(
            footer,
            [
                ('Add', _arm, {'width': 12}),
                ('Cancel', _cancel, {'width': 12}),
            ]
        )
        dlg.protocol("WM_DELETE_WINDOW", _cancel)

    def configure_multi_relay(self):
        # Reset other modes
        self.station_mode = self.sensor_mode = self.asteroid_mode = self.nebula_mode = False
        self.blackhole_mode = self.planet_mode = self.debris_mode = self.minefield_mode = self.zone_mode = False
        self.platform_mode = self.gate_mode = False
        self.zone_pending = None
        if self.station_btn: self.station_btn.config(relief=tk.RAISED, bg='#333333', activebackground='#333333')
        if self.asteroid_btn: self.asteroid_btn.config(relief=tk.RAISED, bg='#333333', activebackground='#333333')
        if self.nebula_btn: self.nebula_btn.config(relief=tk.RAISED, bg='#333333', activebackground='#333333')
        if self.sensor_btn: self.sensor_btn.config(relief=tk.RAISED, bg='#333333', activebackground='#333333')
        if self.blackhole_btn: self.blackhole_btn.config(relief=tk.RAISED, bg='#333333', activebackground='#333333')
        if self.planet_btn: self.planet_btn.config(relief=tk.RAISED, bg='#333333', activebackground='#333333')
        if self.debris_btn: self.debris_btn.config(relief=tk.RAISED, bg='#333333', activebackground='#333333')
        if self.minefield_btn: self.minefield_btn.config(relief=tk.RAISED, bg='#333333', activebackground='#333333')
        if self.zone_btn: self.zone_btn.config(relief=tk.RAISED, bg='#333333', activebackground='#333333')
        if self.platform_btn: self.platform_btn.config(relief=tk.RAISED, bg='#333333', activebackground='#333333')
        if self.gate_btn: self.gate_btn.config(relief=tk.RAISED, bg='#333333', activebackground='#333333')
        dlg, body, footer = self.make_dialog("Batch Sensor Relay Placement", near="pointer")
        tk.Label(body, text='Pattern:').grid(row=0, column=0, padx=5, pady=5, sticky='w')
        pattern_var = tk.StringVar(value='Line')
        tk.Radiobutton(body, text='Line', variable=pattern_var, value='Line').grid(row=0, column=1)
        tk.Radiobutton(body, text='Circle', variable=pattern_var, value='Circle').grid(row=0, column=2)
        tk.Label(body, text='Repeat:').grid(row=1, column=0, padx=5, pady=5, sticky='w')
        rep_var = tk.IntVar(value=45000)
        tk.Spinbox(body, from_=10000, to=100000, textvariable=rep_var).grid(row=1, column=1, padx=5)
        tk.Label(body, text='Radius:').grid(row=2, column=0, padx=5, pady=5, sticky='w')
        rad_var = tk.IntVar(value=45000)
        tk.Spinbox(body, from_=10000, to=100000, textvariable=rad_var).grid(row=2, column=1, padx=5)
        tk.Label(body, text='Relay Type:').grid(row=3, column=0, padx=5, pady=5, sticky='w')
        relay_type_var = tk.StringVar(value=RELAY_TYPE_SENSOR)
        ttk.Combobox(
            body,
            textvariable=relay_type_var,
            values=RELAY_TYPE_OPTIONS,
            state='readonly',
            width=18
        ).grid(row=3, column=1, columnspan=2, padx=5, pady=5, sticky='w')
        tk.Label(body, text='Name Prefix:').grid(row=4, column=0, padx=5, pady=5, sticky='w')
        prefix_var = tk.StringVar(value=self.default_relay_prefix(relay_type_var.get()))
        tk.Entry(body, textvariable=prefix_var, width=18).grid(row=4, column=1, columnspan=2, padx=5, pady=5, sticky='w')
        tk.Label(body, text='Numbering:').grid(row=5, column=0, padx=5, pady=5, sticky='w')
        numbering_var = tk.StringVar(value=RELAY_NUMBERING_ORDERED)
        ttk.Combobox(
            body,
            textvariable=numbering_var,
            values=RELAY_NUMBERING_OPTIONS,
            state='readonly',
            width=18
        ).grid(row=5, column=1, columnspan=2, padx=5, pady=5, sticky='w')
        tk.Label(body, text='Name Preview:').grid(row=6, column=0, padx=5, pady=5, sticky='w')
        name_preview_var = tk.StringVar()
        name_preview_entry = tk.Entry(body, textvariable=name_preview_var, width=18, state='readonly')
        name_preview_entry.grid(row=6, column=1, columnspan=2, padx=5, pady=5, sticky='w')

        warning_frame = tk.Frame(body)
        warning_frame.grid(row=7, column=0, columnspan=3, sticky='w')
        broadcast_var = tk.StringVar(value=WARNING_BUOY_DEFAULT_BROADCAST)
        ping_var = tk.IntVar(value=WARNING_BUOY_DEFAULT_PING)
        range_var = tk.IntVar(value=WARNING_BUOY_DEFAULT_RANGE)

        def sync_prefix(*_):
            current = prefix_var.get().strip()
            sensor_default = self.default_relay_prefix(RELAY_TYPE_SENSOR)
            warning_default = self.default_relay_prefix(RELAY_TYPE_WARNING_BUOY)
            if current in ("", sensor_default, warning_default):
                prefix_var.set(self.default_relay_prefix(relay_type_var.get()))

        def render_warning_fields():
            for child in warning_frame.winfo_children():
                child.destroy()
            if relay_type_var.get() != RELAY_TYPE_WARNING_BUOY:
                return
            tk.Label(warning_frame, text='Broadcast:').grid(row=0, column=0, padx=5, pady=5, sticky='w')
            tk.Entry(warning_frame, textvariable=broadcast_var, width=18).grid(row=0, column=1, columnspan=2, padx=5, pady=5, sticky='w')
            tk.Label(warning_frame, text='Ping:').grid(row=1, column=0, padx=5, pady=5, sticky='w')
            tk.Spinbox(warning_frame, from_=0, to=99, textvariable=ping_var, width=10).grid(row=1, column=1, padx=5, pady=5, sticky='w')
            tk.Label(warning_frame, text='Range:').grid(row=2, column=0, padx=5, pady=5, sticky='w')
            tk.Spinbox(warning_frame, from_=1000, to=1000000, textvariable=range_var, width=10).grid(row=2, column=1, padx=5, pady=5, sticky='w')

        def update_name_preview(*_):
            prefix = prefix_var.get().strip() or self.default_relay_prefix(relay_type_var.get())
            preview = self.build_unique_relay_name(prefix, numbering_var.get())
            name_preview_var.set(preview)

        relay_type_var.trace_add('write', lambda *_: (sync_prefix(), render_warning_fields(), update_name_preview()))
        prefix_var.trace_add('write', update_name_preview)
        numbering_var.trace_add('write', update_name_preview)
        render_warning_fields()
        update_name_preview()

        def start_batch():
            prefix = prefix_var.get().strip() or self.default_relay_prefix(relay_type_var.get())
            self.multi_config = {
                'pattern': pattern_var.get(),
                'repeat': rep_var.get(),
                'radius': rad_var.get(),
                'relay_type': relay_type_var.get(),
                'prefix': prefix,
                'numbering': numbering_var.get(),
                'broadcast': broadcast_var.get().strip(),
                'ping': ping_var.get(),
                'range': range_var.get(),
            }
            self.multi_mode = True
            if self.multi_btn:
                self.multi_btn.config(relief=tk.SUNKEN, bg='#666666', activebackground='#666666')
            dlg.destroy()
        def _cancel():
            self.multi_mode = False
            if self.multi_btn:
                self.multi_btn.config(relief=tk.RAISED, bg='#333333', activebackground='#333333')
            dlg.destroy()
        dlg.protocol("WM_DELETE_WINDOW", _cancel)
        self.footer_buttons(
            footer,
            [
                ('OK', start_batch, {'width': 12}),
                ('Cancel', _cancel, {'width': 12}),
            ]
        )
    
    
    def gen_gate_name(self):
        """Produce a unique GP-## name for jump points."""
        existing = set(self.sm.list_objects())
        for _ in range(100):
            name = f"JP {random.randint(10,99)}"
            if name not in existing:
                return name
        return f"JP {random.randint(100,999)}"

    def toggle_gate_mode(self):
        """Arm/disarm Gate‐placement mode."""
        self.gate_mode = not self.gate_mode
        # reset all other modes
        (self.station_mode, self.sensor_mode, self.multi_mode,
         self.asteroid_mode, self.nebula_mode, self.blackhole_mode,
         self.planet_mode, self.debris_mode, self.minefield_mode, self.zone_mode, self.platform_mode) = (False,)*11
        self.zone_pending = None
       # highlight our button
        if self.gate_btn:
            self.gate_btn.config(
                relief=tk.SUNKEN if self.gate_mode else tk.RAISED,
                bg    = '#666666'    if self.gate_mode else '#333333',
                activebackground = '#666666' if self.gate_mode else '#333333'
            )
        # reset the others
        for btn in (self.station_btn, self.sensor_btn, self.multi_btn,
                    self.asteroid_btn, self.nebula_btn, self.blackhole_btn,
                    self.planet_btn, self.debris_btn, self.minefield_btn, self.zone_btn, self.platform_btn):
            if btn:
                btn.config(relief=tk.RAISED, bg='#333333', activebackground='#333333')
