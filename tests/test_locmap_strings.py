import json
import unittest

from LocMapTemplate import build_object_button, script_json


class LocalMapStringTests(unittest.TestCase):
    def test_button_preserves_names_with_quotes_backslashes_and_newlines(self):
        for name in ["Skorn's Peak", 'A "quoted" name', 'Back\\slash\nNext line', '</script>']:
            encoded = script_json(name)
            button = build_object_button(name, True, 'red')
            self.assertEqual(json.loads(encoded), name)
            self.assertEqual(button, f'addButton({encoded},function(){{highlight({encoded});}},false,"red",true)')
            self.assertNotIn('</script>', button.lower())
            self.assertNotIn('\n', button)

    def test_inline_data_cannot_end_script(self):
        data = {'description': '</ScRiPt><script>example</script>', 'name': "Skorn's Peak"}
        encoded = script_json(data)
        self.assertNotIn('<', encoded)
        self.assertEqual(json.loads(encoded), data)

    def test_default_colour_remains_null(self):
        self.assertTrue(build_object_button('Gate', False).endswith(',false,null,false)'))
