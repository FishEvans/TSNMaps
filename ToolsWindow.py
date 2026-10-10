"""Desktop entry points for bundled generation and export utilities."""
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import EditorSettings
from AppPaths import get_base_path
from scripts.export_jump_table import export_jump_table
from scripts.export_systems_csv import export_system_info
from scripts.generate_test_system import generate_test_system
from scripts import generate_fcs_zones_all


def open_tools(editor):
    existing = getattr(editor, "tools_window", None)
    if existing is not None and existing.winfo_exists():
        existing.lift()
        return
    window = tk.Toplevel(editor.root)
    editor.tools_window = window
    window.title("Tools")
    window.transient(editor.root)
    body = ttk.Frame(window, padding=16)
    body.pack(fill="both", expand=True)
    ttk.Label(body, text="Exports use saved system files from your configured folder.\n"
                        "Save changes in open editors before exporting.").pack(anchor="w", pady=(0, 12))

    include_hidden = tk.BooleanVar(window, value=True)
    spacing = tk.StringVar(window, value="1000")
    per_row = tk.StringVar(window, value="10")

    def choose_output(filename):
        return filedialog.asksaveasfilename(
            parent=window, title="Save output", initialfile=filename,
            initialdir=str(Path(get_base_path()) / "data" / "exports"),
            defaultextension=".json", filetypes=[("JSON files", "*.json")])

    def run(title, operation):
        window.configure(cursor="watch")
        window.update_idletasks()
        try:
            result = operation()
        except Exception as exc:
            messagebox.showerror(title, str(exc), parent=window)
            return
        finally:
            window.configure(cursor="")
        if result:
            messagebox.showinfo(title, f"Saved to:\n{result}", parent=window)

    def export(title, filename, operation):
        output = choose_output(filename)
        if output:
            # Reports are not systems: never replace a live system with a report.
            if Path(output).resolve().parent == Path(EditorSettings.get_data_path()).resolve():
                messagebox.showerror(title, "Choose an export folder outside the systems folder.", parent=window)
                return
            run(title, lambda: operation(EditorSettings.get_data_path(), output))

    def can_update_systems():
        # A separate process is protected by external-change detection on save.
        # In this application, close editors before modifying their files in bulk.
        if any(callable(getattr(child, "confirm_pending_changes", None))
               for child in editor.root.winfo_children()):
            messagebox.showinfo("Tools", "Close the open system editors before updating system files.", parent=window)
            return False
        return editor._confirm_pending_map_changes("updating system files")

    def create_test_system():
        try:
            distance, columns = float(spacing.get()), int(per_row.get())
        except ValueError:
            messagebox.showerror("Generate Test System", "Enter a numeric spacing and a whole number of objects per row.", parent=window)
            return
        shipmap = Path(EditorSettings.get_html_output_path()) / "Images" / "Ships" / "ShipMap.json"
        if not shipmap.is_file():
            selected = filedialog.askopenfilename(parent=window, title="Select ShipMap.json",
                                                  filetypes=[("JSON files", "*.json")])
            if not selected:
                return
            shipmap = Path(selected)
        output = choose_output("AAATestSystem.json")
        if not output:
            return
        live_system = Path(output).resolve().parent == Path(EditorSettings.get_data_path()).resolve()
        if live_system and not can_update_systems():
            return
        def generate():
            result = generate_test_system(shipmap, output, spacing=distance, per_row=columns)
            if live_system:
                editor.reload_systems_data()
            return result
        run("Generate Test System", generate)

    def generate_fcs():
        if not can_update_systems():
            return
        def generate():
            generate_fcs_zones_all.run_tool(window)
            editor.reload_systems_data()
        run("Generate FCS Zones", generate)

    ttk.Button(body, text="Save and Generate HTML", command=editor.save_changes).pack(fill="x", pady=3)
    ttk.Button(body, text="Export Jump Table…", command=lambda: export(
        "Export Jump Table", "jump_table.json", lambda folder, output:
        export_jump_table(folder, output, include_hidden=include_hidden.get()))).pack(fill="x", pady=3)
    ttk.Checkbutton(body, text="Include hidden jumps", variable=include_hidden).pack(anchor="w")
    ttk.Button(body, text="Export System Info…", command=lambda: export(
        "Export System Info", "systems_overview.json", export_system_info)).pack(fill="x", pady=3)
    ttk.Separator(body).pack(fill="x", pady=10)
    options = ttk.Frame(body)
    options.pack(fill="x")
    ttk.Label(options, text="Spacing:").pack(side="left")
    ttk.Entry(options, textvariable=spacing, width=9).pack(side="left", padx=(4, 12))
    ttk.Label(options, text="Objects per row:").pack(side="left")
    ttk.Entry(options, textvariable=per_row, width=5).pack(side="left", padx=4)
    ttk.Button(body, text="Generate Test System…", command=create_test_system).pack(fill="x", pady=3)
    ttk.Button(body, text="Generate FCS Zones…", command=generate_fcs).pack(fill="x", pady=3)
    ttk.Button(body, text="Re-generate Ship Data…", command=editor.regenerate_ship_data).pack(fill="x", pady=3)
    ttk.Button(body, text="Close", command=window.destroy).pack(anchor="e", pady=(12, 0))
