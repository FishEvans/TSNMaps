import json
import random
import sys
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from SystemEditor import (  # noqa: E402
    DEFAULT_FCS_DENSITY_PERCENTILE,
    DEFAULT_FCS_DENSITY_RADIUS,
    DEFAULT_FCS_MIN_SCORE,
    FCS_ZONE_TYPE,
    collect_fcs_blocked_centers,
    collect_nebula_points_for_fcs,
    generate_zone_name,
    get_data_path,
    percentile_value,
    select_fcs_zone_centers,
)


SKIP_FILENAMES = {"package.json", "galmapinfo.json"}
FCS_RADIUS_MIN = 5000
FCS_RADIUS_MAX = 12000
FCS_RADIUS_JITTER = 1000
FCS_RADIUS_FULL_DENSITY_PERCENTILE = 90
DEFAULT_FCS_ALL_MIN_SPACING = 60000


def show_window(window):
    window.update_idletasks()
    window.deiconify()
    window.lift()
    try:
        window.focus_force()
    except Exception:
        try:
            window.focus_set()
        except Exception:
            pass
    window.update()


def create_progress_window(root, title, total, stat_specs):
    dialog = tk.Toplevel(root)
    dialog.title(title)
    dialog.resizable(False, False)
    dialog.protocol("WM_DELETE_WINDOW", lambda: None)

    body = tk.Frame(dialog, padx=12, pady=12)
    body.pack(fill="both", expand=True)

    progress_var = tk.IntVar(value=0)
    step_var = tk.StringVar(value=f"0 / {total}")
    status_var = tk.StringVar(value="Starting...")

    tk.Label(body, textvariable=status_var, anchor="w", justify="left", wraplength=420).grid(
        row=0, column=0, columnspan=2, sticky="w", pady=(0, 8)
    )
    ttk.Progressbar(
        body,
        variable=progress_var,
        maximum=max(1, int(total)),
        length=420,
        mode="determinate",
    ).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 4))
    tk.Label(body, textvariable=step_var, anchor="w").grid(
        row=2, column=0, columnspan=2, sticky="w", pady=(0, 8)
    )

    stat_vars = {}
    row = 3
    for label_text, key in stat_specs:
        value_var = tk.StringVar(value="0")
        stat_vars[key] = value_var
        tk.Label(body, text=f"{label_text}:", anchor="w").grid(
            row=row, column=0, sticky="w", padx=(0, 12), pady=2
        )
        tk.Label(body, textvariable=value_var, anchor="w", justify="left").grid(
            row=row, column=1, sticky="w", pady=2
        )
        row += 1

    show_window(dialog)
    return {
        "window": dialog,
        "total": max(0, int(total)),
        "progress_var": progress_var,
        "step_var": step_var,
        "status_var": status_var,
        "stat_vars": stat_vars,
    }


def update_progress_window(progress, current=None, status=None, **stats):
    if not progress:
        return
    window = progress.get("window")
    if window is None or not window.winfo_exists():
        return

    total = progress.get("total", 0)
    if current is not None:
        current_value = max(0, min(int(current), max(0, total)))
        progress["progress_var"].set(current_value)
        progress["step_var"].set(f"{current_value} / {total}")
    if status is not None:
        progress["status_var"].set(str(status))

    for key, value in stats.items():
        value_var = progress["stat_vars"].get(key)
        if value_var is not None:
            value_var.set(str(value))

    window.update_idletasks()
    window.update()


def close_progress_window(progress):
    if not progress:
        return
    window = progress.get("window")
    if window is None:
        return
    try:
        if window.winfo_exists():
            window.destroy()
    except Exception:
        pass


def list_system_paths():
    data_base = Path(get_data_path())
    if not data_base.exists():
        return data_base, []
    paths = [
        path for path in data_base.iterdir()
        if path.is_file()
        and path.suffix.lower() == ".json"
        and path.name.lower() not in SKIP_FILENAMES
    ]
    return data_base, sorted(paths, key=lambda item: item.name.lower())


def load_system(path):
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("System JSON root is not an object.")
    return data


def save_system(path, data):
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=4)


def count_existing_fcs_zones(system_data):
    total = 0
    for section_name in ("objects", "terrain"):
        entries = system_data.get(section_name, {})
        if not isinstance(entries, dict):
            continue
        total += sum(
            1
            for entry in entries.values()
            if isinstance(entry, dict)
            and str(entry.get("type", "")).strip().lower() == FCS_ZONE_TYPE
        )
    return total


def stable_radius_jitter(zone, max_jitter=FCS_RADIUS_JITTER):
    max_jitter = max(0, int(max_jitter))
    if max_jitter <= 0:
        return 0

    key = "|".join(
        (
            str(zone.get("source", "")),
            f"{float(zone.get('x', 0.0) or 0.0):.3f}",
            f"{float(zone.get('z', 0.0) or 0.0):.3f}",
            f"{float(zone.get('score', 0.0) or 0.0):.3f}",
        )
    )
    return random.Random(key).randint(0, max_jitter)


def get_radius_score_bounds(score_values):
    scores = [float(score) for score in score_values if score is not None]
    if not scores:
        return 0.0, 0.0

    low_score = min(scores)
    high_score = percentile_value(scores, FCS_RADIUS_FULL_DENSITY_PERCENTILE)
    if high_score <= low_score:
        high_score = max(scores)
    return float(low_score), float(high_score)


def calculate_fcs_zone_radius(zone, low_score, high_score):
    score = float(zone.get("score", 0.0) or 0.0)
    base_max = max(FCS_RADIUS_MIN, FCS_RADIUS_MAX - FCS_RADIUS_JITTER)

    if high_score > low_score:
        density_ratio = (score - low_score) / (high_score - low_score)
    else:
        density_ratio = 0.5
    density_ratio = max(0.0, min(1.0, density_ratio))

    base_radius = FCS_RADIUS_MIN + density_ratio * (base_max - FCS_RADIUS_MIN)
    radius = int(round(base_radius + stable_radius_jitter(zone)))
    return max(FCS_RADIUS_MIN, min(FCS_RADIUS_MAX, radius))


def build_fcs_zone_description(zone, radius):
    score = float(zone.get("score", 0.0) or 0.0)
    source = str(zone.get("source", "") or "").strip()
    key = "|".join(
        (
            "fcs-description",
            source,
            f"{float(zone.get('x', 0.0) or 0.0):.3f}",
            f"{float(zone.get('z', 0.0) or 0.0):.3f}",
            f"{score:.3f}",
            str(int(radius)),
        )
    )
    rng = random.Random(key)

    trace_profiles = [
        "hydrogen-rich vapor with low metallic dust",
        "cool deuterium traces threaded through ionized gas",
        "charged nebular wisps with intermittent fuel-cell precursors",
        "thin helium wash over denser collection pockets",
        "volatile ice fines suspended in a quiet plasma band",
        "bright ion trails with usable condenser feedstock",
    ]
    stability_profiles = [
        "stable",
        "lightly turbulent",
        "uneven but workable",
        "slowly drifting",
        "patchy near the edge",
        "dense around the core",
    ]
    collector_notes = [
        "Use wide intake sweeps before narrowing to the central plume.",
        "Hold station near the inner third for the cleanest skim.",
        "Cycle filters often; particulate load may spike without warning.",
        "Best yield is expected on a slow spiral through the marked radius.",
        "Keep condenser temperature margins high during extended collection.",
        "Short passes should outperform a single static collection burn.",
    ]

    confidence = "high" if score >= 60 else "moderate" if score >= 20 else "limited"
    saturation = rng.randint(35, 94)
    source_text = f" Source field: {source}." if source else ""

    return (
        "Auto-surveyed fuel collection zone. "
        f"Estimated radius: {int(radius):,} units. "
        f"Local nebular density index: {score:.1f}.{source_text} "
        f"Survey profile: {rng.choice(trace_profiles)}; "
        f"field stability {rng.choice(stability_profiles)}; "
        f"collector saturation estimate {saturation}%. "
        f"Telemetry confidence: {confidence}. "
        f"{rng.choice(collector_notes)}"
    )


def build_selection_plan(entries, settings, progress=None):
    selections = {}
    scores = []

    for index, entry in enumerate(entries, start=1):
        system_name = entry["path"].name
        update_progress_window(
            progress,
            current=index - 1,
            status=f"Scoring nebula density for {system_name}...",
            scored=index - 1,
        )

        selected = []
        nebula_points = entry["nebula_points"]
        if nebula_points:
            blocked_centers = collect_fcs_blocked_centers(
                entry["data"],
                replace_existing=settings["replace_existing"],
            )
            selected = select_fcs_zone_centers(
                nebula_points,
                min_spacing=settings["min_spacing"],
                density_radius=settings["density_radius"],
                percentile=settings["percentile"],
                min_score=DEFAULT_FCS_MIN_SCORE,
                blocked_centers=blocked_centers,
            )
            scores.extend(float(zone.get("score", 0.0) or 0.0) for zone in selected)

        selections[entry["path"]] = selected
        update_progress_window(
            progress,
            current=index,
            status=f"Scored {system_name}",
            scored=index,
        )

    return selections, get_radius_score_bounds(scores)


def build_system_entries(root, paths):
    entries = []
    errors = []
    systems_with_nebula = 0
    nebula_points_total = 0
    existing_fcs_total = 0

    progress = create_progress_window(
        root,
        "Scanning Systems",
        len(paths),
        [
            ("Readable systems", "readable"),
            ("Systems with nebula dots", "with_nebula"),
            ("Nebula dots found", "nebula_points"),
            ("Existing FCS zones", "existing_fcs"),
            ("Errors", "errors"),
        ],
    )

    try:
        for index, path in enumerate(paths, start=1):
            update_progress_window(
                progress,
                current=index - 1,
                status=f"Scanning {path.name}...",
                readable=len(entries),
                with_nebula=systems_with_nebula,
                nebula_points=nebula_points_total,
                existing_fcs=existing_fcs_total,
                errors=len(errors),
            )
            try:
                data = load_system(path)
                nebula_points = collect_nebula_points_for_fcs(data.get("terrain", {}), cache={})
                existing_fcs_count = count_existing_fcs_zones(data)
            except Exception as exc:
                errors.append(f"{path.name}: {exc}")
                update_progress_window(
                    progress,
                    current=index,
                    status=f"Error scanning {path.name}",
                    readable=len(entries),
                    with_nebula=systems_with_nebula,
                    nebula_points=nebula_points_total,
                    existing_fcs=existing_fcs_total,
                    errors=len(errors),
                )
                continue

            if nebula_points:
                systems_with_nebula += 1
                nebula_points_total += len(nebula_points)
            existing_fcs_total += existing_fcs_count

            entries.append({
                "path": path,
                "data": data,
                "nebula_points": nebula_points,
                "existing_fcs_count": existing_fcs_count,
            })
            update_progress_window(
                progress,
                current=index,
                status=f"Scanned {path.name}",
                readable=len(entries),
                with_nebula=systems_with_nebula,
                nebula_points=nebula_points_total,
                existing_fcs=existing_fcs_total,
                errors=len(errors),
            )
    finally:
        close_progress_window(progress)

    return entries, errors


def show_settings_dialog(root, entries):
    total_systems = len(entries)
    systems_with_nebula = sum(1 for entry in entries if entry["nebula_points"])
    total_nebula_points = sum(len(entry["nebula_points"]) for entry in entries)
    total_existing_fcs = sum(entry["existing_fcs_count"] for entry in entries)

    dialog = tk.Toplevel(root)
    dialog.title("Generate Fuel Collection Zones")
    dialog.resizable(False, False)
    try:
        if root is not None and root.winfo_viewable():
            dialog.transient(root)
    except Exception:
        pass
    dialog.grab_set()

    body = tk.Frame(dialog, padx=10, pady=10)
    body.pack(fill="both", expand=True)

    spacing_var = tk.IntVar(value=DEFAULT_FCS_ALL_MIN_SPACING)
    density_radius_var = tk.IntVar(value=DEFAULT_FCS_DENSITY_RADIUS)
    percentile_var = tk.IntVar(value=DEFAULT_FCS_DENSITY_PERCENTILE)
    replace_var = tk.BooleanVar(value=bool(total_existing_fcs))

    tk.Label(body, text=f"Systems available: {total_systems}").grid(
        row=0, column=0, columnspan=2, padx=6, pady=(2, 2), sticky="w"
    )
    tk.Label(body, text=f"Systems with nebula dots: {systems_with_nebula}").grid(
        row=1, column=0, columnspan=2, padx=6, pady=(0, 2), sticky="w"
    )
    tk.Label(body, text=f"Nebula dots available: {total_nebula_points}").grid(
        row=2, column=0, columnspan=2, padx=6, pady=(0, 2), sticky="w"
    )
    tk.Label(body, text=f"Existing FCS zones: {total_existing_fcs}").grid(
        row=3, column=0, columnspan=2, padx=6, pady=(0, 6), sticky="w"
    )

    def _labeled_spinbox(row, label_text, variable, frm, to):
        tk.Label(body, text=label_text).grid(row=row, column=0, padx=6, pady=2, sticky="w")
        tk.Spinbox(body, from_=frm, to=to, width=10, textvariable=variable).grid(
            row=row, column=1, padx=6, pady=2, sticky="w"
        )

    tk.Label(
        body,
        text=f"Zone radius: {FCS_RADIUS_MIN}-{FCS_RADIUS_MAX} by nebula density.",
    ).grid(row=4, column=0, columnspan=2, padx=6, pady=(0, 2), sticky="w")
    tk.Label(
        body,
        text=f"Radius jitter: 0-{FCS_RADIUS_JITTER} added per zone.",
    ).grid(row=5, column=0, columnspan=2, padx=6, pady=(0, 6), sticky="w")

    _labeled_spinbox(6, "Min Spacing:", spacing_var, 1000, 1000000)
    _labeled_spinbox(7, "Density Radius:", density_radius_var, 1000, 1000000)
    _labeled_spinbox(8, "Density Percentile:", percentile_var, 0, 100)

    tk.Checkbutton(
        body,
        text="Replace existing FCS zones",
        variable=replace_var,
    ).grid(row=9, column=0, columnspan=2, padx=6, pady=(2, 4), sticky="w")

    tk.Label(
        body,
        text="Higher percentile favors tighter nebula clusters.",
        fg="#3a86ff",
    ).grid(row=10, column=0, columnspan=2, padx=6, pady=(0, 6), sticky="w")

    footer = tk.Frame(dialog, padx=10)
    footer.pack(fill="x", pady=(0, 10))
    result = {}

    def _generate():
        try:
            result["min_spacing"] = max(1, int(spacing_var.get() or DEFAULT_FCS_ALL_MIN_SPACING))
            result["density_radius"] = max(1, int(density_radius_var.get() or DEFAULT_FCS_DENSITY_RADIUS))
            result["percentile"] = max(
                0,
                min(100, int(percentile_var.get() or DEFAULT_FCS_DENSITY_PERCENTILE)),
            )
            result["replace_existing"] = bool(replace_var.get())
        except Exception:
            messagebox.showerror("Generate FCS Zones", "Invalid FCS zone settings.", parent=dialog)
            return
        dialog.destroy()

    def _cancel():
        dialog.destroy()

    tk.Button(footer, text="Generate", width=12, command=_generate).pack(side="left", padx=4)
    tk.Button(footer, text="Cancel", width=12, command=_cancel).pack(side="left", padx=4)

    dialog.protocol("WM_DELETE_WINDOW", _cancel)
    show_window(dialog)
    dialog.wait_window()
    return result or None


def apply_batch(root, entries, settings):
    summary = {
        "processed_systems": 0,
        "systems_with_nebula": 0,
        "systems_changed": 0,
        "systems_without_nebula": 0,
        "systems_without_selection": 0,
        "created_total": 0,
        "removed_total": 0,
    }
    errors = []
    total_steps = len(entries) * 2
    progress = create_progress_window(
        root,
        "Generating FCS Zones",
        total_steps,
        [
            ("Systems scored", "scored"),
            ("Processed systems", "processed"),
            ("Systems changed", "changed"),
            ("FCS zones created", "created"),
            ("FCS zones removed", "removed"),
            ("Systems without nebula", "without_nebula"),
            ("No valid placement", "without_selection"),
            ("Errors", "errors"),
        ],
    )

    try:
        selection_plan, (low_score, high_score) = build_selection_plan(
            entries,
            settings,
            progress=progress,
        )

        for index, entry in enumerate(entries, start=1):
            system_name = entry["path"].name
            update_progress_window(
                progress,
                current=len(entries) + index - 1,
                status=f"Generating zones for {system_name}...",
                processed=summary["processed_systems"],
                changed=summary["systems_changed"],
                created=summary["created_total"],
                removed=summary["removed_total"],
                without_nebula=summary["systems_without_nebula"],
                without_selection=summary["systems_without_selection"],
                errors=len(errors),
            )

            summary["processed_systems"] += 1
            nebula_points = entry["nebula_points"]
            if not nebula_points:
                summary["systems_without_nebula"] += 1
                update_progress_window(
                    progress,
                    current=len(entries) + index,
                    status=f"Skipped {system_name}: no nebula dots",
                    processed=summary["processed_systems"],
                    changed=summary["systems_changed"],
                    created=summary["created_total"],
                    removed=summary["removed_total"],
                    without_nebula=summary["systems_without_nebula"],
                    without_selection=summary["systems_without_selection"],
                    errors=len(errors),
                )
                continue

            summary["systems_with_nebula"] += 1
            data = entry["data"]
            selected = selection_plan.get(entry["path"], [])

            if not selected:
                summary["systems_without_selection"] += 1
                update_progress_window(
                    progress,
                    current=len(entries) + index,
                    status=f"Skipped {system_name}: no valid placement",
                    processed=summary["processed_systems"],
                    changed=summary["systems_changed"],
                    created=summary["created_total"],
                    removed=summary["removed_total"],
                    without_nebula=summary["systems_without_nebula"],
                    without_selection=summary["systems_without_selection"],
                    errors=len(errors),
                )
                continue

            objects = data.get("objects", {})
            if objects is None:
                objects = {}
            if not isinstance(objects, dict):
                errors.append(f"{system_name}: objects is not a JSON object.")
                update_progress_window(
                    progress,
                    current=len(entries) + index,
                    status=f"Error updating {system_name}",
                    processed=summary["processed_systems"],
                    changed=summary["systems_changed"],
                    created=summary["created_total"],
                    removed=summary["removed_total"],
                    without_nebula=summary["systems_without_nebula"],
                    without_selection=summary["systems_without_selection"],
                    errors=len(errors),
                )
                continue

            terrain = data.setdefault("terrain", {})
            if not isinstance(terrain, dict):
                errors.append(f"{system_name}: terrain is not a JSON object.")
                update_progress_window(
                    progress,
                    current=len(entries) + index,
                    status=f"Error updating {system_name}",
                    processed=summary["processed_systems"],
                    changed=summary["systems_changed"],
                    created=summary["created_total"],
                    removed=summary["removed_total"],
                    without_nebula=summary["systems_without_nebula"],
                    without_selection=summary["systems_without_selection"],
                    errors=len(errors),
                )
                continue

            removed = 0
            if settings["replace_existing"]:
                for name in list(objects.keys()):
                    obj = objects.get(name)
                    if not isinstance(obj, dict):
                        continue
                    if str(obj.get("type", "")).strip().lower() != FCS_ZONE_TYPE:
                        continue
                    del objects[name]
                    removed += 1
                for name in list(terrain.keys()):
                    feat = terrain.get(name)
                    if not isinstance(feat, dict):
                        continue
                    if str(feat.get("type", "")).strip().lower() != FCS_ZONE_TYPE:
                        continue
                    del terrain[name]
                    removed += 1

            created = 0
            used_names = set(objects.keys()) | set(terrain.keys())
            for zone in selected:
                name = generate_zone_name(used_names, FCS_ZONE_TYPE)
                radius = calculate_fcs_zone_radius(zone, low_score, high_score)
                terrain[name] = {
                    "type": FCS_ZONE_TYPE,
                    "coordinate": [zone["x"], 0, zone["z"]],
                    "radius": radius,
                    "description": build_fcs_zone_description(zone, radius),
                    "hideonmap": bool(zone.get("hideonmap", False)),
                }
                used_names.add(name)
                created += 1

            try:
                save_system(entry["path"], data)
            except Exception as exc:
                errors.append(f"{system_name}: {exc}")
                update_progress_window(
                    progress,
                    current=len(entries) + index,
                    status=f"Error saving {system_name}",
                    processed=summary["processed_systems"],
                    changed=summary["systems_changed"],
                    created=summary["created_total"],
                    removed=summary["removed_total"],
                    without_nebula=summary["systems_without_nebula"],
                    without_selection=summary["systems_without_selection"],
                    errors=len(errors),
                )
                continue

            summary["systems_changed"] += 1
            summary["created_total"] += created
            summary["removed_total"] += removed
            update_progress_window(
                progress,
                current=len(entries) + index,
                status=f"Saved {system_name}: +{created} zone(s)",
                processed=summary["processed_systems"],
                changed=summary["systems_changed"],
                created=summary["created_total"],
                removed=summary["removed_total"],
                without_nebula=summary["systems_without_nebula"],
                without_selection=summary["systems_without_selection"],
                errors=len(errors),
            )
    finally:
        close_progress_window(progress)

    return summary, errors


def show_summary(root, summary, load_errors, apply_errors):
    lines = [
        f"Processed systems: {summary['processed_systems']}",
        f"Systems with nebula dots: {summary['systems_with_nebula']}",
        f"Systems changed: {summary['systems_changed']}",
        f"FCS zones created: {summary['created_total']}",
        f"FCS zones removed: {summary['removed_total']}",
        f"Systems without nebula dots: {summary['systems_without_nebula']}",
        f"Systems with no valid zone placement: {summary['systems_without_selection']}",
    ]

    all_errors = list(load_errors) + list(apply_errors)
    if all_errors:
        lines.append("")
        lines.append(f"Errors: {len(all_errors)}")
        lines.extend(all_errors[:8])
        if len(all_errors) > 8:
            lines.append("...")
        messagebox.showwarning("Generate FCS Zones", "\n".join(lines))
        return

    messagebox.showinfo("Generate FCS Zones", "\n".join(lines))


def main():
    root = tk.Tk()
    root.withdraw()

    data_base, paths = list_system_paths()
    if not paths:
        messagebox.showerror(
            "Generate FCS Zones",
            "No system JSON files were found in:\n" + str(data_base),
        )
        root.destroy()
        return

    entries, load_errors = build_system_entries(root, paths)
    if not entries:
        messagebox.showerror(
            "Generate FCS Zones",
            "No readable system JSON files were found.",
        )
        root.destroy()
        return

    if not any(entry["nebula_points"] for entry in entries):
        messagebox.showinfo(
            "Generate FCS Zones",
            "No nebula dots were found in the available systems.",
        )
        root.destroy()
        return

    settings = show_settings_dialog(root, entries)
    if not settings:
        root.destroy()
        return

    summary, apply_errors = apply_batch(root, entries, settings)
    show_summary(root, summary, load_errors, apply_errors)
    root.destroy()


if __name__ == "__main__":
    main()
