import argparse
import datetime as _dt
import json
import os
import sys
from typing import Any, Dict, Iterable, List, Tuple


EXCLUDE_FILES = {"package.json", "galmapinfo.json"}


def _normalize_author_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raw = [v.strip() for v in value.split(",")]
    elif isinstance(value, list):
        raw = [str(v).strip() for v in value]
    else:
        return []
    cleaned: List[str] = []
    seen = set()
    for item in raw:
        if not item:
            continue
        key = item.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(item)
    return cleaned


def _coerce_revision_date(value: str) -> str:
    if not value:
        return ""
    lowered = value.strip().lower()
    if lowered in ("today", "now"):
        return _dt.date.today().isoformat()
    return value.strip()


def _list_systems(folder: str) -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    for name in os.listdir(folder):
        if not name.lower().endswith(".json"):
            continue
        if name.lower() in EXCLUDE_FILES:
            continue
        path = os.path.join(folder, name)
        if not os.path.isfile(path):
            continue
        sys_name = os.path.splitext(name)[0]
        items.append({"name": sys_name, "filename": name, "path": path})
    items.sort(key=lambda d: d["name"].casefold())
    return items


def _write_json_output(data: Any, output: str) -> None:
    text = json.dumps(data, indent=4)
    if output == "-":
        print(text)
        return
    with open(output, "w", encoding="utf-8") as f:
        f.write(text)


def _iter_system_paths(data: Any, folder: str | None) -> Iterable[str]:
    if isinstance(data, list):
        for item in data:
            path = _resolve_item_to_path(item, folder)
            if path:
                yield path
        return
    raise ValueError("Input JSON must be a list of systems.")


def _resolve_item_to_path(item: Any, folder: str | None) -> str | None:
    if folder:
        if isinstance(item, dict):
            if item.get("filename"):
                return os.path.join(folder, str(item["filename"]))
            if item.get("name"):
                return os.path.join(folder, f"{item['name']}.json")
            if item.get("path"):
                return os.path.join(folder, os.path.basename(str(item["path"])))
            return None
        if isinstance(item, str):
            text = item.strip()
            if not text:
                return None
            if text.lower().endswith(".json") or os.path.sep in text:
                return os.path.join(folder, os.path.basename(text))
            return os.path.join(folder, f"{text}.json")
        return None

    if isinstance(item, dict):
        if item.get("path"):
            return str(item["path"])
        if item.get("filename"):
            if not folder:
                raise ValueError("Folder is required when using 'filename' entries.")
            return os.path.join(folder, str(item["filename"]))
        if item.get("name"):
            if not folder:
                raise ValueError("Folder is required when using 'name' entries.")
            return os.path.join(folder, f"{item['name']}.json")
        return None
    if isinstance(item, str):
        text = item.strip()
        if not text:
            return None
        # treat as path if it looks like one or endswith .json
        if os.path.sep in text or text.lower().endswith(".json"):
            if folder and not os.path.isabs(text):
                return os.path.join(folder, text)
            return text
        if not folder:
            raise ValueError("Folder is required when using bare system names.")
        return os.path.join(folder, f"{text}.json")
    return None


def _update_file(
    path: str,
    original_author: str | None,
    revision_author: str | None,
    revision_date: str | None,
    revision_number: int | None,
) -> Tuple[bool, Dict[str, Tuple[Any, Any]]]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    md = data.setdefault("metadata", {})
    before: Dict[str, Any] = {
        "original_author": md.get("original_author"),
        "last_revision_author": md.get("last_revision_author"),
        "revision_date": md.get("revision_date"),
        "revision_number": md.get("revision_number"),
        "all_authors": md.get("all_authors"),
    }

    if original_author is not None:
        md["original_author"] = original_author
    if revision_author is not None:
        md["last_revision_author"] = revision_author
    if revision_date is not None:
        md["revision_date"] = revision_date
    if revision_number is not None:
        md["revision_number"] = revision_number

    authors = _normalize_author_list(md.get("all_authors"))
    for candidate in (original_author, revision_author):
        if candidate:
            if not any(a.casefold() == candidate.casefold() for a in authors):
                authors.append(candidate)
    if authors:
        md["all_authors"] = authors

    after: Dict[str, Any] = {
        "original_author": md.get("original_author"),
        "last_revision_author": md.get("last_revision_author"),
        "revision_date": md.get("revision_date"),
        "revision_number": md.get("revision_number"),
        "all_authors": md.get("all_authors"),
    }

    changes: Dict[str, Tuple[Any, Any]] = {}
    for key in before.keys():
        if before.get(key) != after.get(key):
            changes[key] = (before.get(key), after.get(key))

    if changes:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        return True, changes
    return False, changes


def main() -> int:
    if len(sys.argv) == 1:
        return run_gui()

    parser = argparse.ArgumentParser(
        description="List system JSON files or bulk update author metadata."
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="List systems in a folder as JSON.")
    p_list.add_argument("--folder", required=True, help="Folder containing system JSON files.")
    p_list.add_argument(
        "--output",
        required=True,
        help="Output JSON file path, or '-' for stdout.",
    )

    p_up = sub.add_parser("update", help="Bulk update author metadata.")
    p_up.add_argument("--input", required=True, help="Input JSON list from 'list' command.")
    p_up.add_argument("--folder", help="Folder for resolving names/filenames.")
    p_up.add_argument("--original-author", help="Value to set for original_author.")
    p_up.add_argument("--revision-author", help="Value to set for last_revision_author.")
    p_up.add_argument(
        "--revision-date",
        help="Value to set for revision_date (use 'today' for current date).",
    )
    p_up.add_argument(
        "--revision-number",
        type=int,
        help="Value to set for revision_number.",
    )

    args = parser.parse_args()

    if args.cmd == "list":
        folder = args.folder
        if not os.path.isdir(folder):
            raise SystemExit(f"Folder not found: {folder}")
        items = _list_systems(folder)
        _write_json_output(items, args.output)
        return 0

    if args.cmd == "update":
        with open(args.input, "r", encoding="utf-8") as f:
            data = json.load(f)

        revision_date = None
        if args.revision_date is not None:
            revision_date = _coerce_revision_date(args.revision_date)

        total = 0
        updated = 0
        for path in _iter_system_paths(data, args.folder):
            total += 1
            if not os.path.isfile(path):
                print(f"[WARN] Missing file: {path}")
                continue
            changed, changes = _update_file(
                path=path,
                original_author=args.original_author,
                revision_author=args.revision_author,
                revision_date=revision_date,
                revision_number=args.revision_number,
            )
            if changed:
                updated += 1
                print(f"[UPDATED] {path}")
                for key, (before, after) in changes.items():
                    print(f"  - {key}: {before!r} -> {after!r}")
        print(f"Done. Updated {updated}/{total} file(s).")
        return 0

    return 1


def run_gui() -> int:
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox
    except Exception as exc:
        print(f"Failed to start GUI: {exc}")
        return 1

    root = tk.Tk()
    root.title("Author Bulk Update")
    root.geometry("720x520")

    def log(msg: str) -> None:
        log_box.config(state="normal")
        log_box.insert(tk.END, msg + "\n")
        log_box.see(tk.END)
        log_box.config(state="disabled")

    # --- List section ---
    list_frame = tk.LabelFrame(root, text="Generate List")
    list_frame.pack(fill="x", padx=10, pady=8)

    list_folder_var = tk.StringVar()
    list_output_var = tk.StringVar()

    tk.Label(list_frame, text="Folder:").grid(row=0, column=0, sticky="w", padx=5, pady=4)
    tk.Entry(list_frame, textvariable=list_folder_var, width=60).grid(row=0, column=1, padx=5, pady=4)
    tk.Button(
        list_frame,
        text="Browse...",
        command=lambda: list_folder_var.set(
            filedialog.askdirectory(title="Select System Folder") or list_folder_var.get()
        ),
    ).grid(row=0, column=2, padx=5, pady=4)

    tk.Label(list_frame, text="Output JSON:").grid(row=1, column=0, sticky="w", padx=5, pady=4)
    tk.Entry(list_frame, textvariable=list_output_var, width=60).grid(row=1, column=1, padx=5, pady=4)
    tk.Button(
        list_frame,
        text="Browse...",
        command=lambda: list_output_var.set(
            filedialog.asksaveasfilename(
                title="Save List As",
                defaultextension=".json",
                filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")],
            ) or list_output_var.get()
        ),
    ).grid(row=1, column=2, padx=5, pady=4)

    def do_generate_list():
        folder = list_folder_var.get().strip()
        output = list_output_var.get().strip()
        if not folder or not os.path.isdir(folder):
            messagebox.showerror("Error", "Please select a valid folder.")
            return
        if not output:
            messagebox.showerror("Error", "Please select an output file.")
            return
        items = _list_systems(folder)
        _write_json_output(items, output)
        log(f"[LIST] Wrote {len(items)} systems to {output}")
        messagebox.showinfo("Done", f"Wrote {len(items)} systems.")

    tk.Button(list_frame, text="Generate List", command=do_generate_list).grid(
        row=2, column=1, sticky="w", padx=5, pady=6
    )

    # --- Update section ---
    update_frame = tk.LabelFrame(root, text="Bulk Update Authors")
    update_frame.pack(fill="x", padx=10, pady=8)

    input_list_var = tk.StringVar()
    update_folder_var = tk.StringVar()
    orig_author_var = tk.StringVar()
    rev_author_var = tk.StringVar()
    rev_date_var = tk.StringVar(value="today")
    rev_num_var = tk.StringVar()

    tk.Label(update_frame, text="Input List JSON:").grid(row=0, column=0, sticky="w", padx=5, pady=4)
    tk.Entry(update_frame, textvariable=input_list_var, width=60).grid(row=0, column=1, padx=5, pady=4)
    tk.Button(
        update_frame,
        text="Browse...",
        command=lambda: input_list_var.set(
            filedialog.askopenfilename(
                title="Select List JSON",
                filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")],
            ) or input_list_var.get()
        ),
    ).grid(row=0, column=2, padx=5, pady=4)

    tk.Label(update_frame, text="Folder (optional, overrides list paths):").grid(row=1, column=0, sticky="w", padx=5, pady=4)
    tk.Entry(update_frame, textvariable=update_folder_var, width=60).grid(row=1, column=1, padx=5, pady=4)
    tk.Button(
        update_frame,
        text="Browse...",
        command=lambda: update_folder_var.set(
            filedialog.askdirectory(title="Select Folder (Optional)") or update_folder_var.get()
        ),
    ).grid(row=1, column=2, padx=5, pady=4)

    tk.Label(update_frame, text="Original Author:").grid(row=2, column=0, sticky="w", padx=5, pady=4)
    tk.Entry(update_frame, textvariable=orig_author_var, width=30).grid(row=2, column=1, sticky="w", padx=5, pady=4)
    tk.Label(update_frame, text="Revision Author:").grid(row=2, column=1, sticky="e", padx=5, pady=4)
    tk.Entry(update_frame, textvariable=rev_author_var, width=30).grid(row=2, column=2, sticky="w", padx=5, pady=4)

    tk.Label(update_frame, text="Revision Date:").grid(row=3, column=0, sticky="w", padx=5, pady=4)
    tk.Entry(update_frame, textvariable=rev_date_var, width=20).grid(row=3, column=1, sticky="w", padx=5, pady=4)
    tk.Label(update_frame, text="Revision Number:").grid(row=3, column=1, sticky="e", padx=5, pady=4)
    tk.Entry(update_frame, textvariable=rev_num_var, width=10).grid(row=3, column=2, sticky="w", padx=5, pady=4)

    def do_bulk_update():
        input_path = input_list_var.get().strip()
        folder = update_folder_var.get().strip() or None
        if not input_path or not os.path.isfile(input_path):
            messagebox.showerror("Error", "Please select a valid input list JSON.")
            return
        with open(input_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        revision_date = None
        if rev_date_var.get().strip():
            revision_date = _coerce_revision_date(rev_date_var.get().strip())

        rev_number = None
        if rev_num_var.get().strip():
            try:
                rev_number = int(rev_num_var.get().strip())
            except ValueError:
                messagebox.showerror("Error", "Revision Number must be an integer.")
                return

        total = 0
        updated = 0
        for path in _iter_system_paths(data, folder):
            total += 1
            if not os.path.isfile(path):
                log(f"[WARN] Missing file: {path}")
                continue
            changed, changes = _update_file(
                path=path,
                original_author=orig_author_var.get().strip() or None,
                revision_author=rev_author_var.get().strip() or None,
                revision_date=revision_date,
                revision_number=rev_number,
            )
            if changed:
                updated += 1
                log(f"[UPDATED] {path}")
                for key, (before, after) in changes.items():
                    log(f"  - {key}: {before!r} -> {after!r}")
        log(f"Done. Updated {updated}/{total} file(s).")
        messagebox.showinfo("Done", f"Updated {updated}/{total} file(s).")

    tk.Button(update_frame, text="Bulk Update", command=do_bulk_update).grid(
        row=4, column=1, sticky="w", padx=5, pady=6
    )

    # --- Log output ---
    log_frame = tk.LabelFrame(root, text="Log")
    log_frame.pack(fill="both", expand=True, padx=10, pady=8)
    log_box = tk.Text(log_frame, height=12, state="disabled")
    log_box.pack(fill="both", expand=True, padx=5, pady=5)

    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
