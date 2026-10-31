import os
import sys
import unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'src'))
import checks
from publish import controls_block, alerts_block

class WarningVisibility(unittest.TestCase):
    def test_warning_details_are_visible_and_escaped(self):
        result = checks.Resultado()
        result.aviso(checks.CONTROL_NAMES[0], 'Unallocated cost <script>example</script>')
        markup = controls_block(result)
        self.assertIn('Unallocated cost &lt;script&gt;', markup)
        self.assertNotIn('<script>', markup)
        self.assertIn('Review needed', alerts_block(result))
        self.assertNotIn('Ready to use', alerts_block(result))

    def test_clean_data_keeps_ready_status(self):
        self.assertIn('Ready to use', alerts_block(checks.Resultado()))
