"""Settings persistence and configured paths, independent of Tk."""
import os
import json
from pathlib import Path
from typing import Any, Dict
from AppPaths import get_base_path
from JsonStorage import atomic_write_json


def get_data_path():
    """Directory where system JSON files live under data/missions/.../Terrain"""
    settings = load_editor_settings()
    return str(resolve_configured_path(settings.get('systemMapsPath'), get_default_data_path()))

def get_default_data_path():
    return os.path.join(get_base_path(), 'data', 'missions', 'Map Designer', 'Terrain')

def get_default_html_path():
    return os.path.join(get_base_path(), 'HTML')

def resolve_configured_path(value: Any, default_path: str) -> Path:
    raw = str(value or '').strip()
    if not raw:
        return Path(default_path)
    path = Path(os.path.expandvars(os.path.expanduser(raw)))
    if not path.is_absolute():
        path = Path(get_base_path()) / path
    return path

def get_html_output_path():
    settings = load_editor_settings()
    return str(resolve_configured_path(settings.get('htmlOutputPath'), get_default_html_path()))

def get_settings_path():
    base = get_base_path()
    settings_path = os.path.join(base, 'Settings.json')
    try:
        if os.path.isdir(base) and os.access(base, os.W_OK):
            return settings_path
    except Exception:
        pass
    home = os.path.expanduser('~')
    return os.path.join(home, '.tsnmaps', 'Settings.json')

def _load_settings_file(path: str) -> Dict[str, Any]:
    try:
        with open(path, 'r') as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}

def load_editor_settings():
    base_path = os.path.join(get_base_path(), 'Settings.json')
    settings = _load_settings_file(base_path)
    user_path = get_settings_path()
    if os.path.abspath(user_path) != os.path.abspath(base_path):
        user_settings = _load_settings_file(user_path)
        settings.update(user_settings)
    return settings

def save_editor_settings(settings: Dict[str, Any]) -> None:
    path = get_settings_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
    except Exception:
        pass
    try:
        atomic_write_json(path, settings)
    except Exception:
        pass
