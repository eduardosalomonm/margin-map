"""The Shopify path on the cases a real store produces and a fixture rarely does.

Refunds, gift cards, unpaid orders, late-evening orders, reduced VAT rates,
tax-exclusive prices, Shopify outages and oversized queries. Each one either
changes a margin silently or stops a real store from publishing.

Run:  python3 -m unittest discover -s tests -v
"""

import copy
import io
import os
import sqlite3
import sys
import unittest
import urllib.error
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import checks  # noqa: E402
import extract  # noqa: E402
from bootstrap_costs import draft_model, merge_model  # noqa: E402
from shopify import Client, ShopifyError  # noqa: E402
from transform import build_rows, fecha_local, write_db  # noqa: E402

COSTS = {
    "meta": {"marca": "Store", "dominio": "store.myshopify.com", "moneda": "EUR"},
    "iva": {"tipo_pct": 21.0},
    "productos": {"A": {"nombre": "A", "coste_unitario": 10.0, "precio_web": 60.5}},
}


def money(amount):
    return {"shopMoney": {"amount": "%.2f" % amount}}


def line(**extra):
    item = {"title": "A", "sku": "A", "quantity": 2, "taxable": True,
            "originalUnitPriceSet": money(60.5), "discountAllocations": []}
    item.update(extra)
    return item


def order(lines, **extra):
    node = {"name": "#1", "createdAt": "2026-02-01T10:00:00Z", "cancelledAt": None, "test": False,
            "displayFinancialStatus": "PAID", "taxesIncluded": True, "discountCodes": [],
            "currentTotalDiscountsSet": money(0.0), "currentTotalTaxSet": money(0.0),
            "totalShippingPriceSet": money(0.0), "lineItems": {"edges": [{"node": l} for l in lines]}}
    node.update(extra)
    return node


class TestOrderAdjustments(unittest.TestCase):
    def test_returned_units_leave_revenue_and_cost(self):
        excluded = {}
        rows = build_rows({"pedidos": [order([line(currentQuantity=1)])]}, COSTS, excluded)
        self.assertEqual(rows[0]["unidades"], 1)
        self.assertAlmostEqual(rows[0]["ingreso_neto"], 50.0, places=2)
        self.assertAlmostEqual(rows[0]["margen_contribucion"], 40.0, places=2)
        self.assertEqual(excluded["unidades_devueltas"], 1)

    def test_a_fully_returned_order_sells_nothing_but_keeps_its_costs(self):
        costs = dict(COSTS, costes_variables={"logistica_por_pedido": 5.0, "comision_pago_pct": 2.0})
        rows = build_rows({"pedidos": [order([line(currentQuantity=0)], displayFinancialStatus="REFUNDED",
                                             totalRefundedSet=money(121.0))]}, costs)
        self.assertEqual([(r["unidades"], r["ingreso_neto"]) for r in rows], [(0, 0.0)])
        # Parcel and payment fee were still paid: 5.00 + 2% of the 121.00 charged.
        self.assertAlmostEqual(rows[0]["coste_logistica"], 5.0, places=2)
        self.assertAlmostEqual(rows[0]["comision_pago"], 2.42, places=2)
        self.assertAlmostEqual(rows[0]["resultado_variable"], -7.42, places=2)

    def test_money_refunded_without_a_return_reduces_sales(self):
        excluded = {}
        rows = build_rows({"pedidos": [order([line()], displayFinancialStatus="PARTIALLY_REFUNDED",
                                             totalRefundedSet=money(12.10))]}, COSTS, excluded)
        self.assertAlmostEqual(rows[0]["ingreso_con_iva"], 108.9, places=2)
        self.assertAlmostEqual(rows[0]["ingreso_neto"], 90.0, places=2)
        self.assertEqual(excluded["reembolsos_sin_devolucion"], 1)
        self.assertAlmostEqual(excluded["importe_reembolsado_sin_devolucion"], 12.1, places=2)

    def test_returned_units_are_not_deducted_twice(self):
        excluded = {}
        rows = build_rows({"pedidos": [order([line(currentQuantity=1)], totalRefundedSet=money(60.5))]},
                          COSTS, excluded)
        self.assertAlmostEqual(rows[0]["ingreso_con_iva"], 60.5, places=2)
        self.assertNotIn("reembolsos_sin_devolucion", excluded)

    def test_an_empty_tax_list_means_no_tax_not_the_default_rate(self):
        for included, expected in ((True, 121.0), (False, 121.0)):
            with self.subTest(taxes_included=included):
                item = line(quantity=1, originalUnitPriceSet=money(121.0), taxLines=[])
                row = build_rows({"pedidos": [order([item], taxesIncluded=included)]}, COSTS)[0]
                self.assertAlmostEqual(row["ingreso_neto"], expected, places=2)
                self.assertAlmostEqual(row["ingreso_con_iva"], 121.0, places=2)

    def test_gift_cards_and_unpaid_orders_are_excluded_and_counted(self):
        excluded = {}
        snapshot = {"pedidos": [order([line(), line(sku="", isGiftCard=True)]),
                                order([line()], name="#2", displayFinancialStatus="VOIDED")]}
        rows = build_rows(snapshot, COSTS, excluded)
        self.assertEqual([row["pedido"] for row in rows], ["#1"])
        self.assertEqual(excluded, {"tarjetas_regalo": 1, "pedidos_sin_pago": 1})

    def test_dates_follow_the_shop_timezone(self):
        self.assertEqual(fecha_local("2026-01-31T23:30:00Z", "Europe/Madrid")[:7]
                         if sys.version_info >= (3, 9) else "2026-02", "2026-02")
        self.assertEqual(fecha_local("2026-01-31T23:30:00Z", None), "2026-01-31")
        self.assertEqual(fecha_local("2026-01-31T23:30:00Z", "Not/AZone"), "2026-01-31")

    def test_tax_lines_set_the_real_vat_amount(self):
        # A reduced 10% rate: 121.00 paid includes 11.00 of VAT, not the 21% default.
        item = line(quantity=1, originalUnitPriceSet=money(121.0),
                    taxLines=[{"ratePercentage": 10.0, "priceSet": money(11.0)}])
        row = build_rows({"pedidos": [order([item])]}, COSTS)[0]
        self.assertAlmostEqual(row["ingreso_neto"], 110.0, places=2)

    def test_tax_exclusive_prices_are_net_and_vat_is_added_on_top(self):
        item = line(quantity=1, originalUnitPriceSet=money(50.0))
        row = build_rows({"pedidos": [order([item], taxesIncluded=False)]}, COSTS)[0]
        self.assertAlmostEqual(row["ingreso_neto"], 50.0, places=2)
        self.assertAlmostEqual(row["ingreso_con_iva"], 60.5, places=2)

    def test_shipping_after_discounts_is_preferred(self):
        costs = dict(COSTS, costes_variables={"logistica_por_pedido": 0})
        snapshot = {"pedidos": [order([line()], totalShippingPriceSet=money(6.05),
                                      currentShippingPriceSet=money(0.0))]}
        self.assertEqual(sum(r["ingreso_envio"] for r in build_rows(snapshot, costs)), 0.0)


class TestShopifyChecks(unittest.TestCase):
    def database(self, rows, excluded=None):
        conn = sqlite3.connect(":memory:")
        columns = list(rows[0])
        conn.execute("CREATE TABLE lineas (%s)" % ", ".join(columns))
        conn.executemany("INSERT INTO lineas VALUES (%s)" % ",".join("?" * len(columns)),
                         [tuple(row[c] for c in columns) for row in rows])
        conn.execute("CREATE TABLE exclusiones (motivo TEXT, cantidad INTEGER)")
        conn.executemany("INSERT INTO exclusiones VALUES (?, ?)", sorted((excluded or {}).items()))
        return conn

    def test_a_live_price_change_warns_instead_of_blocking(self):
        rows = build_rows({"pedidos": [order([line(originalUnitPriceSet=money(55.0))])]}, COSTS)
        result = checks.run_all(self.database(rows), COSTS)
        self.assertFalse(result.errores)
        self.assertTrue(any(c == "Catalogue price vs charged price" for c, _ in result.avisos))

    def test_excluded_orders_are_reported(self):
        excluded = {}
        rows = build_rows({"pedidos": [order([line(), line(sku="", isGiftCard=True)])]}, COSTS, excluded)
        result = checks.run_all(self.database(rows, excluded), COSTS)
        self.assertTrue(any("gift-card" in message for _, message in result.avisos))


def response(body):
    result = MagicMock()
    result.__enter__.return_value.read.return_value = __import__("json").dumps(body).encode()
    result.__enter__.return_value.headers = {}
    return result


class TestShopifyClient(unittest.TestCase):
    def setUp(self):
        sleeper = patch("shopify.time.sleep")
        sleeper.start()
        self.addCleanup(sleeper.stop)

    def test_outages_and_timeouts_are_retried(self):
        outage = urllib.error.HTTPError("https://x", 503, "down", {}, io.BytesIO(b""))
        for failure in (outage, urllib.error.URLError("timeout")):
            with self.subTest(failure=failure):
                with patch("shopify.urllib.request.urlopen",
                           side_effect=[failure, response({"data": {"ok": True}})]):
                    self.assertEqual(Client("s.myshopify.com", "t").query("{}"), {"ok": True})

    def test_error_codes_are_actionable_but_messages_stay_private(self):
        errors = [{"message": "private detail", "extensions": {"code": "ACCESS_DENIED"}}]
        with patch("shopify.urllib.request.urlopen", return_value=response({"errors": errors})):
            with self.assertRaises(ShopifyError) as error:
                Client("s.myshopify.com", "t").query("{}")
        self.assertIn("ACCESS_DENIED", str(error.exception))
        self.assertIn("read_orders", str(error.exception))
        self.assertNotIn("private detail", str(error.exception))

    def test_oversized_pages_shrink_until_shopify_accepts_them(self):
        client = MagicMock()
        page = {"shop": {"ianaTimezone": "Europe/Madrid"},
                "orders": {"pageInfo": {"hasNextPage": False}, "edges": []}}
        client.query.side_effect = [ShopifyError("too big", ("MAX_COST_EXCEEDED",)), page]
        shop = {}
        self.assertEqual(extract.fetch_orders(client, shop=shop), [])
        first, second = [call.args[1]["first"] for call in client.query.call_args_list]
        self.assertLess(second, first)
        self.assertEqual(shop["ianaTimezone"], "Europe/Madrid")


class TestCostBootstrap(unittest.TestCase):
    def test_draft_uses_shopify_costs_and_never_invents_one(self):
        shop = {"name": "Store", "myshopifyDomain": "s.myshopify.com", "currencyCode": "USD",
                "taxesIncluded": False}
        variants = [
            {"sku": "A", "displayName": "Serum", "price": "30.00", "inventoryQuantity": 12,
             "inventoryItem": {"unitCost": {"amount": "7.50"}}},
            {"sku": "B", "displayName": "Balm", "price": "12.00", "inventoryItem": {"unitCost": None}},
            {"sku": "", "displayName": "No SKU", "price": "5.00"},
        ]
        model, missing_cost, missing_sku = draft_model(shop, variants, today="2026-10-31")
        self.assertEqual(model["productos"]["A"]["coste_unitario"], 7.5)
        self.assertEqual(model["productos"]["A"]["stock"], 12)
        self.assertNotIn("B", model["productos"])
        self.assertEqual((missing_cost, missing_sku), (["B"], ["No SKU"]))
        self.assertEqual(model["meta"]["moneda"], "USD")
        self.assertFalse(model["iva"]["precios_incluyen_iva"])
        self.assertNotIn("objetivo", model)  # a sales target is optional


class TestLiveStoreTolerance(TestShopifyChecks):
    def test_discounts_summarise_per_code_and_automatic_discounts_once(self):
        lines = [line(quantity=1, discountAllocations=[{"allocatedAmountSet": money(6.05)}])
                 for _ in range(30)]
        codes = lambda i: ["X"] if i % 2 else (["Z"] if i % 3 == 0 else [])
        snapshot = {"pedidos": [order([l], name="#%d" % i, discountCodes=codes(i))
                                for i, l in enumerate(lines)]}
        # X is declared and valid; Z is undeclared; the rest are automatic discounts.
        costs = dict(COSTS, descuentos={"X": {"porcentaje": 10}})
        result = checks.run_all(self.database(build_rows(snapshot, costs)), costs)
        discount = [m for c, m in result.avisos if c == "Discount rule vs line allocation"]
        self.assertEqual(len(discount), 2)

    def test_a_vat_change_on_a_live_store_warns(self):
        snapshot = {"pedidos": [order([line()]), order([line(taxable=False)], name="#2")]}
        result = checks.run_all(self.database(build_rows(snapshot, COSTS)), COSTS)
        self.assertFalse([m for c, m in result.errores if c == "VAT consistency"])
        self.assertTrue([m for c, m in result.avisos if c == "VAT consistency"])


class TestDashboardReading(unittest.TestCase):
    def test_cover_uses_the_days_actually_observed(self):
        import publish
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE lineas (fecha TEXT, sku TEXT, unidades INTEGER)")
        conn.executemany("INSERT INTO lineas VALUES (?, 'A', 1)",
                         [("2026-10-%02d" % day,) for day in range(1, 31)])
        costs = {"productos": {"A": {"nombre": "A", "stock": 60}}}
        cover = publish.inventory_metrics(conn, costs)[0]["cover_weeks"]
        # 30 units in 30 days is 7 a week: 60 units last about 8.6 weeks, not 25.7.
        self.assertAlmostEqual(cover, 60 / 7.0, places=1)


class TestCostRefresh(unittest.TestCase):
    def test_refresh_adds_skus_and_updates_stock_without_undoing_manual_costs(self):
        existing = {"meta": {}, "productos": {
            "A": {"nombre": "A", "coste_unitario": 9.0, "coste_fuente": "Supplier invoice", "precio_web": 30.0, "stock": 50},
            "B": {"nombre": "B", "coste_unitario": 4.0, "coste_fuente": "Shopify cost per item", "precio_web": 12.0},
        }}
        drafted = {"productos": {
            "A": {"nombre": "A", "coste_unitario": 7.0, "coste_fuente": "Shopify cost per item", "precio_web": 32.0, "stock": 20},
            "B": {"nombre": "B", "coste_unitario": 4.5, "coste_fuente": "Shopify cost per item", "precio_web": 12.0},
            "C": {"nombre": "C", "coste_unitario": 2.0, "coste_fuente": "Shopify cost per item", "precio_web": 8.0},
        }}
        model, added, refreshed = merge_model(existing, drafted, today="2026-11-01")
        self.assertEqual(model["productos"]["A"]["coste_unitario"], 9.0)  # manual cost kept
        self.assertEqual(model["productos"]["A"]["stock"], 20)
        self.assertEqual(model["productos"]["A"]["precio_web"], 32.0)
        self.assertEqual(model["productos"]["B"]["coste_unitario"], 4.5)  # Shopify cost refreshed
        self.assertEqual((added, refreshed), (["C"], 2))
        self.assertEqual(model["meta"]["stock_actualizado"], "2026-11-01")


if __name__ == "__main__":
    unittest.main()
