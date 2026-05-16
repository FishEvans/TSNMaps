import json
import os
import sys
from pathlib import Path
from urllib.parse import quote


VIEWPORT_WIDTH = 1600
VIEWPORT_HEIGHT = 800
SCALE_MODIFIER = 6.0
MAP_INFO_FILENAME = "GalMapInfo.json"
HTML_OUTPUT_NAME = "index.html"
JUMP_TYPES = {"jump_point", "jumppoint", "jumpnode"}
DEFAULT_MAP_INFO = {"borders": [], "texts": []}


def get_base_path():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


BASE = Path(get_base_path())
HTML_OUTPUT = BASE / "HTML" / HTML_OUTPUT_NAME
JSON_FOLDER = BASE / "data/missions/Map Designer/Terrain"


def load_map_info(warnings):
    map_info_file = Path(os.getcwd()) / MAP_INFO_FILENAME
    if not map_info_file.exists():
        return DEFAULT_MAP_INFO

    try:
        return json.loads(map_info_file.read_text())
    except json.JSONDecodeError:
        warnings.append(f"Could not parse {MAP_INFO_FILENAME}, skipping overlays.")
        return DEFAULT_MAP_INFO


def load_systems(json_folder, warnings):
    system_names = set()
    raw_systems = []
    system_meta = {}

    for json_file in json_folder.glob("*.json"):
        if json_file.name.lower() == "package.json":
            continue

        try:
            with open(json_file, "r") as handle:
                data = json.load(handle)
        except json.JSONDecodeError:
            warnings.append(f"Could not parse {json_file.name}, skipping.")
            continue

        if "systemMapCoord" not in data:
            continue

        name = json_file.stem
        meta = data.get("metadata", {})
        visible = meta.get("visible", True)
        alignment = data.get("alignment") or data.get("systemalignment") or "Unknown"

        system_names.add(name)
        system_meta[name] = {
            "visible": visible,
            "alignment": alignment,
            "development": meta.get("development", ""),
            "focus": meta.get("focus", ""),
            "exports": ", ".join(meta.get("exports", [])) or "None",
            "intel": meta.get("intel", {}),
            "description": meta.get("sysdescription", ""),
        }

        destinations = []
        for obj in data.get("objects", {}).values():
            if obj.get("type", "").lower() not in JUMP_TYPES:
                continue
            for target in obj.get("destinations", {}).values():
                destinations.append(
                    {
                        "target": target,
                        "hidden": obj.get("hideonmap", False),
                    }
                )

        raw_systems.append(
            {
                "name": name,
                "alignment": alignment,
                "coord": data["systemMapCoord"],
                "destinations": destinations,
            }
        )

    systems = []
    for system in raw_systems:
        filtered_destinations = [
            destination
            for destination in system["destinations"]
            if destination["target"] in system_names
        ]
        missing_targets = sorted(
            {
                destination["target"]
                for destination in system["destinations"]
                if destination["target"] not in system_names
            }
        )
        if missing_targets:
            warnings.append(
                f"{system['name']} has unknown jump targets: {', '.join(missing_targets)}"
            )
        systems.append(
            {
                "name": system["name"],
                "alignment": system["alignment"],
                "coord": system["coord"],
                "destinations": filtered_destinations,
            }
        )

    return systems, system_meta


def compute_world_bounds(systems, map_info):
    xs = [system["coord"][0] for system in systems]
    ys = [system["coord"][2] for system in systems]

    for border in map_info.get("borders", []):
        for point in border.get("points", []):
            if len(point) >= 2:
                xs.append(point[0])
                ys.append(point[1])

    min_x = min(xs) if xs else 0
    max_x = max(xs) if xs else 0
    min_y = min(ys) if ys else 0
    max_y = max(ys) if ys else 0

    return {
        "min_x": min_x,
        "max_x": max_x,
        "min_y": min_y,
        "max_y": max_y,
        "spread_x": max(max_x - min_x, 1),
        "spread_y": max(max_y - min_y, 1),
    }


def compute_layout(bounds):
    scale = (VIEWPORT_WIDTH / max(bounds["spread_x"], 1)) * SCALE_MODIFIER
    map_width = bounds["spread_x"] * scale
    map_height = bounds["spread_y"] * scale
    offset_x = -bounds["min_x"] * scale
    offset_y = -bounds["min_y"] * scale

    margin_px = 400 * scale
    pan_x_min = VIEWPORT_WIDTH - map_width - margin_px
    pan_x_max = margin_px
    pan_y_min = VIEWPORT_HEIGHT - map_height - margin_px
    pan_y_max = margin_px

    return {
        "scale": scale,
        "map_width": map_width,
        "map_height": map_height,
        "offset_x": offset_x,
        "offset_y": offset_y,
        "pan_x_min": pan_x_min,
        "pan_x_max": pan_x_max,
        "pan_y_min": pan_y_min,
        "pan_y_max": pan_y_max,
        "center_py_pixel": map_height / 2,
    }


def build_coords(systems, layout):
    coords = {}
    for system in systems:
        px = system["coord"][0] * layout["scale"] + layout["offset_x"]
        py = system["coord"][2] * layout["scale"] + layout["offset_y"]
        coords[system["name"]] = {"x": px, "y": py}
    return coords


def build_system_divs(systems, system_meta, coords):
    system_divs = []
    for system in systems:
        px = coords[system["name"]]["x"]
        py = coords[system["name"]]["y"]
        visible = system_meta[system["name"]]["visible"]
        system_class = "system" + ("" if visible else " hidden-system")
        style_attr = f"left:{px}px; top:{py}px;{'display:none;' if not visible else ''}"
        system_divs.append(
            f'<a href="{quote(system["name"])}.html" class="{system_class}" '
            f'data-system="{system["name"]}" style="{style_attr}">'
            f'<div class="icon">'
            f'<img src="Images/Factions/{system["alignment"]}.png" class="alignment-img" />'
            f'<img src="Images/ring.png" class="tint-img" />'
            f"</div>"
            f'<div class="system-name">{system["name"]}</div></a>'
        )
    return system_divs


def build_directed_jumps(systems, coords):
    directed_jumps = {}
    for system in systems:
        for destination in system.get("destinations", []):
            target = destination.get("target")
            if target not in coords:
                continue
            directed_jumps.setdefault((system["name"], target), []).append(destination)
    return directed_jumps


def build_one_way_jump_svg(src_name, tgt_name, hidden_jump, coords):
    src_class = src_name.replace(" ", "-")
    px = coords[src_name]["x"]
    py = coords[src_name]["y"]
    tx = coords[tgt_name]["x"]
    ty = coords[tgt_name]["y"]
    line_style = ' style="display:none;"' if hidden_jump else ""
    line_class = " hidden-jump" if hidden_jump else ""
    dx = tx - px
    dy = ty - py
    arrow_x = px + dx * (2 / 3)
    arrow_y = py + dy * (2 / 3)

    return [
        f'<line x1="{px}" y1="{py}" x2="{tx}" y2="{ty}" '
        f'stroke="#666666" stroke-width="9" opacity="0.6" '
        f'class="jump-base jump-from-{src_class}{line_class}"{line_style} />',
        f'<line x1="{px}" y1="{py}" x2="{arrow_x}" y2="{arrow_y}" '
        f'stroke="#50CC50" stroke-width="12" marker-end="url(#arrow)" '
        f'class="jump-line jump-from-{src_class}{line_class}"{line_style} />',
    ]


def build_jump_lines(systems, system_meta, coords):
    svg_lines = []
    directed_jumps = build_directed_jumps(systems, coords)
    processed_pairs = set()

    for src_name, tgt_name in directed_jumps:
        pair_key = tuple(sorted((src_name, tgt_name)))
        if pair_key in processed_pairs:
            continue
        processed_pairs.add(pair_key)

        a_name, b_name = pair_key
        a_to_b_entries = directed_jumps.get((a_name, b_name), [])
        b_to_a_entries = directed_jumps.get((b_name, a_name), [])
        pair_public = (
            system_meta.get(a_name, {}).get("visible", True)
            and system_meta.get(b_name, {}).get("visible", True)
        )
        a_to_b_public = pair_public and any(
            not entry.get("hidden", False) for entry in a_to_b_entries
        )
        b_to_a_public = pair_public and any(
            not entry.get("hidden", False) for entry in b_to_a_entries
        )
        a_to_b_hidden = any(entry.get("hidden", False) for entry in a_to_b_entries) or not pair_public
        b_to_a_hidden = any(entry.get("hidden", False) for entry in b_to_a_entries) or not pair_public

        ax = coords[a_name]["x"]
        ay = coords[a_name]["y"]
        bx = coords[b_name]["x"]
        by = coords[b_name]["y"]
        a_class = a_name.replace(" ", "-")
        b_class = b_name.replace(" ", "-")

        if a_to_b_public and b_to_a_public:
            svg_lines.append(
                f'<line x1="{ax}" y1="{ay}" x2="{bx}" y2="{by}" '
                f'stroke="#50CC50" stroke-width="12" '
                f'class="jump-line jump-from-{a_class} jump-from-{b_class}" />'
            )
            continue

        if a_to_b_public:
            svg_lines.extend(build_one_way_jump_svg(a_name, b_name, False, coords))
        elif a_to_b_hidden:
            svg_lines.extend(build_one_way_jump_svg(a_name, b_name, True, coords))

        if b_to_a_public:
            svg_lines.extend(build_one_way_jump_svg(b_name, a_name, False, coords))
        elif b_to_a_hidden:
            svg_lines.extend(build_one_way_jump_svg(b_name, a_name, True, coords))

    return svg_lines


def build_overlay_lines(map_info, layout):
    overlay_lines = []
    scale = layout["scale"]
    offset_x = layout["offset_x"]
    offset_y = layout["offset_y"]

    for border in map_info.get("borders", []):
        points = " ".join(
            f"{x * scale + offset_x},{y * scale + offset_y}"
            for x, y in border.get("points", [])
        )
        overlay_lines.append(
            f'<polyline points="{points}" stroke="{border.get("color", "white")}" '
            f'stroke-width="{border.get("width", 16)}" fill="none">'
            f'<title>{border.get("hover_text", "")}</title></polyline>'
        )

    for text in map_info.get("texts", []):
        position = text.get("position", [])
        if len(position) < 2:
            continue
        cy = position[2] if len(position) > 2 else position[1]
        tx = position[0] * scale + offset_x
        ty = cy * scale + offset_y
        size = text.get("size", 12)
        tspans = "".join(
            f'<tspan x="{tx}" dy="{(1.2 if index else 0)}em">{line}</tspan>'
            for index, line in enumerate(text.get("lines", []))
        )
        overlay_lines.append(
            f'<text data-base-size="{size}" x="{tx}" y="{ty}" '
            f'fill="{text.get("color", "white")}" font-size="{size}">{tspans}</text>'
        )

    return overlay_lines


def build_system_list_html(systems, system_meta):
    return "".join(
        f"<button class='system-button' type='button' data-system=\"{system['name']}\" "
        f"data-target-url=\"{quote(system['name'])}.html\" "
        f"data-visible=\"{'true' if system_meta[system['name']]['visible'] else 'false'}\" "
        f"style=\"{'display:none;' if not system_meta[system['name']]['visible'] else ''}\">"
        f"<img src=\"Images/Factions/{system_meta[system['name']]['alignment']}.png\" "
        f"class=\"button-icon\" alt=\"{system_meta[system['name']]['alignment']}\" />"
        f"{system['name']}</button>"
        for system in sorted(systems, key=lambda item: item["name"])
    )


def build_styles(layout):
    return f"""
    * {{ box-sizing: border-box; }}
    body {{ margin:0; background:black; color:white; display:flex; min-height:100dvh; height:100dvh; overflow:hidden; }}
    #controls {{ width:220px; min-width:220px; background:#333; padding:10px; overflow-y:auto; }}
    .system-button {{ width:100%; min-height:42px; padding:6px 10px; font-size:14pt; background:rgba(54,54,54,0.94); color:white; border:1px solid rgba(255,255,255,0.12); border-radius:999px; margin-bottom:5px; cursor:pointer; text-align:left; display:flex; align-items:center; box-shadow:inset 0 0 0 1px rgba(255,255,255,0.03); transition:transform 0.18s ease, border-color 0.18s ease, box-shadow 0.18s ease, filter 0.18s ease; }}
    .system-button:hover,
    .system-button:focus-visible {{ transform:translateY(-1px); filter:brightness(1.06); outline:none; }}
    .system-button .button-icon {{ height:1em; width:auto; margin-right:0.5em; }}
    #system-search {{ font-size:16px; }}
    #sort-options {{ display:flex; flex-wrap:wrap; gap:8px; }}
    #maparea {{ flex:1; position:relative; background:url("Images/starfield.jpg") center/cover; overflow:hidden; cursor: grab; touch-action:none; }}
    #map {{ width: {layout["map_width"]}px; height: {layout["map_height"]}px; transform-origin: top left; cursor: grab; }}
    .map-container {{ position:absolute; top:0; left:0; }}
    #mobile-toolbar {{
      display:none;
      position:absolute;
      top:12px;
      left:12px;
      right:12px;
      z-index:5;
      gap:8px;
      pointer-events:none;
    }}
    .mobile-toggle {{
      flex:1;
      min-height:42px;
      border:1px solid rgba(255,255,255,0.18);
      background:rgba(24,24,24,0.88);
      color:white;
      font-size:11pt;
      pointer-events:auto;
    }}
    svg {{ position:absolute; top:0; left:0; z-index:0; pointer-events:auto; }}
    svg polyline {{ pointer-events: stroke; }}
    .system {{ position:absolute; width:75px; transform:translate(-50%,-50%); z-index:1; cursor:pointer; text-align:center; }}
    .icon {{ position:relative; width:75px; height:75px; margin:0 auto; }}
    .alignment-img {{ position:absolute; top:15px; left:15px; width:40px; height:40px; }}
    .tint-img {{ position:absolute; top:0; left:0; width:70px; height:70px; opacity:0.3; }}
    .system-name {{
      position: absolute;
      left: 50%;
      text-align: center;
      top: calc(100% + 4px);
      transform: translateX(-50%);
      white-space: normal;
      font-size: 90px;
      font-weight: bold;
      color: white;
      text-decoration: none;
      pointer-events: none;
    }}
    @keyframes jumpPulse {{
      0%   {{ stroke: #50CC50; stroke-width: 12; }}
      100% {{ stroke: #c8facc; stroke-width: 18; }}
    }}
    .jump-line {{ stroke: #50CC50; }}
    .jump-arrow-active {{
      animation: jumpPulse 1s infinite alternate ease-in-out !important;
      pointer-events: none !important;
    }}
    #info {{
      width: 300px;
      min-width: 280px;
      background: #333;
      padding: 10px;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
       align-items: stretch;
       justify-content: flex-start;
       gap: 10px;
    }}
    .page-nav-stack {{
      display: grid;
      gap: 8px;
      width: 100%;
    }}
    .page-nav-link {{
      width: 100%;
      min-height: 44px;
      padding: 12px 18px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      border: 1px solid rgba(255,255,255,0.12);
      border-radius: 999px;
      color: #f1f5fb;
      background: rgba(54,54,54,0.94);
      box-shadow: inset 0 0 0 1px rgba(255,255,255,0.03);
      cursor: pointer;
      text-decoration: none;
      text-align: center;
      font-family: "Consolas", "Lucida Console", monospace;
      font-size: 0.82rem;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      transition: transform 0.18s ease, border-color 0.18s ease, box-shadow 0.18s ease, filter 0.18s ease;
    }}
    .page-nav-link:hover,
    .page-nav-link:focus-visible {{
      transform: translateY(-1px);
      filter: brightness(1.06);
      outline: none;
    }}
    .page-nav-link.page-nav-map {{
      border-color: rgba(255,255,255,0.18);
      background: linear-gradient(180deg, rgba(77,77,77,0.96), rgba(54,54,54,0.96));
      box-shadow: inset 0 0 0 1px rgba(255,255,255,0.04), 0 8px 18px rgba(0,0,0,0.24);
    }}
    .page-nav-link.page-nav-library {{
      border-color: rgba(125,183,255,0.45);
      background: linear-gradient(180deg, rgba(27,51,84,0.96), rgba(18,35,58,0.96));
      box-shadow: inset 0 0 0 1px rgba(255,255,255,0.04), 0 8px 18px rgba(6,14,28,0.28);
    }}
    .page-nav-link.page-nav-production {{
      border-color: rgba(147,255,215,0.3);
      background: linear-gradient(180deg, rgba(18,46,39,0.96), rgba(12,29,25,0.96));
      box-shadow: inset 0 0 0 1px rgba(255,255,255,0.04), 0 8px 18px rgba(0,0,0,0.28);
    }}
    #info img {{
      align-self: center;
      max-width: 80%;
      height: auto;
    }}
    #system-details {{ text-align: left; width:100%; }}
    .system-link-button {{
      display: none;
      margin: 0;
    }}
    .system-link-button.is-disabled {{
      opacity:0.45;
      pointer-events:none;
    }}
    @media (max-width: 960px) {{
      body {{ display:block; position:relative; }}
      #mobile-toolbar {{ display:flex; z-index:6; }}
      #controls {{
        position:fixed;
        inset:0 auto 0 0;
        width:100vw;
        height:100dvh;
        min-height:100dvh;
        z-index:4;
        padding: max(env(safe-area-inset-top, 0px), 10px) 10px max(env(safe-area-inset-bottom, 0px), 10px);
        border:1px solid rgba(255,255,255,0.12);
        box-shadow:0 18px 40px rgba(0,0,0,0.42);
        transition:transform 0.2s ease, opacity 0.2s ease;
        overscroll-behavior:contain;
      }}
      #maparea {{
        position:fixed;
        inset:0;
        min-height:100dvh;
      }}
      #info {{
        position:fixed;
        inset:0 0 0 auto;
        width:100vw;
        height:100dvh;
        min-height:100dvh;
        z-index:4;
        padding: max(env(safe-area-inset-top, 0px), 10px) 10px max(env(safe-area-inset-bottom, 0px), 10px);
        border:1px solid rgba(255,255,255,0.12);
        box-shadow:0 18px 40px rgba(0,0,0,0.42);
        transition:transform 0.2s ease, opacity 0.2s ease;
        overscroll-behavior:contain;
      }}
      #controls.mobile-collapsed {{
        transform:translateX(-100%);
        opacity:0;
        pointer-events:none;
      }}
      #info.mobile-collapsed {{
        transform:translateX(100%);
        opacity:0;
        pointer-events:none;
      }}
      .system-link-button {{ display: inline-flex; }}
      .system-button {{ font-size: 11pt; }}
      .system-name {{ font-size: 64px; }}
    }}
    @media (max-width: 640px) {{
      #mobile-toolbar {{ top:8px; left:8px; right:8px; }}
      #controls {{ width:100vw; height:100dvh; padding: max(env(safe-area-inset-top, 0px), 8px) 8px max(env(safe-area-inset-bottom, 0px), 8px); }}
      #info {{ width:100vw; height:100dvh; padding: max(env(safe-area-inset-top, 0px), 8px) 8px max(env(safe-area-inset-bottom, 0px), 8px); }}
      .system-button {{ min-height: 40px; font-size: 10pt; }}
      .system {{ width:60px; }}
      .icon {{ width:60px; height:60px; margin:0 auto; }}
      .alignment-img {{ top:12px; left:12px; width:34px; height:34px; }}
      .tint-img {{ width:58px; height:58px; }}
      .system-name {{ font-size: 52px; }}
      #info img {{ max-width: 56%; }}
    }}
    """


def build_script(layout, system_meta, coords):
    meta_json = json.dumps(system_meta)
    coords_json = json.dumps(coords)
    return f"""
    function enterGMMode() {{
      document.cookie = "gmMode=1; path=/; max-age=31536000";
    }}
    function isGM() {{
      return document.cookie
        .split(';')
        .some(c => c.trim() === 'gmMode=1');
    }}
    function exitGMMode() {{
      document.cookie = "gmMode=; path=/; expires=Thu, 01 Jan 1970 00:00:00 UTC;";
    }}

    function applyGMVisibility() {{
      const showHidden = isGM();
      document.querySelectorAll('.hidden-system').forEach(el => el.style.display = showHidden ? '' : 'none');
      document.querySelectorAll('.hidden-jump').forEach(el => el.style.display = showHidden ? '' : 'none');
      document.querySelectorAll('.system-button[data-visible="false"]').forEach(btn => btn.style.display = showHidden ? '' : 'none');
    }}

    function isMobileLayout() {{
      return window.matchMedia('(max-width: 960px)').matches;
    }}

    function syncMobileDrawerState() {{
      const systemsOpen = activeMobileDrawer === 'systems';
      const infoOpen = activeMobileDrawer === 'info';
      if (!isMobileLayout()) {{
        controls.classList.remove('mobile-collapsed');
        infoPanel.classList.remove('mobile-collapsed');
      }} else {{
        controls.classList.toggle('mobile-collapsed', !systemsOpen);
        infoPanel.classList.toggle('mobile-collapsed', !infoOpen);
      }}
      if (systemsToggleBtn) {{
        systemsToggleBtn.setAttribute('aria-expanded', systemsOpen ? 'true' : 'false');
      }}
      if (infoToggleBtn) {{
        infoToggleBtn.setAttribute('aria-expanded', infoOpen ? 'true' : 'false');
      }}
    }}

    function setActiveMobileDrawer(drawerName) {{
      if (!isMobileLayout()) return;
      activeMobileDrawer = drawerName;
      syncMobileDrawerState();
    }}

    function toggleMobileDrawer(drawerName) {{
      if (!isMobileLayout()) return;
      activeMobileDrawer = activeMobileDrawer === drawerName ? null : drawerName;
      syncMobileDrawerState();
    }}

    function setSelectedSystemLink(name) {{
      if (!selectedSystemLink) return;
      if (!name) {{
        selectedSystemLink.href = '#';
        selectedSystemLink.classList.add('is-disabled');
        selectedSystemLink.textContent = 'Open Selected System';
        return;
      }}
      selectedSystemLink.href = `${{encodeURIComponent(name)}}.html`;
      selectedSystemLink.classList.remove('is-disabled');
      selectedSystemLink.textContent = `Open ${{name}}`;
    }}

    const controls = document.getElementById('controls');
    const infoPanel = document.getElementById('info');
    const systemsToggleBtn = document.getElementById('mobile-systems-toggle');
    const infoToggleBtn = document.getElementById('mobile-info-toggle');
    const selectedSystemLink = document.getElementById('selected-system-link');
    const oniBtn = document.getElementById('oni-login-btn');
    if (oniBtn) {{
      oniBtn.addEventListener('click', toggleOniAuth);
    }}

    applyGMVisibility();

    const map = document.getElementById('map');
    const maparea = document.getElementById('maparea');
    const isCoarsePointer = window.matchMedia('(pointer: coarse)').matches;
    let scale = Math.min(maparea.clientWidth / map.clientWidth, maparea.clientHeight / map.clientHeight);
    let panX = 0;
    let panY = 0;
    const INITIAL_CENTER_PY = {layout["center_py_pixel"]};
    let PANX_MIN = {layout["pan_x_min"]};
    let PANX_MAX = {layout["pan_x_max"]};
    let PANY_MIN = {layout["pan_y_min"]};
    let PANY_MAX = {layout["pan_y_max"]};
    const systemMeta = {meta_json};
    const systemCoords = {coords_json};

    function updatePanBounds() {{
      const mapW = map.clientWidth * scale;
      const mapH = map.clientHeight * scale;
      const margin = 400 * scale;
      PANX_MIN = maparea.clientWidth - mapW - margin;
      PANX_MAX = margin;
      PANY_MIN = maparea.clientHeight - mapH - margin;
      PANY_MAX = margin;
      console.log(`Bounds -> X:[${{PANX_MIN.toFixed(0)}},${{PANX_MAX.toFixed(0)}}] Y:[${{PANY_MIN.toFixed(0)}},${{PANY_MAX.toFixed(0)}}]`);
    }}

    updatePanBounds();
    let isPanning = false;
    let startX = 0;
    let startY = 0;
    let selectedSystem = null;
    let pinchStartDistance = 0;
    let pinchStartScale = scale;
    let activeMobileDrawer = null;

    function applyTransform() {{
      panX = Math.min(PANX_MAX, Math.max(PANX_MIN, panX));
      panY = Math.min(PANY_MAX, Math.max(PANY_MIN, panY));
      map.style.transform = `translate(${{panX}}px,${{panY}}px) scale(${{scale}})`;

      document.querySelectorAll('.system-name').forEach(label => {{
        const minSize = 70;
        const maxSize = 90;
        let newSize = minSize + (scale - 1) * (maxSize - minSize);
        newSize = Math.max(minSize, Math.min(maxSize, newSize));
        label.style.setProperty('font-size', `${{newSize}}px`, 'important');
        const offset = (newSize - minSize) / 2;
        label.style.transform = `translateX(-50%) translateY(-${{offset}}px)`;
      }});

      document.querySelectorAll('.icon').forEach(icon => {{
        const iconGrowFactor = 0.9;
        const iconScale = scale > 1 ? Math.min(scale, 1 + iconGrowFactor) : 1 / scale;
        icon.style.transform = `scale(${{iconScale}})`;
      }});

      document.querySelectorAll('svg text[data-base-size]').forEach(el => {{
        const baseSize = parseFloat(el.getAttribute('data-base-size'));
        const screenSize = Math.max(32, baseSize * scale);
        const attrSize = screenSize / scale;
        el.setAttribute('font-size', attrSize);
      }});
    }}

    function setJumpHighlight(systemName, active) {{
      const sys = systemName.replace(/ /g, '-');
      document.querySelectorAll(`.jump-from-${{sys}}`).forEach(line =>
        line.classList.toggle('jump-arrow-active', active)
      );
    }}

    function showSystemDetails(name) {{
      const m = systemMeta[name] || {{}};
      const intel = m.intel || {{}};
      const pirate = intel.pirate || 'Unknown';
      const enemy = intel.enemy || 'Unknown';
      const assets = Array.isArray(intel.assets) ? intel.assets : [];
      document.getElementById('system-details').innerHTML =
        `<h3>${{name}}</h3>` +
        `<p>Alignment: ${{m.alignment}}</p>` +
        `<p>Development Level: ${{m.development}}</p>` +
        `<p>System Focus: ${{m.focus}}</p>` +
        `<p>Exports: ${{m.exports}}</p>` +
        `<div><strong>Intelligence estimate:</strong></div>` +
        `<div>` +
        `<img src="Images/SysBadges/${{pirate}}Pirate.png" width="50" height="50" alt="${{pirate}} Pirate" /> ` +
        `<img src="Images/SysBadges/${{enemy}}Enemy.png" width="50" height="50" alt="${{enemy}} Enemy" />` +
        `</div>` +
        `<div>Pirate Activity: ${{pirate}}</div>` +
        `<div>Enemy Activity: ${{enemy}}</div>` +
        `<div><strong>Known Important Assets:</strong></div>` +
        `<div class="asset-icons">` +
        `${{assets.map(a => `<img src="Images/SysBadges/${{a}}.png" width="50" height="50" alt="${{a}}" title="${{a}}" />`).join('')}}` +
        `</div>` +
        `<div class="asset-text">` +
        `${{assets.map(a => `<div>${{a}}</div>`).join('')}}` +
        `<p>${{m.description}}</p>`;
    }}

    function selectSystem(name) {{
      if (selectedSystem && selectedSystem !== name) {{
        setJumpHighlight(selectedSystem, false);
      }}
      selectedSystem = name;
      showSystemDetails(name);
      setJumpHighlight(name, true);
      setSelectedSystemLink(name);
      if (isMobileLayout()) {{
        setActiveMobileDrawer('info');
      }}
    }}

    function clearSelectedSystem() {{
      if (!selectedSystem) return;
      setJumpHighlight(selectedSystem, false);
      selectedSystem = null;
      setSelectedSystemLink(null);
    }}

    function centerOnSystem(name) {{
      const coord = systemCoords[name];
      if (!coord) return;
      panX = (maparea.clientWidth / 2) - (coord.x * scale);
      panY = (maparea.clientHeight / 2) - (coord.y * scale);
      applyTransform();
    }}

    function zoomAroundPoint(nextScale, clientX, clientY) {{
      const rect = maparea.getBoundingClientRect();
      const mx = clientX - rect.left;
      const my = clientY - rect.top;
      const prev = scale;
      scale = nextScale;
      const minS = Math.min(maparea.clientWidth / map.clientWidth, maparea.clientHeight / map.clientHeight);
      const maxS = Math.min(maparea.clientWidth / 500, maparea.clientHeight / 500);
      scale = Math.max(minS, Math.min(scale, maxS));
      const factor = scale / prev;
      panX -= (mx - panX) * (factor - 1);
      panY -= (my - panY) * (factor - 1);
      updatePanBounds();
      applyTransform();
    }}

    function getTouchDistance(touchA, touchB) {{
      const dx = touchA.clientX - touchB.clientX;
      const dy = touchA.clientY - touchB.clientY;
      return Math.hypot(dx, dy);
    }}

    function getTouchMidpoint(touchA, touchB) {{
      return {{
        x: (touchA.clientX + touchB.clientX) / 2,
        y: (touchA.clientY + touchB.clientY) / 2,
      }};
    }}

    maparea.addEventListener('mousedown', e => {{
      if (isCoarsePointer) return;
      e.preventDefault();
      isPanning = true;
      startX = e.clientX - panX;
      startY = e.clientY - panY;
      maparea.style.cursor = 'grabbing';
    }});

    document.addEventListener('mouseup', () => {{
      if (!isPanning) return;
      isPanning = false;
      maparea.style.cursor = 'grab';
    }});

    document.addEventListener('mousemove', e => {{
      if (!isPanning) return;
      panX = e.clientX - startX;
      panY = e.clientY - startY;
      applyTransform();
    }});

    maparea.addEventListener('wheel', e => {{
      e.preventDefault();
      const nextScale = scale * (e.deltaY > 0 ? 0.9 : 1.1);
      zoomAroundPoint(nextScale, e.clientX, e.clientY);
    }});

    maparea.addEventListener('touchstart', e => {{
      if (e.touches.length === 1) {{
        isPanning = true;
        startX = e.touches[0].clientX - panX;
        startY = e.touches[0].clientY - panY;
      }} else if (e.touches.length === 2) {{
        isPanning = false;
        pinchStartDistance = getTouchDistance(e.touches[0], e.touches[1]);
        pinchStartScale = scale;
      }}
    }}, {{ passive: false }});

    maparea.addEventListener('touchmove', e => {{
      if (e.touches.length === 1 && isPanning) {{
        e.preventDefault();
        panX = e.touches[0].clientX - startX;
        panY = e.touches[0].clientY - startY;
        applyTransform();
      }} else if (e.touches.length === 2) {{
        e.preventDefault();
        const distance = getTouchDistance(e.touches[0], e.touches[1]);
        if (!pinchStartDistance) {{
          pinchStartDistance = distance;
          pinchStartScale = scale;
          return;
        }}
        const midpoint = getTouchMidpoint(e.touches[0], e.touches[1]);
        const nextScale = pinchStartScale * (distance / pinchStartDistance);
        zoomAroundPoint(nextScale, midpoint.x, midpoint.y);
      }}
    }}, {{ passive: false }});

    maparea.addEventListener('touchend', e => {{
      if (e.touches.length === 0) {{
        isPanning = false;
        pinchStartDistance = 0;
      }} else if (e.touches.length === 1) {{
        isPanning = true;
        startX = e.touches[0].clientX - panX;
        startY = e.touches[0].clientY - panY;
        pinchStartDistance = 0;
      }}
    }}, {{ passive: false }});

    if (systemsToggleBtn) {{
      systemsToggleBtn.addEventListener('click', () => {{
        toggleMobileDrawer('systems');
      }});
    }}

    if (infoToggleBtn) {{
      infoToggleBtn.addEventListener('click', () => {{
        toggleMobileDrawer('info');
      }});
    }}

    document.querySelectorAll('.system-button[data-system]').forEach(btn => {{
      btn.addEventListener('click', () => {{
        const name = btn.getAttribute('data-system');
        const targetUrl = btn.getAttribute('data-target-url');
        if (!name) return;
        if (isMobileLayout()) {{
          selectSystem(name);
          centerOnSystem(name);
          return;
        }}
        if (targetUrl) {{
          document.location.href = targetUrl;
        }}
      }});
    }});

    function resetZoom() {{
      scale = Math.min(maparea.clientWidth / map.clientWidth, maparea.clientHeight / map.clientHeight);
      panX = (maparea.clientWidth - map.clientWidth * scale) / 2;
      panY = (maparea.clientHeight - map.clientHeight * scale) / 2;
      updatePanBounds();
      applyTransform();
    }}

    window.addEventListener('load', resetZoom);
    window.addEventListener('resize', () => {{
      resetZoom();
      syncMobileDrawerState();
    }});
    resetZoom();
    setSelectedSystemLink(null);
    syncMobileDrawerState();

    document.querySelectorAll('.system').forEach(el => {{
      const name = el.getAttribute('data-system');
      el.addEventListener('mouseenter', () => {{
        if (isCoarsePointer) return;
        showSystemDetails(name);
        setJumpHighlight(name, true);
      }});
      el.addEventListener('mouseleave', () => {{
        if (isCoarsePointer || selectedSystem === name) return;
        setJumpHighlight(name, false);
      }});
      el.addEventListener('click', e => {{
        if (!isCoarsePointer) return;
        if (selectedSystem !== name) {{
          e.preventDefault();
          selectSystem(name);
        }}
      }});
    }});

    const searchInput = document.getElementById('system-search');
    if (searchInput) {{
      searchInput.addEventListener('input', () => {{
        const term = searchInput.value.toLowerCase();
        document.querySelectorAll('.system-button[data-system]').forEach(btn => {{
          const nameAttr = btn.getAttribute('data-system');
          if (!nameAttr) return;
          const isVisibleFlag = btn.getAttribute('data-visible') === 'true';
          if (!isGM() && !isVisibleFlag) {{
            btn.style.display = 'none';
            return;
          }}
          const name = nameAttr.toLowerCase();
          btn.style.display = name.includes(term) ? '' : 'none';
        }});
      }});
    }}

    document.querySelectorAll('input[name="sort"]').forEach(radio => {{
      radio.addEventListener('change', reorderButtons);
    }});

    function reorderButtons() {{
      const container = document.getElementById('controls');
      const sortBy = document.querySelector('input[name="sort"]:checked').value;
      let buttons = Array.from(container.querySelectorAll('.system-button[data-system]'));
      if (!isGM()) {{
        buttons = buttons.filter(btn => btn.getAttribute('data-visible') === 'true');
      }}

      buttons.sort((a, b) => {{
        const nameA = a.getAttribute('data-system');
        const nameB = b.getAttribute('data-system');
        if (sortBy === 'name') {{
          return nameA.localeCompare(nameB);
        }}
        const alignA = systemMeta[nameA].alignment || '';
        const alignB = systemMeta[nameB].alignment || '';
        if (alignA !== alignB) {{
          return alignA.localeCompare(alignB);
        }}
        return nameA.localeCompare(nameB);
      }});

      buttons.forEach(btn => container.appendChild(btn));
    }}

    reorderButtons();

    function toggleOniAuth() {{
      if (isGM()) {{
        exitGMMode();
        document.getElementById('oni-login-btn').innerText = 'ONI Login';
        applyGMVisibility();
        return;
      }}

      const pwd = prompt('Enter GM password:');
      if (pwd === 'oni1') {{
        enterGMMode();
        document.getElementById('oni-login-btn').innerText = 'ONI Logout';
        applyGMVisibility();
      }} else {{
        alert('Incorrect password');
      }}
    }}

    window.addEventListener('load', () => {{
      if (isGM()) {{
        document.getElementById('oni-login-btn').innerText = 'ONI Logout';
      }}
      applyGMVisibility();
      syncMobileDrawerState();
    }});
    """


def build_page_html(system_divs, svg_lines, system_list_html, layout, system_meta, coords):
    styles = build_styles(layout)
    script = build_script(layout, system_meta, coords)
    home_button_html = (
        '<button onclick="resetZoom()" class="page-nav-link page-nav-map" type="button">'
        "Galactic Map"
        "</button>"
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1.0">
  <title>System Map</title>
  <style>
{styles}
  </style>
</head>
<body>
  <div id="controls">
    <div id="oni-login-container" style="margin-bottom:10px;">
      <button id="oni-login-btn" class="system-button">
        ONI Login
      </button>
    </div>
    <h2>Systems</h2>
    <input type="text" id="system-search" placeholder="Search systems..." style="width:95%; padding:5px; margin-bottom:5px;" />
    <div id="sort-options" style="margin-bottom:5px;">
      <label><input type="radio" name="sort" value="name" checked /> A-Z</label>
      <label style="margin-left:10px;"><input type="radio" name="sort" value="alignment" /> Alignment</label>
    </div>
    {system_list_html}
  </div>
  <div id="maparea">
    <div id="mobile-toolbar">
      <button id="mobile-systems-toggle" class="system-button mobile-toggle" type="button">Systems</button>
      <button id="mobile-info-toggle" class="system-button mobile-toggle" type="button">Info</button>
    </div>
    <div class="map-container" id="map">
      <svg width="100%" height="100%">
        <defs>
          <marker id="arrow" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="4" markerHeight="4" orient="auto-start-reverse">
            <path d="M0,0 L10,5 L0,10 Z" fill="#50CC50" />
          </marker>
        </defs>
        {''.join(svg_lines)}
      </svg>
      {''.join(system_divs)}
    </div>
  </div>
  <div id="info">
    <div class="page-nav-stack">
      {home_button_html}
      <a id="selected-system-link" class="page-nav-link page-nav-map system-link-button is-disabled" href="#">Open Selected System</a>
      <a href="Library.html" class="page-nav-link page-nav-library">Ship Library</a>
      <a href="ProductionFlow.html" class="page-nav-link page-nav-production">Production Flow</a>
    </div>
    <img src="Images/compass.png" alt="Compass" />
    <div id="system-details">
      <p>Select a system to view metadata.</p>
    </div>
  </div>
  <script>
{script}
  </script>
</body>
</html>"""


def main():
    warnings = []
    systems, system_meta = load_systems(JSON_FOLDER, warnings)
    if not systems:
        print("GalMapGen summary: built 0 galactic map(s), failed 1, warnings 0.")
        print("GalMapGen failed outputs:")
        print("  - index.html: no systems with 'systemMapCoord' found.")
        sys.exit(1)

    map_info = load_map_info(warnings)
    bounds = compute_world_bounds(systems, map_info)
    layout = compute_layout(bounds)
    coords = build_coords(systems, layout)

    if len(coords) != len(systems):
        warnings.append(f"coords ({len(coords)}) != systems ({len(systems)})")

    system_divs = build_system_divs(systems, system_meta, coords)
    jump_lines = build_jump_lines(systems, system_meta, coords)
    overlay_lines = build_overlay_lines(map_info, layout)
    system_list_html = build_system_list_html(systems, system_meta)
    html = build_page_html(
        system_divs=system_divs,
        svg_lines=jump_lines + overlay_lines,
        system_list_html=system_list_html,
        layout=layout,
        system_meta=system_meta,
        coords=coords,
    )

    HTML_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    HTML_OUTPUT.write_text(html, encoding="utf-8")
    print(
        f"GalMapGen summary: built 1 galactic map(s) from {len(systems)} system(s), "
        f"failed 0, warnings {len(warnings)}."
    )
    if warnings:
        print("GalMapGen warnings:")
        for warning in warnings:
            print(f"  - {warning}")


if __name__ == "__main__":
    main()
