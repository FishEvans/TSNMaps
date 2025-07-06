import os
import sys
import json
import glob
import traceback
import argparse
from pathlib import Path
import math
import re

# Helper to locate resources when running as a module or frozen executable
def get_base_path():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    try:
        return os.path.dirname(os.path.abspath(__file__))
    except NameError:
        # Fallback if __file__ is not defined
        return os.getcwd()

# Base directories\
BASE = get_base_path()
JSON_FOLDER =  Path(get_base_path()) / "data/missions/Map Designer/Terrain"
DEFAULT_HTML_DIR = Path(BASE) / 'HTML'

# Configuration for station side colors
STATION_SIDE_COLORS = {
    'TSN': 'green',
    'USFP': 'blue'
}
DEFAULT_STATION_COLOR = 'red'

# Grid reference generator
def get_grid_reference(x, z):
    grid_size = 20000
    origin_x = -240000
    origin_z = 280000

    dx = int((x - origin_x) // grid_size)
    dz = int((z - origin_z) // grid_size)

    col = dx % 100  # Numbers increase left to right (x)
    row = dz % 26   # Letters increase bottom to top (z)

    letter = chr(ord('A') + row)
    number = f"{col:02d}"
    return f"{letter}{number}"

# Patched HTML template with escaped braces
# Debug function to find unmatched braces in the template

def is_hidden(obj):
    return str(obj.get('hideonmap')).lower() == 'true'

def debug_braces(template):
    count = 0
    for idx, ch in enumerate(template):
        if ch == '{':
            count += 1
        elif ch == '}':
            count -= 1
        if count < 0:
            print(f"[BRACE DEBUG] Extra '}}' at position {idx}")
            count = 0
    if count > 0:
        print(f"[BRACE DEBUG] {count} unmatched '{{' remain")

# End debug function

def debug_braces_detailed(template):
    """
    Print per-line brace counts and cumulative balance to locate mismatches.
    """
    total = 0
    for lineno, line in enumerate(template.splitlines(), start=1):
        opens = line.count('{') - line.count('{{')*2
        closes = line.count('}') - line.count('}}')*2
        delta = opens - closes
        total += delta
        if delta != 0:
            print(f"[BRACE DEBUG] Line {lineno}: opens={opens}, closes={closes}, cumulative={total}")

# Debug function to parse template fields
import string

def debug_template(template):
    """
    Parse the template and report literal chunks containing unmatched braces and field names.
    """
    formatter = string.Formatter()
    for idx, (literal, field_name, format_spec, conversion) in enumerate(formatter.parse(template)):
        if literal and ('{' in literal or '}' in literal):
            print(f"[TEMPLATE DEBUG] Chunk {idx}: literal has brace: {literal!r}")
        if field_name is not None:
            print(f"[TEMPLATE DEBUG] Chunk {idx}: field_name={field_name!r}")


def debug_braces_detailed(template):
    """
    Print per-line brace counts and cumulative balance to locate mismatches.
    """
    total = 0
    for lineno, line in enumerate(template.splitlines(), start=1):
        opens = line.count('{') - line.count('{{')*2
        closes = line.count('}') - line.count('}}')*2
        delta = opens - closes
        total += delta
        if delta != 0:
            print(f"[BRACE DEBUG] Line {lineno}: opens={opens}, closes={closes}, cumulative={total}")


HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <style>
        body {{ margin: 0; background: black; color: white; display: flex; height: 100vh; }}
        #controls {{ flex: 1; min-width: 200px; max-width: 350px; overflow-y: auto; background: #333; padding: 10px; }}
        #plot {{ flex: 3; min-width: 400px; }}
        #info {{ flex: 1; min-width: 200px; background: #333; padding: 10px; overflow-y: auto; }}
        h2.header {{ margin-top: 0; margin-bottom: 5px; text-align: center; }}
        h3.subheader {{ margin-top: 0; margin-bottom: 15px; text-align: center; color: #ccc; }}
        .alignment-image {{ display: block; max-width: 100%; height: auto; margin: 10px auto; }}
        button {{ display: block; width: 100%; margin-bottom: 5px; background: #555; color: white; border: none; padding: 5px; text-align: left; cursor: pointer; font-size: 20px; }}
        button.header {{ background: #444; cursor: default; font-size: 24px; }}
    </style>
</head>
<body>
    <div id="controls">
        <h2 class="header">{sys_name}</h2>
        <h3 class="subheader">Alignment: {alignment}</h3>
        <img src="Images/Factions/{alignment}.png" alt="Alignment Logo" class="alignment-image" onerror="this.style.display='none';">
    </div>
    <div id="plot"></div>
    <div id="info">
        <img src="Images/Compass.png" alt="Compass" style="display:block; max-width:100%; height:auto; margin-bottom:10px;">
        <button id="galactic-map-btn" title="Back to Galactic Map">Show Galactic Map</button>
        Select an object
    </div>
<script>
    var objData = {obj_data};
        console.log("[DEBUG JS] objData keys:", Object.keys(objData));
        console.log("[DEBUG JS] objData sample:", objData[Object.keys(objData)[0]]);

    function clearAnnotations() {{
        Plotly.relayout('plot', {{annotations: []}});
        document.getElementById('info').innerHTML = getInfoHeader() + 'Select an object';
        document.getElementById('galactic-map-btn').addEventListener('click', function() {{
            window.location.href = 'index.html';
        }});
        document.getElementById('galactic-map-btn').addEventListener('click', function() {{
            window.location.href = 'index.html';
        }});
    }}
    
    function getInfoHeader() {{
    return '<img src="Images/Compass.png" alt="Compass" '
         + 'style="display:block; max-width:100%; height:auto; margin-bottom:10px;">'
         + '<button id="galactic-map-btn" title="Back to Galactic Map">Galactic Map</button>';
        }}
    
    function highlight(name) {{
        var obj = objData[name];
        var annotation = {{
            x: obj.x, y: obj.y, xref: 'x', yref: 'y', text: name,
            showarrow: true, arrowcolor: 'yellow', arrowwidth: 2,
            arrowhead: 3, font: {{color: 'yellow', size: 28}}
        }};

        Plotly.relayout('plot', {{annotations: [annotation]}});

        var infoHtml = '<span style="font-size:20pt;">' + name + '</span><br>';
        infoHtml += '<b>Location:</b> ' + obj.grid + '<br>';

        if (obj.type === 'station') {{
            // Station selected: display detailed station info
            if (obj.hullImage) {{
                infoHtml += '<img src="' + obj.hullImage + '" alt="Hull Art" style="max-width:48%; height:auto;">';
            }}
            if (obj.sides && obj.sides.length > 0) {{
                infoHtml += '<img src="Images/Factions/' + obj.sides[0] + '.png" alt="Faction Logo" style="max-width:48%; height:auto;">';
            }}
            infoHtml += '<b>Facilities:</b> ' + (obj.facilities.length ? obj.facilities.join(', ') : 'None') + '<br>';
            if (obj.hullName && obj.hullImage) {{
                infoHtml += '<b>General Class:</b> ' + obj.hullName + '<br>';
            }}
            if (obj.hullDescription) {{
                infoHtml += '<p style="margin-top:5px; font-size:90%; color:#ccc;">' + obj.hullDescription + '</p>';
            }}
        }} else if ((obj.type === 'jump_point' || obj.type === 'jumppoint' || obj.type === 'jumpnode') && obj.destinations && typeof obj.destinations === 'object') {{
            infoHtml += '<b>Type:</b> ' + obj.type + '<br>';
            infoHtml += '<b>Destinations:</b><br>';
            for (const [target, label] of Object.entries(obj.destinations)) {{
                if (typeof target === 'string' && typeof label === 'string') {{
                    let file = label + '.html';
                    // Correctly escape single quotes for JS string
                    infoHtml += `<button onclick="window.open('${{file}}', '_blank')">${{label}}, ${{target}}</button>`;
                }}
            }}
            }}
        else {{
            infoHtml += '<b>Type:</b> ' + obj.type;
        }}

            // ——— append a description paragraph if one exists ———
            if (obj.description) {{
                infoHtml += '<p style="font-size:90%; margin-top:8px;">'
                          + obj.description
                          + '</p>';
            }}
            document.getElementById('info').innerHTML = getInfoHeader() + infoHtml;
            document.getElementById('galactic-map-btn').addEventListener('click', function() {{
                window.location.href = 'index.html';
            }});
                + infoHtml;
         
    }}
         document.getElementById('galactic-map-btn').addEventListener('click', function() {{
        window.location.href = 'index.html';
    }});
    

    var fig = {fig_json};
    fig.layout.showlegend = false;
    fig.layout.dragmode = 'pan';
    fig.layout.title = '{sys_name}';
    Plotly.newPlot('plot', fig.data, fig.layout, {{responsive: true, scrollZoom: true}});
        console.log("[DEBUG JS] Plotted traces count:", fig.data.length);
        console.log("[DEBUG JS] fig.data sample:", fig.data.slice(0,3));

    var plotDiv = document.getElementById('plot');
    // Custom click: select nearest object within 10px of cursor
    plotDiv.addEventListener('click', function(evt) {{
        var rect = plotDiv.getBoundingClientRect();
        var px = evt.clientX - rect.left;
        var py = evt.clientY - rect.top;
        var xaxis = plotDiv._fullLayout.xaxis;
        var yaxis = plotDiv._fullLayout.yaxis;
        var l2px = xaxis.l2p.bind(xaxis);
        var l2py = yaxis.l2p.bind(yaxis);
        var minDist = Infinity, closest = null;
        for (var name in objData) {{
            var pt = objData[name];
            var xPx = l2px(pt.x);
            var yPx = l2py(pt.y);
            var dx = xPx - px, dy = yPx - py;
            var d = Math.sqrt(dx*dx + dy*dy);
            console.log(`${{name}}: data=(${{pt.x}}, ${{pt.y}}) -> screen=(${{xPx.toFixed(1)}}, ${{yPx.toFixed(1)}}), cursor=(${{px.toFixed(1)}}, ${{py.toFixed(1)}}), dx=${{dx.toFixed(1)}}, dy=${{dy.toFixed(1)}}, d=${{d.toFixed(1)}}`);
            if (d < minDist) {{
                minDist = d;
                closest = name;
            }}
        }}
        if (minDist <= 35 && closest) {{
            highlight(closest);
        }}
    }});

  var ctrl = document.getElementById('controls');

  // Helper: create and append a single button
  function addButton(label, fn, header, color) {{
    var btn = document.createElement('button');
    btn.textContent = label;
    if (header) {{
      btn.className = 'header';     // section header style
      btn.onclick = null;           // no click action
    }} else {{
      btn.onclick = fn;             // bind the handler
      if (color) btn.style.backgroundColor = color;
    }}
    ctrl.appendChild(btn);
  }}

  // ——— Populate the sidebar ———
  addButton('None', clearAnnotations, false, null);

  addButton('--- Gates ---', null, true, null);
  {gate_buttons}

  addButton('--- Nav Points/POI ---', null, true, null);
  {relay_buttons}

  addButton('--- Stations ---', null, true, null);
  {station_buttons}
    
</script>
</body>
</html>'''

# Load external ship map once
shipmap_path = DEFAULT_HTML_DIR / 'Images' / 'Ships' / 'ShipMap.json'
print(f"[INFO] Loading ship map from: {shipmap_path}")
with open(shipmap_path) as f:
    loaded_map = json.load(f)
    if isinstance(loaded_map, list):
        SHIP_MAP = {entry['key']: entry for entry in loaded_map if 'key' in entry}
        print(f"[INFO] Converted ship map from list to dict with {len(SHIP_MAP)} entries.")
    else:
        SHIP_MAP = loaded_map
        print(f"[INFO] Loaded ship map with {len(SHIP_MAP)} keys.")

class MapViewer:
    def __init__(self, system_file):
        try:
            with open(system_file) as f:
                self.system_data = json.load(f)
        except Exception as e:
            raise ValueError(f"Error loading system file {system_file}: {e}")
        self.objects = self.system_data.get('objects', {})
        self.terrain = self.system_data.get('terrain', {})
        self.system_file = system_file
        self.offset = self.system_data.get('systemMapCoord', [0, 0, 0])

        if 'sensor_relay' in self.system_data:
            for name, coord in self.system_data['sensor_relay'].items():
                if name in self.objects:
                    continue
                entry = {'type': 'sensor_relay'}
                # pull out coordinate (as before)…
                if isinstance(coord, dict) and 'coordinate' in coord:
                    entry['coordinate'] = coord['coordinate']
                    # …but also carry over any hideonmap/description flags
                    for fld in ('hideonmap', 'HideOnSCMap', 'description'):
                        if fld in coord:
                            entry[fld] = coord[fld]
                else:
                    entry['coordinate'] = coord
                self.objects[name] = entry

    def project(self, coord):
        ox, oy, oz = self.offset
        x, y, z = coord
        return x - ox, z - oz

    def get_station_color(self, obj):
        for side, color in STATION_SIDE_COLORS.items():
            if side in obj.get('sides', []):
                return color
        return DEFAULT_STATION_COLOR

    def generate(self, output_html=None):
        if output_html:
            out_path = output_html
        else:
            os.makedirs(DEFAULT_HTML_DIR, exist_ok=True)
            sys_name = os.path.splitext(os.path.basename(self.system_file))[0]
            out_path = os.path.join(DEFAULT_HTML_DIR, f"{sys_name}.html")

        sys_name = os.path.splitext(os.path.basename(self.system_file))[0]
        alignment = self.system_data.get('systemalignment', '')
        print(f"[DEBUG] sys_name={sys_name}, alignment={alignment}")
        print(f"[DEBUG] Loaded objects: {list(self.objects.keys())}")
        terrain_traces = []
        data = terrain_traces[:]
        obj_data = {}
        gates, stations, relays = [], [], []
        
        for r in self.terrain.values():
            # ignore hidden terrain or anything without start/end
            if is_hidden(r) or 'start' not in r or 'end' not in r:
                continue
            x1, y1 = self.project(r['start'])
            x2, y2 = self.project(r['end'])
            length = math.hypot(x2 - x1, y2 - y1)
            width = 2 * r.get('scatter', 0)
            area = length * width
            density = r.get('density', 0)
            eff_den = density * 1e8 / area if area else density
            alpha = max(0.4, min(1, eff_den / 200))
            rgb = ('165,42,42' if r['type'] == 'asteroids' else '128,0,128' if r['type'] == 'nebulas' else '0,0,0')
            ux, uy = ((x2 - x1) / length, (y2 - y1) / length) if length else (1, 0)
            vx, vy = -uy, ux
            cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
            hl, hw = length / 2, width / 2
            corners_x = [cx + ux * hl + vx * hw, cx - ux * hl + vx * hw, cx - ux * hl - vx * hw, cx + ux * hl - vx * hw]
            corners_y = [cy + uy * hl + vy * hw, cy - uy * hl + vy * hw, cy - uy * hl - vy * hw, cy + uy * hl - vy * hw]
            fill = f'rgba({rgb},{alpha})'
            terrain_traces.append({
                'type': 'scatter', 'x': corners_x + [corners_x[0]], 'y': corners_y + [corners_y[0]],
                'fill': 'toself', 'fillcolor': fill, 'line': {'shape': 'spline', 'color': fill, 'width': 0}, 'hoverinfo': 'none'
            })

        data = terrain_traces[:]
        obj_data = {}

        # ——— Add black holes as their own markers ———
        # ——— Prep a helper so we treat hideonmap exactly the same everywhere ———
        blackholes = []
        for key, r in self.terrain.items():
            if r.get('type') != 'blackhole' or is_hidden(r):
                continue
            coord = r.get('coordinate')
            if isinstance(coord, (list, tuple)) and len(coord) >= 2:
                x, y = self.project(coord)
                name = r.get('name', key)
                grid_ref = get_grid_reference(x, y)
                # add scatter marker+label for the black hole
                data.append({
                    'type': 'scatter',
                    'x': [x], 'y': [y],
                    'mode': 'markers+text',
                    'marker': {'symbol': 'star', 'size': 14, 'color': 'yellow'},
                    'text': [name],
                    'textposition': 'top center',
                    'hovertext': [f"{name} [{grid_ref}]"],
                    'hoverinfo': 'text'
                })
                # expose it to the JS highlight/info panel
                obj_data[name] = {'type': 'blackhole', 'x': x, 'y': y, 'grid': grid_ref}
                blackholes.append(name)
        print(f"[DEBUG] obj_data initialized, will populate entries based on objects")

        for name, obj in self.objects.items():
            # debug each object
            print(f"[DEBUG] Inspecting {name} (type={obj.get('type')}): hideonmap={obj.get('hideonmap')}")
            # now skip solely based on hideonmap
            if is_hidden(obj):
                print(f"[DEBUG] → SKIPPING {name} because hideonmap is True")
                continue
            x, y = self.project(obj.get('coordinate', [0, 0, 0]))
            typ = obj.get('type', '')
            grid_ref = get_grid_reference(x, y)
            symbol = 'circle'
            mode = 'markers+text'
            color = 'white'
            size = 12
            text_size = 14

            if typ in ('jumppoint', 'jumpnode'):
                symbol = 'circle-open'
                size = 16
                text_size = 20
                color = 'lightblue'
                gates.append(name)
            elif typ == 'station':
                symbol = 'square'
                color = self.get_station_color(obj)
                stations.append((name, color))
            elif typ == 'sensor_relay':
                symbol = 'circle'
                
                if re.match(r'^(?:SR[- ]?\d+|Sensor Relay \d+)$', name):
                    size = 3
                    mode = 'markers'
                else:
                    size = 6
                    color = '#FF13F0'
                    mode = 'markers+text'
                    relays.append(name)
            
            elif typ == 'platform':
                symbol = 'pentagon-open'
                size = 3
                color = 'orange'
                mode = 'markers'
            
            
            trace = {
                'type': 'scatter',
                'x': [x],
                'y': [y],
                'mode': mode,
                'marker': {'symbol': symbol, 'size': size, 'color': color},
                'hovertext': [f"{name} [{grid_ref}]"],
                'hoverinfo': 'text'
            }
            if 'text' in mode:
                trace.update({'text': [name], 'textposition': 'top center', 'textfont': {'color': 'white', 'size': text_size}})
            data.append(trace)

            entry = {'type': typ, 'x': x, 'y': y, 'grid': grid_ref}
            entry = {'type': typ, 'x': x, 'y': y, 'grid': grid_ref}
            # ——— carry over description if present ———
            if obj.get('description'):
                entry['description'] = obj['description']            
            
            if typ in ('jump_point', 'jumppoint', 'jumpnode'):
                raw_dest = obj.get('destinations', {})
                clean_dest = {
                    str(k): str(v) for k, v in raw_dest.items()
                    if isinstance(k, (str, int)) and isinstance(v, (str, int))
                }
                if clean_dest:
                    entry['destinations'] = clean_dest
            if typ == 'station':
                entry.update({'hull': obj.get('hull', 'Unknown'), 'facilities': obj.get('facilities', []), 'sides': obj.get('sides', [])})
                hull_key = obj.get('hull')
                hull_data = SHIP_MAP.get(hull_key)
                if hull_data:
                    print(f"[INFO] Matched hull '{hull_key}' to: {hull_data.get('name')}")
                else:
                    print(f"[WARN] No match found for hull: {hull_key}")
                if hull_data:
                    entry['hullName'] = hull_data.get('name')
                    entry['hullImage'] = f"Images/Ships/{hull_data.get('artfileroot')}256.png"
                    entry['hullDescription'] = hull_data.get('long_desc', '')
            obj_data[name] = entry

        gates.sort()
        print(f"[DEBUG] Gates: {gates}")
        stations.sort(key=lambda x: x[0])
        print(f"[DEBUG] Stations: {[name for name, _ in stations]}")
        relays.sort()
        print(f"[DEBUG] Relays: {relays}")
        blackholes.sort()
        print(f"[DEBUG] Black holes: {blackholes}")
        print(f"[DEBUG] Total traces: {len(data)} (including terrain)")

        layout = {
    'title': sys_name,
    'paper_bgcolor': 'black',
    'plot_bgcolor': 'black',
    'font': {'color': 'white'},
    'margin': {'l': 0, 'r': 0, 't': 40, 'b': 0},
    'autosize': True,
    'dragmode': 'pan',
        'hovermode': 'closest',
    'xaxis': {
        'color': 'white',
        'showgrid': True,
        'gridcolor': 'gray',
        'dtick': 20000,
        'title': 'X Axis'
    },
    'yaxis': {
        'color': 'white',
        'showgrid': True,
        'gridcolor': 'gray',
        'dtick': 20000,
        'scaleanchor': 'x',
        'scaleratio': 1,
        'title': 'Z Axis'
    },
    'shapes': [
    ]
}
        fig_json = {'data': data, 'layout': layout}
        gate_buttons = '\n    '.join([f"addButton('{g}',function(){{highlight('{g}');}},false,null);" for g in gates])
        station_buttons = '\n    '.join([f"addButton('{s}',function(){{highlight('{s}');}},false,'{c}');" for s, c in stations])
        relay_buttons = '\n    '.join([f"addButton('{r}',function(){{highlight('{r}');}},false,null);" for r in relays])

        # Debug braces before formatting to catch mismatches


        debug_braces(HTML_TEMPLATE)
        # Additional debugging: inspect obj_data keys and placeholder values
        print(f"[DEBUG] obj_data keys: {list(obj_data.keys())}")
        print(f"[DEBUG] gate_buttons snippet: {gate_buttons[:100]}{'...' if len(gate_buttons)>100 else ''}")
        print(f"[DEBUG] station_buttons snippet: {station_buttons[:100]}{'...' if len(station_buttons)>100 else ''}")
        print(f"[DEBUG] relay_buttons snippet: {relay_buttons[:100]}{'...' if len(relay_buttons)>100 else ''}")


        try:
            html = HTML_TEMPLATE.format(
                title=os.path.basename(out_path),
                sys_name=sys_name,
                alignment=alignment,
                fig_json=json.dumps(fig_json),
                obj_data=json.dumps(obj_data),
                gate_buttons=gate_buttons,
                station_buttons=station_buttons,
                relay_buttons=relay_buttons
            )
        except Exception as e:
            print("[ERROR] Failed to format HTML template")
            traceback.print_exc()
            print("-- Context --")
            print("sys_name:", sys_name)
            print("alignment:", alignment)
            print("gate_buttons:\n", gate_buttons)
            print("station_buttons:\n", station_buttons)
            print("relay_buttons:\n", relay_buttons)
            raise RuntimeError(f"Error formatting HTML template: {e}")

        with open(out_path, 'w') as f:
            f.write(html)
        print(f"Map saved to {out_path}")

      
    def plot(self, output_html=None):
        self.generate(output_html)

# Module entry point
def main():
    os.chdir(BASE)
    parser = argparse.ArgumentParser(description='Generate interactive map HTML from system JSON')
    parser.add_argument('system_files', nargs='*', help='JSON files to process')
    parser.add_argument('-d', '--output-dir', default=None, help='Override HTML output directory')
    args = parser.parse_args()
    files = args.system_files or glob.glob(str(JSON_FOLDER / '*.json'))
    for jf in files:
        out_dir = args.output_dir or DEFAULT_HTML_DIR
        os.makedirs(out_dir, exist_ok=True)
        out_file = os.path.join(out_dir, os.path.splitext(os.path.basename(jf))[0] + '.html')
        MapViewer(jf).plot(out_file)

if __name__ == '__main__':
    main()
