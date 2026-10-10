"""Application resources are relative to the program, not its launch folder."""
from pathlib import Path
import sys


def get_base_path():
    return str(Path(sys.executable if getattr(sys, 'frozen', False) else __file__).resolve().parent)


def get_resource_path(relative_path):
    """Read-only reference data lives inside the bundle; writable data stays outside."""
    return Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent)) / relative_path
