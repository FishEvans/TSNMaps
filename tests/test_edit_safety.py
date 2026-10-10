import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import JsonStorage
import SystemEditor as editor
import StellarCartography as cartography
from test_station_overview import EditorFixture


class EditSafetyTests(EditorFixture):
    def setUp(self):
        super().setUp()
        self.enterContext(patch.object(editor, 'save_editor_settings'))

    def test_metadata_and_direct_edits_are_detected(self):
        s = self.state
        self.assertFalse(s['has_unsaved_changes']())
        for name, value in [('align_var', 'Changed'), ('sec_var', 'Changed'),
                            ('focus_var', 'Changed'), ('vis_var', 'Hide')]:
            with self.subTest(field=name):
                old = s[name].get()
                s[name].set(value)
                self.assertTrue(s['has_unsaved_changes']())
                s[name].set(old)
                self.assertFalse(s['has_unsaved_changes']())
        s['coord_vars'][0].set('123')
        self.assertTrue(s['has_unsaved_changes']())
        s['coord_vars'][0].set('0')
        self.object()['description'] = 'Direct edit without undo'
        self.assertTrue(s['has_unsaved_changes']())

    def test_pending_text_and_save_baseline(self):
        s = self.state
        s['desc_text'].insert('end', 'An unsaved description')
        self.assertTrue(s['has_unsaved_changes']())
        with patch.object(editor.SystemMap, 'save') as save:
            self.assertTrue(s['save_all']())
        save.assert_called_once()
        self.root.update()
        self.assertFalse(s['has_unsaved_changes']())
        s['convert_station_type']('Alpha', 'platform')
        self.assertTrue(s['has_unsaved_changes']())
        s['do_undo']()
        self.assertFalse(s['has_unsaved_changes']())

    def test_failed_save_keeps_window_edits_and_revision(self):
        s = self.state
        s['align_var'].set('Changed')
        before = copy.deepcopy(s['sm'].data['metadata'])
        with patch.object(editor.SystemMap, 'save', side_effect=OSError('disk full')), \
                patch.object(editor.messagebox, 'showerror') as error, \
                patch.object(editor.messagebox, 'askyesnocancel', return_value=True):
            s['on_close']()
        error.assert_called_once()
        self.assertTrue(self.win.winfo_exists())
        self.assertTrue(s['has_unsaved_changes']())
        self.assertEqual(s['align_var'].get(), 'Changed')
        self.assertEqual(s['sm'].data['metadata'].get('revision_number'), before.get('revision_number'))

    def test_invalid_coordinate_blocks_close(self):
        s = self.state
        s['coord_vars'][0].set('invalid')
        with patch.object(editor.SystemMap, 'save') as save, \
                patch.object(editor.messagebox, 'showerror'), \
                patch.object(editor.messagebox, 'askyesnocancel', return_value=True):
            s['on_close']()
        save.assert_not_called()
        self.assertTrue(self.win.winfo_exists())

    def test_cancel_blocks_reload_and_switch(self):
        s = self.state
        s['align_var'].set('Changed')
        with patch.object(editor.messagebox, 'askyesnocancel', return_value=None), \
                patch.object(editor.SystemMap, '_load') as load, \
                patch.object(editor.filedialog, 'askopenfilename', return_value='elsewhere/Next.json'), \
                patch.object(editor, 'open_system_editor') as open_editor:
            self.assertFalse(s['reload_all']())
            s['load_different_system']()
        load.assert_not_called()
        open_editor.assert_not_called()
        self.assertTrue(self.win.winfo_exists())

    def test_save_failure_blocks_reload_and_switch(self):
        s = self.state
        s['align_var'].set('Changed')
        with patch.object(editor.messagebox, 'askyesnocancel', return_value=True), \
                patch.object(editor.messagebox, 'showerror'), \
                patch.object(editor.SystemMap, 'save', side_effect=OSError('disk full')), \
                patch.object(editor.SystemMap, '_load') as load, \
                patch.object(editor.filedialog, 'askopenfilename', return_value='elsewhere/Next.json'), \
                patch.object(editor, 'open_system_editor') as open_editor:
            self.assertFalse(s['reload_all']())
            s['load_different_system']()
        load.assert_not_called()
        open_editor.assert_not_called()
        self.assertTrue(self.win.winfo_exists())

    def test_reload_reconnects_controls_and_clears_history(self):
        s = self.state
        original = s['sm']
        fresh = copy.deepcopy(original.data)
        fresh['traffic'] = dict(commercial='none', civilian='none', security='none')
        fresh['metadata']['skybox'] = ''
        s['convert_station_type']('Alpha', 'platform')
        with patch.object(editor.SystemMap, '_load', return_value=fresh), \
                patch.object(editor.SystemMap, 'save'), \
                patch.object(editor.messagebox, 'askyesnocancel', return_value=False):
            self.assertTrue(s['reload_all']())
        self.assertIs(s['toolbar'].sm, original)
        self.assertIs(s['ctx']['sm'], original)
        self.assertEqual(s['undo_stack'], [])
        self.assertEqual(s['redo_stack'], [])
        self.assertFalse(s['has_unsaved_changes']())
        self.assertEqual(self.object()['type'], 'station')
        self.assertEqual(self.row_control(1).get(), 'station')
        s['traffic_vars']['commercial'].set('high')
        s['skybox_var'].set('New skybox')
        self.assertEqual(original.data['traffic']['commercial'], 'high')
        self.assertEqual(original.data['metadata']['skybox'], 'New skybox')
        self.assertTrue(s['has_unsaved_changes']())
        with patch.object(editor.SystemMap, 'save'):
            self.assertTrue(s['save_all']())
        self.assertEqual(original.data['traffic']['commercial'], 'high')

    def test_failed_reload_keeps_current_model(self):
        s = self.state
        s['convert_station_type']('Alpha', 'platform')
        before = copy.deepcopy(s['sm'].data)
        with patch.object(editor.SystemMap, '_load', side_effect=OSError('read failure')), \
                patch.object(editor.messagebox, 'showerror'), \
                patch.object(editor.messagebox, 'askyesnocancel', return_value=False):
            self.assertFalse(s['reload_all']())
        self.assertEqual(s['sm'].data, before)
        self.assertTrue(s['has_unsaved_changes']())

    def test_switch_uses_selected_path_and_preserves_session_on_failure(self):
        selected = str(Path(tempfile.gettempdir()) / 'elsewhere' / 'Next.json')
        with patch.object(editor.filedialog, 'askopenfilename', return_value=selected), \
                patch.object(editor, 'open_system_editor', return_value=None) as open_editor:
            self.state['load_different_system']()
        open_editor.assert_called_once_with(selected)
        self.assertTrue(self.win.winfo_exists())

    def test_successful_save_and_close(self):
        self.state['align_var'].set('Changed')
        with patch.object(editor.SystemMap, 'save') as save, \
                patch.object(editor.messagebox, 'askyesnocancel', return_value=True):
            self.state['on_close']()
        save.assert_called_once()
        self.assertFalse(self.win.winfo_exists())


class AtomicSaveTests(unittest.TestCase):
    def test_success_and_failures_preserve_last_complete_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'system.json'
            JsonStorage.atomic_write_json(path, {'description': 'Café'})
            original = path.read_bytes()
            self.assertEqual(json.loads(original), {'description': 'Café'})
            for data in ({'bad': object()}, {'bad': float('nan')}):
                with self.subTest(data=data):
                    with self.assertRaises((TypeError, ValueError)):
                        JsonStorage.atomic_write_json(path, data)
                    self.assertEqual(path.read_bytes(), original)
            with patch.object(JsonStorage.os, 'replace', side_effect=PermissionError('locked')):
                with self.assertRaises(PermissionError):
                    JsonStorage.atomic_write_json(path, {'new': 'data'})
            self.assertEqual(path.read_bytes(), original)
            with patch.object(JsonStorage.os, 'fsync', side_effect=OSError('disk full')):
                with self.assertRaises(OSError):
                    JsonStorage.atomic_write_json(path, {'new': 'data'})
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(list(Path(directory).iterdir()), [path])
            model = editor.SystemMap(str(path))
            model.data = {'new': 'data'}
            model.save()
            self.assertEqual(json.loads(path.read_bytes()), model.data)


class MapSaveSafetyTests(unittest.TestCase):
    def setUp(self):
        self.directory = self.enterContext(tempfile.TemporaryDirectory())
        self.app = cartography.SystemMapEditor.__new__(cartography.SystemMapEditor)
        self.app.root = Mock()
        self.app.saved_system_coords = {}
        self.app.systems = {}
        self.app.borders = []
        self.app.texts = []
        self.app.saved_overlays = ([], [])
        self.app._get_systems_dir = lambda: self.directory
        self.app._run_generators = Mock()
        self.enterContext(patch.object(cartography, 'get_base_path', return_value=self.directory))
        self.error = self.enterContext(patch.object(cartography.messagebox, 'showerror'))
        self.app._write_system_json('Test.json', {'systemMapCoord': [0, 0, 0]})
        self.app.load_systems()

    def test_map_drag_survives_child_refresh_and_save(self):
        self.app.systems['Test.json']['coord'] = [20, 0, 30]
        self.assertTrue(self.app._map_has_unsaved_changes())
        self.assertTrue(self.app._refresh_system_record_from_disk('Test.json'))
        self.assertEqual(self.app.systems['Test.json']['coord'], [20, 0, 30])
        self.assertTrue(self.app.save_changes())
        saved = json.loads(Path(self.directory, 'Test.json').read_text())
        self.assertEqual(saved['systemMapCoord'], [20, 0, 30])
        self.assertFalse(self.app._map_has_unsaved_changes())
        self.app._run_generators.assert_called_once()

    def test_failed_map_save_remains_dirty_and_skips_generation(self):
        self.app.systems['Test.json']['coord'] = [20, 0, 30]
        with patch.object(self.app, '_write_system_json', side_effect=PermissionError('locked')):
            self.assertFalse(self.app.save_changes())
        self.assertTrue(self.app._map_has_unsaved_changes())
        self.assertEqual(self.app.systems['Test.json']['coord'], [20, 0, 30])
        self.app._run_generators.assert_not_called()
        self.error.assert_called_once()

    def test_parent_close_respects_child_cancel(self):
        child = Mock()
        child.confirm_pending_changes.return_value = False
        self.app.root.winfo_children.return_value = [child]
        self.app.on_close()
        self.app.root.destroy.assert_not_called()

    def test_parent_close_respects_map_save_failure(self):
        self.app.systems['Test.json']['coord'] = [20, 0, 30]
        self.app.root.winfo_children.return_value = []
        with patch.object(cartography.messagebox, 'askyesnocancel', return_value=True), \
                patch.object(self.app, '_write_system_json', side_effect=PermissionError('locked')):
            self.app.on_close()
        self.app.root.destroy.assert_not_called()


if __name__ == '__main__':
    unittest.main()
