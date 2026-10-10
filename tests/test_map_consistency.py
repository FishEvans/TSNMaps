import copy
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import GalMapGen
import JsonStorage
from MapConsistency import validate_map_coordinate, parse_map_coordinate_fields
import StellarCartography as cartography
import SystemEditor as editor
from test_station_overview import EditorFixture


def gate(destinations=None, kind='jumpnode'):
    return dict(type=kind, coordinate=[0, 0, 0], destinations=destinations or {})


class MapConsistencyTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.app = cartography.SystemMapEditor.__new__(cartography.SystemMapEditor)
        self.app.root = Mock()
        self.app.root.winfo_children.return_value = []
        self.app.systems = {}
        self.app.saved_system_coords = {}
        self.app.borders, self.app.texts = [], []
        self.app.saved_overlays = ([], [])
        self.app._get_systems_dir = lambda: str(self.folder)
        self.app.redraw_map = Mock()
        self.app.clear_selection = Mock()
        self.app.draw_scale = Mock()
        self.app.canvas = Mock()
        self.app.canvas.winfo_width.return_value = 1200
        self.app.SCALE = 0.123456789
        self.app.min_zoom_scale = self.app.SCALE
        self.app.pan_offset_x, self.app.pan_offset_y = 637.25, 429.75
        self.app.drag_data = {}
        self.enterContext(patch.object(cartography, 'get_base_path', return_value=str(self.folder)))
        self.warning = self.enterContext(patch.object(cartography.messagebox, 'showwarning'))
        self.error = self.enterContext(patch.object(cartography.messagebox, 'showerror'))
        self.info = self.enterContext(patch.object(cartography.messagebox, 'showinfo'))

    def write(self, name, objects=None, coordinate=None, metadata=None):
        path = self.folder / (name + '.json')
        JsonStorage.atomic_write_json(path, dict(
            systemMapCoord=coordinate if coordinate is not None else [0, 0, 0],
            objects=objects or {}, metadata=metadata or {}))
        return path

    def read(self, name):
        return json.loads((self.folder / (name + '.json')).read_bytes())

    def test_pan_zoom_and_repeated_save_preserve_exact_coordinates(self):
        original = [12345.678901234567, 42, -98765.43210987654]
        self.write('Alpha', coordinate=original)
        self.app.load_systems()
        # Saving must never derive coordinates from any canvas item.
        self.app.canvas.coords.side_effect = AssertionError('Read screen coordinates during save')
        for i in range(30):
            self.app.drag_data = dict(panning=True, x=0, y=0, press_x=0, press_y=0)
            self.app.do_pan(SimpleNamespace(x=31 + i, y=-19))
            self.app.zoom_in(413, 277)
            self.app.zoom_out(413, 277)
            self.assertTrue(self.app._save_map_data())
            self.assertEqual(self.read('Alpha')['systemMapCoord'], original)
        self.assertFalse(self.app._map_has_unsaved_changes())

    def test_drag_uses_total_displacement_and_preserves_y(self):
        original = [1000.123456789, 73, -2000.987654321]
        self.write('Alpha', coordinate=original)
        self.app.load_systems()
        self.app._find_system_hit = lambda *a, **kw: {'filename': 'Alpha.json'}
        self.app.canvas.coords.return_value = [10, 20, 80, 90]  # Fallback oval.
        self.app.start_pan(SimpleNamespace(x=100, y=100))
        for x in range(101, 141):
            self.app.do_pan(SimpleNamespace(x=x, y=120))
        expected = [original[0] + 40 / self.app.SCALE, 73, original[2] + 20 / self.app.SCALE]
        self.assertEqual(self.app.systems['Alpha.json']['coord'], expected)
        self.app.canvas.coords.assert_not_called()
        # Returning to the original pointer position returns the exact numbers.
        self.app.do_pan(SimpleNamespace(x=100, y=100))
        self.app.end_pan(SimpleNamespace(x=100, y=100))
        self.assertEqual(self.app.systems['Alpha.json']['coord'], original)

    def test_small_click_movement_does_not_change_coordinates(self):
        original = [12.345678912345, 7, -98.765432198765]
        self.write('Alpha', coordinate=original)
        self.app.load_systems()
        self.app._find_system_hit = lambda *a, **kw: {'filename': 'Alpha.json'}
        for _ in range(20):
            self.app.start_pan(SimpleNamespace(x=100, y=100))
            self.app.do_pan(SimpleNamespace(x=103, y=105))
            self.app.end_pan(SimpleNamespace(x=103, y=105))
            self.assertEqual(self.app.systems['Alpha.json']['coord'], original)

    def test_invalid_coordinates_are_reported_and_skipped(self):
        self.write('Valid')
        self.write('Short', coordinate=[1, 2])
        self.write('Text', coordinate=['1', 2, 3])
        self.app.load_systems()
        self.assertEqual(set(self.app.systems), {'Valid.json'})
        self.assertIn('Short.json', self.warning.call_args.args[1])
        self.assertIn('Text.json', self.warning.call_args.args[1])
        warnings = []
        systems, _ = GalMapGen.load_systems(self.folder, warnings)
        self.assertEqual([system['name'] for system in systems], ['Valid'])
        self.assertEqual(len(warnings), 2)

    def test_auto_link_requires_existing_unambiguous_gate(self):
        self.write('Alpha', {'Beta Gate': gate()})
        self.write('Beta', {'Unrelated Gate': gate()})
        self.app.load_systems()
        self.assertTrue(self.app.auto_link_gates())
        self.assertEqual(self.read('Alpha')['objects']['Beta Gate']['destinations'], {})
        self.write('Beta', {'Alpha One': gate(), 'Alpha Two': gate()})
        self.assertTrue(self.app.auto_link_gates())
        self.assertEqual(self.read('Alpha')['objects']['Beta Gate']['destinations'], {})
        self.assertIn('ambiguous', self.info.call_args.args[1])

    def test_auto_link_supports_multiword_names_and_incoming_only(self):
        self.write('Alpha', {'Vesper Point Gate': gate(kind='jump_point'), 'Vesper Point Arrival': gate()},
                   metadata={'incomingOnlyGates': ['Vesper Point Arrival']})
        self.write('Vesper Point', {'Alpha Gate': gate({'Elsewhere': 'Existing'})})
        self.app.load_systems()
        self.assertTrue(self.app.auto_link_gates())
        objects = self.read('Alpha')['objects']
        self.assertEqual(objects['Vesper Point Gate']['destinations'], {'Alpha Gate': 'Vesper Point'})
        self.assertEqual(objects['Vesper Point Arrival']['destinations'], {})
        self.assertEqual(self.read('Vesper Point')['objects']['Alpha Gate']['destinations'], {'Elsewhere': 'Existing'})

    def test_system_rename_updates_all_references_and_keeps_backups(self):
        self.write('Alpha', {'Self': gate({'Self': 'Alpha'})})
        self.write('Beta', {'Return': gate({'Self': 'ALPHA.JSON'}, kind='jump_point')})
        self.app.load_systems()
        self.app.systems['Alpha.json']['coord'] = [20, 7, 30]
        self.assertEqual(self.app.rename_system('Alpha.json', 'New Alpha'), 'New Alpha.json')
        self.assertFalse((self.folder / 'Alpha.json').exists())
        self.assertEqual(self.read('Beta')['objects']['Return']['destinations'], {'Self': 'New Alpha.json'})
        self.assertEqual(self.read('New Alpha')['objects']['Self']['destinations'], {'Self': 'New Alpha'})
        self.assertEqual(self.app.systems['New Alpha.json']['coord'], [20, 7, 30])
        self.assertEqual(len(list((self.folder / '.map-backups').glob('*/manifest.json'))), 1)

    def test_system_rename_rolls_back_if_a_reference_write_fails(self):
        alpha = self.write('Alpha', {'Self': gate({'Self': 'Alpha'})})
        beta = self.write('Beta', {'Return': gate({'Self': 'Alpha'})})
        originals = {p: p.read_bytes() for p in (alpha, beta)}
        write = JsonStorage.atomic_write_bytes
        def fail_beta(path, payload):
            if path == beta:
                raise PermissionError('locked')
            return write(path, payload)
        with patch.object(JsonStorage, 'atomic_write_bytes', side_effect=fail_beta):
            with self.assertRaisesRegex(OSError, 'Original files restored'):
                self.app.rename_system('Alpha.json', 'Renamed')
        for path, original in originals.items():
            self.assertEqual(path.read_bytes(), original)
        self.assertFalse((self.folder / 'Renamed.json').exists())

    def test_invalid_file_aborts_rename_before_any_write(self):
        path = self.write('Alpha')
        original = path.read_bytes()
        (self.folder / 'Broken.json').write_text('{broken')
        with self.assertRaisesRegex(ValueError, 'Broken.json'):
            self.app.rename_system('Alpha.json', 'Renamed')
        self.assertEqual(path.read_bytes(), original)
        self.assertFalse((self.folder / 'Renamed.json').exists())

    def test_rename_failure_restores_already_updated_references(self):
        alpha = self.write('Alpha')
        beta = self.write('Beta', {'Return': gate({'Self': 'Alpha'})})
        originals = {p: p.read_bytes() for p in (alpha, beta)}
        replace = JsonStorage.os.replace
        def fail_rename(source, destination):
            if Path(destination).name == 'Renamed.json':
                raise PermissionError('rename denied')
            return replace(source, destination)
        with patch.object(JsonStorage.os, 'replace', side_effect=fail_rename):
            with self.assertRaisesRegex(OSError, 'Original files restored'):
                self.app.rename_system('Alpha.json', 'Renamed')
        for path, original in originals.items():
            self.assertEqual(path.read_bytes(), original)

    def test_case_only_rename_and_existing_name_collision(self):
        self.write('Alpha')
        self.write('Beta')
        self.app.load_systems()
        with self.assertRaises(FileExistsError):
            self.app.rename_system('Alpha.json', 'Beta')
        self.assertEqual(self.app.rename_system('Alpha.json', 'ALPHA'), 'ALPHA.json')
        self.assertIn('ALPHA.json', [p.name for p in self.folder.iterdir()])

    def test_html_destinations_accept_case_and_json_suffix(self):
        self.write('Alpha', {'Outbound': gate({'Arrival': '  BETA.JSON '})})
        self.write('Beta', {'Arrival': gate()})
        warnings = []
        systems, _ = GalMapGen.load_systems(self.folder, warnings)
        alpha = next(system for system in systems if system['name'] == 'Alpha')
        self.assertEqual(alpha['destinations'][0]['target'], 'Beta')
        self.assertEqual(warnings, [])

    def test_gate_save_updates_incoming_links_and_stale_editor_cannot_overwrite(self):
        alpha = self.write('Alpha', {'Old Gate': gate()})
        beta = self.write('Beta', {'Return': gate({'Old Gate': 'ALPHA.json'})})
        model, stale = editor.SystemMap(str(alpha)), editor.SystemMap(str(beta))
        model.data['objects']['New Gate'] = model.data['objects'].pop('Old Gate')
        model.save(gate_renames={'Old Gate': 'New Gate'})
        self.assertEqual(self.read('Beta')['objects']['Return']['destinations'], {'New Gate': 'ALPHA.json'})
        with self.assertRaisesRegex(ValueError, 'changed on disk'):
            stale.save()

    def test_gate_reference_collision_aborts_without_overwriting(self):
        alpha = self.write('Alpha', {'Old Gate': gate()})
        beta = self.write('Beta', {'Return': gate({'Old Gate': 'Alpha', 'New Gate': 'Another System'})})
        original = {p: p.read_bytes() for p in (alpha, beta)}
        model = editor.SystemMap(str(alpha))
        model.data['objects']['New Gate'] = model.data['objects'].pop('Old Gate')
        with self.assertRaisesRegex(ValueError, 'overwrite destination'):
            model.save(gate_renames={'Old Gate': 'New Gate'})
        for path, content in original.items():
            self.assertEqual(path.read_bytes(), content)

    def test_silent_name_migration_updates_all_categories_and_references(self):
        alpha = self.write('Alpha', {
            'Old-Gate': gate(), 'Self Link': gate({'Old-Gate': 'Alpha'}),
            'Station-One': dict(type='station', coordinate=[0, 0, 0]),
        }, metadata={'incoming_only_gates': ['Old-Gate']})
        self.write('Beta', {'Return': gate({'Old-Gate': 'ALPHA.JSON'})})
        data = self.read('Alpha')
        data['sensor_relay'] = {'Relay-One': {'coordinate': [1, 2, 3]}}
        data['terrain'] = {'Field-One': {'type': 'asteroids'}}
        JsonStorage.atomic_write_json(alpha, data)
        model = editor.SystemMap(str(alpha))
        self.assertTrue(model.migrate_names())
        saved = self.read('Alpha')
        self.assertIn('Old Gate', saved['objects'])
        self.assertIn('Station One', saved['objects'])
        self.assertIn('Relay One', saved['sensor_relay'])
        self.assertIn('Field One', saved['terrain'])
        self.assertEqual(saved['objects']['Self Link']['destinations'], {'Old Gate': 'Alpha'})
        self.assertEqual(editor.get_incoming_only_gate_names(saved), {'old gate'})
        self.assertEqual(self.read('Beta')['objects']['Return']['destinations'], {'Old Gate': 'ALPHA.JSON'})
        before = alpha.read_bytes()
        self.assertFalse(model.migrate_names())
        self.assertEqual(alpha.read_bytes(), before)

    def test_silent_name_migration_resolves_collisions_without_data_loss(self):
        alpha = self.write('Alpha', {
            'Old-Gate': gate({'Source': 'Beta'}),
            'Old Gate': gate({'Other': 'Gamma'}),
            'old gate 2': gate({'Third': 'Delta'}),
        })
        self.write('Beta', {'Return': gate({'Old-Gate': 'Alpha', 'Old Gate': 'Alpha'})})
        model = editor.SystemMap(str(alpha))
        model.migrate_names()
        saved = self.read('Alpha')['objects']
        self.assertEqual(len(saved), 3)
        self.assertEqual(saved['Old Gate 3']['destinations'], {'Source': 'Beta'})
        self.assertEqual(saved['Old Gate']['destinations'], {'Other': 'Gamma'})
        self.assertEqual(self.read('Beta')['objects']['Return']['destinations'],
                         {'Old Gate 3': 'Alpha', 'Old Gate': 'Alpha'})

    def test_silent_migration_write_failure_restores_model_and_files(self):
        alpha = self.write('Alpha', {'Old-Gate': gate()})
        beta = self.write('Beta', {'Return': gate({'Old-Gate': 'Alpha'})})
        originals = {path: path.read_bytes() for path in (alpha, beta)}
        model = editor.SystemMap(str(alpha))
        old_data = copy.deepcopy(model.data)
        write = JsonStorage.atomic_write_bytes
        def fail_beta(path, payload):
            if path == beta:
                raise PermissionError('locked')
            return write(path, payload)
        with patch.object(JsonStorage, 'atomic_write_bytes', side_effect=fail_beta):
            with self.assertRaises(OSError):
                model.migrate_names()
        self.assertEqual(model.data, old_data)
        for path, raw in originals.items():
            self.assertEqual(path.read_bytes(), raw)

    def test_overlays_use_application_folder_from_another_working_directory(self):
        expected = {'borders': [], 'texts': [{'lines': ['Correct map']} ]}
        JsonStorage.atomic_write_json(self.folder / 'GalMapInfo.json', expected)
        with tempfile.TemporaryDirectory() as other, patch.object(GalMapGen, 'get_base_path', return_value=str(self.folder)):
            previous = Path.cwd()
            try:
                os.chdir(other)
                self.assertEqual(GalMapGen.load_map_info([]), expected)
            finally:
                os.chdir(previous)

    def test_coordinate_fields_preserve_large_integers_and_reject_nonfinite_values(self):
        original = [9007199254740993, 19, 12.345678912345]
        self.assertEqual(parse_map_coordinate_fields(list(map(str, original)), original), original)
        for value in ([1, 2], [1, 2, float('inf')], [True, 2, 3], [1, 2, '3']):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_map_coordinate(value)


class GateRenameEditorTests(EditorFixture):
    def make_test_data(self, data):
        data['objects']['Old-Gate'] = gate()
        data['objects']['Self Link'] = gate({'Old-Gate': 'OverviewTest'})
        data['metadata']['incomingOnlyGates'] = ['Old-Gate']
        return data

    def setUp(self):
        super().setUp()
        self.enterContext(patch.object(editor, 'save_editor_settings'))

    def test_open_silently_migrates_names_and_manual_rename_can_be_undone(self):
        s = self.state
        self.assertIn('Old Gate', s['sm'].data['objects'])
        self.assertNotIn('Old-Gate', s['sm'].data['objects'])
        self.assertEqual(s['sm'].data['objects']['Self Link']['destinations'], {'Old Gate': 'OverviewTest'})
        self.assertFalse(s['has_unsaved_changes']())
        with patch.object(editor.simpledialog, 'askstring', return_value='New Gate'):
            s['rename_object']('Old Gate')
        self.assertEqual(s['sm'].data['objects']['Self Link']['destinations'], {'New Gate': 'OverviewTest'})
        self.assertEqual(s['gate_origins']['New Gate'], 'Old Gate')
        s['do_undo']()
        self.assertIn('Old Gate', s['sm'].data['objects'])
        self.assertNotIn('New Gate', s['gate_origins'])
        s['do_redo']()
        with patch.object(editor.SystemMap, 'save') as save:
            self.assertTrue(s['save_all']())
        save.assert_called_once_with(gate_renames={'Old Gate': 'New Gate'})
        self.assertFalse(s['has_unsaved_changes']())

    def test_rename_collision_preserves_both_objects(self):
        s = self.state
        before = copy.deepcopy(s['sm'].data)
        with patch.object(editor.simpledialog, 'askstring', return_value='Alpha'), \
                patch.object(editor.messagebox, 'showerror') as error:
            s['rename_object']('Old Gate')
        error.assert_called_once()
        self.assertEqual(s['sm'].data, before)

    def test_reload_also_silently_migrates_newly_encountered_names(self):
        s = self.state
        reloaded = copy.deepcopy(s['sm'].data)
        reloaded['sensor_relay']['New-Relay'] = {'coordinate': [0, 0, 0]}
        with patch.object(editor.SystemMap, '_load', return_value=reloaded), \
                patch.object(editor.SystemMap, 'save') as save:
            self.assertTrue(s['reload_all']())
        save.assert_called_once_with(gate_renames={})
        self.assertIn('New Relay', s['sm'].data['sensor_relay'])
        self.assertFalse(s['has_unsaved_changes']())


if __name__ == '__main__':
    unittest.main()
