# Maintenance guide

The desktop entry point is `StellarCartography.py`. It opens individual system
editors through `SystemEditor.open_system_editor`. Keep window creation, dialogs,
Tk variables and event wiring in the UI modules. Shared rules and file operations
belong in the modules below, which can be used without starting the editor.

| Module | Responsibility |
| --- | --- |
| `AppPaths.py` | Application resource location, including frozen executables. |
| `EditorSettings.py` | Settings loading/saving and configured data/output paths. |
| `SystemMap.py` | System model, loading, atomic saves, external-change detection and reference-aware name migration. |
| `JsonStorage.py` | Atomic file replacement; backups and rollback for multi-file reference updates. |
| `MapConsistency.py` | Coordinate validation, legacy name planning, gate matching and reference rewriting. |
| `MapMetadata.py` | Incoming-only gate metadata, author normalization and gate indexes. |
| `MapTypes.py` | Shared object types, normalization, hull checks and display defaults. |
| `SystemMigrations.py` | Required legacy structure, side and planet-class corrections; returns warnings to the UI. |
| `SystemValidation.py` | Read-only validation returning errors/warnings; no dialogs or writes. |
| `TerrainGeometry.py` | Terrain point generation and fuel collection zone placement. |
| `GalacticMapData.py` | Translation between system JSON and galactic-map data records; excludes canvas item IDs. |
| `SystemMapRenderer.py` | Canvas drawing from the model and explicit view inputs. |
| `StationOverview.py` | Station overview window, using editor-supplied actions and refresh callbacks. |
| `SysMapCanvas.py`, `Toolbar.py` | Pointer interactions and placement controls. |
| `MapGeneration.py` | Configures and runs the existing HTML generators from explicit paths. |
| `ToolsWindow.py` | Main application's Tools window; file selection, options and error reporting. |
| `scripts` package | Bundled utility implementations with retained command-line entry points. |

The model, settings, geometry, migration, validation and HTML generation modules
must not import `SystemEditor` or require Tk. `SystemEditor` re-exports established
helpers so existing external scripts continue to work; new code should import the
owning module directly. The station overview and renderer receive dependencies
explicitly and must not reach back into editor module globals.

## Behaviour to preserve

- **Silent migrations are required for main-game compatibility.** Encountered
  hyphenated object, relay and terrain names are corrected on open/reload, before
  establishing saved state and undo history. Gate renames must also update local
  links, incoming-only metadata and incoming links from other system files.
  Successful migration does not prompt. A failed write must remain visible.
- File writes use `JsonStorage`. Multi-file changes retain originals and a
  manifest under `.map-backups/`, with rollback on caught failures. Individual
  replacements are atomic; an entire batch is not crash-atomic.
- Model coordinates are authoritative. Pan, zoom and save must not reconstruct
  positions from canvas pixels. Dragging uses original coordinates plus total
  pointer displacement and preserves Y.
- Undo history, pending text, saved-state snapshots and gate rename origins belong
  to each editor window. Do not reintroduce module-global editor state.
- A save failure must keep the window open and stop reload/switch/close actions.
- Resource paths are relative to the application or configured paths, never the
  process's working directory.
- Preserve existing workflow defaults during refactoring. For example, warning
  buoy placement uses 12,000 while the editor's legacy range fallback is 15,000;
  these are separately named in `MapTypes`.

## Checks and builds

Run `py -m unittest discover -s tests`. Pure-service tests cover module boundaries,
settings, migrations and validation; Tk integration tests exercise editor actions
with mocked map reads/writes. File-operation tests use temporary directories.

The existing tests access selected editor closures to drive callbacks. Prefer
testing newly extracted services directly; use UI tests for window behaviour.

Source changes do not update the checked-in executables. `Build.bat` recreates
`build` and `dist`, so preserve any working maps or generated files in `dist`
before running a release build. New modules use normal imports and are discovered
by PyInstaller through the existing spec files. The release build now produces
only `StellarCartography.exe` and `SystemEditor.exe`. Generators and utilities
are imported normally, including terrain generation in both applications;
do not load utility source files dynamically or launch a Python subprocess.
Legacy generator spec files remain for optional developer builds but are not
part of `Build.bat`. Writable data, settings and HTML assets are still external.
Read-only ship/production reference snapshots are bundled as data and resolved
through `AppPaths.get_resource_path`; they must not depend on a loose scripts
folder or the launch directory. Generator imports perform no ShipMap reads;
local-map generation reads the current configured ShipMap when invoked.

Tools exports use explicit configured paths and saved files. The historically
named `export_systems_csv.py` writes system-info JSON, not CSV. Export services
and test-system generation raise exceptions for the UI to report and write
atomically. FCS generation accepts an existing Tk parent, preserves original
files in backups and checks for external changes before each write; it reports
partial batch failures. Old one-off repair scripts are not automatic migrations
and are not exposed in the Tools menu.
