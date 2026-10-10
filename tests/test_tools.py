import json
from pathlib import Path
import tempfile
import tkinter as tk
import unittest
import subprocess
import sys
from unittest.mock import Mock, patch

import ToolsWindow
from scripts.export_jump_table import export_jump_table
from scripts.export_systems_csv import export_system_info
from scripts.generate_test_system import generate_test_system
from scripts.generate_fcs_zones_all import save_system


class ToolServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.systems = self.base / 'systems'
        self.systems.mkdir()
        for name, destinations in [('A', {'Gate': 'B.json'}), ('B', {}), ('C', {})]:
            data = {'systemMapCoord': [1.234567890123, 0, 4], 'systemalignment': 'USFP',
                    'objects': {'Jump': {'type': 'jumpnode', 'hideonmap': True,
                                         'destinations': destinations}},
                    'metadata': {'sysdescription': 'Description', 'exports': ['Ore']}}
            (self.systems / f'{name}.json').write_text(json.dumps(data))

    def test_jump_export_hidden_option_and_unreachable_system(self):
        output = self.base / 'jump.json'
        for hidden, distance in [(True, 1), (False, '-')]:
            export_jump_table(self.systems, output, include_hidden=hidden)
            result = json.loads(output.read_text())
            self.assertEqual(result['distances']['A']['B'], distance)
            self.assertEqual(result['distances']['A']['C'], '-')
            self.assertEqual(result['distances']['A']['A'], 0)

    def test_info_export_does_not_modify_systems(self):
        before = {p: p.read_bytes() for p in self.systems.iterdir()}
        output = export_system_info(self.systems, self.base / 'nested' / 'info.json')
        result = json.loads(output.read_text())
        self.assertEqual(result[0]['description'], 'Description')
        self.assertEqual(result[0]['hidden_jumps'][0]['dest_system'], 'B')
        self.assertEqual(before, {p: p.read_bytes() for p in self.systems.iterdir()})

    def test_empty_folder_leaves_existing_output_intact(self):
        output = self.base / 'output.json'
        output.write_text('original')
        with self.assertRaises(ValueError):
            export_jump_table(self.base / 'missing', output)
        self.assertEqual(output.read_text(), 'original')

    def test_test_system_generation_and_invalid_settings(self):
        shipmap = self.base / 'ShipMap.json'
        shipmap.write_text(json.dumps([{'key': 'station', 'roles': ['station']},
                                      {'key': 'planet', 'roles': ['planet'], 'name': 'World'}]))
        output = self.base / 'test.json'
        generate_test_system(shipmap, output, spacing=2000, per_row=2)
        data = json.loads(output.read_text())
        self.assertTrue(data['objects'])
        self.assertTrue(any(t['type'] == 'planet' for t in data['terrain'].values()))
        before = output.read_bytes()
        for spacing, columns in [(float('nan'), 2), (0, 2), (1000, 0)]:
            with self.assertRaises(ValueError):
                generate_test_system(shipmap, output, spacing=spacing, per_row=columns)
        self.assertEqual(output.read_bytes(), before)

    def test_fcs_save_keeps_backup_and_rejects_stale_data(self):
        path = self.systems / 'A.json'
        original = path.read_bytes()
        save_system(path, {'terrain': {}}, original)
        backups = list((self.systems / '.map-backups').glob('*/originals/*'))
        self.assertTrue(any(p.read_bytes() == original for p in backups))
        with self.assertRaises(ValueError):
            save_system(path, {'terrain': {'stale': {}}}, original)
        self.assertEqual(json.loads(path.read_text()), {'terrain': {}})

    def test_generators_import_from_an_unrelated_working_folder(self):
        source = str(Path(__file__).resolve().parents[1])
        result = subprocess.run([sys.executable, '-c',
                                 'import sys; sys.path.insert(0, sys.argv[1]); '
                                 'import MapGeneration; import ToolsWindow', source],
                                cwd=self.base, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_reference_data_uses_bundle_directory(self):
        from AppPaths import get_resource_path
        with patch.object(sys, '_MEIPASS', str(self.base), create=True):
            self.assertEqual(get_resource_path('scripts/Referance/shipData.yaml'),
                             self.base / 'scripts/Referance/shipData.yaml')


class ToolsWindowTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.editor = Mock(root=self.root, tools_window=None)
        ToolsWindow.open_tools(self.editor)

    def button(self, text):
        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)
        return next(w for w in descendants(self.editor.tools_window)
                    if w.winfo_class() == 'TButton' and w.cget('text') == text)

    def test_single_window_and_cancelled_export(self):
        first = self.editor.tools_window
        ToolsWindow.open_tools(self.editor)
        self.assertIs(first, self.editor.tools_window)
        with patch.object(ToolsWindow.filedialog, 'asksaveasfilename', return_value=''), \
                patch.object(ToolsWindow, 'export_jump_table') as export:
            self.button('Export Jump Table…').invoke()
        export.assert_not_called()

    def test_export_action_uses_configured_path_and_reports_error(self):
        with patch.object(ToolsWindow.EditorSettings, 'get_data_path', return_value='configured'), \
                patch.object(ToolsWindow.filedialog, 'asksaveasfilename', return_value='output.json'), \
                patch.object(ToolsWindow, 'export_system_info', side_effect=OSError('Disk full')) as export, \
                patch.object(ToolsWindow.messagebox, 'showerror') as error:
            self.button('Export System Info…').invoke()
        export.assert_called_once_with('configured', 'output.json')
        self.assertIn('Disk full', error.call_args.args)

    def test_fcs_does_not_modify_open_system_editors(self):
        child = tk.Toplevel(self.root)
        child.confirm_pending_changes = Mock()
        with patch.object(ToolsWindow.generate_fcs_zones_all, 'run_tool') as run, \
                patch.object(ToolsWindow.messagebox, 'showinfo'):
            self.button('Generate FCS Zones…').invoke()
        run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
