"""Rebuild a dated demo without silently moving the public trading window."""
import datetime
import os
import sys
import tempfile
import unittest
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from make_demo_workbook import build_workbook, bundle_total_formula, order_cost_formula
from excel_input import build_inputs, sheet_paths, shared_strings, read_sheet
from transform import build_rows


class WorkbookGeneration(unittest.TestCase):
    def test_cost_formulas_resolve_editable_catalogue_and_bundle_contents(self):
        formula = order_cost_formula(3, 24)
        self.assertNotIn('"SKU-', formula)
        self.assertIn("MATCH(C3,'Catalogue'!$B$3:$B$100,0)", formula)
        self.assertIn("'Catalogue'!$H$3:$H$100", formula)
        self.assertIn("_xlfn.TEXTSPLIT", formula)
        self.assertIn("LOOKUP(2,", formula)
        self.assertIn("quantities", formula)
        self.assertLess(len(formula), 8192)
        solo = bundle_total_formula("H7", "E")
        self.assertIn("'Catalogue'!$E$3:$E$100", solo)
        self.assertIn('TEXTSPLIT(H7,"|")', solo)

    def test_fixed_date_rebuild_and_per_order_fee_reconciliation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "demo.xlsx")
            build_workbook(path, as_of=datetime.date(2026, 10, 22))
            costs, snapshot = build_inputs(path)
            self.assertEqual(max(order["createdAt"][:10] for order in snapshot["pedidos"]), "2026-10-22")
            rows = build_rows(snapshot, costs)
            with zipfile.ZipFile(path) as archive:
                paths = sheet_paths(archive)
                dashboard = read_sheet(archive, paths["Dashboard"], shared_strings(archive))
                orders_xml = archive.read(paths["Orders"]).decode()
            self.assertAlmostEqual(float(dashboard[14][4]), sum(row["resultado_variable"] for row in rows), places=2)
            self.assertIn("SUMIFS($M$3:", orders_xml)
            self.assertIn("K3=TRUE", orders_xml)
            self.assertIn("First line of order", orders_xml)

if __name__ == "__main__":
    unittest.main()
