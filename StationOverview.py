"""Station overview window; editor actions are supplied as callbacks."""
import tkinter as tk
from tkinter import ttk
from MapTypes import STATION_OR_PLATFORM_TYPES


def open_station_overview(*,
    win, bind_history_shortcuts, valid_sides,
    ship_entries, overview_refreshers, sm,
    refresh_objects_list, _az09_key, valid_hulls,
    convert_station_type, open_cargo_teams_dialog, push_undo,
    flush_pending_text_widgets, ctx, _refresh_ui,
    draw_map
):
    list_win = tk.Toplevel(win)
    list_win.title("Stations Overview")
    list_win.transient(win)
    list_win.geometry(f"{min(1250, list_win.winfo_screenwidth() - 80)}x{min(700, list_win.winfo_screenheight() - 100)}")
    list_win.minsize(600, 350)
    bind_history_shortcuts(list_win)

    tk.Label(list_win, text="Click a name to edit cargo/teams. Drag header dividers to resize columns; click headings to sort.").pack(anchor='w', padx=8, pady=(8, 0))

    bulk = tk.LabelFrame(list_win, text="Change side for all stations and platforms")
    bulk.pack(fill='x', padx=8, pady=6)
    source_var = tk.StringVar()
    target_var = tk.StringVar()
    tk.Label(bulk, text="From:").pack(side='left')
    source_cb = ttk.Combobox(bulk, textvariable=source_var, state='readonly', width=20)
    source_cb.pack(side='left', padx=4)
    tk.Label(bulk, text="To:").pack(side='left')
    ttk.Combobox(bulk, textvariable=target_var, values=sorted(valid_sides),
                 state='readonly', width=20).pack(side='left', padx=4)
    status_var = tk.StringVar()
    def change_all_sides():
        source, target = source_var.get(), target_var.get()
        if not source or not target or source == target:
            status_var.set("Choose two different sides.")
            return
        matches = [obj for obj in sm.data.get('objects', {}).values()
                   if str(obj.get('type', '')).lower() in STATION_OR_PLATFORM_TYPES
                   and _first_side(obj) == source]
        if matches:
            flush_pending_text_widgets()
            push_undo()
            for obj in matches:
                sides = obj.get('sides')
                obj['sides'] = [target] + (list(sides[1:]) if isinstance(sides, (list, tuple)) else [])
            _refresh_ui()
        status_var.set(f"Changed {len(matches)} objects from {source} to {target}.")
    tk.Button(bulk, text="Change all", command=change_all_sides).pack(side='left', padx=4)
    tk.Label(list_win, textvariable=status_var, anchor='w').pack(fill='x', padx=8)

    container = tk.Frame(list_win)
    container.pack(fill='both', expand=True, padx=8, pady=8)

    canvas = tk.Canvas(container, highlightthickness=0)
    vsb = ttk.Scrollbar(container, orient='vertical', command=canvas.yview)
    hsb = ttk.Scrollbar(container, orient='horizontal', command=canvas.xview)
    canvas.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
    hsb.grid(row=1, column=0, sticky='ew')
    canvas.grid(row=0, column=0, sticky='nsew')
    vsb.grid(row=0, column=1, sticky='ns')
    container.grid_rowconfigure(0, weight=1)
    container.grid_columnconfigure(0, weight=1)

    rows_frame = tk.Frame(canvas)
    rows_id = canvas.create_window((0, 0), window=rows_frame, anchor='nw')

    def _sync_scrollregion(event=None):
        canvas.configure(scrollregion=canvas.bbox('all'))

    def _sync_width(event):
        canvas.itemconfigure(rows_id, width=max(canvas.winfo_width(), sum(column_widths.values())))

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

    def _first_side(obj):
        sides = obj.get('sides')
        if isinstance(sides, (list, tuple)) and sides:
            return str(sides[0] or '')
        if isinstance(sides, str):
            return sides
        return ''

    def _count_positive_values(values):
        if not isinstance(values, dict):
            return 0
        count = 0
        for qty in values.values():
            try:
                if int(qty) > 0:
                    count += 1
            except Exception:
                if qty:
                    count += 1
        return count

    def _cargo_team_counts(obj):
        return (
            _count_positive_values(obj.get('cargo') or {}),
            _count_positive_values(obj.get('teams') or {}),
        )

    def _cargo_team_summary(obj):
        cargo_count, team_count = _cargo_team_counts(obj)
        if cargo_count or team_count:
            return f"Cargo {cargo_count} / Teams {team_count}"
        return "Empty"

    def _facilities_text(obj):
        facilities = obj.get('facilities') or []
        if not isinstance(facilities, (list, tuple, set)):
            return str(facilities or '')
        return ", ".join(str(item) for item in facilities)

    sort_state = {'column': 'name', 'reverse': False}
    overview_columns = (
        ('name', 'Name', 200),
        ('type', 'Type', 110),
        ('side', 'Side', 140),
        ('hull', 'Hull', 180),
        ('facilities', 'Facilities', 280),
        ('cargo', 'Cargo/Teams', 160),
    )

    column_widths = {key: width for key, _, width in overview_columns}
    initial_layout = True

    def _station_sort_value(obj_name, obj, column):
        if column == 'name':
            return _az09_key(obj_name)
        if column == 'type':
            return _az09_key(str(obj.get('type', '') or ''))
        if column == 'side':
            return _az09_key(_first_side(obj))
        if column == 'hull':
            return _az09_key(str(obj.get('hull', '') or ''))
        if column == 'facilities':
            return _az09_key(_facilities_text(obj))
        if column == 'cargo':
            cargo_count, team_count = _cargo_team_counts(obj)
            return (cargo_count + team_count, cargo_count, team_count)
        return _az09_key(obj_name)

    def _sort_entries(entries):
        column = sort_state.get('column', 'name')
        return sorted(
            entries,
            key=lambda item: (_station_sort_value(item[0], item[1], column), _az09_key(item[0])),
            reverse=bool(sort_state.get('reverse')),
        )

    def _set_station_sort(column):
        if sort_state.get('column') == column:
            sort_state['reverse'] = not sort_state.get('reverse', False)
        else:
            sort_state['column'] = column
            sort_state['reverse'] = False
        build_rows()

    def _maybe_resort_after_change(column):
        if sort_state.get('column') == column:
            list_win.after_idle(build_rows)

    def open_ct_dialog(obj_name):
        open_cargo_teams_dialog(obj_name)
        build_rows()
        refresh_objects_list()

    def build_rows():
        nonlocal initial_layout
        for child in rows_frame.winfo_children():
            child.destroy()

        for idx, (_, _, minsize) in enumerate(overview_columns):
            rows_frame.grid_columnconfigure(idx, minsize=column_widths[overview_columns[idx][0]], weight=0)
        _sync_width(None)
        source_cb['values'] = sorted({_first_side(o) for o in sm.data.get('objects', {}).values()
                                      if str(o.get('type', '')).lower() in STATION_OR_PLATFORM_TYPES and _first_side(o)})

        active_sort = sort_state.get('column', 'name')
        sort_suffix = " v" if sort_state.get('reverse') else " ^"
        for col_idx, (key, label, _) in enumerate(overview_columns):
            header_text = f"{label}{sort_suffix if key == active_sort else ''}"
            header = tk.Frame(rows_frame, width=column_widths[key], height=30)
            header.grid(row=0, column=col_idx, sticky='ew')
            header.pack_propagate(False)
            grip = tk.Frame(header, width=7, cursor='sb_h_double_arrow', relief='raised', bd=1)
            grip.pack(side='right', fill='y')
            drag = {}
            def start_resize(event, k=key, d=drag):
                d.update(x=event.x_root, width=column_widths[k])
            def resize(event, k=key, d=drag, col=col_idx):
                column_widths[k] = max(70, d['width'] + event.x_root - d['x'])
                rows_frame.grid_columnconfigure(col, minsize=column_widths[k])
                for cell in rows_frame.grid_slaves(column=col):
                    cell.configure(width=column_widths[k])
                _sync_width(None)
            grip.bind('<ButtonPress-1>', start_resize)
            grip.bind('<B1-Motion>', resize)
            tk.Button(
                header,
                text=header_text,
                font=('Arial', 9, 'bold'),
                relief=tk.SUNKEN if key == active_sort else tk.RAISED,
                command=lambda k=key: _set_station_sort(k),
                anchor='w',
            ).pack(side='left', fill='both', expand=True)

        entries = []
        for obj_name in sm.list_objects():
            obj = sm.get_object(obj_name)
            otype = str(obj.get('type', '')).lower()
            if otype not in ('station', 'platform'):
                continue
            entries.append((obj_name, obj))
        entries = _sort_entries(entries)

        if not entries:
            tk.Label(rows_frame, text="No stations or platforms found.").grid(row=1, column=0, columnspan=len(overview_columns), sticky='w', padx=2, pady=4)
            return

        row = 1
        for obj_name, obj in entries:
            otype = str(obj.get('type', '')).lower()
            if otype not in ('station', 'platform'):
                otype = 'station'

            cells = []
            for col, (key, _, _) in enumerate(overview_columns):
                cell = tk.Frame(rows_frame, width=column_widths[key], height=32)
                cell.grid(row=row, column=col, sticky='ew')
                cell.grid_propagate(False)
                cell.grid_columnconfigure(0, weight=1)
                cells.append(cell)

            name_lbl = tk.Label(cells[0], text=obj_name, cursor='hand2')
            if not has_cargo(obj):
                name_lbl.configure(fg='red')
            name_lbl.grid(row=0, column=0, sticky='ew', padx=2, pady=2)
            name_lbl.bind("<Button-1>", lambda e, n=obj_name: open_ct_dialog(n))

            type_var = tk.StringVar(value=otype)
            type_cb = ttk.Combobox(cells[1], textvariable=type_var, values=type_values, state='readonly', width=10)
            type_cb.grid(row=0, column=0, sticky='ew', padx=2, pady=2)

            current_side = _first_side(obj)
            side_values = list(valid_sides)
            if current_side and current_side not in side_values:
                side_values = [current_side] + side_values
            side_var = tk.StringVar(value=current_side)
            side_cb = ttk.Combobox(cells[2], textvariable=side_var, values=side_values, state='readonly', width=14)
            side_cb.grid(row=0, column=0, sticky='ew', padx=2, pady=2)

            def apply_overview_side(*_, o=obj, v=side_var):
                if o.get('sides') == [v.get()]:
                    return
                push_undo()
                o['sides'] = [v.get()]
                draw_map(ctx)
                _maybe_resort_after_change('side')

            side_var.trace_add('write', apply_overview_side)

            hull_var = tk.StringVar(value=obj.get('hull', ''))
            hull_vals = platform_hulls if type_var.get() == 'platform' else valid_hulls
            hull_cb = ttk.Combobox(cells[3], textvariable=hull_var, values=hull_vals, state='readonly', width=16)
            hull_cb.grid(row=0, column=0, sticky='ew', padx=2, pady=2)

            def apply_overview_hull(*_, o=obj, v=hull_var):
                if o.get('hull') == v.get():
                    return
                push_undo()
                o['hull'] = v.get()
                draw_map(ctx)
                _maybe_resort_after_change('hull')

            hull_var.trace_add('write', apply_overview_hull)

            fac_frame = tk.Frame(cells[4])
            fac_frame.grid(row=0, column=0, sticky='ew', padx=2, pady=2)
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
                if o.get('facilities', []) == new_list:
                    return
                push_undo()
                o['facilities'] = new_list
                _maybe_resort_after_change('facilities')

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

            def on_type_change(*_, n=obj_name, tv=type_var):
                convert_station_type(n, tv.get())

            type_var.trace_add('write', on_type_change)
            set_facility_state(type_var.get() == 'station')

            cargo_frame = tk.Frame(cells[5])
            cargo_frame.grid(row=0, column=0, sticky='ew', padx=2, pady=2)
            cargo_lbl = tk.Label(cargo_frame, text=_cargo_team_summary(obj))
            if not has_cargo(obj):
                cargo_lbl.configure(fg='red')
            cargo_lbl.pack(side='left', padx=(0, 4))
            tk.Button(cargo_frame, text="Edit", command=lambda n=obj_name: open_ct_dialog(n)).pack(side='left')

            row += 1

        # Size for the actual font/DPI and contents on first open. Later
        # rebuilds retain the user's column widths, including after undo.
        rows_frame.update_idletasks()
        for col, (key, _, _) in enumerate(overview_columns):
            cells = rows_frame.grid_slaves(column=col)
            for cell in cells:
                children = cell.winfo_children()
                cell.configure(height=max([32] + [child.winfo_reqheight() + 4 for child in children]))
            if initial_layout:
                content_width = max([column_widths[key]] + [
                    child.winfo_reqwidth() + 8 for cell in cells
                    for child in cell.winfo_children()])
                column_widths[key] = min(500, content_width)
                rows_frame.grid_columnconfigure(col, minsize=column_widths[key])
                for cell in cells:
                    cell.configure(width=column_widths[key])
        if initial_layout:
            width = min(sum(column_widths.values()) + 40, list_win.winfo_screenwidth() - 80)
            list_win.geometry(f"{width}x{min(700, list_win.winfo_screenheight() - 100)}")
            initial_layout = False
        _sync_width(None)

    overview_refreshers[list_win] = build_rows
    def on_destroy(event):
        if event.widget == list_win:
            overview_refreshers.pop(list_win, None)
    list_win.bind('<Destroy>', on_destroy, add='+')
    build_rows()
