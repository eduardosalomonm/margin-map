import datetime
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from xml.etree import ElementTree as ET
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from excel_input import build_inputs, read_sheet, shared_strings, sheet_paths
from make_demo_workbook import build_workbook
from transform import build_rows


@unittest.skipUnless(os.environ.get("MARGIN_MAP_SOFFICE"), "Optional native recalculation: set MARGIN_MAP_SOFFICE")
class NativeWorkbook(unittest.TestCase):
    def test_recalculation_matches_pipeline_for_sample_and_custom_catalogue(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile = root / "profile" / "user"
            profile.mkdir(parents=True)
            (profile / "registrymodifications.xcu").write_text(
                '<oor:items xmlns:oor="http://openoffice.org/2001/registry">'
                '<item oor:path="/org.openoffice.Office.Calc/Formula/Load">'
                '<prop oor:name="OOXMLRecalcMode" oor:op="fuse"><value>0</value></prop>'
                '</item></oor:items>')
            original = root / "original.xlsx"
            build_workbook(str(original), as_of=datetime.date(2026, 10, 22))
            for variant in ("sample", "renamed-scenario", "renamed-actual", "uncovered-actual"):
                with self.subTest(variant=variant):
                    source = root / (variant + ".xlsx")
                    with zipfile.ZipFile(original) as archive, zipfile.ZipFile(source, "w") as target:
                        paths = sheet_paths(archive)
                        changes = {paths["Catalogue"]: {"D3": "15.5", "E3": "72", "H7": "STORE-A:2| SKU-C:1"},
                                   paths["Orders"]: {"K3": "FALSE"}}
                        if variant.endswith("-actual"):
                            changes[paths["Settings"]] = {"B11": "Actual"}
                        if variant == "uncovered-actual":
                            pricing = read_sheet(archive, paths["Pricing & promotions"], shared_strings(archive))
                            first_cost = next(index + 2 for index, row in enumerate(pricing)
                                              if "Cost effective from" in row)
                            changes[paths["Pricing & promotions"]] = {"B%d" % first_cost: "2026-06-01"}
                        for member in archive.infolist():
                            data = archive.read(member.filename)
                            if variant != "sample" and member.filename.endswith(".xml"):
                                data = data.replace(b"SKU-A", b"STORE-A")
                            if member.filename in paths.values():
                                sheet = ET.fromstring(data)
                                for cell in sheet.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}c"):
                                    value = changes.get(member.filename, {}).get(cell.attrib["r"]) if variant != "sample" else None
                                    if value is not None:
                                        for node in cell.iter():
                                            if node.tag.endswith(("}t", "}v")):
                                                node.text = value
                                    if any(node.tag.endswith("}f") for node in cell):
                                        for node in list(cell):
                                            if node.tag.endswith("}v"):
                                                cell.remove(node)
                                data = ET.tostring(sheet)
                            target.writestr(member, data)
                    output = root / "recalculated"
                    output.mkdir(exist_ok=True)
                    process = subprocess.run([
                        os.environ["MARGIN_MAP_SOFFICE"],
                        "-env:UserInstallation=" + (root / "profile").as_uri(),
                        "--headless", "--convert-to", "xlsx", "--outdir", str(output), str(source)
                    ], capture_output=True, text=True, timeout=90)
                    self.assertEqual(process.returncode, 0, process.stderr)
                    calculated = output / source.name
                    costs, snapshot = build_inputs(str(calculated))
                    expected = build_rows(snapshot, costs)
                    with zipfile.ZipFile(calculated) as archive:
                        paths = sheet_paths(archive)
                        strings = shared_strings(archive)
                        orders = read_sheet(archive, paths["Orders"], strings)[2:]
                        dashboard = read_sheet(archive, paths["Dashboard"], strings)
                        charts = [name for name in archive.namelist() if name.startswith("xl/charts/chart")]
                    self.assertEqual(len(orders), len(expected))
                    for order, result in zip(orders, expected):
                        if result["coste_total"] is None:
                            self.assertEqual(order[15], "#N/A")
                        else:
                            self.assertAlmostEqual(float(order[15]), result["coste_total"], places=2)
                    if variant == "uncovered-actual":
                        self.assertTrue(any(result["coste_total"] is None for result in expected))
                        self.assertEqual(dashboard[10][1], "#N/A")
                        continue
                    self.assertAlmostEqual(float(dashboard[10][1]), sum(row["margen_contribucion"] for row in expected), places=2)
                    self.assertAlmostEqual(float(dashboard[14][4]), sum(row["resultado_variable"] for row in expected), places=2)
                    self.assertGreaterEqual(len(charts), 2)
                    if variant != "sample":
                        self.assertIn("STORE-A", costs["productos"])
                        self.assertEqual(costs["bundles"]["SKU-D"]["contiene"][0]["uds"], 2)


if __name__ == "__main__":
    unittest.main()
