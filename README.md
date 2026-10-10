# TSNMaps

Stellar cartography editor and HTML map generators.

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
