"""Draft a store's cost model from its own Shopify catalogue.

Shopify already holds each variant's price, stock and, when the merchant fills it
in, its unit cost ("Cost per item"). This reads them once and writes a starting
cost model, so a merchant reviews costs instead of typing a catalogue by hand.

Nothing is guessed: a variant without a cost in Shopify is left out and listed, so
the pipeline's Unknown SKU check blocks publication until its cost is declared.
An existing cost model is never overwritten.

Needs read_products and read_inventory.

Usage:  python3 src/bootstrap_costs.py
        python3 src/bootstrap_costs.py --output costs.private.json
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
    args = parser.parse_args()
    output = args.output if os.path.isabs(args.output) else os.path.join(BASE, args.output)
    if os.path.exists(output):
        print("%s already exists; it is never overwritten. Choose another --output." % output)
        return 1
    try:
        shop, variants = fetch_catalogue(Client.from_env())
    except ShopifyError as exc:
        print("ERROR: %s" % exc)
        return 1

    model, missing_cost, missing_sku = draft_model(shop, variants)
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


if __name__ == "__main__":
    sys.exit(main())
