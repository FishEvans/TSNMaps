"""Translate system JSON into galactic-map records without canvas state."""
from MapConsistency import is_gate, validate_map_coordinate
from MapMetadata import get_incoming_only_gate_names
from MapTypes import system_has_blank_or_invalid_station_hull


def build_author_meta(meta, fallback=None):
    if not isinstance(meta, dict):
        meta = {}
    if not isinstance(fallback, dict):
        fallback = {}
    all_authors = meta.get("all_authors", fallback.get("all_authors", []))
    if not isinstance(all_authors, list):
        all_authors = []
    return {
        "original_author": meta.get("original_author", fallback.get("original_author", "")),
        "last_revision_author": meta.get(
            "last_revision_author",
            meta.get("last_author", fallback.get("last_revision_author", "")),
        ),
        "revision_number": meta.get("revision_number", fallback.get("revision_number", 0)),
        "revision_date": meta.get("revision_date", fallback.get("revision_date", "")),
        "all_authors": list(all_authors),
    }


def normalize_system_record(data, fallback_author_meta=None, valid_hull_keys=()):
    if not isinstance(data, dict) or "systemMapCoord" not in data:
        return None

    meta = data.get("metadata", {})
    if not isinstance(meta, dict):
        meta = {}

    objects = data.get("objects", {})
    if not isinstance(objects, dict):
        objects = {}

    jump_points = [
        {**value, "name": key}
        for key, value in objects.items()
        if is_gate(value)
    ]

    intel = meta.get("intel", {})
    if not isinstance(intel, dict):
        intel = {}

    traffic = data.get("traffic", {})
    if not isinstance(traffic, dict):
        traffic = {}

    coord = validate_map_coordinate(data["systemMapCoord"])

    exports = meta.get("exports", [])
    if not isinstance(exports, list):
        exports = []

    return {
        "coord": list(coord),
        "alignment": data.get("alignment") or data.get("systemalignment") or "Unknown",
        "description": meta.get("sysdescription", ""),
        "security": meta.get("security", "Neutral"),
        "exports": list(exports),
        "focus": meta.get("focus", ""),
        "intel": dict(intel),
        "development": meta.get("development", "Unclaimed"),
        "visible": meta.get("visible", True),
        "skybox": meta.get("skybox", ""),
        "traffic": dict(traffic),
        "author_meta": build_author_meta(meta, fallback_author_meta),
        "jump_points": jump_points,
        "incoming_only_gates": get_incoming_only_gate_names(data),
        "has_invalid_station_hull": system_has_blank_or_invalid_station_hull(
            data, valid_hull_keys
        ),
    }


def build_author_source(data, author_meta):
    meta = data.get("metadata", {})
    if not isinstance(meta, dict):
        meta = {}

    author_source = dict(meta)
    if isinstance(author_meta, dict):
        for key, value in author_meta.items():
            if author_source.get(key) in (None, "", []):
                author_source[key] = value

    for key in (
        "original_author",
        "last_revision_author",
        "last_author",
        "revision_number",
        "revision_date",
        "all_authors",
    ):
        if author_source.get(key) in (None, "", []):
            top_level_value = data.get(key)
            if top_level_value not in (None, "", []):
                author_source[key] = top_level_value
    return author_source


def apply_system_record_to_data(data, system_data, coord_override=None):
    if not isinstance(data, dict):
        data = {}

    coord = coord_override if coord_override is not None else system_data.get("coord")
    if coord is not None:
        data["systemMapCoord"] = validate_map_coordinate(coord)

    data["systemalignment"] = system_data.get("alignment", data.get("systemalignment", ""))
    if "alignment" in data:
        data["alignment"] = data["systemalignment"]
    metadata = data.get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}

    metadata.update({
        "sysdescription": system_data.get("description", ""),
        "security": system_data.get("security", "Neutral"),
        "exports": system_data.get("exports", []),
        "focus": system_data.get("focus", ""),
        "intel": system_data.get("intel", {}),
        "development": system_data.get("development", "Unclaimed"),
        "visible": system_data.get("visible", True),
        "skybox": system_data.get("skybox", metadata.get("skybox", "")),
    })

    author_meta = system_data.get("author_meta", {})
    if isinstance(author_meta, dict):
        metadata.update(author_meta)

    data["metadata"] = metadata

    traffic = system_data.get("traffic", {})
    if isinstance(traffic, dict):
        data["traffic"] = traffic

    return data
