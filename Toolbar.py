import os
import tkinter as tk
from tkinter import ttk
from tkinter import messagebox

import CenteringTool
import ResizeTool
from PIL import Image, ImageTk
import random
import math
from tkinter import messagebox

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
        self.planet_mode = False
        self.debris_pending = None  # holds {'density': int, 'scatter': int, 'seed': int} when armed
        self.gate_mode        = False
        self.platform_mode    = False

        # Multi relay configuration
        self.multi_config = {}

        # Toolbar frame
        self.frame = parent

        # Buttons: station, single relay, batch relay, asteroid, nebula, blackhole, plus our new Center/Scale tool
        icons = [
            'Station.png','Relay.png','RelayP.png','Asteroid.png',
            'Nebular.png','Blackhole.png','Planet.png','Debris.png','Platform.png','Gate.png',
            'Center.png'
        ]
        cmds  = [
            self.toggle_station_mode,self.toggle_sensor_mode,self.configure_multi_relay,
            self.toggle_asteroid_mode,self.toggle_nebula_mode,self.toggle_blackhole_mode,
            self.toggle_planet_mode, self.open_debris_dialog,
            self.toggle_platform_mode,self.toggle_gate_mode,
            self.open_center_dialog
        ]
        refs  = [
            'station_btn','sensor_btn','multi_btn','asteroid_btn',
            'nebula_btn','blackhole_btn','planet_btn','debris_btn','platform_btn','gate_btn',
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
        existing = set(self.sm.list_sensor_relays().keys())
        for _ in range(100):
            name = f"SR {random.randint(10,99)}"
            if name not in existing:
                return name
        return f"SR {random.randint(100,999)}"

    def gen_station_name(self):
        existing = set(self.sm.list_objects())
        for _ in range(100):
            name = f"DS {random.randint(10,99)}"
            if name not in existing:
                return name
        return f"DS {random.randint(100,999)}"

    def toggle_station_mode(self):
        self.station_mode = not self.station_mode
        self.sensor_mode = self.multi_mode = self.asteroid_mode = self.nebula_mode = self.blackhole_mode = False
        if self.station_btn:
            self.station_btn.config(relief=tk.SUNKEN if self.station_mode else tk.RAISED,
                                     bg='#666666' if self.station_mode else '#333333',
                                     activebackground='#666666' if self.station_mode else '#333333')
        for btn in (self.sensor_btn, self.multi_btn, self.asteroid_btn, self.nebula_btn, self.blackhole_btn):
            if btn:
                btn.config(relief=tk.RAISED, bg='#333333', activebackground='#333333')

    def toggle_sensor_mode(self):
        self.sensor_mode = not self.sensor_mode
        self.station_mode = self.multi_mode = self.asteroid_mode = self.nebula_mode = self.blackhole_mode = False
        if self.sensor_btn:
            self.sensor_btn.config(relief=tk.SUNKEN if self.sensor_mode else tk.RAISED,
                                    bg='#666666' if self.sensor_mode else '#333333',
                                    activebackground='#666666' if self.sensor_mode else '#333333')
        for btn in (self.station_btn, self.multi_btn, self.asteroid_btn, self.nebula_btn, self.blackhole_btn):
            if btn:
                btn.config(relief=tk.RAISED, bg='#333333', activebackground='#333333')

    def toggle_asteroid_mode(self):
        self.asteroid_mode = not self.asteroid_mode
        self.station_mode = self.sensor_mode = self.multi_mode = self.nebula_mode = self.blackhole_mode = False
        if self.asteroid_btn:
            self.asteroid_btn.config(relief=tk.SUNKEN if self.asteroid_mode else tk.RAISED,
                                     bg='#666666' if self.asteroid_mode else '#333333',
                                     activebackground='#666666' if self.asteroid_mode else '#333333')
        for btn in (self.station_btn, self.sensor_btn, self.multi_btn, self.nebula_btn, self.blackhole_btn):
            if btn:
                btn.config(relief=tk.RAISED, bg='#333333', activebackground='#333333')

    def toggle_planet_mode(self):
        """Arm/disarm Planet placement mode (single-point terrain)."""
        self.planet_mode = not self.planet_mode
        # reset others
        (self.station_mode, self.sensor_mode, self.multi_mode,
         self.asteroid_mode, self.nebula_mode, self.blackhole_mode,
         self.debris_mode, self.platform_mode, self.gate_mode) = (False,)*9
        # highlight our button
        if getattr(self, 'planet_btn', None):
            self.planet_btn.config(
                relief=tk.SUNKEN if self.planet_mode else tk.RAISED,
                bg    = '#666666' if self.planet_mode else '#333333',
                activebackground = '#666666' if self.planet_mode else '#333333'
            )
        # reset others' buttons
        for btn in (self.station_btn, self.sensor_btn, self.multi_btn, self.asteroid_btn, self.nebula_btn,
                    self.blackhole_btn, self.debris_btn, self.platform_btn, self.gate_btn):
            if btn: btn.config(relief=tk.RAISED, bg='#333333', activebackground='#333333')

    def toggle_nebula_mode(self):
        self.nebula_mode = not self.nebula_mode
        self.station_mode = self.sensor_mode = self.multi_mode = self.asteroid_mode = self.blackhole_mode = self.planet_mode = False
        if self.nebula_btn:
            self.nebula_btn.config(relief=tk.SUNKEN if self.nebula_mode else tk.RAISED,
                                    bg='#666666' if self.nebula_mode else '#333333',
                                    activebackground='#666666' if self.nebula_mode else '#333333')
        for btn in (self.station_btn, self.sensor_btn, self.multi_btn, self.asteroid_btn, self.blackhole_btn):
            if btn:
                btn.config(relief=tk.RAISED, bg='#333333', activebackground='#333333')

    def toggle_blackhole_mode(self):
        self.blackhole_mode = not self.blackhole_mode
        # reset all other modes
        self.station_mode = self.sensor_mode = self.multi_mode = self.asteroid_mode = self.nebula_mode = self.planet_mode = False
        # update button relief/colors
        if self.blackhole_btn:
            self.blackhole_btn.config(
                relief=tk.SUNKEN if self.blackhole_mode else tk.RAISED,
                bg    = '#666666' if self.blackhole_mode else '#333333',
                activebackground = '#666666' if self.blackhole_mode else '#333333'
            )
        for btn in (self.station_btn, self.sensor_btn, self.multi_btn, self.asteroid_btn, self.nebula_btn):
            if btn:
                btn.config(relief=tk.RAISED, bg='#333333', activebackground='#333333')

    def toggle_platform_mode(self):
        """Arm/disarm Platform‐placement mode."""
        self.platform_mode = not self.platform_mode
        # turn off all other modes
        (self.station_mode, self.sensor_mode, self.multi_mode,
         self.asteroid_mode, self.nebula_mode, self.blackhole_mode) = (False,)*6
        # update button reliefs
        if self.platform_btn:
            self.platform_btn.config(
                relief=tk.SUNKEN if self.platform_mode else tk.RAISED,
                bg    = '#666666'    if self.platform_mode else '#333333',
                activebackground = '#666666' if self.platform_mode else '#333333'
            )
        # reset others
        for btn in (self.station_btn, self.sensor_btn, self.multi_btn,
                    self.asteroid_btn, self.nebula_btn, self.blackhole_btn):
            if btn:
                btn.config(relief=tk.RAISED, bg='#333333', activebackground='#333333')

    def toggle_debris_mode(self):
        """Arm/disarm Debris‐field placement mode."""
        self.debris_mode = not self.debris_mode
        # reset all other modes
        (self.station_mode, self.sensor_mode, self.multi_mode, self.planet_mode,
         self.asteroid_mode, self.nebula_mode, self.blackhole_mode,
         self.platform_mode, self.gate_mode) = (False,)*9
        # update button states
        if getattr(self, 'debris_btn', None):
            self.debris_btn.config(
                relief=tk.SUNKEN if self.debris_mode else tk.RAISED,
                bg    = '#666666' if self.debris_mode else '#333333',
                activebackground = '#666666' if self.debris_mode else '#333333'
            )
        for btn in (self.station_btn, self.sensor_btn, self.multi_btn, self.asteroid_btn,
                    self.nebula_btn, self.blackhole_btn, self.platform_btn, self.gate_btn):
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
         self.platform_mode, self.gate_mode) = (False,)*9

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

        # Center the dialog near the toolbar
        dlg.update_idletasks()
        w = dlg.winfo_width(); h = dlg.winfo_height()
        px = self.frame.winfo_rootx() + self.frame.winfo_width() // 2
        py = self.frame.winfo_rooty() + self.frame.winfo_height() // 2
        dlg.geometry(f"+{px - w//2}+{py - h//2}")

    def configure_multi_relay(self):
        # Reset other modes
        self.station_mode = self.sensor_mode = self.asteroid_mode = self.nebula_mode = False
        if self.station_btn: self.station_btn.config(relief=tk.RAISED, bg='#333333', activebackground='#333333')
        if self.asteroid_btn: self.asteroid_btn.config(relief=tk.RAISED, bg='#333333', activebackground='#333333')
        if self.nebula_btn: self.nebula_btn.config(relief=tk.RAISED, bg='#333333', activebackground='#333333')
        if self.sensor_btn: self.sensor_btn.config(relief=tk.RAISED, bg='#333333', activebackground='#333333')
        dlg = tk.Toplevel(self.frame)
        dlg.title('Batch Sensor Relay Placement')
        tk.Label(dlg, text='Pattern:').grid(row=0, column=0, padx=5, pady=5, sticky='w')
        pattern_var = tk.StringVar(value='Line')
        tk.Radiobutton(dlg, text='Line', variable=pattern_var, value='Line').grid(row=0, column=1)
        tk.Radiobutton(dlg, text='Circle', variable=pattern_var, value='Circle').grid(row=0, column=2)
        tk.Label(dlg, text='Repeat:').grid(row=1, column=0, padx=5, pady=5, sticky='w')
        rep_var = tk.IntVar(value=45000)
        tk.Spinbox(dlg, from_=10000, to=100000, textvariable=rep_var).grid(row=1, column=1, padx=5)
        tk.Label(dlg, text='Radius:').grid(row=2, column=0, padx=5, pady=5, sticky='w')
        rad_var = tk.IntVar(value=45000)
        tk.Spinbox(dlg, from_=10000, to=100000, textvariable=rad_var).grid(row=2, column=1, padx=5)
        def start_batch():
            self.multi_config = {'pattern': pattern_var.get(), 'repeat': rep_var.get(), 'radius': rad_var.get()}
            self.multi_mode = True
            if self.multi_btn:
                self.multi_btn.config(relief=tk.SUNKEN, bg='#666666', activebackground='#666666')
            dlg.destroy()
        tk.Button(dlg, text='OK', command=start_batch).grid(row=3, column=0, columnspan=3, pady=10)
        dlg.update_idletasks()  # ensure correct winfo_width/height
        w = dlg.winfo_width()
        h = dlg.winfo_height()
        # center dialog on current mouse pointer
        px = dlg.winfo_pointerx()
        py = dlg.winfo_pointery()
        x = px - w // 2
        y = py - h // 2
        dlg.geometry(f"+{x}+{y}")
    
    
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
         self.asteroid_mode, self.nebula_mode, self.blackhole_mode) = (False,)*6
       # highlight our button
        if self.gate_btn:
            self.gate_btn.config(
                relief=tk.SUNKEN if self.gate_mode else tk.RAISED,
                bg    = '#666666'    if self.gate_mode else '#333333',
                activebackground = '#666666' if self.gate_mode else '#333333'
            )
        # reset the others
        for btn in (self.station_btn, self.sensor_btn, self.multi_btn,
                    self.asteroid_btn, self.nebula_btn, self.blackhole_btn):
            if btn:
                btn.config(relief=tk.RAISED, bg='#333333', activebackground='#333333')
