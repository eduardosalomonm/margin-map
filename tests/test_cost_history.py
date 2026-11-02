import copy
import contextlib
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile
from xml.etree import ElementTree as ET
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))

from bootstrap_costs import draft_model, merge_model
from config import ConfigError, validate_costs, variable_cost_gaps
from excel_input import ExcelInputError, build_inputs, load_workbook, variable_cost_inputs
from test_shopify_path import COSTS, line, order
from transform import build_rows
import run_excel_dashboard as runner
import bootstrap_costs


class CostHistory(unittest.TestCase):
    def setUp(self):
        self.costs = copy.deepcopy(COSTS)
        self.costs["productos"]["A"]["costes"] = [
            {"desde": "2026-01-01", "coste_unitario": 8},
            {"desde": "2026-03-01", "coste_unitario": 12},
        ]

    def rows(self, costs=None, sku="A"):
        snapshot = {"pedidos": [order([line(sku=sku, quantity=1)], createdAt=date + "T12:00:00Z")
                                for date in ("2025-12-31", "2026-02-28", "2026-03-01")]}
        return build_rows(snapshot, costs or self.costs)

    def test_sale_dates_choose_cost_and_uncovered_history_stays_unknown(self):
        self.assertEqual([row["coste_unitario"] for row in self.rows()], [None, 8, 12])
        self.assertIsNone(self.rows()[0]["margen_contribucion"])
        self.costs["productos"]["A"]["coste_unitario"] = 99
        self.assertEqual([row["coste_unitario"] for row in self.rows()], [None, 8, 12])

    def test_bundles_use_each_components_effective_cost(self):
        self.costs["productos"]["B"] = {"nombre": "B", "coste_unitario": 2, "precio_web": 5}
        self.costs["bundles"] = {"duo": {"sku": "D", "nombre": "Duo", "precio_web": 110,
                                        "contiene": [{"sku": "A", "uds": 2}, {"sku": "B", "uds": 1}]}}
        self.assertEqual([row["coste_unitario"] for row in self.rows(sku="D")], [None, 18, 26])

    def test_scenario_uses_catalogue_without_mutating_history(self):
        self.costs["meta"]["pricing_model"] = "scenario"
        before = copy.deepcopy(self.costs)
        self.assertEqual([row["coste_unitario"] for row in self.rows()], [10, 10, 10])
        self.assertEqual(self.costs, before)

    def test_invalid_dates_duplicates_and_costs_fail_early(self):
        for history in ([], [{"desde": "2026-02-30", "coste_unitario": 1}],
                        [{"desde": "2026-01-01", "coste_unitario": -1}],
                        [{"desde": "2026-01-01", "coste_unitario": 1}] * 2):
            with self.subTest(history=history), self.assertRaises(ConfigError):
                self.costs["productos"]["A"]["costes"] = history
                validate_costs(self.costs)

    def test_shopify_refresh_appends_observation_without_repricing_old_sales(self):
        self.costs["productos"]["A"]["coste_fuente"] = "Shopify cost per item"
        updated = copy.deepcopy(self.costs)
        updated["productos"]["A"]["coste_unitario"] = 20
        merge_model(self.costs, updated, "2026-04-01")
        self.assertEqual([row["coste_unitario"] for row in self.rows()], [None, 8, 12])
        self.assertEqual(self.costs["productos"]["A"]["costes"][-1]["coste_unitario"], 20)
        merge_model(self.costs, updated, "2026-04-02")
        self.assertEqual(len(self.costs["productos"]["A"]["costes"]), 3)

    def test_bootstrap_does_not_invent_costs_before_the_observation(self):
        costs, _, _ = draft_model({}, [{"sku": "A", "price": "60.5",
                                       "inventoryItem": {"unitCost": {"amount": "10"}}}], "2026-03-01")
        self.assertEqual([row["coste_unitario"] for row in self.rows(costs)], [None, None, 10])

    def test_excel_imports_history_and_rejects_unsorted_dates(self):
        workbook = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "unit-economics-input.xlsx")
        sheets = load_workbook(workbook)
        for row in sheets["Settings"]:
            if row[0] == "Pricing model":
                row[1] = "Actual"
        pricing = sheets["Pricing & promotions"]
        headers = ["SKU", "Cost effective from", "Unit cost ex VAT", "Cost evidence"]
        if headers in pricing:
            del pricing[pricing.index(headers) - 1:]
        pricing.extend([[""], headers, ["SKU-A", "2025-01-01", "8", "Example"]])
        with patch("excel_input.load_workbook", return_value=sheets):
            costs, _ = build_inputs(workbook)
            self.assertEqual(costs["productos"]["SKU-A"]["costes"][0]["coste_unitario"], 8)
            pricing.append(["SKU-A", "2024-01-01", "7", "Example"])
            with self.assertRaisesRegex(ExcelInputError, "oldest first"):
                build_inputs(workbook)

    def test_workbook_actual_mode_applies_history_to_products_and_bundles(self):
        sheets = load_workbook(runner.DEFAULT_INPUT)
        for row in sheets["Settings"]:
            if row[0] == "Pricing model":
                row[1] = "Actual"
        with patch("excel_input.load_workbook", return_value=sheets):
            costs, snapshot = build_inputs(runner.DEFAULT_INPUT)
        rows = build_rows(snapshot, costs)
        early = [row for row in rows if row["sku"] == "SKU-A" and row["fecha"] < "2026-07-01"]
        late = [row for row in rows if row["sku"] == "SKU-A" and row["fecha"] >= "2026-07-01"]
        bundles = [row for row in rows if row["sku"] == "SKU-D" and row["fecha"] < "2026-07-01"]
        self.assertTrue(early and late and bundles)
        self.assertTrue(all(row["coste_unitario"] == 11.8 for row in early))
        self.assertTrue(all(row["coste_unitario"] == 12.8 for row in late))
        self.assertTrue(all(abs(row["coste_unitario"] - 15.7) < 0.001 for row in bundles))
        with zipfile.ZipFile(runner.DEFAULT_INPUT) as archive:
            formulas = [node.text for name in archive.namelist() if name.startswith("xl/worksheets/sheet")
                        for node in ET.fromstring(archive.read(name)).iter()
                        if node.tag.endswith("}f")]
        self.assertTrue(any("LOOKUP(2," in formula for formula in formulas))
        self.assertLess(max(map(len, formulas)), 8192)

    def test_same_day_observation_updates_and_manual_costs_are_preserved(self):
        self.costs["productos"]["A"]["coste_fuente"] = "Shopify cost per item"
        fresh = copy.deepcopy(self.costs)
        fresh["productos"]["A"]["coste_unitario"] = 15
        merge_model(self.costs, fresh, "2026-03-01")
        self.assertEqual(len(self.costs["productos"]["A"]["costes"]), 2)
        self.assertEqual(self.costs["productos"]["A"]["costes"][-1]["coste_unitario"], 15)
        self.costs["productos"]["A"]["coste_fuente"] = "Manual invoice"
        before = copy.deepcopy(self.costs["productos"]["A"]["costes"])
        fresh["productos"]["A"]["coste_unitario"] = 20
        merge_model(self.costs, fresh, "2026-04-01")
        self.assertEqual(self.costs["productos"]["A"]["costes"], before)
        self.assertEqual(self.costs["productos"]["A"]["coste_unitario"], 15)

    def test_failed_refresh_preserves_file_and_explains_invalid_history(self):
        import json
        self.costs["productos"]["A"]["costes"][0]["desde"] = "invalid"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "costs.json"
            path.write_text(json.dumps(self.costs))
            before = path.read_bytes()
            with patch.object(bootstrap_costs.Client, "from_env"), patch.object(bootstrap_costs, "fetch_catalogue", return_value=({}, [])):
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    self.assertEqual(bootstrap_costs.update(str(path)), 1)
            self.assertIn("Catalogue refresh skipped", output.getvalue())
            self.assertEqual(path.read_bytes(), before)


class CostCoverage(unittest.TestCase):
    def test_shipping_income_does_not_turn_unknown_fulfilment_into_zero(self):
        model, shipping = variable_cost_inputs({"Shipping charged per order incl VAT": "4.95"}, [])
        self.assertEqual(shipping, 4.95)
        self.assertNotIn("logistica_por_pedido", model)
        self.assertIn("fulfilment cost", variable_cost_gaps({"costes_variables": model}, []))

    def test_duplicate_month_is_rejected_even_when_first_amount_is_blank(self):
        rows = [["Month (YYYY-MM)", "Advertising spend ex VAT"], ["2026-01", ""], ["2026-01", "0"]]
        with self.assertRaisesRegex(ExcelInputError, "listed twice"):
            variable_cost_inputs({}, rows)

    def test_zero_is_declared_and_blank_advertising_is_unknown(self):
        settings = {"Fulfilment cost per order ex VAT": "0", "Payment fee (%)": "0",
                    "Payment fee per order": "0"}
        rows = [["Month (YYYY-MM)", "Advertising spend ex VAT"], ["2026-01", ""], ["2026-02", "0"]]
        model, _ = variable_cost_inputs(settings, rows)
        gaps = variable_cost_gaps({"costes_variables": model}, {"2026-01", "2026-02"})
        self.assertEqual(gaps, ["advertising for 2026-01"])

    def test_incomplete_inputs_stay_visible_in_html_and_pdf(self):
        costs, snapshot = build_inputs(runner.DEFAULT_INPUT)
        del costs["costes_variables"]["comision_pago_fija"]
        del costs["costes_variables"]["publicidad"]["2026-10"]
        with tempfile.TemporaryDirectory() as directory:
            with patch("excel_input.build_inputs", return_value=(costs, snapshot)):
                with contextlib.redirect_stdout(io.StringIO()):
                    html_path, pdf_path = runner.build_dashboard(runner.DEFAULT_INPUT, str(Path(directory) / "index.html"))
            page = Path(html_path).read_text()
            pdf = Path(pdf_path).read_bytes().decode("latin-1")
        self.assertIn("Incomplete costs · known-cost subtotal only", page)
        self.assertIn('"incomplete":true', page.replace(" ", ""))
        self.assertIn("fixed payment fee", page)
        self.assertIn("advertising for 2026-10", page)
        self.assertIn("Known-cost subtotal", pdf)
        self.assertIn("excluded, not confirmed zero", pdf)
        self.assertIn("Scenario: current catalogue costs", pdf)


if __name__ == "__main__":
    unittest.main()
