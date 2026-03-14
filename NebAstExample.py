def distance_to_spine(px, pz, ax, az, bx, bz):
    abx = bx - ax
    abz = bz - az
    apx = px - ax
    apz = pz - az

    ab_len_sq = abx*abx + abz*abz
    if ab_len_sq == 0:
        return math.hypot(apx, apz)

    # NOTE: no clamping → ends fade naturally
    t = (apx*abx + apz*abz) / ab_len_sq
    cx = ax + t * abx
    cz = az + t * abz

    return math.hypot(px - cx, pz - cz)


def influence(dist, radius):
    if dist >= radius:
        return 0.0
    x = 1.0 - (dist / radius)
    return x * x
def generateLineCoords(start, end, count, radius, seed=None, y_range=(-600, 600), clump_count=10, void_count=6, clump_radius_range=(300, 800), void_radius_range=(400, 900), clump_strength_range=(0.3, 0.9), void_strength_range=(0.4, 1.0)):
    rng = random.Random(seed)
    coords = []
        # --- Bounding volume (intentionally oversized) ---
    min_x = min(start[0], end[0]) - radius * 2.0
    max_x = max(start[0], end[0]) + radius * 2.0
    min_z = min(start[2], end[2]) - radius * 2.0
    max_z = max(start[2], end[2]) + radius * 2.0

    # --- Pre-generate clumps & voids ---
    clumps = []
    voids = []

    for _ in range(clump_count):
        t = rng.random()
        x = start[0] + t * (end[0] - start[0]) + rng.uniform(-radius, radius)
        z = start[2] + t * (end[2] - start[2]) + rng.uniform(-radius, radius)
        r = rng.uniform(*clump_radius_range)
        s = rng.uniform(*clump_strength_range)
        clumps.append((x, z, r, s))

    for _ in range(void_count):
        t = rng.random()
        x = start[0] + t * (end[0] - start[0]) + rng.uniform(-radius, radius)
        z = start[2] + t * (end[2] - start[2]) + rng.uniform(-radius, radius)
        r = rng.uniform(*void_radius_range)
        s = rng.uniform(*void_strength_range)
        voids.append((x, z, r, s))

    attempts = 0
    max_attempts = count * 8

    while len(coords) < count and attempts < max_attempts:
        attempts += 1

        x = rng.uniform(min_x, max_x)
        z = rng.uniform(min_z, max_z)
        y = rng.uniform(*y_range)

        # --- Base density from distance to spine ---
        d = distance_to_spine(
            x, z,
            start[0], start[2],
            end[0], end[2]
        )

        t = d / radius
        density = math.exp(-t * t)

        if density < 0.01:
            continue

        # --- Clumps ---
        for cx, cz, r, s in clumps:
            density += influence(math.hypot(x - cx, z - cz), r) * s

        # --- Voids ---
        for vx, vz, r, s in voids:
            density -= influence(math.hypot(x - vx, z - vz), r) * s

        density = max(0.0, min(density, 1.0))

        if rng.random() < density:
            coords.append((x, y, z))

    return coords