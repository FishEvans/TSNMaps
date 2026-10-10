"""Behaviour checks for the extracted services and their UI adapters."""
import copy
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

import EditorSettings
import GalacticMapData
import MapGeneration
from MapMetadata import get_incoming_only_gate_names, set_incoming_only_gate
from SystemMap import SystemMap
from SystemMigrations import migrate_legacy_structure, migrate_planet_classes, migrate_sides
from SystemValidation import verify_system_data
from TerrainGeometry import generate_line_coords
from test_station_overview import EditorFixture


class ServiceTests(unittest.TestCase):
    def test_data_services_and_generators_import_without_tk(self):
        code = '''
import sys
import EditorSettings, SystemMap, MapMetadata, MapTypes, MapConsistency
import SystemMigrations, SystemValidation, TerrainGeometry, GalacticMapData
import MapGeneration, LocMapGen, GalMapGen, LibraryGen, ProductionFlowGen
assert 'SystemEditor' not in sys.modules
assert 'tkinter' not in sys.modules
'''
        result = subprocess.run([sys.executable, '-c', code], cwd=Path(__file__).resolve().parents[1],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_settings_merge_and_relative_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / 'Settings.json').write_text(json.dumps({'author': 'Default', 'systemMapsPath': 'maps'}))
            personal = base / 'personal' / 'Settings.json'
            personal.parent.mkdir()
            personal.write_text(json.dumps({'author': 'User', 'htmlOutputPath': 'output'}))
            with patch.object(EditorSettings, 'get_base_path', return_value=str(base)), \
                    patch.object(EditorSettings, 'get_settings_path', return_value=str(personal)):
                self.assertEqual(EditorSettings.load_editor_settings()['author'], 'User')
                self.assertEqual(Path(EditorSettings.get_data_path()), base / 'maps')
                self.assertEqual(Path(EditorSettings.get_html_output_path()), base / 'output')
                EditorSettings.save_editor_settings({'author': 'Updated'})
            self.assertEqual(json.loads(personal.read_text()), {'author': 'Updated'})
            self.assertEqual(json.loads((base / 'Settings.json').read_text())['author'], 'Default')

    def test_legacy_migration_rules_persist_and_return_warnings(self):
        model = SystemMap.__new__(SystemMap)
        model.data = {
            'objects': {
                'Gate': {'type': 'jump_point', 'state': 'Unteathered'},
                'Station': {'type': 'station', 'sides': ['TSN', 'pirate', 'UnknownSide']},
            },
            'terrain': {'Rocks': {'type': 'asteroids'}, 'World': {'type': 'planet'}},
            'sensor_relay': {'Relay': [1, 2, 3]},
        }
        model.save = Mock()
        migrate_legacy_structure(model)
        self.assertEqual(model.data['objects']['Gate'], {'type': 'jumppoint', 'state': 'Untethered'})
        self.assertEqual(model.data['sensor_relay']['Relay'], {'coordinate': [1, 2, 3]})
        self.assertEqual(model.data['terrain']['Rocks']['composition'], ['Ast. Std Rand'])
        self.assertEqual(migrate_planet_classes(model, ['EarthLike']), [])
        warnings = migrate_sides(model, ['USFP', 'Pirate'])
        self.assertEqual(model.data['objects']['Station']['sides'], ['USFP', 'Pirate', 'UnknownSide'])
        self.assertEqual(len(warnings), 1)
        self.assertIn('UnknownSide', warnings[0])
        self.assertGreater(model.save.call_count, 0)
        model.save.reset_mock()
        migrate_legacy_structure(model)
        migrate_planet_classes(model, ['EarthLike'])
        migrate_sides(model, ['USFP', 'Pirate'])
        model.save.assert_not_called()

    def test_validation_reports_errors_and_warnings_without_mutation(self):
        data = {'systemMapCoord': [0, 0, 0], 'metadata': {}, 'terrain': {}, 'sensor_relay': {},
                'objects': {'Gate': {'type': 'jumpnode', 'coordinate': [1, 2, 3],
                                     'destinations': {'Missing': 'Elsewhere'}}}}
        original = copy.deepcopy(data)
        errors, warnings = verify_system_data(data, filename='Test.json', system_files={},
                                             other_gate_index={}, ct_config={})
        self.assertEqual(errors, [])
        self.assertEqual(len(warnings), 1)
        self.assertIn('Elsewhere', warnings[0])
        self.assertEqual(data, original)
        data['objects']['Gate']['coordinate'] = ['bad', 2, 3]
        errors, _ = verify_system_data(data, filename='Test.json', system_files={},
                                      other_gate_index={}, ct_config={})
        self.assertTrue(any('coordinate' in error for error in errors))

    def test_seeded_geometry_stays_reproducible(self):
        # Captured from the original terrain routine before extraction.
        expected = [(56.42300300937469, -332.1471142214127, 175.3061915732642),
                    (85.82014092715573, -495.6734008447006, 137.50151125540023),
                    (51.366416096884066, 6.426345724034832, 130.3372860579897)]
        random_state = random.getstate()
        actual = generate_line_coords([0, 0, 0], [100, 0, 200], 3, 25, seed=42)
        for point, wanted in zip(actual, expected):
            for value, reference in zip(point, wanted):
                self.assertAlmostEqual(value, reference, places=10)
        self.assertEqual(len(actual), 3)
        self.assertEqual(random.getstate(), random_state)

    def test_shared_incoming_gate_aliases(self):
        data = {'metadata': {'incoming_only_gates': [' Gate ', 'GATE']}}
        self.assertEqual(get_incoming_only_gate_names(data), {'gate'})
        set_incoming_only_gate(data, 'New', True)
        self.assertEqual(data['metadata'], {'incomingOnlyGates': ['Gate', 'New']})

    def test_galactic_projection_preserves_coordinates_and_unrelated_data(self):
        original = {'systemMapCoord': [123.456789012345, 42, -98.765432109876],
                    'systemalignment': 'USFP', 'metadata': {'custom': 'Keep'},
                    'objects': {'Station': {'type': 'station', 'hull': 'valid'}}}
        record = GalacticMapData.normalize_system_record(original, valid_hull_keys={'valid'})
        self.assertNotIn('canvas_items', record)
        self.assertFalse(record['has_invalid_station_hull'])
        result = GalacticMapData.apply_system_record_to_data(copy.deepcopy(original), record)
        self.assertEqual(result['systemMapCoord'], original['systemMapCoord'])
        self.assertEqual(result['objects'], original['objects'])
        self.assertEqual(result['metadata']['custom'], 'Keep')

    def test_generation_adapter_configures_all_outputs_in_order(self):
        modules = [Mock() for _ in range(4)]
        calls = []
        for index, module in enumerate(modules):
            module.main.side_effect = lambda *args, i=index: calls.append(i)
        with patch.object(MapGeneration, 'LocMapGen', modules[0]), \
                patch.object(MapGeneration, 'GalMapGen', modules[1]), \
                patch.object(MapGeneration, 'LibraryGen', modules[2]), \
                patch.object(MapGeneration, 'ProductionFlowGen', modules[3]):
            MapGeneration.generate_maps('maps', 'output', 'preferences.json')
        self.assertEqual(calls, [0, 1, 2, 3])
        self.assertEqual(modules[0].JSON_FOLDER, Path('maps'))
        self.assertEqual(modules[1].HTML_OUTPUT, Path('output/index.html'))
        self.assertEqual(modules[2].SETTINGS_PATH, Path('preferences.json'))
        self.assertEqual(modules[3].OUTPUT_PATH, Path('output/ProductionFlow.html'))


class RendererAdapterTests(EditorFixture):
    def test_extracted_renderer_handles_terrain_and_side_colours(self):
        state = self.state
        terrain = {
            'Nebula': {'type': 'nebula', 'start': [0, 0, 0], 'end': [20000, 0, 40000],
                       'density': 5, 'scatter': 1000, 'seed': 42},
            'Planet': {'type': 'planet', 'coordinate': [30000, 0, 0], 'radius': 5000},
        }
        state['sm'].data['terrain'] = terrain
        state['terrain_keys'][:] = list(terrain)
        state['side_colour_view_var'].set(True)
        state['draw_map'](state['ctx'])
        self.root.update()
        self.assertTrue(state['ctx']['map_canvas'].find_withtag('terrain'))
        self.assertTrue(state['ctx']['map_canvas'].find_all())


if __name__ == '__main__':
    unittest.main()
