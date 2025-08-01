import os
import tkinter as tk
from tkinter import ttk

import CenteringTool
import ResizeTool
from PIL import Image, ImageTk
import random
import math

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
        self.gate_mode        = False
        self.platform_mode    = False

        # Multi relay configuration
        self.multi_config = {}

        # Toolbar frame
        self.frame = parent

        # Buttons: station, single relay, batch relay, asteroid, nebula, blackhole, plus our new Center/Scale tool
        icons = [
            'Station.png','Relay.png','RelayP.png','Asteroid.png',
            'Nebular.png','Blackhole.png','Platform.png','Gate.png',
            'Center.png'
        ]
        cmds  = [
            self.toggle_station_mode,self.toggle_sensor_mode,self.configure_multi_relay,
            self.toggle_asteroid_mode,self.toggle_nebula_mode,self.toggle_blackhole_mode,
            self.toggle_platform_mode,self.toggle_gate_mode,
            self.open_center_dialog
        ]
        refs  = [
            'station_btn','sensor_btn','multi_btn','asteroid_btn',
            'nebula_btn','blackhole_btn','platform_btn','gate_btn',
            'center_btn'
        ]
        for icon, cmd, ref in zip(icons, cmds, refs):
            container = tk.Frame(self.frame, width=35, height=35)
            container.pack(side=tk.LEFT, padx=5)
            container.pack_propagate(False)
            btn = self.load_icon_button(container, icon, cmd)
            setattr(self, ref, btn)
            btn.pack(fill=tk.BOTH, expand=True)

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
        # Dialog for centering and optional scaling
        dlg = tk.Toplevel(self.frame)
        dlg.title("Center and Scale System")
        # Scale multiplier input
        tk.Label(dlg, text="Scale multiplier:").grid(row=0, column=0, padx=5, pady=5, sticky='e')
        scale_var = tk.DoubleVar(value=1.0)
        tk.Entry(dlg, textvariable=scale_var).grid(row=0, column=1, padx=5, pady=5)

        def center_only():
            try:
                CenteringTool.shift_coordinates(self.sm.file_path)
            except Exception as e:
                tk.messagebox.showerror("Center Error", f"Failed to center system:\n{e}")
            dlg.destroy()

        def center_and_resize():
            try:
                # Center first
                CenteringTool.shift_coordinates(self.sm.file_path)
                # Then resize (stubbed)
                ResizeTool.scale_system(self.sm.file_path, scale_var.get())
            except Exception as e:
                tk.messagebox.showerror("Center/Resize Error", f"Failed to center/resize system:\n{e}")
            dlg.destroy()

        # Action buttons
        tk.Button(dlg, text="Center Only",      command=center_only)     .grid(row=1, column=0, padx=5, pady=10)
        tk.Button(dlg, text="Center & Resize",  command=center_and_resize).grid(row=1, column=1, padx=5, pady=10)

        # Center dialog relative to toolbar
        dlg.update_idletasks()
        w, h = dlg.winfo_width(), dlg.winfo_height()
        px = self.frame.winfo_rootx() + self.frame.winfo_width() // 2
        py = self.frame.winfo_rooty() + self.frame.winfo_height() // 2
        dlg.geometry(f"+{px - w//2}+{py - h//2}")

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

    def toggle_nebula_mode(self):
        self.nebula_mode = not self.nebula_mode
        self.station_mode = self.sensor_mode = self.multi_mode = self.asteroid_mode = self.blackhole_mode = False
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
        self.station_mode = self.sensor_mode = self.multi_mode = self.asteroid_mode = self.nebula_mode = False
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
