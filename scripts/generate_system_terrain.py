import argparse
import copy
import json
import math
import random
import sys
from datetime import date
from pathlib import Path

SIZE_TO_RADIUS = {
    "small": 300000.0,
    "medium": 600000.0,
    "large": 750000.0,
}

DEFAULT_ASTEROIDS = 12
DEFAULT_NEBULAS = 8

DEFAULT_OUT = (
    Path("data") / "missions" / "Map Designer" / "Terrain" / "GeneratedTerrain.json"
)

TYPE_LABELS = {
    "asteroids": "Asteroid",
    "nebulas": "Nebula",
    "debris_field": "Debris",
}

PATTERN_LABELS = {
    "ring": "Ring",
    "arc": "Arc",
    "path": "Path",
    "random": "Field",
}


def load_template():
    try:
        from SystemTemplates import new_system_template
    except Exception:
        return {
            "systemMapCoord": [0, 0, 0],
            "systemalignment": "USFP",
            "metadata": {},
            "objects": {},
            "sensor_relay": {},
            "terrain": {},
            "traffic": {},
        }
    return copy.deepcopy(new_system_template)


def load_system(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Failed to read system JSON: {path} ({exc})")
    if not isinstance(data, dict):
        raise SystemExit(f"System JSON is not an object: {path}")
    return data


def unique_name(base: str, used: set) -> str:
    if base not in used:
        used.add(base)
        return base
    idx = 2
    while f"{base} {idx}" in used:
        idx += 1
    name = f"{base} {idx}"
    used.add(name)
    return name


def fmt_coord(val: float) -> float:
    return round(float(val), 2)


def point_within_radius(point, radius: float) -> bool:
    return (point[0] * point[0] + point[2] * point[2]) <= radius * radius


def clamp_to_radius(x: float, z: float, radius: float):
    r2 = x * x + z * z
    if r2 <= radius * radius:
        return x, z
    if r2 == 0:
        return x, z
    scale = radius / math.sqrt(r2)
    return x * scale, z * scale


def extend_segment(
    p0,
    p1,
    overlap_ratio: float,
    radius_limit: float,
):
    if overlap_ratio <= 0:
        return p0, p1
    dx = p1[0] - p0[0]
    dz = p1[1] - p0[1]
    length = math.hypot(dx, dz)
    if length == 0:
        return p0, p1
    ext = length * overlap_ratio
    ux = dx / length
    uz = dz / length
    sx = p0[0] - ux * ext
    sz = p0[1] - uz * ext
    ex = p1[0] + ux * ext
    ez = p1[1] + uz * ext
    if radius_limit:
        sx, sz = clamp_to_radius(sx, sz, radius_limit)
        ex, ez = clamp_to_radius(ex, ez, radius_limit)
    return (sx, sz), (ex, ez)


def random_point_in_annulus(rng: random.Random, r_min: float, r_max: float):
    if r_max <= r_min:
        r_max = r_min
    angle = rng.uniform(0.0, 2.0 * math.pi)
    r = math.sqrt(rng.uniform(r_min * r_min, r_max * r_max))
    return (r * math.cos(angle), r * math.sin(angle))


def dist2(a, b):
    dx = a[0] - b[0]
    dz = a[1] - b[1]
    return dx * dx + dz * dz


def is_far_enough(center, centers, min_gap: float) -> bool:
    if min_gap <= 0:
        return True
    limit = min_gap * min_gap
    for other in centers:
        if dist2(center, other) < limit:
            return False
    return True


def scatter_range(ttype: str, radius: float, max_allowed=None):
    if ttype == "debris_field":
        scale = 1.0
        base_min, base_max = 4000, 10000
        mid = 8000
    else:
        scale = radius / SIZE_TO_RADIUS["small"]
        if ttype == "asteroids":
            base_min, base_max = 8000, 25000
            mid = 15000
        elif ttype == "nebulas":
            base_min, base_max = 15000, 60000
            mid = 35000
        else:
            base_min, base_max = 8000, 40000
            mid = 20000
    min_scatter = base_min * scale
    max_scatter = base_max * scale
    if max_allowed is not None:
        max_scatter = min(max_scatter, max_allowed)
    max_scatter = min(max_scatter, radius * 0.2)
    min_scatter = max(min_scatter, 2000)
    if max_scatter < min_scatter:
        max_scatter = min_scatter
    return min_scatter, max_scatter, mid * scale


def pick_scatter(
    rng: random.Random, ttype: str, radius: float, max_allowed=None
) -> int:
    min_scatter, max_scatter, mid = scatter_range(ttype, radius, max_allowed)
    scatter = rng.triangular(min_scatter, max_scatter, mid)
    return int(max(1, scatter))


def pick_density(rng: random.Random, min_val: int, max_val: int) -> int:
    if max_val < min_val:
        max_val = min_val
    mid = (min_val + max_val) / 2.0
    val = rng.triangular(min_val, max_val, mid)
    return int(max(1, val))


def apply_swing(value: float, swing: float, min_val: float, max_val: float, rng):
    if swing <= 0:
        return max(min_val, min(max_val, value))
    factor = 1.0 + rng.uniform(-swing, swing)
    swung = value * factor
    return max(min_val, min(max_val, swung))


def build_lane(start, end, pattern):
    cx = (start[0] + end[0]) / 2.0
    cz = (start[2] + end[2]) / 2.0
    return {
        "start": [fmt_coord(start[0]), 0, fmt_coord(start[2])],
        "end": [fmt_coord(end[0]), 0, fmt_coord(end[2])],
        "center": (cx, cz),
        "pattern": pattern,
    }


def build_point(coord, pattern):
    return {
        "coordinate": [fmt_coord(coord[0]), 0, fmt_coord(coord[1])],
        "center": (coord[0], coord[1]),
        "pattern": pattern,
    }


def arc_points(
    rng: random.Random,
    radius: float,
    segments: int,
    arc_span: float,
    close_ring: bool,
    max_sides: int,
):
    segs = max(1, int(segments))
    if close_ring and max_sides:
        segs = min(segs, max_sides)
    ring_radius = rng.uniform(radius * 0.25, radius * 0.9)
    arc_start = rng.uniform(0.0, 2.0 * math.pi)
    if close_ring:
        arc_span = 2.0 * math.pi
    step = arc_span / segs
    count = segs if close_ring else segs + 1
    points = []
    for idx in range(count):
        angle = arc_start + idx * step
        points.append((ring_radius * math.cos(angle), ring_radius * math.sin(angle)))
    return points


def lane_arc_track(
    rng: random.Random,
    radius: float,
    segments: int,
    arc_span=None,
    max_sides=24,
    overlap_ratio=0.0,
):
    close_ring = arc_span is None
    if arc_span is None:
        arc_span = 2.0 * math.pi
    points = arc_points(rng, radius, segments, arc_span, close_ring, max_sides)
    lanes = []
    radius_limit = radius * 0.95
    if close_ring:
        for idx in range(len(points)):
            p0 = points[idx]
            p1 = points[(idx + 1) % len(points)]
            (sx, sz), (ex, ez) = extend_segment(
                p0, p1, overlap_ratio, radius_limit
            )
            lanes.append(build_lane([sx, 0, sz], [ex, 0, ez], "ring"))
        return lanes
    for idx in range(len(points) - 1):
        p0 = points[idx]
        p1 = points[idx + 1]
        (sx, sz), (ex, ez) = extend_segment(
            p0, p1, overlap_ratio, radius_limit
        )
        lanes.append(build_lane([sx, 0, sz], [ex, 0, ez], "arc"))
    return lanes


def path_points(
    rng: random.Random,
    radius: float,
    segments: int,
    turn_deg: float,
):
    segs = max(1, int(segments))
    max_turn = math.radians(max(5.0, float(turn_deg)))
    step_min = radius * 0.08
    step_max = radius * 0.18
    safe_radius = radius * 0.92
    cx, cz = random_point_in_annulus(rng, radius * 0.1, radius * 0.6)
    angle = rng.uniform(0.0, 2.0 * math.pi)
    points = [(cx, cz)]
    for _ in range(segs):
        length = rng.uniform(step_min, step_max)
        for _ in range(25):
            turn = rng.uniform(-max_turn, max_turn)
            ang_try = angle + turn
            nx = cx + math.cos(ang_try) * length
            nz = cz + math.sin(ang_try) * length
            if nx * nx + nz * nz <= safe_radius * safe_radius:
                angle = ang_try
                cx, cz = nx, nz
                points.append((cx, cz))
                break
        else:
            angle = math.atan2(-cz, -cx)
            cx += math.cos(angle) * length * 0.6
            cz += math.sin(angle) * length * 0.6
            points.append((cx, cz))
    return points


def lane_path_track(
    rng: random.Random,
    radius: float,
    segments: int,
    turn_deg: float,
    overlap_ratio: float,
):
    points = path_points(rng, radius, segments, turn_deg)
    lanes = []
    radius_limit = radius * 0.95
    for idx in range(len(points) - 1):
        p0 = points[idx]
        p1 = points[idx + 1]
        (sx, sz), (ex, ez) = extend_segment(
            p0, p1, overlap_ratio, radius_limit
        )
        lanes.append(build_lane([sx, 0, sz], [ex, 0, ez], "path"))
    return lanes


def point_arc_track(
    rng: random.Random,
    radius: float,
    segments: int,
    arc_span=None,
    max_sides=24,
):
    close_ring = arc_span is None
    if arc_span is None:
        arc_span = 2.0 * math.pi
    points = arc_points(rng, radius, segments, arc_span, close_ring, max_sides)
    pattern = "ring" if close_ring else "arc"
    return [build_point((x, z), pattern) for x, z in points]


def point_path_track(
    rng: random.Random, radius: float, segments: int, turn_deg: float
):
    points = path_points(rng, radius, segments, turn_deg)
    return [build_point((x, z), "path") for x, z in points[1:]]


def random_lane(rng: random.Random, radius: float):
    safe_radius = radius * 0.95
    for _ in range(40):
        cx, cz = random_point_in_annulus(rng, radius * 0.1, safe_radius)
        length = rng.uniform(radius * 0.08, radius * 0.25)
        angle = rng.uniform(0.0, 2.0 * math.pi)
        dx = math.cos(angle) * length / 2.0
        dz = math.sin(angle) * length / 2.0
        start = [cx - dx, 0, cz - dz]
        end = [cx + dx, 0, cz + dz]
        if point_within_radius(start, safe_radius) and point_within_radius(end, safe_radius):
            return build_lane(start, end, "random")
    return build_lane([0, 0, 0], [radius * 0.05, 0, 0], "random")


def random_point_feature(rng: random.Random, radius: float, max_scatter: float):
    safe_radius = max(0.0, radius - max_scatter)
    cx, cz = random_point_in_annulus(rng, 0.0, safe_radius)
    return build_point((cx, cz), "random")


def plan_tracks(total: int, rng: random.Random, min_seg=2, max_seg=5):
    tracks = []
    remaining = total
    min_seg = max(1, int(min_seg))
    max_seg = max(min_seg, int(max_seg))
    while remaining > 0:
        if remaining <= min_seg:
            segs = remaining
        else:
            segs = rng.randint(min_seg, min(max_seg, remaining))
        tracks.append(segs)
        remaining -= segs
    return tracks


def choose_pattern(rng: random.Random, weights: dict):
    roll = rng.random()
    acc = 0.0
    for key, weight in weights.items():
        acc += weight
        if roll <= acc:
            return key
    return list(weights.keys())[-1]


def generate_lane_features(
    count: int,
    ttype: str,
    radius: float,
    rng: random.Random,
    pattern_ratio: float,
    min_gap: float,
    centers: list,
    track_min: int,
    track_max: int,
    max_circle_sides: int,
    path_turn_deg: float,
    segment_overlap: float,
    arc_angle_min: float,
    arc_angle_max: float,
):
    results = []
    patterned = int(round(count * pattern_ratio))
    random_count = max(0, count - patterned)
    track_id = 0

    weights = (
        {"ring": 0.4, "arc": 0.4, "path": 0.2}
        if ttype == "asteroids"
        else {"ring": 0.2, "arc": 0.6, "path": 0.2}
    )

    for segs in plan_tracks(patterned, rng, track_min, track_max):
        pattern = choose_pattern(rng, weights)
        for _ in range(30):
            if pattern == "path":
                track = lane_path_track(
                    rng, radius, segs, path_turn_deg, segment_overlap
                )
            else:
                track = []
                if pattern == "ring" and max_circle_sides and segs > max_circle_sides:
                    remaining = segs
                    while remaining > 0:
                        chunk = min(max_circle_sides, remaining)
                        track.extend(
                            lane_arc_track(
                                rng,
                                radius,
                                chunk,
                                arc_span=None,
                                max_sides=max_circle_sides,
                                overlap_ratio=segment_overlap,
                            )
                        )
                        remaining -= chunk
                else:
                    arc_span = None
                    if pattern == "arc":
                        arc_span = rng.uniform(
                            math.radians(arc_angle_min),
                            math.radians(arc_angle_max),
                        )
                    track = lane_arc_track(
                        rng,
                        radius,
                        segs,
                        arc_span=arc_span,
                        max_sides=max_circle_sides,
                        overlap_ratio=segment_overlap,
                    )
            track_centers = [lane["center"] for lane in track]
            if all(is_far_enough(c, centers, min_gap) for c in track_centers):
                break
        else:
            track = [random_lane(rng, radius) for _ in range(segs)]
        for seg_index, lane in enumerate(track):
            lane["track_id"] = track_id
            lane["seg_index"] = seg_index
            centers.append(lane["center"])
            results.append(lane)
        track_id += 1

    for _ in range(random_count):
        for _ in range(40):
            lane = random_lane(rng, radius)
            if is_far_enough(lane["center"], centers, min_gap):
                break
        lane["track_id"] = track_id
        lane["seg_index"] = 0
        centers.append(lane["center"])
        results.append(lane)
        track_id += 1

    return results


def generate_point_features(
    count: int,
    radius: float,
    rng: random.Random,
    pattern_ratio: float,
    min_gap: float,
    centers: list,
    max_scatter_fn,
    track_min: int,
    track_max: int,
    max_circle_sides: int,
    path_turn_deg: float,
    segment_overlap: float,
    arc_angle_min: float,
    arc_angle_max: float,
):
    results = []
    patterned = int(round(count * pattern_ratio))
    random_count = max(0, count - patterned)

    weights = {"ring": 0.45, "arc": 0.35, "path": 0.2}

    for segs in plan_tracks(patterned, rng, track_min, track_max):
        pattern = choose_pattern(rng, weights)
        for _ in range(30):
            if pattern == "path":
                track = point_path_track(rng, radius, segs, path_turn_deg)
            else:
                track = []
                if pattern == "ring" and max_circle_sides and segs > max_circle_sides:
                    remaining = segs
                    while remaining > 0:
                        chunk = min(max_circle_sides, remaining)
                        track.extend(
                            point_arc_track(
                                rng,
                                radius,
                                chunk,
                                arc_span=None,
                                max_sides=max_circle_sides,
                            )
                        )
                        remaining -= chunk
                else:
                    arc_span = None
                    if pattern == "arc":
                        arc_span = rng.uniform(
                            math.radians(arc_angle_min),
                            math.radians(arc_angle_max),
                        )
                    track = point_arc_track(
                        rng,
                        radius,
                        segs,
                        arc_span=arc_span,
                        max_sides=max_circle_sides,
                    )
            track_centers = [pt["center"] for pt in track]
            if all(is_far_enough(c, centers, min_gap) for c in track_centers):
                break
        else:
            track = [
                random_point_feature(rng, radius, max_scatter_fn()) for _ in range(segs)
            ]
        for pt in track:
            centers.append(pt["center"])
            results.append(pt)

    for _ in range(random_count):
        for _ in range(40):
            pt = random_point_feature(rng, radius, max_scatter_fn())
            if is_far_enough(pt["center"], centers, min_gap):
                break
        centers.append(pt["center"])
        results.append(pt)

    return results


def build_terrain(
    radius: float,
    asteroid_count: int,
    nebula_count: int,
    debris_count: int,
    rng: random.Random,
    pattern_ratio: float,
    min_gap: float,
    used_names: set,
    track_min: int,
    track_max: int,
    max_circle_sides: int,
    path_turn_deg: float,
    segment_overlap: float,
    density_min: int,
    density_max: int,
    segment_swing: float,
    debris_density: int,
    arc_angle_min: float,
    arc_angle_max: float,
):
    terrain = {}
    centers = []

    lane_specs = [
        ("asteroids", asteroid_count),
        ("nebulas", nebula_count),
    ]
    for ttype, count in lane_specs:
        lanes = generate_lane_features(
            count,
            ttype,
            radius,
            rng,
            pattern_ratio,
            min_gap,
            centers,
            track_min,
            track_max,
            max_circle_sides,
            path_turn_deg,
            segment_overlap,
            arc_angle_min,
            arc_angle_max,
        )
        track_order = []
        tracks = {}
        for lane in lanes:
            track_id = lane.pop("track_id", None)
            seg_index = lane.pop("seg_index", 0)
            if track_id not in tracks:
                tracks[track_id] = []
                track_order.append(track_id)
            tracks[track_id].append((seg_index, lane))

        for track_id in track_order:
            track = sorted(tracks[track_id], key=lambda x: x[0])
            pattern = track[0][1]["pattern"]
            is_pattern = len(track) > 1 or pattern in ("arc", "ring", "path")
            width_min, width_max = (16000.0, 45000.0) if is_pattern else (16000.0, 70000.0)
            length_min, length_max = (16000.0, 45000.0) if is_pattern else (16000.0, 70000.0)
            base_density = float(pick_density(rng, density_min, density_max))
            base_width = rng.uniform(width_min, width_max)
            base_length = rng.uniform(length_min, length_max)
            prev_width = float(base_width)
            prev_length = float(base_length)
            prev_core_end = None
            for seg_index, lane in track:
                if seg_index > 0:
                    prev_width = apply_swing(
                        prev_width, segment_swing, width_min, width_max, rng
                    )
                    prev_length = apply_swing(
                        prev_length, segment_swing, length_min, length_max, rng
                    )
                width = float(prev_width)
                length = float(prev_length)
                density = int(
                    round(base_density * (width * length) / (20000.0 * 20000.0))
                )
                density = max(1, density)
                scatter = int(round(width / 2.0))

                sx, sz = lane["start"][0], lane["start"][2]
                ex, ez = lane["end"][0], lane["end"][2]
                dx = ex - sx
                dz = ez - sz
                seg_len = math.hypot(dx, dz)
                if seg_len == 0:
                    ang = rng.uniform(0.0, 2.0 * math.pi)
                    ux, uz = math.cos(ang), math.sin(ang)
                else:
                    ux, uz = dx / seg_len, dz / seg_len

                radius_limit = radius * 0.95
                if not is_pattern:
                    center = lane["center"]
                    ang = rng.uniform(0.0, 2.0 * math.pi)
                    ux, uz = math.cos(ang), math.sin(ang)
                    core_start = (
                        center[0] - ux * length / 2.0,
                        center[1] - uz * length / 2.0,
                    )
                else:
                    if prev_core_end is None:
                        core_start = (sx, sz)
                    else:
                        core_start = prev_core_end

                core_end = (
                    core_start[0] + ux * length,
                    core_start[1] + uz * length,
                )
                if radius_limit:
                    core_start = clamp_to_radius(core_start[0], core_start[1], radius_limit)
                    core_end = clamp_to_radius(core_end[0], core_end[1], radius_limit)

                (fx, fz), (tx, tz) = extend_segment(
                    core_start, core_end, segment_overlap, radius_limit
                )
                lane["start"] = [fmt_coord(fx), 0, fmt_coord(fz)]
                lane["end"] = [fmt_coord(tx), 0, fmt_coord(tz)]
                prev_core_end = core_end
                base = f"{TYPE_LABELS[ttype]} {PATTERN_LABELS[lane['pattern']]}"
                key = unique_name(base, used_names)
                terrain[key] = {
                    "type": ttype,
                    "seed": rng.randint(0, 9999999),
                    "start": lane["start"],
                    "end": lane["end"],
                    "density": density,
                    "scatter": scatter,
                    "composition": ["Ast. Std Rand"] if ttype == "asteroids" else [],
                }

    def max_scatter_limit():
        return min(10000.0, radius * 0.2)

    for pt in generate_point_features(
        debris_count,
        radius,
        rng,
        pattern_ratio,
        min_gap,
        centers,
        max_scatter_limit,
        track_min,
        track_max,
        max_circle_sides,
        path_turn_deg,
        segment_overlap,
        arc_angle_min,
        arc_angle_max,
    ):
        max_scatter = min(10000.0, radius * 0.2)
        center_r = math.hypot(pt["center"][0], pt["center"][1])
        if center_r >= radius:
            max_scatter = min(10000.0, radius * 0.05)
        else:
            max_scatter = max(1000.0, min(10000.0, radius - center_r))
        density = int(
            round(
                apply_swing(
                    float(debris_density),
                    segment_swing,
                    1,
                    debris_density * 2,
                    rng,
                )
            )
        )
        scatter = pick_scatter(
            rng, "debris_field", radius, max_allowed=min(10000.0, max_scatter)
        )
        base = f"{TYPE_LABELS['debris_field']} {PATTERN_LABELS[pt['pattern']]}"
        key = unique_name(base, used_names)
        terrain[key] = {
            "type": "debris_field",
            "seed": rng.randint(0, 9999999),
            "coordinate": pt["coordinate"],
            "density": density,
            "scatter": scatter,
        }

    return terrain


def interactive_prompt(defaults, parent=None, show_io=True):
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk
    except Exception as exc:
        raise SystemExit(f"Interactive mode requires Tkinter: {exc}")

    owns_root = parent is None
    root = tk.Tk() if owns_root else tk.Toplevel(parent)
    root.title("Generate System Terrain")
    root.resizable(False, False)

    def add_row(label, var, row, width=14):
        tk.Label(root, text=label).grid(row=row, column=0, sticky="w", padx=6, pady=3)
        entry = tk.Entry(root, textvariable=var, width=width)
        entry.grid(row=row, column=1, sticky="w", padx=6, pady=3)
        return entry

    size_var = tk.StringVar(value=defaults.size)
    tk.Label(root, text="Size:").grid(row=0, column=0, sticky="w", padx=6, pady=3)
    size_cb = ttk.Combobox(
        root, textvariable=size_var, values=sorted(SIZE_TO_RADIUS), state="readonly"
    )
    size_cb.grid(row=0, column=1, sticky="w", padx=6, pady=3)

    radius_var = tk.StringVar(value="" if defaults.radius is None else str(defaults.radius))
    add_row("Radius override:", radius_var, 1)

    ast_var = tk.StringVar(value=str(defaults.asteroids))
    neb_var = tk.StringVar(value=str(defaults.nebulas))
    deb_var = tk.StringVar(value=str(defaults.debris))
    add_row("Asteroids:", ast_var, 2)
    add_row("Nebulas:", neb_var, 3)
    add_row("Debris:", deb_var, 4)

    dmin_var = tk.StringVar(value=str(defaults.density_min))
    dmax_var = tk.StringVar(value=str(defaults.density_max))
    debris_density_var = tk.StringVar(value=str(defaults.debris_density))
    add_row("Density min (20k area):", dmin_var, 5, width=8)
    add_row("Density max (20k area):", dmax_var, 6, width=8)
    add_row("Debris density:", debris_density_var, 7, width=8)

    pattern_var = tk.StringVar(value=str(defaults.pattern_ratio))
    gap_var = tk.StringVar(value="" if defaults.min_gap is None else str(defaults.min_gap))
    add_row("Pattern ratio (0-1):", pattern_var, 8)
    add_row("Min gap (blank=auto):", gap_var, 9, width=18)

    tmin_var = tk.StringVar(value=str(defaults.track_min))
    tmax_var = tk.StringVar(value=str(defaults.track_max))
    arc_min_var = tk.StringVar(value=str(defaults.arc_angle_min))
    arc_max_var = tk.StringVar(value=str(defaults.arc_angle_max))
    sides_var = tk.StringVar(value=str(defaults.max_circle_sides))
    turn_var = tk.StringVar(value=str(defaults.path_turn))
    overlap_var = tk.StringVar(value=str(defaults.segment_overlap))
    swing_var = tk.StringVar(value=str(defaults.segment_swing))
    add_row("Track min segments:", tmin_var, 10, width=6)
    add_row("Track max segments:", tmax_var, 11, width=6)
    add_row("Arc angle min:", arc_min_var, 12, width=6)
    add_row("Arc angle max:", arc_max_var, 13, width=6)
    add_row("Max circle sides:", sides_var, 14, width=6)
    add_row("Path turn deg:", turn_var, 15, width=6)
    add_row("Segment overlap (0-0.5):", overlap_var, 16, width=6)
    add_row("Segment swing (0-0.5):", swing_var, 17, width=6)

    seed_var = tk.StringVar(value="" if defaults.seed is None else str(defaults.seed))
    add_row("Seed (blank=random):", seed_var, 18, width=12)

    mode_var = tk.StringVar(value=defaults.mode)
    tk.Label(root, text="Mode:").grid(row=19, column=0, sticky="w", padx=6, pady=3)
    mode_cb = ttk.Combobox(
        root, textvariable=mode_var, values=["replace", "append"], state="readonly"
    )
    mode_cb.grid(row=19, column=1, sticky="w", padx=6, pady=3)

    input_var = tk.StringVar(value="" if defaults.input is None else str(defaults.input))
    output_var = tk.StringVar(value="" if defaults.out is None else str(defaults.out))

    if show_io:
        def browse_input():
            path = filedialog.askopenfilename(
                title="Select system JSON",
                filetypes=[("JSON Files", "*.json")],
                parent=root,
            )
            if path:
                input_var.set(path)

        def browse_output():
            path = filedialog.asksaveasfilename(
                title="Save system JSON",
                defaultextension=".json",
                filetypes=[("JSON Files", "*.json")],
                parent=root,
            )
            if path:
                output_var.set(path)

        tk.Label(root, text="Input system:").grid(
            row=20, column=0, sticky="w", padx=6, pady=3
        )
        tk.Entry(root, textvariable=input_var, width=28).grid(
            row=20, column=1, sticky="w", padx=6, pady=3
        )
        tk.Button(root, text="Browse", command=browse_input).grid(
            row=20, column=2, padx=6, pady=3
        )

        tk.Label(root, text="Output system:").grid(
            row=21, column=0, sticky="w", padx=6, pady=3
        )
        tk.Entry(root, textvariable=output_var, width=28).grid(
            row=21, column=1, sticky="w", padx=6, pady=3
        )
        tk.Button(root, text="Browse", command=browse_output).grid(
            row=21, column=2, padx=6, pady=3
        )

    result = {"args": None}

    def parse_int(text, field, min_val=None):
        text = text.strip()
        if text == "":
            return None
        try:
            val = int(text)
        except ValueError:
            raise ValueError(f"{field} must be an integer.")
        if min_val is not None and val < min_val:
            raise ValueError(f"{field} must be >= {min_val}.")
        return val

    def parse_float(text, field, min_val=None, max_val=None):
        text = text.strip()
        if text == "":
            return None
        try:
            val = float(text)
        except ValueError:
            raise ValueError(f"{field} must be a number.")
        if min_val is not None and val < min_val:
            raise ValueError(f"{field} must be >= {min_val}.")
        if max_val is not None and val > max_val:
            raise ValueError(f"{field} must be <= {max_val}.")
        return val

    def on_ok():
        try:
            size = size_var.get()
            radius = parse_float(radius_var.get(), "Radius override", min_val=1)
            asteroids = parse_int(ast_var.get(), "Asteroids", min_val=0)
            nebulas = parse_int(neb_var.get(), "Nebulas", min_val=0)
            debris = parse_int(deb_var.get(), "Debris", min_val=0)
            density_min = parse_int(dmin_var.get(), "Density min", min_val=1)
            density_max = parse_int(dmax_var.get(), "Density max", min_val=1)
            debris_density = parse_int(
                debris_density_var.get(), "Debris density", min_val=1
            )
            pattern_ratio = parse_float(
                pattern_var.get(), "Pattern ratio", min_val=0.0, max_val=1.0
            )
            min_gap = parse_float(gap_var.get(), "Min gap", min_val=0.0)
            track_min = parse_int(tmin_var.get(), "Track min segments", min_val=1)
            track_max = parse_int(tmax_var.get(), "Track max segments", min_val=1)
            arc_min = parse_float(arc_min_var.get(), "Arc angle min", min_val=1.0)
            arc_max = parse_float(arc_max_var.get(), "Arc angle max", min_val=1.0)
            max_sides = parse_int(sides_var.get(), "Max circle sides", min_val=1)
            path_turn = parse_float(turn_var.get(), "Path turn deg", min_val=1.0)
            overlap = parse_float(
                overlap_var.get(), "Segment overlap", min_val=0.0, max_val=0.5
            )
            swing = parse_float(
                swing_var.get(), "Segment swing", min_val=0.0, max_val=0.5
            )
            seed = parse_int(seed_var.get(), "Seed", min_val=0)
            mode = mode_var.get()
        except ValueError as exc:
            messagebox.showerror("Invalid input", str(exc))
            return

        if density_min is None or density_max is None:
            messagebox.showerror(
                "Invalid input", "Density min/max must be set."
            )
            return
        if density_min > density_max:
            messagebox.showerror(
                "Invalid input", "Density min cannot exceed max."
            )
            return
        if track_min is None or track_max is None:
            messagebox.showerror(
                "Invalid input", "Track min/max segments must be set."
            )
            return
        if track_min > track_max:
            messagebox.showerror(
                "Invalid input", "Track min segments cannot exceed max."
            )
            return

        input_path = input_var.get().strip()
        output_path = output_var.get().strip()
        if input_path == "":
            input_path = None
        if output_path == "":
            output_path = None
        if output_path is None and input_path:
            output_path = input_path

        ns = argparse.Namespace(**vars(defaults))
        ns.size = size
        ns.radius = radius
        ns.asteroids = asteroids if asteroids is not None else defaults.asteroids
        ns.nebulas = nebulas if nebulas is not None else defaults.nebulas
        ns.debris = debris if debris is not None else defaults.debris
        ns.pattern_ratio = (
            pattern_ratio if pattern_ratio is not None else defaults.pattern_ratio
        )
        ns.min_gap = min_gap
        ns.density_min = density_min
        ns.density_max = density_max
        ns.debris_density = debris_density
        ns.track_min = track_min
        ns.track_max = track_max
        ns.arc_angle_min = arc_min
        ns.arc_angle_max = arc_max
        ns.max_circle_sides = max_sides
        ns.path_turn = path_turn if path_turn is not None else defaults.path_turn
        ns.segment_overlap = overlap if overlap is not None else defaults.segment_overlap
        ns.segment_swing = swing if swing is not None else defaults.segment_swing
        ns.seed = seed
        ns.mode = mode
        ns._counts_custom = (
            ns.asteroids != defaults.asteroids or ns.nebulas != defaults.nebulas
        )
        ns.input = Path(input_path) if input_path else None
        ns.out = Path(output_path) if output_path else None
        ns.interactive = False

        result["args"] = ns
        root.destroy()

    def on_cancel():
        root.destroy()

    btn_row = 22 if show_io else 20
    btn_frame = tk.Frame(root)
    btn_frame.grid(row=btn_row, column=0, columnspan=3, pady=8)
    tk.Button(btn_frame, text="Generate", width=14, command=on_ok).pack(
        side=tk.LEFT, padx=6
    )
    tk.Button(btn_frame, text="Cancel", width=10, command=on_cancel).pack(
        side=tk.LEFT, padx=6
    )

    if owns_root:
        root.mainloop()
    else:
        try:
            root.transient(parent)
        except Exception:
            pass
        try:
            root.grab_set()
        except Exception:
            pass
        root.wait_window()

    if result["args"] is None:
        raise SystemExit("Canceled.")
    return result["args"]


def main():
    parser = argparse.ArgumentParser(
        description="Generate arc/path-heavy terrain for a system JSON."
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Show a dialog to configure options.",
    )
    parser.add_argument(
        "--size",
        type=str.lower,
        choices=sorted(SIZE_TO_RADIUS),
        default="medium",
        help="System size preset (radius in units).",
    )
    parser.add_argument("--radius", type=float, help="Override size radius.")
    parser.add_argument(
        "--asteroids", type=int, default=DEFAULT_ASTEROIDS, help="Asteroid fields."
    )
    parser.add_argument(
        "--nebulas", type=int, default=DEFAULT_NEBULAS, help="Nebula fields."
    )
    parser.add_argument("--debris", type=int, default=6, help="Debris fields.")
    parser.add_argument(
        "--density-min",
        type=int,
        default=100,
        help="Minimum density for 20k x 20k area (asteroids/nebula).",
    )
    parser.add_argument(
        "--density-max",
        type=int,
        default=300,
        help="Maximum density for 20k x 20k area (asteroids/nebula).",
    )
    parser.add_argument(
        "--debris-density",
        type=int,
        default=130,
        help="Target debris density (radius capped at 10,000).",
    )
    parser.add_argument("--seed", type=int, help="Random seed.")
    parser.add_argument(
        "--pattern-ratio",
        type=float,
        default=0.7,
        help="Share of features placed along arcs/paths (0-1).",
    )
    parser.add_argument(
        "--track-min",
        type=int,
        default=4,
        help="Minimum segments per arc/path track.",
    )
    parser.add_argument(
        "--track-max",
        type=int,
        default=9,
        help="Maximum segments per arc/path track.",
    )
    parser.add_argument(
        "--arc-angle-min",
        type=float,
        default=20.0,
        help="Minimum arc angle in degrees.",
    )
    parser.add_argument(
        "--arc-angle-max",
        type=float,
        default=45.0,
        help="Maximum arc angle in degrees.",
    )
    parser.add_argument(
        "--max-circle-sides",
        type=int,
        default=24,
        help="Max segments used to approximate a full circle.",
    )
    parser.add_argument(
        "--path-turn",
        type=float,
        default=40.0,
        help="Max turn angle in degrees between chained path segments.",
    )
    parser.add_argument(
        "--segment-overlap",
        type=float,
        default=0.15,
        help="Overlap ratio for chained arc/path segments (0-0.5).",
    )
    parser.add_argument(
        "--segment-swing",
        type=float,
        default=0.15,
        help="Per-segment density/size swing along a track (0-0.5).",
    )
    parser.add_argument(
        "--min-gap",
        type=float,
        default=None,
        help="Minimum spacing between feature centers.",
    )
    parser.add_argument("--input", type=Path, help="Existing system JSON.")
    parser.add_argument("--out", type=Path, help="Output system JSON.")
    parser.add_argument(
        "--mode",
        choices=("replace", "append"),
        default="replace",
        help="Replace or append to existing terrain.",
    )
    args = parser.parse_args()

    counts_custom = any(
        flag in sys.argv for flag in ("--asteroids", "--nebulas")
    )
    if args.interactive or len(sys.argv) == 1:
        args = interactive_prompt(args)
    args._counts_custom = counts_custom or getattr(args, "_counts_custom", False)

    if args.asteroids < 0 or args.nebulas < 0 or args.debris < 0:
        raise SystemExit("Counts must be non-negative integers.")
    if not (0.0 <= args.pattern_ratio <= 1.0):
        raise SystemExit("--pattern-ratio must be between 0 and 1.")
    if args.density_min <= 0 or args.density_max <= 0:
        raise SystemExit("--density-min and --density-max must be positive integers.")
    if args.density_min > args.density_max:
        raise SystemExit("--density-min cannot exceed --density-max.")
    if args.debris_density <= 0:
        raise SystemExit("--debris-density must be a positive integer.")
    if args.track_min <= 0 or args.track_max <= 0:
        raise SystemExit("--track-min and --track-max must be positive integers.")
    if args.track_min > args.track_max:
        raise SystemExit("--track-min cannot be greater than --track-max.")
    if args.arc_angle_min <= 0 or args.arc_angle_max <= 0:
        raise SystemExit("--arc-angle-min/max must be positive numbers.")
    if args.arc_angle_min > args.arc_angle_max:
        raise SystemExit("--arc-angle-min cannot exceed --arc-angle-max.")
    if args.arc_angle_max > 360:
        raise SystemExit("--arc-angle-max must be <= 360.")
    if args.max_circle_sides <= 0:
        raise SystemExit("--max-circle-sides must be a positive integer.")
    if args.path_turn <= 0:
        raise SystemExit("--path-turn must be a positive number.")
    if not (0.0 <= args.segment_overlap <= 0.5):
        raise SystemExit("--segment-overlap must be between 0 and 0.5.")
    if not (0.0 <= args.segment_swing <= 0.5):
        raise SystemExit("--segment-swing must be between 0 and 0.5.")

    radius = args.radius if args.radius else SIZE_TO_RADIUS[args.size]
    min_gap = args.min_gap
    if min_gap is None:
        min_gap = max(20000.0, radius * 0.08)

    counts_custom = getattr(args, "_counts_custom", False)
    if not counts_custom:
        if args.size == "medium":
            args.asteroids *= 2
            args.nebulas *= 2
        elif args.size == "large":
            args.asteroids *= 4
            args.nebulas *= 4

    rng = random.Random(args.seed)

    data = load_system(args.input) if args.input else load_template()
    terrain_data = data.setdefault("terrain", {})
    used_names = set(terrain_data.keys())

    new_terrain = build_terrain(
        radius,
        args.asteroids,
        args.nebulas,
        args.debris,
        rng,
        args.pattern_ratio,
        min_gap,
        used_names,
        args.track_min,
        args.track_max,
        args.max_circle_sides,
        args.path_turn,
        args.segment_overlap,
        args.density_min,
        args.density_max,
        args.segment_swing,
        args.debris_density,
        args.arc_angle_min,
        args.arc_angle_max,
    )

    if args.mode == "append":
        terrain_data.update(new_terrain)
    else:
        data["terrain"] = new_terrain

    if not args.input and not data.get("metadata", {}).get("sysdescription"):
        data.setdefault("metadata", {})["sysdescription"] = (
            f"Autogenerated terrain ({args.size}, {int(radius)} radius) "
            f"on {date.today().isoformat()}."
        )

    out_path = args.out if args.out else (args.input or DEFAULT_OUT)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, indent=4), encoding="utf-8")

    total = len(new_terrain)
    print(
        f"Wrote {total} terrain features "
        f"(asteroids={args.asteroids}, nebulas={args.nebulas}, debris={args.debris}) "
        f"to {out_path}"
    )


if __name__ == "__main__":
    main()
