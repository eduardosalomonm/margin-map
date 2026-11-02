import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from config import ConfigError, currency_code, validate_costs
from excel_input import ExcelInputError, load_workbook
from publish import currency, script_json
import run_excel_dashboard as runner


class CurrencySafety(unittest.TestCase):
    def test_currency_is_normalised_and_unsafe_input_is_rejected(self):
        model = {"productos": {"A": {"nombre": "Sample", "coste_unitario": 1, "precio_web": 2}}}
        self.assertEqual(currency_code(model), "EUR")
        for value in ("eur", "USD", "cad"):
            model["meta"] = {"moneda": value}
            validate_costs(model)
            self.assertEqual(currency_code(model), value.upper())
        for value in ('</script><script>globalThis.__currency=1</script>', "'", "EU", "EUR\n", None, 123):
            with self.subTest(value=value), self.assertRaises(ConfigError):
                model["meta"] = {"moneda": value}
                validate_costs(model)

    def test_invalid_workbook_currency_preserves_existing_deliverables(self):
        sheets = load_workbook(runner.DEFAULT_INPUT)
        for row in sheets["Settings"]:
            if row[0] == "Currency":
                row[1] = '</script><script>globalThis.__currency=1</script>'
        with tempfile.TemporaryDirectory() as directory:
            html = Path(directory) / "index.html"
            pdf = Path(directory) / "executive-summary.pdf"
            html.write_text("previous dashboard")
            pdf.write_bytes(b"previous PDF")
            with patch("excel_input.load_workbook", return_value=copy.deepcopy(sheets)):
                with self.assertRaisesRegex(ExcelInputError, "three-letter currency code"):
                    runner.build_dashboard(runner.DEFAULT_INPUT, str(html))
            self.assertEqual(html.read_text(), "previous dashboard")
            self.assertEqual(pdf.read_bytes(), b"previous PDF")

    def test_currency_output_uses_context_appropriate_encoding(self):
        with patch("publish.SYMBOL", '<img src=x onerror="alert(1)">'):
            self.assertNotIn("<img", currency(10))
            self.assertIn("&lt;img", currency(10))
        self.assertNotIn("</script>", script_json("</script>"))
        template = (Path(runner.BASE) / "src/panel_template.html").read_text()
        self.assertIn("cur={{CURRENCY_SYMBOL_JSON}}", template)
        self.assertIn("currency:{{CURRENCY_CODE_JSON}}", template)


if __name__ == "__main__":
    unittest.main()
