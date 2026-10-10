"""Gate metadata and author normalization shared by editors and storage."""
import json
import os
from typing import Any, Dict, List


INCOMING_ONLY_GATES_KEY = "incomingOnlyGates"

INCOMING_ONLY_GATES_ALIASES = (INCOMING_ONLY_GATES_KEY, "incoming_only_gates")

def get_incoming_only_gate_list(data: Any) -> List[str]:
    meta = data.get("metadata", {}) if isinstance(data, dict) else {}
    if not isinstance(meta, dict):
        return []

    cleaned = []
    seen = set()
    for key in INCOMING_ONLY_GATES_ALIASES:
        raw_names = meta.get(key, [])
        if isinstance(raw_names, str):
            raw_names = [raw_names]
        if not isinstance(raw_names, (list, tuple, set)):
            continue
        for name in raw_names:
            gate_name = str(name or "").strip()
            gate_key = gate_name.casefold()
            if not gate_name or gate_key in seen:
                continue
            cleaned.append(gate_name)
            seen.add(gate_key)
    return cleaned

def get_incoming_only_gate_names(data: Any) -> set:
    return {name.casefold() for name in get_incoming_only_gate_list(data)}

def set_incoming_only_gate(data: Dict[str, Any], gate_name: str, enabled: bool) -> None:
    md = data.setdefault("metadata", {})
    if not isinstance(md, dict):
        md = {}
        data["metadata"] = md

    cleaned_name = str(gate_name or "").strip()
    existing = get_incoming_only_gate_list(data)
    existing_keys = {name.casefold() for name in existing}
    gate_key = cleaned_name.casefold()

    if enabled and cleaned_name and gate_key not in existing_keys:
        existing.append(cleaned_name)
    elif not enabled:
        existing = [name for name in existing if name.casefold() != gate_key]

    for key in INCOMING_ONLY_GATES_ALIASES:
        md.pop(key, None)
    if existing:
        md[INCOMING_ONLY_GATES_KEY] = existing

def rename_incoming_only_gate(data: Dict[str, Any], old_name: str, new_name: str) -> None:
    cleaned_new = str(new_name or "").strip()
    old_key = str(old_name or "").strip().casefold()
    if not old_key or not cleaned_new:
        return

    existing = get_incoming_only_gate_list(data)
    changed = False
    renamed = []
    seen = set()
    for name in existing:
        candidate = cleaned_new if name.casefold() == old_key else name
        candidate_key = candidate.casefold()
        if candidate_key in seen:
            changed = True
            continue
        renamed.append(candidate)
        seen.add(candidate_key)
        changed = changed or candidate != name

    if changed:
        md = data.setdefault("metadata", {})
        if isinstance(md, dict):
            for key in INCOMING_ONLY_GATES_ALIASES:
                md.pop(key, None)
            if renamed:
                md[INCOMING_ONLY_GATES_KEY] = renamed

def remove_incoming_only_gate(data: Dict[str, Any], gate_name: str) -> None:
    set_incoming_only_gate(data, gate_name, False)

def _normalize_author_list(value: Any) -> List[str]:
    if value is None:
        return []
    items = []
    if isinstance(value, str):
        items = [x.strip() for x in value.split(',')]
    elif isinstance(value, list):
        items = [str(x).strip() for x in value]
    else:
        return []
    cleaned = []
    seen = set()
    for item in items:
        if not item:
            continue
        key = item.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(item)
    return cleaned

def _coerce_revision_number(value: Any) -> int:
    try:
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str):
            return int(value.strip() or 0)
    except Exception:
        return 0
    return 0

def build_gate_index_for_systems(data_base: str, current_filename: str):
    system_files = {}
    other_gate_index = {}
    try:
        filenames = os.listdir(data_base)
    except Exception:
        return system_files, other_gate_index

    for filename in filenames:
        if not filename.endswith('.json'):
            continue
        lowered = filename.lower()
        if lowered in ('package.json', 'galmapinfo.json'):
            continue
        system_name = os.path.splitext(filename)[0]
        system_files[system_name.lower()] = filename
        if current_filename and lowered == current_filename.lower():
            continue
        path = os.path.join(data_base, filename)
        try:
            with open(path, 'r') as f:
                data = json.load(f)
        except Exception:
            continue
        objects = data.get('objects', {})
        if not isinstance(objects, dict):
            continue
        gate_names = set()
        for name, obj in objects.items():
            if not isinstance(obj, dict):
                continue
            otype = str(obj.get('type', '')).lower()
            if otype in ('jumpnode', 'jumppoint', 'jump_point'):
                gate_names.add(name.lower())
        other_gate_index[filename] = gate_names

    if current_filename:
        current_name = os.path.splitext(current_filename)[0]
        system_files.setdefault(current_name.lower(), current_filename)

    return system_files, other_gate_index
