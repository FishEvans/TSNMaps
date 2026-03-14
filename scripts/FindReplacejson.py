#!/usr/bin/env python3
"""
bulk_json_find_replace_gui.py

GUI tool to recursively find/replace text in .json files under a selected folder.
- Text-based replacement (does not parse JSON).
- Supports dry-run, backups, include patterns, exclude dirs, cancel, and logging.
"""

from __future__ import annotations

import fnmatch
import os
import queue
import threading
from dataclasses import dataclass
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext


@dataclass
class RunConfig:
    root: Path
    find_text: str
    replace_text: str
    dry_run: bool
    backup: bool
    include_patterns: list[str]
    exclude_dir_names: set[str]


@dataclass
class RunResult:
    files_scanned: int = 0
    files_changed: int = 0
    replacements: int = 0
    mode: str = "DRY RUN"
    backups: str = "OFF"


def iter_json_files(root: Path, include_patterns: list[str], exclude_dir_names: set[str]) -> list[Path]:
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in exclude_dir_names]

        for name in filenames:
            if not name.lower().endswith(".json"):
                continue

            full_path = Path(dirpath) / name

            if include_patterns:
                matched = any(
                    fnmatch.fnmatch(full_path.name, pat) or fnmatch.fnmatch(str(full_path), pat)
                    for pat in include_patterns
                )
                if not matched:
                    continue

            files.append(full_path)

    return sorted(files)


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")


def write_text_atomic(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Bulk JSON Find/Replace (GUI)")
        self.geometry("980x720")
        self.minsize(880, 640)

        self._worker_thread: threading.Thread | None = None
        self._cancel_event = threading.Event()
        self._log_queue: "queue.Queue[str]" = queue.Queue()
        self._result_queue: "queue.Queue[RunResult]" = queue.Queue()

        self._build_ui()
        self.after(100, self._drain_queues)

    def _build_ui(self) -> None:
        pad = {"padx": 10, "pady": 6}

        # Root folder row
        root_frame = tk.Frame(self)
        root_frame.pack(fill="x", **pad)

        tk.Label(root_frame, text="Root folder:").pack(side="left")
        self.root_var = tk.StringVar()
        self.root_entry = tk.Entry(root_frame, textvariable=self.root_var)
        self.root_entry.pack(side="left", fill="x", expand=True, padx=(8, 8))

        tk.Button(root_frame, text="Browse…", command=self._browse_root).pack(side="left")

        # Find/Replace row
        fr_frame = tk.Frame(self)
        fr_frame.pack(fill="x", **pad)

        tk.Label(fr_frame, text="Find:").grid(row=0, column=0, sticky="w")
        self.find_var = tk.StringVar()
        tk.Entry(fr_frame, textvariable=self.find_var).grid(row=0, column=1, sticky="ew", padx=(8, 16))

        tk.Label(fr_frame, text="Replace:").grid(row=0, column=2, sticky="w")
        self.replace_var = tk.StringVar()
        tk.Entry(fr_frame, textvariable=self.replace_var).grid(row=0, column=3, sticky="ew", padx=(8, 0))

        fr_frame.grid_columnconfigure(1, weight=1)
        fr_frame.grid_columnconfigure(3, weight=1)

        # Options row
        opt_frame = tk.Frame(self)
        opt_frame.pack(fill="x", **pad)

        self.dry_run_var = tk.BooleanVar(value=True)
        self.backup_var = tk.BooleanVar(value=False)

        tk.Checkbutton(opt_frame, text="Dry run (no writes)", variable=self.dry_run_var).pack(side="left")
        tk.Checkbutton(opt_frame, text="Backup (.bak)", variable=self.backup_var).pack(side="left", padx=(12, 0))

        # Include/exclude panes
        ie_frame = tk.Frame(self)
        ie_frame.pack(fill="both", expand=False, **pad)

        left = tk.Frame(ie_frame)
        left.pack(side="left", fill="both", expand=True, padx=(0, 10))
        right = tk.Frame(ie_frame)
        right.pack(side="left", fill="both", expand=True)

        tk.Label(left, text="Include patterns (optional, one per line):").pack(anchor="w")
        self.include_text = scrolledtext.ScrolledText(left, height=6)
        self.include_text.pack(fill="both", expand=True)

        tk.Label(right, text="Exclude directory names (optional, one per line):").pack(anchor="w")
        self.exclude_text = scrolledtext.ScrolledText(right, height=6)
        self.exclude_text.pack(fill="both", expand=True)

        # Action buttons + progress
        action_frame = tk.Frame(self)
        action_frame.pack(fill="x", **pad)

        self.run_btn = tk.Button(action_frame, text="Run", command=self._on_run)
        self.run_btn.pack(side="left")

        self.cancel_btn = tk.Button(action_frame, text="Cancel", command=self._on_cancel, state="disabled")
        self.cancel_btn.pack(side="left", padx=(8, 0))

        self.status_var = tk.StringVar(value="Ready.")
        tk.Label(action_frame, textvariable=self.status_var).pack(side="left", padx=(16, 0))

        # Log
        log_frame = tk.Frame(self)
        log_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        tk.Label(log_frame, text="Log:").pack(anchor="w")
        self.log = scrolledtext.ScrolledText(log_frame, state="disabled")
        self.log.pack(fill="both", expand=True)

    def _browse_root(self) -> None:
        folder = filedialog.askdirectory(title="Select root folder")
        if folder:
            self.root_var.set(folder)

    def _append_log(self, line: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", line + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _drain_queues(self) -> None:
        # Drain log messages
        try:
            while True:
                msg = self._log_queue.get_nowait()
                self._append_log(msg)
        except queue.Empty:
            pass

        # Drain result messages (completion)
        try:
            while True:
                res = self._result_queue.get_nowait()
                self._on_worker_done(res)
        except queue.Empty:
            pass

        self.after(100, self._drain_queues)

    def _set_running(self, running: bool) -> None:
        self.run_btn.configure(state="disabled" if running else "normal")
        self.cancel_btn.configure(state="normal" if running else "disabled")
        if running:
            self.status_var.set("Running…")
        else:
            self.status_var.set("Ready.")

    def _parse_multiline(self, widget: scrolledtext.ScrolledText) -> list[str]:
        raw = widget.get("1.0", "end").strip()
        if not raw:
            return []
        lines = []
        for line in raw.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            lines.append(line)
        return lines

    def _validate_config(self) -> RunConfig | None:
        root_str = self.root_var.get().strip()
        if not root_str:
            messagebox.showerror("Missing root folder", "Please choose a root folder.")
            return None

        root = Path(root_str).expanduser().resolve()
        if not root.exists() or not root.is_dir():
            messagebox.showerror("Invalid folder", f"Root path does not exist or is not a folder:\n{root}")
            return None

        find_text = self.find_var.get()
        replace_text = self.replace_var.get()

        if find_text == "":
            messagebox.showerror("Missing find text", "Find text cannot be empty.")
            return None

        include_patterns = self._parse_multiline(self.include_text)
        exclude_dirs = set(self._parse_multiline(self.exclude_text))

        cfg = RunConfig(
            root=root,
            find_text=find_text,
            replace_text=replace_text,
            dry_run=bool(self.dry_run_var.get()),
            backup=bool(self.backup_var.get()),
            include_patterns=include_patterns,
            exclude_dir_names=exclude_dirs,
        )
        return cfg

    def _on_run(self) -> None:
        if self._worker_thread and self._worker_thread.is_alive():
            return

        cfg = self._validate_config()
        if cfg is None:
            return

        # Warn if backups enabled but dry-run also enabled (not wrong, just pointless)
        if cfg.backup and cfg.dry_run:
            if not messagebox.askyesno(
                "Backups + Dry run",
                "You enabled both 'Backup' and 'Dry run'.\n"
                "Dry run won’t write changes, so backups won’t be created.\n\nContinue?",
            ):
                return

        self._cancel_event.clear()
        self._set_running(True)
        self._append_log("----")
        self._append_log(f"Root: {cfg.root}")
        self._append_log(f"Find: {repr(cfg.find_text)}")
        self._append_log(f"Replace: {repr(cfg.replace_text)}")
        self._append_log(f"Dry run: {cfg.dry_run} | Backup: {cfg.backup}")
        if cfg.include_patterns:
            self._append_log(f"Include patterns: {cfg.include_patterns}")
        if cfg.exclude_dir_names:
            self._append_log(f"Exclude dirs: {sorted(cfg.exclude_dir_names)}")

        self._worker_thread = threading.Thread(target=self._worker, args=(cfg,), daemon=True)
        self._worker_thread.start()

    def _on_cancel(self) -> None:
        if self._worker_thread and self._worker_thread.is_alive():
            self._cancel_event.set()
            self.status_var.set("Cancelling…")

    def _worker(self, cfg: RunConfig) -> None:
        res = RunResult()
        res.mode = "DRY RUN" if cfg.dry_run else "APPLIED"
        res.backups = "ON" if cfg.backup else "OFF"

        try:
            files = iter_json_files(cfg.root, cfg.include_patterns, cfg.exclude_dir_names)
            res.files_scanned = len(files)
            if not files:
                self._log_queue.put("No .json files found.")
                self._result_queue.put(res)
                return

            for idx, path in enumerate(files, start=1):
                if self._cancel_event.is_set():
                    self._log_queue.put("Cancelled by user.")
                    break

                # Light progress updates
                if idx == 1 or idx % 50 == 0:
                    self._log_queue.put(f"Scanning… ({idx}/{len(files)})")

                original = read_text(path)
                count = original.count(cfg.find_text)
                if count == 0:
                    continue

                updated = original.replace(cfg.find_text, cfg.replace_text)

                self._log_queue.put(f"[CHANGE] {path}  (replacements: {count})")
                res.files_changed += 1
                res.replacements += count

                if cfg.dry_run:
                    continue

                if cfg.backup:
                    bak = path.with_suffix(path.suffix + ".bak")
                    if not bak.exists():
                        bak.write_text(original, encoding="utf-8")
                    else:
                        self._log_queue.put(f"  [SKIP BACKUP] Backup already exists: {bak}")

                write_text_atomic(path, updated)

        except Exception as e:
            self._log_queue.put(f"[ERROR] {type(e).__name__}: {e}")

        self._result_queue.put(res)

    def _on_worker_done(self, res: RunResult) -> None:
        self._set_running(False)

        summary = (
            "----\n"
            "Summary\n"
            f"  Files scanned: {res.files_scanned}\n"
            f"  Files changed: {res.files_changed}\n"
            f"  Replacements:  {res.replacements}\n"
            f"  Mode:          {res.mode}\n"
            f"  Backups:       {res.backups}\n"
        )
        self._append_log(summary)

        # Also show a small popup for quick confirmation
        messagebox.showinfo(
            "Done",
            f"Files scanned: {res.files_scanned}\n"
            f"Files changed: {res.files_changed}\n"
            f"Replacements: {res.replacements}\n"
            f"Mode: {res.mode}\n"
            f"Backups: {res.backups}",
        )


if __name__ == "__main__":
    app = App()
    app.mainloop()