"""Draft a store's cost model from its own Shopify catalogue.

Shopify already holds each variant's price, stock and, when the merchant fills it
in, its unit cost ("Cost per item"). This reads them once and writes a starting
cost model, so a merchant reviews costs instead of typing a catalogue by hand.

Nothing is guessed: a variant without a cost in Shopify is left out and listed, so
the pipeline's Unknown SKU check blocks publication until its cost is declared.
An existing cost model is never overwritten.

Needs read_products and read_inventory.

With --update, an existing model is refreshed instead: new SKUs are added, stock
and prices are brought up to date, and costs are refreshed only where they still
come from Shopify. Costs, bundles and settings edited by hand are kept.

Usage:  python3 src/bootstrap_costs.py
        python3 src/bootstrap_costs.py --output costs.private.json
        python3 src/bootstrap_costs.py --update
"""

import argparse
import datetime
import json
import os
import sys

from shopify import Client, ShopifyError

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

VARIANTS_QUERY = """
query($cursor: String) {
  shop { name myshopifyDomain currencyCode ianaTimezone taxesIncluded }
  productVariants(first: 100, after: $cursor) {
    pageInfo { hasNextPage endCursor }
    edges {
      node {
        sku
        title
        displayName
        price
        inventoryQuantity
        inventoryItem { unitCost { amount } }
      }
    }
  }
}
"""


def draft_model(shop, variants, today=None):
    """Turn Shopify's shop and variant records into a cost model and a to-do list."""
    today = today or datetime.date.today().isoformat()
    products, missing_cost, missing_sku = {}, [], []
    for variant in variants:
        sku = (variant.get("sku") or "").strip()
        if not sku:
            missing_sku.append(variant.get("displayName") or variant.get("title") or "?")
            continue
        cost = ((variant.get("inventoryItem") or {}).get("unitCost") or {}).get("amount")
        if cost is None:
            missing_cost.append(sku)
            continue
        product = {
            "nombre": variant.get("displayName") or variant.get("title") or sku,
            "coste_unitario": round(float(cost), 2),
            "coste_fuente": "Shopify cost per item",
            "precio_web": round(float(variant.get("price") or 0), 2),
        }
        if variant.get("inventoryQuantity") is not None:
            product["stock"] = int(variant["inventoryQuantity"])
        products[sku] = product
    model = {
        "meta": {"marca": shop.get("name") or "Store",
                 "dominio": shop.get("myshopifyDomain") or "",
                 "moneda": shop.get("currencyCode") or "EUR",
                 "actualizado": today,
                 "nota_costes": "Drafted from Shopify; review every cost before relying on margins."},
        "iva": {"tipo_pct": 21.0, "precios_incluyen_iva": bool(shop.get("taxesIncluded", True))},
        "productos": products,
        "bundles": {},
        "descuentos": {},
    }
    return model, missing_cost, missing_sku


def merge_model(existing, drafted, today=None):
    """Refresh an existing model from a new draft without undoing manual work."""
    today = today or datetime.date.today().isoformat()
    products = existing.setdefault("productos", {})
    added, refreshed = [], 0
    for sku, fresh in drafted["productos"].items():
        current = products.get(sku)
        if current is None:
            products[sku] = fresh
            added.append(sku)
            continue
        if "stock" in fresh:
            current["stock"] = fresh["stock"]
        current["precio_web"] = fresh["precio_web"]
        if current.get("coste_fuente") == "Shopify cost per item":
            current["coste_unitario"] = fresh["coste_unitario"]
        refreshed += 1
    existing.setdefault("meta", {})["stock_actualizado"] = today
    return existing, added, refreshed


def fetch_catalogue(client):
    shop, variants, cursor = {}, [], None
    while True:
        data = client.query(VARIANTS_QUERY, {"cursor": cursor})
        shop = data.get("shop") or shop
        block = data["productVariants"]
        variants.extend(edge["node"] for edge in block["edges"])
        if not block["pageInfo"]["hasNextPage"]:
            return shop, variants
        cursor = block["pageInfo"]["endCursor"]


def main():
    parser = argparse.ArgumentParser(description="Draft a cost model from the Shopify catalogue.")
    parser.add_argument("--output", default="costs.private.json")
    parser.add_argument("--update", action="store_true",
                        help="refresh stock, prices and Shopify costs in an existing model")
    args = parser.parse_args()
    output = args.output if os.path.isabs(args.output) else os.path.join(BASE, args.output)
    if args.update:
        return update(output)
    if os.path.exists(output):
        print("%s already exists; it is never overwritten. Choose another --output." % output)
        return 1
    try:
        shop, variants = fetch_catalogue(Client.from_env())
    except ShopifyError as exc:
        print("ERROR: %s" % exc)
        return 1

    model, missing_cost, missing_sku = draft_model(shop, variants)
    model["meta"]["stock_actualizado"] = datetime.date.today().isoformat()
    if not model["productos"]:
        print("No variant has a cost per item in Shopify yet. Add costs in Shopify "
              "(Products > variant > Cost per item) or write costs.private.json by hand.")
        return 1
    with open(output, "w", encoding="utf-8") as handle:
        json.dump(model, handle, ensure_ascii=False, indent=2)
    print("Cost model drafted: %s (%d SKUs)" % (os.path.relpath(output, BASE), len(model["productos"])))
    print("Check the VAT rate (iva.tipo_pct): Shopify does not expose one store-wide rate.")
    if missing_cost:
        print("Add these %d SKUs with their unit cost; until then their sales block publication: %s"
              % (len(missing_cost), ", ".join(missing_cost[:10]) + (" ..." if len(missing_cost) > 10 else "")))
    if missing_sku:
        print("%d variants have no SKU and were skipped; give them a SKU in Shopify." % len(missing_sku))
    print("Declare bundles and, optionally, variable costs before building the dashboard.")
    return 0


def update(output):
    if not os.path.exists(output):
        print("No cost model at %s to update. Run without --update first." % output)
        return 1
    try:
        shop, variants = fetch_catalogue(Client.from_env())
    except ShopifyError as exc:
        print("Catalogue refresh skipped: %s" % exc)
        return 1
    with open(output, encoding="utf-8") as handle:
        existing = json.load(handle)
    drafted, missing_cost, _missing_sku = draft_model(shop, variants)
    model, added, refreshed = merge_model(existing, drafted)
    temporary = output + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(model, handle, ensure_ascii=False, indent=2)
    os.replace(temporary, output)  # never leave a half-written cost model
    print("Catalogue refreshed: %d SKUs updated, %d added%s."
          % (refreshed, len(added), (" (%s)" % ", ".join(added[:5])) if added else ""))
    unknown = [sku for sku in missing_cost if sku not in model["productos"]]
    if unknown:
        print("Still without a cost: %s" % ", ".join(unknown[:10]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
