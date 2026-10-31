# TSNMaps

Stellar cartography editor and HTML map generators.

## Briefing controls for generated maps

Generated local maps and the galactic map accept URL settings for their initial
state. Use `?panels=none`, `?panels=left`, `?panels=right`, or `?panels=both` to
choose which side panels appear. On a local map, `?panels=none&object=Station%20Name`
selects an object and opens its information panel. On the galactic map (`index.html`),
use `?panels=none&system=System%20Name`. Names must match the map exactly. Selecting
an object or system opens the right panel even when `panels=none` was requested.

An embedding briefing page can change the map while it is open by sending these
messages to the map iframe:

```js
const map = document.querySelector('iframe#map');
const mapOrigin = new URL(map.src).origin;
map.contentWindow.postMessage(
  { source: 'tsn-briefing', type: 'setPanels', left: false, right: false },
  mapOrigin
);
map.contentWindow.postMessage(
  { source: 'tsn-briefing', type: 'showObject', name: 'Station Name' },
  mapOrigin
);
// Galactic map: type: 'showSystem', name: 'System Name'
// Either map: type: 'clearSelection'
```

`setPanels` accepts either or both Boolean fields; omitted fields keep their
current state. `showObject` and `showSystem` reveal the right panel, display the
selected information, and highlight or center the selection. Unknown names and
objects hidden from public viewers are ignored. Messages are accepted only from
the parent frame at the briefing site's origin or the map's own origin. Regenerate
the HTML maps after changing these generators; existing exported HTML will not
gain the controls automatically.

Run the desktop application with `py StellarCartography.py` and the tests with
`py -m unittest discover -s tests`.

The release build produces two independent applications: `StellarCartography.exe`
and `SystemEditor.exe`. HTML generators are built into Stellar Cartography;
separate generator executables and loose utility scripts are no longer required.
Keep the application data, settings and HTML assets alongside the executables.

Use **Tools** in Stellar Cartography for HTML generation, test-system generation,
jump-table and system-info JSON exports, FCS-zone generation and ship-data
regeneration. Exports read saved files from the configured systems folder and
let you choose the output location. Test-system generation uses the configured
HTML folder's ShipMap and offers object spacing and row-size settings.
FCS generation updates system files and keeps originals under `.map-backups`;
close system-editor windows before running it. Historical bulk repair scripts
remain available in the source repository rather than the Tools menu.

See [the maintenance guide](ARCHITECTURE.md) for module responsibilities, required
silent migrations, coordinate/save invariants and build notes.
