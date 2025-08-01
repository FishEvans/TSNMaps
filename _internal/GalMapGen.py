import os
import json
import sys
from pathlib import Path
from urllib.parse import quote

# Helper to locate resources when running as a module or frozen executable
def get_base_path():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

# Base paths
BASE = get_base_path()
default_base = get_base_path()
HTML_OUTPUT = Path(default_base) / "HTML" / "index.html"
JSON_FOLDER = Path(default_base) / "data/missions/Map Designer/Terrain"
# Offsets for map centering (computed later)
OFFSET_X = 0
OFFSET_Y = 0


def main():
    # Load system definitions from JSON files
    system_names = set()
    raw_systems = []
    # collect metadata for each system
    system_meta = {}
    # Scale modifier (tweak this to adjust overall zoom level)
    SCALE_MODIFIER = 6.0
    for json_file in JSON_FOLDER.glob("*.json"):
        if json_file.name.lower() == "package.json":
            continue
        try:
            with open(json_file, 'r') as f:
                data = json.load(f)
        except json.JSONDecodeError:
            print(f"Warning: Could not parse {json_file.name}, skipping.")
            continue
        if "systemMapCoord" not in data:
            continue
        name = json_file.stem
        # read visibility flag from metadata
        meta = data.get("metadata", {})
        # GM visibility flag: include hidden systems but mark them
        visible = meta.get("visible", True)
        system_names.add(name)
        alignment = data.get("alignment") or data.get("systemalignment") or "Unknown"
        # collect metadata
        meta = data.get("metadata", {})
        system_meta[name] = {
            "visible": visible,
            "alignment": alignment,
            "development": meta.get("development", ""),
            "focus": meta.get("focus", ""),
            "exports": ", ".join(meta.get("exports", [])) or "None",
            "intel": meta.get("intel", {}),
            "description": meta.get("sysdescription", "")
        }
        dests = []
        for obj in data.get("objects", {}).values():
        # accept multiple jump‐point type labels
            typ = obj.get("type", "").lower()
            if typ in ("jump_point", "jumppoint", "jumpnode"):
              # skip any jump‐points flagged as hidden in the JSON
                if obj.get("hideonmap", False):
                    continue
                for target in obj.get("destinations", {}).values():
                    dests.append({"target": target})
        raw_systems.append({"name": name, "alignment": alignment, "coord": data["systemMapCoord"], "destinations": dests})

    # Filter valid destinations based on final system_names
    systems = []

    for s in raw_systems:
        filtered_dests = s["destinations"]
       # filtered_dests = [d for d in s["destinations"] if d["target"] in system_names]
        systems.append({"name": s["name"], "alignment": s["alignment"], "coord": s["coord"], "destinations": filtered_dests})

    # If no systems found, exit or define defaults
    if not systems:
        print("No systems with 'systemMapCoord' found. Exiting without generating map.")
        sys.exit(1)

    # Compute map extents safely
    xs = [s["coord"][0] for s in systems]
    ys = [s["coord"][2] for s in systems]
    extent_x = max(abs(min(xs)), abs(max(xs))) if xs else 0
    extent_y = max(abs(min(ys)), abs(max(ys))) if ys else 0
    spread_x, spread_y = extent_x * 2, extent_y * 2

    # Viewport and scaling
    viewport_w, viewport_h = 1600, 800
    # apply scale modifier to zoom level
    SCALE = (viewport_w / max(spread_x, 1)) * SCALE_MODIFIER
    pan_w = spread_x * SCALE
    pan_h = spread_y * SCALE

    # Center offsets (accounting for DIST_MODIFIER)
    center_x = pan_w / 2
    center_y = pan_h / 2
    globals()['OFFSET_X'] = center_x
    globals()['OFFSET_Y'] = center_y

    # Build HTML elements
    coords = {}

    for s in systems:
    # position each system according to the modified scale
        px = s["coord"][0] * SCALE + OFFSET_X
        py = s["coord"][2] * SCALE + OFFSET_Y
        coords[s["name"]] = {"x": px, "y": py}

    # Debug: ensure all systems loaded before pan bounds calculation
    if len(coords) != len(systems):
        print(f"Warning: coords ({len(coords)}) != systems ({len(systems)})")
    else:
        print(f"Debug: loaded {len(systems)} systems")

    system_divs = []
    svg_lines = []
    print(f"[DEBUG] rendering jump‐lines, total systems: {len(systems)}")

    for s in systems:
        print(f"[DEBUG] {s['name']} → {len(s['destinations'])} raw dests")
        px, py = coords[s["name"]]["x"], coords[s["name"]]["y"]
        # build system icon, hiding if not visible by default
        vis = system_meta[s["name"]]["visible"]
        cls = "system" + ("" if vis else " hidden-system")
        sty = f"left:{px}px;top:{py}px;" + ("" if vis else "display:none;")
        system_divs.append(
    f'<a href="{quote(s["name"])}.html" class="system" data-system="{s["name"]}" style="left:{px}px;top:{py}px;">'                                
    f'<div class="icon">'
    f'<img src="Images/Factions/{s["alignment"]}.png" class="alignment-img" />'
    f'<img src="Images/ring.png" class="tint-img" />'
    f'</div>'
    f'<div class="system-name">{s["name"]}</div></a>'
)
        for d in s.get("destinations", []):
            tgt = coords.get(d["target"])
            if not tgt:
                continue
            svg_lines.append(
                f'<line x1="{px}" y1="{py}" x2="{tgt["x"]}" y2="{tgt["y"]}" '
                'stroke="white" stroke-width="6" opacity="0.5" />'
            )
            dx, dy = tgt["x"] - px, tgt["y"] - py
            ax, ay = px + dx / 3, py + dy / 3
            svg_lines.append(
                f'<line x1="{px}" y1="{py}" x2="{ax}" y2="{ay}" '
                'stroke="white" stroke-width="12" marker-end="url(#arrow)" '
                f'class="jump-arrow jump-from-{s["name"].replace(" ", "-")}" />'
            )

    # Optional map info overlays
    map_info_file = Path(BASE) / "GalMapInfo.json"
    if map_info_file.exists():
        try:
            info = json.loads(map_info_file.read_text())
            for border in info.get("borders", []):
                pts = ' '.join(f"{x * SCALE + OFFSET_X},{y * SCALE + OFFSET_Y}" for x, y in border.get("points", []))
                svg_lines.append(
                    f'<polyline points="{pts}" stroke="{border.get("color","white")}" '
                    f'stroke-width="{border.get("width",16)}" fill="none">'
                    f'<title>{border.get("hover_text","")}</title></polyline>'
                )
            for text in info.get("texts", []):
                pos = text.get("position", [])
                if len(pos) < 2:
                    continue
                cy = pos[2] if len(pos) > 2 else pos[1]
                tx, ty = pos[0] * SCALE + OFFSET_X, cy * SCALE + OFFSET_Y
                size = text.get("size", 12)
                # use em-units for line spacing so multi-line text scales correctly
                line_height_em = 1.2
                tspans = ''.join(
                    f'<tspan x="{tx}" dy="{(line_height_em if i else 0)}em">{line}</tspan>'
                    for i, line in enumerate(text.get("lines", []))
                )
                svg_lines.append(
                    f'<text data-base-size="{size}" x="{tx}" y="{ty}" fill="{text.get("color","white")}" '
                    f'font-size="{size}">{tspans}</text>'
                )
        except json.JSONDecodeError:
            print("Warning: Could not parse GalMapInfo.json, skipping overlays.")

    # Compute pan bounds using full map dimensions + 400‐unit buffer
    margin_px = 400 * SCALE
    # pan_w and pan_h already include DIST_MODIFIER
    panX_min = viewport_w - pan_w - margin_px
    panX_max = margin_px
    panY_min = viewport_h - pan_h - margin_px
    panY_max = margin_px

    center_py_pixel = OFFSET_Y  # define vertical center for JS

    print(f"Pan X range: {panX_min} to {panX_max}, Pan Y range: {panY_min} to {panY_max}")
    PANX_MIN = panX_min
    PANX_MAX = panX_max
    PANY_MIN = panY_min
    PANY_MAX = panY_max

    # Controls HTML
    home_button_html = '<button onclick="resetZoom()" class="system-button" style="background-color:#222;width:100%;font-size:16pt;">Home</button>'

    system_list_html = ''.join(
        f"<button class='system-button' data-system=\"{s['name']}\" "
        f"style=\"{'' if system_meta[s['name']]['visible'] else 'display:none;'}\" "
        f"onclick=\"document.location.href='{quote(s['name'])}.html'\">"
        f"<img src=\"Images/Factions/{system_meta[s['name']]['alignment']}.png\" "
        f"class=\"button-icon\" alt=\"{system_meta[s['name']]['alignment']}\" />"
        f"{s['name']}</button>"
        for s in sorted(systems, key=lambda x: x['name'])
    )

    # Compose final HTMLs
    # Serialize system metadata for JS
    meta_json = json.dumps(system_meta)
    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1.0">
  <title>System Map</title>
  <style>
    body {{ margin:0; background:black; color:white; display:flex; height:100vh; }}
    #controls {{ width:200px; background:#333; padding:10px; overflow-y:auto; }}
    .system-button {{ width:100%; padding:2px; font-size:14pt; background:#444; color:white; border:none; margin-bottom:5px; cursor:pointer; text-align:left; display:flex; align-items:center; }}
    .system-button .button-icon {{ height:1em; width:auto; margin-right:0.5em; }}
    #maparea {{ flex:1; position:relative; background:url("Images/starfield.jpg") center/cover; overflow:hidden; cursor: grab; }}
    #map {{ width: {pan_w}px; height: {pan_h}px; transform-origin: top left; cursor: grab; }}
    .map-container {{ position:absolute; top:0; left:0; }}
    svg {{ position:absolute; top:0; left:0; z-index:0; pointer-events:auto; }}
    svg polyline {{ pointer-events: stroke; }}
    .system {{ position:absolute; width:50px; transform:translate(-50%,-50%); z-index:1; cursor:pointer; text-align:center; }}
    .icon {{ position:relative; width:75px; height:75px; }}
    .alignment-img {{ position:absolute; top:15px; left:15px; width:40px; height:40px; }}
    .tint-img {{ position:absolute; top:0; left:0; width:70px; height:70px; opacity:0.3; }}
    .system-name {{
      position: absolute;
      left: 50%;
      
      text-align: center;
      top: calc(=100% + 4px);
      transform: translateX(-50%);
      white-space: wrap;
      font-size: 90px;
      font-weight: bold;
      color: white;
      text-decoration: none;
      pointer-events: none;
    }}
    
@keyframes jumpPulse {{
  0% {{ stroke: white; stroke-width: 12; }}
  100% {{ stroke: cyan; stroke-width: 18; }}
}}

.jump-arrow-active {{
  animation: jumpPulse 1s infinite alternate ease-in-out !important;
  pointer-events: none !important;

}}
    #info {{
      width: 300px;
      background: #333;
      padding: 10px;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: flex-start;
    }}
    #info img {{
      max-width: 80%;
      height: auto;
    }}
    #system-details {{ text-align: left; }}
</style>
</head>
<body>
  <div id="controls">
    <!-- Oni authentication control -->
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
    <div class="map-container" id="map">
      <svg width="100%" height="100%">
        <defs>
          <marker id="arrow" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="4" markerHeight="4" orient="auto-start-reverse">
            <path d="M0,0 L10,5 L0,10 Z" fill="white" />
          </marker>
        </defs>
        {''.join(svg_lines)}
      </svg>
      {''.join(system_divs)}
    </div>
  </div>
  <div id="info">
    <img src="Images/compass.png" alt="Compass" />
    {home_button_html}
    <div id="system-details">
      <p>Select a system to view metadata.</p>
    </div>
  </div>
  <script>
  
    // ——— ONI GM Authentication Helpers ———
    function enterGMMode() {{
      // set a long-lived cookie flag
      document.cookie = "gmMode=1; path=/; max-age=31536000";
    }}
    function isGM() {{
        return document.cookie
        .split(';')
        .some(c => c.trim() === 'gmMode=1');
    }}
    function exitGMMode() {{
      // clear the cookie
      document.cookie = "gmMode=; path=/; expires=Thu, 01 Jan 1970 00:00:00 UTC;";
    }}

    // Bind ONI login/logout button directly (element present at end of body)
    const oniBtn = document.getElementById('oni-login-btn');
        if (oniBtn) {{
      oniBtn.addEventListener('click', toggleOniAuth);
    }}

    const map     = document.getElementById('map');
    const maparea = document.getElementById('maparea');
    let scale = Math.min(maparea.clientWidth/map.clientWidth, maparea.clientHeight/map.clientHeight);
    let panX = 0, panY = 0;
    // Initial center of Y (from Python)
    const INITIAL_CENTER_PY = {center_py_pixel};
    // Pan bounds
    let PANX_MIN, PANX_MAX, PANY_MIN, PANY_MAX;    
    PANX_MIN = {panX_min};
    PANX_MAX = {panX_max};
    PANY_MIN = {panY_min};
    PANY_MAX = {panY_max};

    // Parsed system metadata
    const systemMeta = {meta_json};

    // Recompute pan bounds based on current scale & viewport
    function updatePanBounds() {{
      const mapW = map.clientWidth * scale;
      const mapH = map.clientHeight * scale;
      const margin = 400 * scale;  // 400px “buffer” at this zoom
      PANX_MIN = maparea.clientWidth - mapW - margin;
      PANX_MAX = margin;
      PANY_MIN = maparea.clientHeight - mapH - margin;
      PANY_MAX = margin;
      console.log(`Bounds → X:[${{PANX_MIN.toFixed(0)}},${{PANX_MAX.toFixed(0)}}] Y:[${{PANY_MIN.toFixed(0)}},${{PANY_MAX.toFixed(0)}}]`);
    }}

    // Initial bounds calculation
    updatePanBounds();
    let isPanning = false, startX = 0, startY = 0;

    function applyTransform() {{ 
      // Clamp panning to within 400px margin
      panX = Math.min(PANX_MAX, Math.max(PANX_MIN, panX));
      panY = Math.min(PANY_MAX, Math.max(PANY_MIN, panY));
      map.style.transform = `translate(${{panX}}px,${{panY}}px) scale(${{scale}})`;
     
      // Dynamic label resizing with enforced min/max font sizes
      document.querySelectorAll('.system-name').forEach(label => {{
      const minSize = 70;
      const maxSize = 90;
      // interpolate size based on zoom—use (scale - 1) so baseSize at scale=1
      let newSize = minSize + (scale - 1) * (maxSize - minSize);
      newSize = Math.max(minSize, Math.min(maxSize, newSize));
      label.style.setProperty('font-size', `${{newSize}}px`, 'important');
      // shift label upward by half the extra height
      const offset = (newSize - minSize) / 2;
      label.style.transform = `translateY(-${{offset}}px)`;
      const halfWidth = label.offsetWidth / 2;
      label.style.marginLeft = `-${{halfWidth}}px`;
      }});
      // Icon scaling: keep icons a consistent on-screen size
      
      document.querySelectorAll('.icon').forEach(icon => {{
        // dynamic icon scaling: shrink when zooming out, grow up to a max when zooming in
        const iconGrowFactor = 0.9; // max 20% growth
        let iconScale = scale > 1
          ? Math.min(scale, 1 + iconGrowFactor)
          : 1 / scale;
        icon.style.transform = `scale(${{iconScale}})`;
      }});
      // Keep free‐floating text at least 24px on‐screen:
      document.querySelectorAll('svg text[data-base-size]').forEach(el => {{
        const baseSize   = parseFloat(el.getAttribute('data-base-size'));
        const screenSize = Math.max(32, baseSize * scale);
        // undo the map’s scale so font renders at `screenSize` px exactly
        const attrSize   = screenSize / scale;
        el.setAttribute('font-size', attrSize);
      }}); 
      
      
    }}

    maparea.addEventListener('mousedown', e => {{
      e.preventDefault(); isPanning = true; startX = e.clientX - panX; startY = e.clientY - panY; maparea.style.cursor = 'grabbing';
    }});

    document.addEventListener('mouseup', () => {{ if (!isPanning) return; isPanning = false; maparea.style.cursor = 'grab'; }});
    document.addEventListener('mousemove', e => {{
      if (!isPanning) return;
      panX = e.clientX - startX;
      panY = e.clientY - startY;
      applyTransform();
    }});
    
     maparea.addEventListener('wheel', e => {{ e.preventDefault();
       const rect = maparea.getBoundingClientRect();
       const mx = e.clientX - rect.left, my = e.clientY - rect.top;
       const prev = scale;
       scale *= e.deltaY > 0 ? 0.9 : 1.1;
       const minS = Math.min(maparea.clientWidth / map.clientWidth, maparea.clientHeight / map.clientHeight);
       const maxS = Math.min(maparea.clientWidth / 500, maparea.clientHeight / 500);
       scale = Math.max(minS, Math.min(scale, maxS));
       const factor = scale / prev;
       panX -= (mx - panX) * (factor - 1);
       panY -= (my - panY) * (factor - 1);

       // recalc bounds now that scale has changed
       updatePanBounds();
       applyTransform();
    }});

    function resetZoom() {{
       scale = Math.min(maparea.clientWidth / map.clientWidth, maparea.clientHeight / map.clientHeight);
       panX = (maparea.clientWidth - map.clientWidth * scale) / 2;
       panY = (maparea.clientHeight - map.clientHeight * scale) / 2;
       updatePanBounds();   // make sure bounds reflect the new scale
       applyTransform();
    }}

    // Center map on load and on resize
    window.addEventListener('load', resetZoom);
    window.addEventListener('resize', resetZoom);
    resetZoom();
    
    document.querySelectorAll('.system').forEach(el => {{
      const sys = el.getAttribute('data-system').replace(/ /g, '-');
      el.addEventListener('mouseenter', () => {{
        // animate arrows and display metadata on hover
        document.querySelectorAll(`.jump-from-${{sys}}`).forEach(line =>
          line.classList.add('jump-arrow-active')
        );
        const name = el.getAttribute('data-system');
        const m = systemMeta[name] || {{}};
        document.getElementById('system-details').innerHTML =
          `<h3>${{name}}</h3>` +
          `<p>Alignment: ${{m.alignment}}</p>` +
          `<p>Development Level: ${{m.development}}</p>` +
          `<p>System Focus: ${{m.focus}}</p>` +
      `<p>Exports: ${{m.exports}}</p>`+
      `<div><strong>Intelligence estimate:</strong></div>`+
      `<div>`+
        `<img src="Images/SysBadges/${{m.intel.pirate}}Pirate.png" width="50" height="50" alt="${{m.intel.pirate}} Pirate" /> `+
        `<img src="Images/SysBadges/${{m.intel.enemy}}Enemy.png" width="50" height="50" alt="${{m.intel.enemy}} Enemy" />`+
      `</div>`+
      `<div>Pirate Activity: ${{m.intel.pirate}}</div>`+
      `<div>Enemy Activity: ${{m.intel.enemy}}</div>`+
      `<div><strong>Known Important Assets:</strong></div>` +
      `<div class="asset-icons">` +
        `${{m.intel.assets.map(a =>
          `<img src="Images/SysBadges/${{a}}.png" width="50" height="50" alt="${{a}}" title="${{a}}" />`
        ).join('')}}` +
      `</div>` +
      `<div class="asset-text">` +
        `${{m.intel.assets.map(a =>
          `<div>${{a}}</div>`
        ).join('')}}` +
      `<p>${{m.description}}</p>`;
      }});
      el.addEventListener('mouseleave', () => {{
        document.querySelectorAll(`.jump-from-${{sys}}`).forEach(line =>
          line.classList.remove('jump-arrow-active')
        );
      }});
    }});
  
  // system search filter
  const searchInput = document.getElementById('system-search');
  searchInput.addEventListener('input', () => {{
    const term = searchInput.value.toLowerCase();
    document.querySelectorAll('.system-button').forEach(btn => {{
      const name = btn.getAttribute('data-system').toLowerCase();
      btn.style.display = name.includes(term) ? '' : 'none';
    }});
  }});
  // sort functionality
  document.querySelectorAll('input[name="sort"]').forEach(radio => {{
    radio.addEventListener('change', reorderButtons);
  }});
  function reorderButtons() {{
    const container = document.getElementById('controls');
    const sortBy = document.querySelector('input[name="sort"]:checked').value;
    // only sort the actual system buttons (ignore login/home buttons)
const buttons = Array.from(container.querySelectorAll('.system-button[data-system]'))
  .filter(btn => btn.getAttribute('data-system'));
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
  // initialize sort order
  reorderButtons();
  
    // Toggle ONI authentication (login/logout)
    function toggleOniAuth() {{
      if (isGM()) {{
        // GM is currently logged in → log out
        exitGMMode();
        document.getElementById('oni-login-btn').innerText = 'ONI Login';
        // hide GM‐only systems and buttons again
        document.querySelectorAll('.hidden-system').forEach(el => el.style.display = 'none');
        document.querySelectorAll('.system-button').forEach(btn => {{
          if (btn.dataset.visible === 'false') btn.style.display = 'none';
       }});
      }} else {{
        // prompt for GM password
        const pwd = prompt('Enter GM password:');
        if (pwd === 'oni1') {{
          enterGMMode();
          document.getElementById('oni-login-btn').innerText = 'ONI Logout';
          // reveal GM‐only systems and buttons
         document.querySelectorAll('.hidden-system').forEach(el => el.style.display = '');
          document.querySelectorAll('.system-button').forEach(btn => btn.style.display = '');
        }} else {{
          alert('Incorrect password');
        }}
      }}
    }}

  // on GM login, reveal hidden systems and list buttons
  window.addEventListener('load', () => {{
    if (isGM()) {{
      document.querySelectorAll('.hidden-system').forEach(el => el.style.display = '');
      document.querySelectorAll('.system-button').forEach(btn => {{
        if (btn.style.display === 'none') btn.style.display = '';
      }});
    }}
  }});
  
  
  </script>
</body>
</html>'''

    # Write out HTML
    HTML_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    HTML_OUTPUT.write_text(html, encoding='utf-8')
    print(f"HTML map written to: {HTML_OUTPUT}")

if __name__ == "__main__":
    os.chdir(default_base)
    main()
