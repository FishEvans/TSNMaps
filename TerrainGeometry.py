"""Deterministic terrain generation and zone placement; no UI or file writes."""
import math
import random
import re
from MapTypes import (FCS_ZONE_TYPE, DEFAULT_FCS_MIN_SPACING, DEFAULT_FCS_DENSITY_RADIUS,
    DEFAULT_FCS_DENSITY_PERCENTILE, DEFAULT_FCS_MIN_SCORE, DEFAULT_FCS_SPACING_JITTER)


def distance_to_spine(px, pz, ax, az, bx, bz):
    abx = bx - ax
    abz = bz - az
    apx = px - ax
    apz = pz - az

    ab_len_sq = abx * abx + abz * abz
    if ab_len_sq == 0:
        return math.hypot(apx, apz)

    # NOTE: no clamping → ends fade naturally
    t = (apx * abx + apz * abz) / ab_len_sq
    cx = ax + t * abx
    cz = az + t * abz

    return math.hypot(px - cx, pz - cz)

def influence(dist, radius):
    if dist >= radius:
        return 0.0
    x = 1.0 - (dist / radius)
    return x * x

def generate_line_coords(start, end, count, radius, seed=None, y_range=(-600, 600),
                         clumps=(), voids=()):
    # Match the reference TerrainHandling.generateLineCoords placement so the
    # editor preview uses the same asteroid/nebula dot distribution as runtime.
    rng = random.Random(seed)
    coords = []

    dx = end[0] - start[0]
    dz = end[2] - start[2]
    length = math.hypot(dx, dz)

    if length == 0:
        return []

    for _ in range(count):
        # Position uniformly along the terrain spine.
        t = rng.random()
        cx = start[0] + t * dx
        cz = start[2] + t * dz

        # Scatter with the same Gaussian-style radial falloff as the reference.
        u = max(1e-6, rng.random())
        d = radius * math.sqrt(-math.log(u))

        angle = rng.uniform(0, 2 * math.pi)
        ox = math.cos(angle) * d
        oz = math.sin(angle) * d

        x = cx + ox
        z = cz + oz
        y = rng.uniform(*y_range)

        density_bias = 0.0

        for cx_, cz_, r, s in clumps:
            dist = math.hypot(x - cx_, z - cz_)
            if dist < r:
                density_bias += (1 - dist / r) ** 2 * s

        for vx_, vz_, r, s in voids:
            dist = math.hypot(x - vx_, z - vz_)
            if dist < r:
                density_bias -= (1 - dist / r) ** 2 * s

        if density_bias != 0:
            push = density_bias * radius * 0.15
            x += rng.uniform(-push, push)
            z += rng.uniform(-push, push)

        coords.append((x, y, z))

    return coords

def distance_sq_2d(ax, az, bx, bz):
    dx = ax - bx
    dz = az - bz
    return dx * dx + dz * dz

def percentile_value(values, percentile):
    if not values:
        return 0.0
    pct = max(0.0, min(100.0, float(percentile)))
    ordered = sorted(float(v) for v in values)
    if len(ordered) == 1:
        return ordered[0]
    index = int((len(ordered) - 1) * (pct / 100.0))
    index = max(0, min(len(ordered) - 1, index))
    return ordered[index]

def jittered_fcs_spacing(candidate, base_spacing, jitter_ratio=DEFAULT_FCS_SPACING_JITTER):
    """
    Return a deterministic spacing value for a candidate so repeated runs stay stable.
    """
    base_spacing = max(1.0, float(base_spacing))
    jitter_ratio = max(0.0, float(jitter_ratio))
    key = f"{candidate['source']}|{float(candidate['x']):.3f}|{float(candidate['z']):.3f}"
    rng = random.Random(key)
    factor = 1.0 + rng.uniform(-jitter_ratio, jitter_ratio)
    return base_spacing * max(0.01, factor)

def collect_nebula_points_for_fcs(terrain_data, cache=None):
    nebula_points = []
    if not isinstance(terrain_data, dict):
        return nebula_points

    cache_dict = cache if isinstance(cache, dict) else None

    for key, feat in terrain_data.items():
        if not isinstance(feat, dict):
            continue
        if str(feat.get("type", "")).strip().lower() != "nebulas":
            continue

        start = feat.get("start", [0, 0, 0])
        end = feat.get("end", [0, 0, 0])
        density = int(feat.get("density", 0) or 0)
        scatter = float(feat.get("scatter", 0) or 0)
        seed = feat.get("seed")
        hide_on_map = bool(feat.get("hideonmap", False))

        if density <= 0 or scatter <= 0:
            continue
        if not (isinstance(start, (list, tuple)) and isinstance(end, (list, tuple))):
            continue
        if len(start) < 3 or len(end) < 3:
            continue

        cache_key = (
            "nebulas",
            tuple(start),
            tuple(end),
            float(scatter),
            int(density),
            seed,
        )
        cache_token = (key, cache_key)
        coords = cache_dict.get(cache_token) if cache_dict is not None else None
        if coords is None:
            coords = generate_line_coords(start, end, density, scatter, seed=seed)
            if cache_dict is not None:
                cache_dict[cache_token] = coords

        for gx, _, gz in coords:
            nebula_points.append((float(gx), float(gz), key, hide_on_map))

    return nebula_points

def collect_fcs_blocked_centers(system_data, replace_existing=False):
    blocked = []
    if not isinstance(system_data, dict):
        return blocked

    if replace_existing:
        return blocked

    objects = system_data.get("objects", {})
    if isinstance(objects, dict):
        for obj in objects.values():
            if not isinstance(obj, dict):
                continue
            if str(obj.get("type", "")).strip().lower() != FCS_ZONE_TYPE:
                continue
            coord = obj.get("coordinate")
            if isinstance(coord, (list, tuple)) and len(coord) >= 3:
                blocked.append((float(coord[0]), float(coord[2])))

    terrain_data = system_data.get("terrain", {})
    if isinstance(terrain_data, dict):
        for feat in terrain_data.values():
            if not isinstance(feat, dict):
                continue
            if str(feat.get("type", "")).strip().lower() != FCS_ZONE_TYPE:
                continue
            coord = feat.get("coordinate")
            if isinstance(coord, (list, tuple)) and len(coord) >= 3:
                blocked.append((float(coord[0]), float(coord[2])))

    return blocked

def generate_zone_name(existing_objects, zone_type=FCS_ZONE_TYPE):
    prefix = "ZONE"
    zone_key = str(zone_type or "").strip().lower()
    if zone_key == FCS_ZONE_TYPE:
        prefix = "FCS"
    elif zone_key.endswith("_zone"):
        candidate_prefix = zone_key[:-5].replace("_", "").upper()
        if candidate_prefix:
            prefix = candidate_prefix

    if isinstance(existing_objects, dict):
        existing_names = {str(name) for name in existing_objects.keys()}
    else:
        existing_names = {str(name) for name in (existing_objects or [])}

    pattern = re.compile(rf'^{re.escape(prefix)}\s*(\d+)$', re.IGNORECASE)
    used_numbers = []
    for name in existing_names:
        match = pattern.match(name.strip())
        if not match:
            continue
        try:
            used_numbers.append(int(match.group(1)))
        except ValueError:
            continue

    next_value = (max(used_numbers) + 1) if used_numbers else 1
    candidate = f"{prefix}{next_value}"
    while candidate in existing_names:
        next_value += 1
        candidate = f"{prefix}{next_value}"
    return candidate

def select_fcs_zone_centers(points, min_spacing=DEFAULT_FCS_MIN_SPACING,
                            density_radius=DEFAULT_FCS_DENSITY_RADIUS,
                            percentile=DEFAULT_FCS_DENSITY_PERCENTILE,
                            min_score=DEFAULT_FCS_MIN_SCORE,
                            blocked_centers=()):
    """
    Pick zone centers from nebula dots using local point density.

    Points are scored by nearby dot concentration, then greedily selected with a
    minimum center-to-center spacing so zones track dense clusters without
    piling into the same pocket.
    """
    if not points:
        return []

    min_spacing = max(1.0, float(min_spacing))
    density_radius = max(1.0, float(density_radius))
    cell_size = density_radius
    radius_sq = density_radius * density_radius
    min_spacing_sq = min_spacing * min_spacing

    grid = {}
    for idx, (x, z, source_key, source_hidden) in enumerate(points):
        cell_key = (int(math.floor(x / cell_size)), int(math.floor(z / cell_size)))
        grid.setdefault(cell_key, []).append(idx)

    candidates = []
    raw_scores = []

    for idx, (x, z, source_key, source_hidden) in enumerate(points):
        gx = int(math.floor(x / cell_size))
        gz = int(math.floor(z / cell_size))
        score = 0.0
        weighted_x = 0.0
        weighted_z = 0.0

        for dx in (-1, 0, 1):
            for dz in (-1, 0, 1):
                for other_idx in grid.get((gx + dx, gz + dz), []):
                    ox, oz, _, _ = points[other_idx]
                    dist_sq = distance_sq_2d(x, z, ox, oz)
                    if dist_sq > radius_sq:
                        continue
                    weight = 1.0 - (dist_sq / radius_sq)
                    score += weight
                    weighted_x += ox * weight
                    weighted_z += oz * weight

        if score <= 0:
            continue

        raw_scores.append(score)
        candidates.append({
            "score": float(score),
            "x": float(weighted_x / score),
            "z": float(weighted_z / score),
            "source": source_key,
            "hideonmap": bool(source_hidden),
        })

    if not candidates:
        return []

    threshold = max(float(min_score), percentile_value(raw_scores, percentile))
    blocked = [
        {"x": float(x), "z": float(z), "spacing": float(min_spacing)}
        for x, z in blocked_centers
    ]
    selected = []
    selected_signatures = set()

    def _candidate_signature(candidate):
        return (
            candidate["source"],
            round(float(candidate["x"]), 6),
            round(float(candidate["z"]), 6),
        )

    def _try_select_candidate(candidate):
        cx = float(candidate["x"])
        cz = float(candidate["z"])
        candidate_spacing = jittered_fcs_spacing(candidate, min_spacing)
        for blocked_item in blocked:
            bx = float(blocked_item["x"])
            bz = float(blocked_item["z"])
            blocked_spacing = float(blocked_item.get("spacing", min_spacing))
            required_spacing = (candidate_spacing + blocked_spacing) / 2.0
            if distance_sq_2d(cx, cz, bx, bz) < required_spacing * required_spacing:
                return False
        selected.append({
            "x": cx,
            "z": cz,
            "score": float(candidate["score"]),
            "source": candidate["source"],
            "hideonmap": bool(candidate["hideonmap"]),
        })
        blocked.append({
            "x": cx,
            "z": cz,
            "spacing": candidate_spacing,
        })
        selected_signatures.add(_candidate_signature(candidate))
        return True

    candidates_by_source = {}
    for candidate in candidates:
        candidates_by_source.setdefault(candidate["source"], []).append(candidate)

    # Pass 1: try to guarantee one zone per nebula field, unless spacing blocks it.
    source_priority = sorted(
        (
            max(source_candidates, key=lambda item: item["score"])
            for source_candidates in candidates_by_source.values()
        ),
        key=lambda item: item["score"],
        reverse=True,
    )

    for source_head in source_priority:
        source_candidates = sorted(
            candidates_by_source.get(source_head["source"], []),
            key=lambda item: item["score"],
            reverse=True,
        )
        for candidate in source_candidates:
            if _try_select_candidate(candidate):
                break

    # Pass 2: add extra zones only for stronger dense pockets.
    for candidate in sorted(candidates, key=lambda item: item["score"], reverse=True):
        if candidate["score"] < threshold:
            break
        if _candidate_signature(candidate) in selected_signatures:
            continue
        _try_select_candidate(candidate)

    return selected
