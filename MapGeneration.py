"""Configure and run the existing HTML generators from explicit paths.

The generators retain their standalone entry points. This adapter owns the
module settings needed when they are invoked together inside the application.
"""
from pathlib import Path
import LocMapGen
import GalMapGen
import LibraryGen
import ProductionFlowGen


def configure_generators(systems_dir, html_dir, settings_path):
    systems_dir = Path(systems_dir)
    html_dir = Path(html_dir)
    LocMapGen.JSON_FOLDER = systems_dir
    LocMapGen.DEFAULT_HTML_DIR = html_dir
    GalMapGen.JSON_FOLDER = systems_dir
    GalMapGen.HTML_OUTPUT = html_dir / "index.html"
    LibraryGen.HTML_DIR = html_dir
    LibraryGen.SHIPS_DIR = html_dir / "Images" / "Ships"
    LibraryGen.FACTIONS_DIR = html_dir / "Images" / "Factions"
    LibraryGen.SHIPMAP_PATH = LibraryGen.SHIPS_DIR / "ShipMap.json"
    LibraryGen.SETTINGS_PATH = Path(settings_path)
    LibraryGen.OUTPUT_PATH = html_dir / "Library.html"
    ProductionFlowGen.SPRITE_PATH = html_dir / "Images" / "Production" / "grid-icon-sheet2.png"
    ProductionFlowGen.HTML_DIR = html_dir
    ProductionFlowGen.OUTPUT_PATH = html_dir / "ProductionFlow.html"


def generate_maps(systems_dir, html_dir, settings_path):
    configure_generators(systems_dir, html_dir, settings_path)
    LocMapGen.main([])
    GalMapGen.main()
    LibraryGen.main()
    ProductionFlowGen.main()
