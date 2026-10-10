"""System data model, safe persistence and required compatibility migrations."""
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from JsonStorage import atomic_write_json, commit_json_updates
from MapConsistency import (is_gate, validate_map_coordinate, read_system_documents,
                            rewrite_gate_references, normalize_legacy_names)
from MapMetadata import rename_incoming_only_gate


class SystemMap:
    """
    A class to load, edit, and save stellar system maps for StellarCartography.
    """
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.disk_bytes = None
        self.data: Dict[str, Any] = self._load()

    def _load(self) -> Dict[str, Any]:
        raw = Path(self.file_path).read_bytes()
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("System file must contain a JSON object.")
        if 'systemMapCoord' in data:
            validate_map_coordinate(data['systemMapCoord'])
        self.disk_bytes = raw
        return data

    def save(self, file_path: Optional[str] = None, *, gate_renames=None) -> None:
        target = Path(file_path or self.file_path).resolve()
        if 'systemMapCoord' in self.data:
            validate_map_coordinate(self.data['systemMapCoord'])
        if target == Path(self.file_path).resolve() and self.disk_bytes is not None:
            if target.read_bytes() != self.disk_bytes:
                raise ValueError("This system changed on disk. Reload it before saving to avoid overwriting newer edits.")
        if gate_renames:
            documents, originals = read_system_documents(target.parent)
            updates = {target: self.data}
            for path, data in documents.items():
                if path != target and rewrite_gate_references(data, target.stem, gate_renames):
                    updates[path] = data
            commit_json_updates(updates, expected=originals)
        else:
            atomic_write_json(target, self.data)
        if target == Path(self.file_path).resolve():
            self.disk_bytes = target.read_bytes()

    def migrate_names(self):
        """Silently correct legacy names and persist their incoming references."""
        # Game compatibility requires these corrections on open and reload,
        # before the editor establishes its saved state and undo history.
        # Successful migrations intentionally persist without a prompt.
        migrated, renames = normalize_legacy_names(self.data)
        if not renames:
            return False
        object_renames = renames.get('objects', {})
        gate_renames = {old: new for old, new in object_renames.items()
                        if is_gate(self.data['objects'][old])}
        for old, new in object_renames.items():
            rename_incoming_only_gate(migrated, old, new)
        rewrite_gate_references(migrated, Path(self.file_path).stem, gate_renames)
        original = self.data
        self.data = migrated
        try:
            # Gate names are referenced by other systems and incoming-only
            # metadata. Save their updates together using the backed-up batch
            # path; failures must propagate so a partial migration is not
            # presented as successful. Restore the in-memory data on failure.
            self.save(gate_renames=gate_renames)
        except Exception:
            self.data = original
            raise
        return True

    def list_sensor_relays(self) -> Dict[str, List[float]]:
        return self.data.get('sensor_relay', {})

    def list_objects(self) -> List[str]:
        return list(self.data.get('objects', {}).keys())

    def get_object(self, name: str) -> Dict[str, Any]:
        return self.data.get('objects', {}).get(name, {})

    def update_object_coordinate(self, name: str, coord: List[float]) -> bool:
        obj = self.data.get('objects', {}).get(name)
        if obj:
            obj['coordinate'] = coord
            return True
        return False

    def list_terrain(self) -> List[str]:
        return list(self.data.get('terrain', {}).keys())

    def get_terrain_feature(self, key: str) -> Dict[str, Any]:
        return self.data.get('terrain', {}).get(key, {})

    def update_terrain_feature(self, key: str, feature: Dict[str, Any]) -> bool:
        if key in self.data.get('terrain', {}):
            self.data['terrain'][key] = feature
            return True
        return False

    def get_system_map_coord(self) -> List[float]:
        return self.data.get('systemMapCoord', [])

    def set_system_map_coord(self, coord: List[float]) -> None:
        self.data['systemMapCoord'] = coord

    def get_alignment(self) -> Optional[str]:
        return self.data.get('alignment') or self.data.get('systemalignment')

    def set_alignment(self, alignment: str) -> None:
        if 'alignment' in self.data:
            self.data['alignment'] = alignment
        else:
            self.data['systemalignment'] = alignment

    def get_description(self) -> str:
        return self.data.get('metadata', {}).get('sysdescription', '')

    def set_description(self, description: str) -> None:
        md = self.data.setdefault('metadata', {})
        md['sysdescription'] = description
