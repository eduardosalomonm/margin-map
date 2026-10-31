"""The dashboard says where its numbers come from, and labels a sample store once.

A private Shopify store must never be shown as a demo, and a sample store must
never pass for a real one.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import publish  # noqa: E402
from config import data_source  # noqa: E402


class TestDataSource(unittest.TestCase):
    def test_private_shopify_store_is_not_labelled_as_a_sample(self):
        costs = {"meta": {"marca": "Store", "dominio": "store.myshopify.com"}}
        self.assertEqual(data_source(costs), ("Shopify Admin API", False))
        self.assertIn("Connected to Shopify", publish.source_note(costs))

    def test_excel_import_names_its_source(self):
        costs = {"meta": {"dominio": "shop.es", "actualizado": "from Excel"}}
        self.assertEqual(data_source(costs), ("Excel import", False))
        self.assertIn("Excel import", publish.source_note(costs))

    def test_sample_store_says_so_and_points_to_a_real_connection(self):
        for meta in ({"dominio": "lumavale.example", "actualizado": "from Excel"},
                     {"dominio": "store.myshopify.com", "demo": True}):
            with self.subTest(meta=meta):
                self.assertTrue(data_source({"meta": meta})[1])
                note = publish.source_note({"meta": meta})
                self.assertIn("Sample store", note)
                self.assertIn("Connect a Shopify store", note)


if __name__ == "__main__":
    unittest.main()
