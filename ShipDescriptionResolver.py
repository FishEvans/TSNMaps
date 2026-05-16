import ast
import json
import os
import re
import sys
from functools import lru_cache
from pathlib import Path


SHIPMAP_RELATIVE_PATH = Path("HTML") / "Images" / "Ships" / "ShipMap.json"
AUTHORITATIVE_DB_PATH = Path("scripts") / "Referance" / "tsn_databases.py"
SHIPDATA_PATH = Path("scripts") / "Referance" / "shipData.yaml"
LOW_PRIORITY_DESC_PATH = Path("scripts") / "Referance" / "ship_descriptions_fallback.json"
DESCRIPTION_FIELDS = {"description", "type", "race", "tags"}
SHIP_STAT_FIELDS = {"shields", "systemhealth", "abilities"}


def get_base_path():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def normalize_roles(roles):
    if isinstance(roles, str):
        return [part.strip() for part in roles.split(",") if part.strip()]
    if isinstance(roles, list):
        return [str(part).strip() for part in roles if str(part).strip()]
    return []


def prettify_label(value):
    value = str(value or "").strip()
    if not value:
        return "Unknown"
    if value.upper() in {"TSN", "USFP"}:
        return value.upper()
    if value.islower():
        return value.title()
    return value


def clean_description(value):
    text = str(value or "").strip()
    return text if text else ""


def _read_json_file(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _strip_hash_comments(text):
    lines = []
    for raw_line in text.splitlines():
        in_string = False
        escaped = False
        quote_char = ""
        collected = []
        for char in raw_line:
            if escaped:
                collected.append(char)
                escaped = False
                continue
            if char == "\\":
                collected.append(char)
                escaped = True
                continue
            if in_string:
                collected.append(char)
                if char == quote_char:
                    in_string = False
                continue
            if char in {'"', "'"}:
                collected.append(char)
                in_string = True
                quote_char = char
                continue
            if char == "#":
                break
            collected.append(char)
        lines.append("".join(collected))
    return "\n".join(lines)


def _strip_comments_and_commas(text):
    cleaned = _strip_hash_comments(text)
    return re.sub(r",\s*([\]\}])", r"\1", cleaned)


def _load_hjson_like_file(path):
    raw = path.read_text(encoding="utf-8")
    try:
        import hjson  # type: ignore

        return hjson.loads(raw)
    except Exception:
        return json.loads(_strip_comments_and_commas(raw))


@lru_cache(maxsize=1)
def load_shipmap_index():
    path = Path(get_base_path()) / SHIPMAP_RELATIVE_PATH
    if not path.exists():
        return {}

    data = _read_json_file(path)
    if not isinstance(data, list):
        return {}

    result = {}
    for entry in data:
        if not isinstance(entry, dict):
            continue
        key = str(entry.get("key", "")).strip()
        if key:
            result[key] = entry
    return result


@lru_cache(maxsize=1)
def load_shipdata_index():
    path = Path(get_base_path()) / SHIPDATA_PATH
    if not path.exists():
        return {}

    data = _load_hjson_like_file(path)
    if not isinstance(data, dict):
        return {}

    entries = data.get("#ship-list") or data.get("ship-list") or []
    if not isinstance(entries, list):
        return {}

    result = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        key = str(entry.get("key", "")).strip()
        if key:
            result[key] = entry
    return result


def _parse_description_fields(entry_node):
    extracted = {}
    if not isinstance(entry_node, ast.Dict):
        return extracted

    for field_key, field_value in zip(entry_node.keys, entry_node.values):
        if not isinstance(field_key, ast.Constant) or not isinstance(field_key.value, str):
            continue
        field_name = field_key.value
        if field_name not in DESCRIPTION_FIELDS:
            continue
        try:
            extracted[field_name] = ast.literal_eval(field_value)
        except Exception:
            continue
    return extracted


def _parse_literal_fields(entry_node, allowed_fields):
    extracted = {}
    if not isinstance(entry_node, ast.Dict):
        return extracted

    for field_key, field_value in zip(entry_node.keys, entry_node.values):
        if not isinstance(field_key, ast.Constant) or not isinstance(field_key.value, str):
            continue
        field_name = field_key.value
        if field_name not in allowed_fields:
            continue
        try:
            extracted[field_name] = ast.literal_eval(field_value)
        except Exception:
            continue
    return extracted


@lru_cache(maxsize=1)
def load_authoritative_description_index():
    path = Path(get_base_path()) / AUTHORITATIVE_DB_PATH
    if not path.exists():
        return {}

    source = path.read_text(encoding="utf-8")
    module = ast.parse(source, filename=str(path))
    index = {}

    for node in module.body:
        if not isinstance(node, ast.Assign):
            continue
        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            continue
        if not isinstance(node.value, ast.Dict):
            continue

        for item_key, item_value in zip(node.value.keys, node.value.values):
            if not isinstance(item_key, ast.Constant) or not isinstance(item_key.value, str):
                continue
            record = _parse_description_fields(item_value)
            if record:
                index[item_key.value] = record

    return index


@lru_cache(maxsize=1)
def load_authoritative_ship_stats_index():
    path = Path(get_base_path()) / AUTHORITATIVE_DB_PATH
    if not path.exists():
        return {}

    source = path.read_text(encoding="utf-8")
    module = ast.parse(source, filename=str(path))
    index = {}

    for node in module.body:
        if not isinstance(node, ast.Assign):
            continue
        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            continue
        if not isinstance(node.value, ast.Dict):
            continue

        for item_key, item_value in zip(node.value.keys, node.value.values):
            if not isinstance(item_key, ast.Constant) or not isinstance(item_key.value, str):
                continue
            record = _parse_literal_fields(item_value, SHIP_STAT_FIELDS)
            if record:
                index[item_key.value] = record

    return index


@lru_cache(maxsize=1)
def load_low_priority_description_index():
    path = Path(get_base_path()) / LOW_PRIORITY_DESC_PATH
    if not path.exists():
        return {}

    data = _read_json_file(path)
    if not isinstance(data, dict):
        return {}

    index = {}
    for key, value in data.items():
        key = str(key).strip()
        if not key:
            continue
        if isinstance(value, dict):
            description = clean_description(value.get("description", ""))
        else:
            description = clean_description(value)
        if description:
            index[key] = {"description": description}
    return index


def _select_kind_label(roles):
    lowered = [role.casefold() for role in roles]
    if "platform" in lowered:
        return "platform"
    if "station" in lowered or "static" in lowered:
        return "station"
    if "node" in lowered:
        return "node"
    return "ship"


def _build_generated_fallback(key, name, side, roles, meta):
    display_name = str(name or meta.get("type") or key or "This object").strip()
    race_label = prettify_label(meta.get("race") or side or "")
    role_labels = []
    for role in roles:
        normalized = role.casefold()
        if normalized in {"ship", "station", "static", "platform", "node"}:
            continue
        role_labels.append(prettify_label(role.replace("_", " ")))

    sentence = f"{display_name} is catalogued as a {_select_kind_label(roles)}"
    if race_label and race_label != "Unknown":
        sentence += f" aligned with {race_label}"
    if role_labels:
        sentence += f", associated with {', '.join(role_labels[:3])}"
    sentence += ". No formal database description is currently available."
    return sentence


def resolve_ship_description(key, *, name="", side="", roles=None, shipmap_entry=None):
    key = str(key or "").strip()
    roles = normalize_roles(roles if roles is not None else [])

    authoritative = load_authoritative_description_index().get(key, {})
    shipdata = load_shipdata_index().get(key, {})
    shipmap_index = load_shipmap_index()
    resolved_shipmap_entry = shipmap_entry if isinstance(shipmap_entry, dict) else shipmap_index.get(key, {})
    low_priority = load_low_priority_description_index().get(key, {})

    candidates = [
        ("tsn_databases.py", clean_description(authoritative.get("description", ""))),
        ("shipData.yaml", clean_description(shipdata.get("long_desc", ""))),
        ("ShipMap.json", clean_description(resolved_shipmap_entry.get("long_desc", ""))),
        ("ship_descriptions_fallback.json", clean_description(low_priority.get("description", ""))),
    ]
    for source_name, description in candidates:
        if description:
            return {
                "description": description,
                "source": source_name,
            }

    combined_roles = roles[:]
    if not combined_roles:
        combined_roles = normalize_roles(authoritative.get("tags", []))
        if not combined_roles and isinstance(shipdata, dict):
            combined_roles = normalize_roles(shipdata.get("roles", []))
        if not combined_roles and isinstance(resolved_shipmap_entry, dict):
            combined_roles = normalize_roles(resolved_shipmap_entry.get("roles", []))

    fallback_text = _build_generated_fallback(
        key,
        name or shipdata.get("name", "") or resolved_shipmap_entry.get("name", ""),
        side or shipdata.get("side", "") or resolved_shipmap_entry.get("side", ""),
        combined_roles,
        authoritative or shipdata,
    )
    return {
        "description": fallback_text,
        "source": "generated",
    }
