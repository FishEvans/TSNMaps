"""Tk integration checks; run with py -m unittest discover -s tests.

Map reads/writes are mocked so the editor's load-time migrations cannot
change real system files. Requires Tk and the project's reference data.
"""
import copy
import sys
import unittest
from unittest.mock import patch

import SystemEditor as editor


class StationOverviewTests(unittest.TestCase):
    def setUp(self):
        self.root = editor.tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.errors = []
        self.root.report_callback_exception = lambda *args: self.errors.append(args)
        self.state = {}
        station = dict(type='station', sides=['USFP'], hull='starbase_command',
                       coordinate=[0, 0, 0], description='Keep this description',
                       cargo={}, teams={}, facilities=['Docking'])
        data = dict(metadata={}, terrain={}, sensor_relay={}, objects={
            'Alpha': station,
            'Beta': dict(copy.deepcopy(station), type='platform', coordinate=[10000, 0, 0]),
            'Other': dict(copy.deepcopy(station), sides=['Pirate'], coordinate=[20000, 0, 0]),
            'Static': dict(copy.deepcopy(station), type='static', coordinate=[30000, 0, 0]),
        })
        # Capture the editor's closures without adding a production test API.
        def capture(frame, event, result):
            if frame.f_code is editor.open_system_editor.__code__ and event == 'return':
                self.state.update(frame.f_locals)
        previous_profile = sys.getprofile()
        try:
            sys.setprofile(capture)
            with patch.object(editor.SystemMap, '_load', return_value=data), \
                    patch.object(editor.SystemMap, 'save'), \
                    patch.object(editor.messagebox, 'showwarning'), \
                    patch.object(editor.messagebox, 'showerror') as error:
                self.win = editor.open_system_editor('OverviewTest.json')
            self.assertIsInstance(self.win, editor.tk.Toplevel, error.call_args)
        finally:
            sys.setprofile(previous_profile)
        self.win.withdraw()
        self.state['show_station_list']()
        self.overview, rebuild = next(iter(self.state['overview_refreshers'].items()))
        self.ui = dict(zip(rebuild.__code__.co_freevars,
                           (cell.cell_contents for cell in rebuild.__closure__)))
        self.root.update()

    def tearDown(self):
        self.assertEqual(self.errors, [])

    def object(self, name='Alpha'):
        return self.state['sm'].get_object(name)

    def row_control(self, column, row=1):
        cell = self.ui['rows_frame'].grid_slaves(row=row, column=column)[0]
        return cell.winfo_children()[0]

    def test_conversion_and_ten_action_history(self):
        before = copy.deepcopy(self.object())
        # Exercise the actual overview dropdown, then the edit-pane button.
        self.row_control(1).set('platform')
        self.root.update()
        self.assertEqual(self.object(), dict(before, type='platform'))
        pane = self.state['edit_frame'].winfo_children()[-1]
        button = next(w for w in pane.winfo_children()
                      if isinstance(w, editor.tk.Button) and w.cget('text') == 'Convert to Station')
        button.invoke()
        self.assertEqual(self.object(), before)
        self.state['undo_stack'].clear()
        for i in range(12):
            self.state['convert_station_type']('Alpha', 'platform' if i % 2 == 0 else 'station')
        self.assertEqual(len(self.state['undo_stack']), 10)
        for _ in range(10):
            self.state['do_undo']()
        self.assertEqual(len(self.state['undo_stack']), 0)
        self.assertEqual(len(self.state['redo_stack']), 10)
        for _ in range(10):
            self.state['do_redo']()
        self.assertEqual(self.object(), before)
        self.state['do_undo']()
        self.state['convert_station_type']('Alpha', 'station')
        self.assertEqual(self.state['redo_stack'], [])

    def test_bulk_side_and_shortcuts(self):
        bulk = next(w for w in self.overview.winfo_children() if isinstance(w, editor.tk.LabelFrame))
        combos = [w for w in bulk.winfo_children() if isinstance(w, editor.ttk.Combobox)]
        combos[0].set('USFP')
        combos[1].set('Pirate')
        next(w for w in bulk.winfo_children() if isinstance(w, editor.tk.Button)).invoke()
        self.root.update()
        self.assertEqual(self.object()['sides'], ['Pirate'])
        self.assertEqual(self.object('Beta')['sides'], ['Pirate'])
        self.assertEqual(self.object('Static')['sides'], ['USFP'])
        self.assertEqual(len(self.state['undo_stack']), 1)
        # Check the shortcut even when a combobox has focus: no Cut fallback.
        control = self.row_control(2)
        control.focus_force()
        self.root.update()
        control.event_generate('<Control-z>')
        self.root.update()
        self.assertEqual(self.object()['sides'], ['USFP'])
        self.assertEqual(self.object('Beta')['sides'], ['USFP'])
        self.overview.focus_force()
        self.root.update()
        self.overview.event_generate('<Control-x>')
        self.root.update()
        self.assertEqual(self.object()['sides'], ['Pirate'])

    def test_column_drag_scroll_and_rebuild(self):
        widths = self.ui['column_widths']
        original = widths['name']
        header = self.ui['rows_frame'].grid_slaves(row=0, column=0)[0]
        grip = header.winfo_children()[0]
        grip.event_generate('<ButtonPress-1>', rootx=100)
        grip.event_generate('<B1-Motion>', rootx=220)
        self.root.update()
        self.assertEqual(widths['name'], original + 120)
        self.state['refresh_overviews']()
        self.root.update()
        self.assertEqual(widths['name'], original + 120)
        self.overview.geometry('600x350')
        self.root.update()
        canvas = self.ui['_sync_width'].__closure__[0].cell_contents
        self.assertIsInstance(canvas, editor.tk.Canvas)
        self.assertLess(canvas.xview()[1], 1)
        canvas.xview_moveto(1)
        self.assertAlmostEqual(canvas.xview()[1], 1)


if __name__ == '__main__':
    unittest.main()
