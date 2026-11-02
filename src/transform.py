"""Fase 3: transformacion. Del snapshot crudo a una fila por linea de pedido.

Salidas:
  data/pipeline.db     SQLite, para consultar y para conectar Power BI
  data/margins.csv  resumen por SKU, legible sin herramientas

No inventa nada: si un SKU no esta en costs.yml, la fila sale con coste nulo y
checks.py lo convierte en error. Un margen calculado sobre un coste inventado es
peor que no tener margen.

Uso:  python3 src/transform.py
"""

import csv
import datetime
import glob
import json
import os
import sqlite3
import sys

from config import ConfigError, costs_path, load_costs, validate_finite_values, variable_costs

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.abspath(os.environ.get("PIPELINE_DATA_DIR", os.path.join(BASE, "data")))
RAW_DIR = os.path.join(DATA_DIR, "raw")
DB_PATH = os.path.join(DATA_DIR, "pipeline.db")
CSV_PATH = os.path.join(DATA_DIR, "margins.csv")
COSTS_PATH = costs_path()


def latest_snapshot():
    """SNAPSHOT fuerza un archivo concreto; si no, el mas reciente por fecha de
    modificacion (por nombre, orders-demo.json ordena despues de una fecha)."""
    forzado = os.environ.get("SNAPSHOT")
    if forzado:
        return forzado if os.path.isabs(forzado) else os.path.join(BASE, forzado)
    files = glob.glob(os.path.join(RAW_DIR, "orders-*.json"))
    if not files:
        raise SystemExit("No snapshots exist in data/raw. Run src/extract.py first "
                         "(or src/make_demo_data.py for the synthetic demo).")
    return max(files, key=os.path.getmtime)


def money(node, field):
    """Extrae un importe de un *Set de Shopify. Devuelve None si no viene."""
    block = (node or {}).get(field) or {}
    shop_money = block.get("shopMoney") or {}
    amount = shop_money.get("amount")
    validate_finite_values(amount, "amount")
    return float(amount) if amount is not None else None


def allocated_discount(item):
    """Return Shopify's final discount allocation for a line, if supplied.

    The Admin API allocates every applicable discount to the line, including
    code-based and order-level promotions. This is more accurate than dividing an
    order total proportionally, which can incorrectly assign a shipping discount
    to merchandise revenue. Older snapshots and the minimal test fixture have no
    allocation field, so callers can explicitly use the legacy fallback.
    """
    allocations = item.get("discountAllocations")
    if allocations is None:
        return None
    total = 0.0
    for allocation in allocations:
        total += money(allocation, "allocatedAmountSet") or 0.0
    return round(total, 2)


def coste_vigente(product, fecha):
    history = product.get("costes")
    if fecha is None or not history:
        return float(product["coste_unitario"])
    eligible = [entry for entry in history if entry["desde"] <= fecha]
    return float(max(eligible, key=lambda entry: entry["desde"])["coste_unitario"]) if eligible else None


def catalogo(costs, fecha=None):
    """SKU -> nombre y coste, productos y bundles juntos.

    El coste de un bundle es la suma de sus componentes. Sin esto, la primera venta
    de un Ritual Duo entraria como SKU desconocido y se quedaria sin margen.
    """
    tabla = {}
    for sku, producto in costs["productos"].items():
        tabla[sku] = {
            "nombre": producto["nombre"],
            "coste": coste_vigente(producto, fecha),
            "es_bundle": False,
        }
    for bundle in (costs.get("bundles") or {}).values():
        sku = bundle.get("sku")
        if not sku:
            continue
        coste = 0.0
        completo = True
        for comp in bundle.get("contiene") or []:
            producto = costs["productos"].get(comp["sku"])
            if not producto:
                completo = False
                break
            unit_cost = coste_vigente(producto, fecha)
            if unit_cost is None:
                completo = False
                break
            coste += unit_cost * comp.get("uds", 1)
        if completo:
            tabla[sku] = {"nombre": bundle["nombre"], "coste": round(coste, 2),
                          "es_bundle": True}
    return tabla


def precio_catalogo(costs, sku, fecha):
    """Precio vigente ese dia, segun el historico declarado en costs.yml.

    Un precio unico no sirve: un SKU puede haber tenido varios. Comparar un pedido de 2025
    contra el precio de hoy genera errores falsos que acaban ignorandose, y un
    control que se ignora no es un control.
    """
    producto = costs["productos"].get(sku)
    if not producto:
        for bundle in (costs.get("bundles") or {}).values():
            if bundle.get("sku") == sku:
                return float(bundle["precio_web"])
        return None
    historico = producto.get("precios")
    if not historico:
        return float(producto["precio_web"])

    vigente = None
    for tramo in sorted(historico, key=lambda t: str(t["desde"])):
        desde = tramo["desde"]
        desde = desde.isoformat() if hasattr(desde, "isoformat") else str(desde)
        if fecha >= desde:
            vigente = float(tramo["precio"])
    return vigente if vigente is not None else float(producto["precio_web"])


EXCLUSION_LABELS = {
    "tarjetas_regalo": "Gift-card lines excluded",
    "pedidos_sin_pago": "Voided or expired orders excluded",
    "unidades_devueltas": "Units returned or removed",
    "reembolsos_sin_devolucion": "Orders with money refunded without a return",
    "importe_reembolsado_sin_devolucion": "Amount refunded without a return",
}

# Orders whose payment never completed: not trading, whatever their line items say.
ESTADOS_EXCLUIDOS = {"VOIDED", "EXPIRED"}


def fecha_local(created_at, zona=None):
    """The order's calendar date in the shop's timezone.

    Shopify returns UTC. An order at 23:30 UTC on 31 January is a February order
    in Madrid, and month-level figures (advertising, month to date) follow the
    shop's calendar. Without a timezone, or on Python 3.8, the UTC date is kept.
    """
    if not zona or not created_at.endswith("Z"):
        return created_at[:10]
    try:
        from zoneinfo import ZoneInfo
        instante = datetime.datetime.strptime(created_at[:19], "%Y-%m-%dT%H:%M:%S")
        instante = instante.replace(tzinfo=datetime.timezone.utc)
        return instante.astimezone(ZoneInfo(zona)).date().isoformat()
    except Exception:  # unknown zone or no zoneinfo: fall back to the stated UTC date
        return created_at[:10]


def build_rows(snapshot, costs, excluidas=None):
    """Una fila por linea de pedido, con dos correcciones que no son opcionales:

    1. El descuento final se toma de discountAllocations por linea. Es la asignacion
       de Shopify para descuentos de codigo, pedido y producto. Snapshots antiguos
       sin ese campo usan un reparto proporcional como compatibilidad, nunca como
       sustituto de una extraccion actual.
    2. Los precios de la tienda INCLUYEN IVA (taxesIncluded). Comparar un precio con
       IVA contra un coste sin IVA infla el margen. El margen se calcula ex IVA.

    Una linea cuenta por su cantidad vigente (currentQuantity): devoluciones,
    reembolsos y ediciones de pedido la reducen, y con ella ingreso y coste. Las
    tarjetas regalo no son venta de producto y se excluyen; `excluidas`, si se pasa,
    recibe el recuento de lo excluido para que se informe en lugar de perderse.
    """
    excluidas = excluidas if excluidas is not None else {}
    validate_finite_values(snapshot)
    validate_finite_values(costs)
    tipo_iva = float(costs.get("iva", {}).get("tipo_pct", 21.0))
    catalogues = {}
    rows = []
    envio_por_pedido = {}
    # What each order originally charged. Payment providers keep their fee when an
    # order is refunded, so fees are calculated on this, not on what remains.
    cobrado_original = {}
    zona = snapshot.get("zona_horaria")
    for order in snapshot["pedidos"]:
        if order.get("test") or order.get("cancelledAt"):
            continue
        if order.get("displayFinancialStatus") in ESTADOS_EXCLUIDOS:
            excluidas["pedidos_sin_pago"] = excluidas.get("pedidos_sin_pago", 0) + 1
            continue
        fecha = fecha_local(order["createdAt"], zona)
        cost_date = None if (costs.get("meta") or {}).get("pricing_model") == "scenario" else fecha
        if cost_date not in catalogues:
            catalogues[cost_date] = catalogo(costs, cost_date)
        tabla = catalogues[cost_date]
        codigos = ",".join(order.get("discountCodes") or [])
        incluye_iva = bool(order.get("taxesIncluded"))
        descuento_pedido = money(order, "currentTotalDiscountsSet") or 0.0

        # Shipping is charged once per order object. The Excel workflow writes one
        # object per line, so it records the charge on the first line of each order.
        # currentShippingPriceSet is after shipping discounts and refunds; older
        # snapshots and the Excel path only carry the total.
        envio = money(order, "currentShippingPriceSet")
        if envio is None:
            envio = money(order, "totalShippingPriceSet") or 0.0
        envio_neto = envio / (1 + tipo_iva / 100.0) if incluye_iva else envio
        cobrado, neto = envio_por_pedido.get(order["name"], (0.0, 0.0))
        envio_por_pedido[order["name"]] = (cobrado + envio, neto + envio_neto)
        envio_original = money(order, "totalShippingPriceSet")
        envio_original = envio if envio_original is None else envio_original
        cobrado_original[order["name"]] = cobrado_original.get(order["name"], 0.0) + envio_original
        filas_pedido = []
        devuelto = 0.0  # value of the units returned, as charged

        lineas = [e["node"] for e in order["lineItems"]["edges"]]
        base_total = sum((money(i, "originalUnitPriceSet") or 0.0) * (i.get("quantity") or 0)
                         for i in lineas)

        for item in lineas:
            if item.get("isGiftCard"):
                excluidas["tarjetas_regalo"] = excluidas.get("tarjetas_regalo", 0) + 1
                # A refunded gift card is in the order's refund total too; it must
                # not be read as money refunded on the products.
                pedidas = item.get("quantity") or 0
                vigentes = item.get("currentQuantity", pedidas)
                vigentes = pedidas if vigentes is None else vigentes
                devuelto += (money(item, "originalUnitPriceSet") or 0.0) * max(pedidas - vigentes, 0)
                continue
            sku = item.get("sku") or ""
            pedida = item.get("quantity") or 0
            qty = item.get("currentQuantity", pedida)
            if qty is None:
                qty = pedida
            if pedida and qty < pedida:
                excluidas["unidades_devueltas"] = excluidas.get("unidades_devueltas", 0) + pedida - qty
            qty = max(qty, 0)
            # Price and discount are stated for the quantity ordered; keep the share
            # that is still sold. A fully returned line stays as a zero-unit row, so
            # the order's fulfilment and payment fee, which were still spent, remain.
            vigente = (qty / float(pedida)) if pedida else 1.0
            bruto = money(item, "originalUnitPriceSet")
            base_linea = (bruto or 0.0) * pedida

            # 1. Shopify supplies a final allocation per line. Fall back only for
            # legacy raw snapshots that predate that field.
            descuento_linea = allocated_discount(item)
            if descuento_linea is None:
                cuota = (base_linea / base_total) if base_total else 0.0
                descuento_linea = round(descuento_pedido * cuota, 2)
            # Every amount is first stated for the quantity ordered, then scaled to
            # the quantity still sold. The difference is what was returned.
            precio_completo = base_linea - descuento_linea
            descuento_linea = round(descuento_linea * vigente, 2)
            precio_linea = round(precio_completo * vigente, 2)

            # 2. Paso a ex IVA. Las taxLines de Shopify dan el impuesto real de la
            # linea (tipos reducidos, otros paises); sin ellas se aplica el tipo
            # declarado. En tiendas sin IVA incluido, el precio ya es neto y el
            # cliente paga el impuesto encima.
            gravada = bool(item.get("taxable"))
            lineas_iva = item.get("taxLines")
            # A present list is Shopify's answer, even when empty (zero-rated or
            # exempt). Only a snapshot without the field falls back to the declared rate.
            if lineas_iva is not None:
                iva_completo = sum(money(t, "priceSet") or 0.0 for t in lineas_iva)
            elif gravada and incluye_iva:
                iva_completo = precio_completo - precio_completo / (1 + tipo_iva / 100.0)
            elif gravada:
                iva_completo = precio_completo * tipo_iva / 100.0
            else:
                iva_completo = 0.0
            iva = round(iva_completo * vigente, 2)
            if incluye_iva:
                ingreso_con_iva, ingreso_ex_iva = precio_linea, round(precio_linea - iva, 2)
                pagado_completo = precio_completo
            else:
                ingreso_con_iva, ingreso_ex_iva = round(precio_linea + iva, 2), precio_linea
                pagado_completo = precio_completo + iva_completo
            iva_implicito = round(ingreso_con_iva - ingreso_ex_iva, 2)
            devuelto += pagado_completo - ingreso_con_iva
            cobrado_original[order["name"]] += pagado_completo

            entrada = tabla.get(sku)
            coste_unit = entrada["coste"] if entrada else None
            coste = round(coste_unit * qty, 2) if coste_unit is not None else None
            margen = round(ingreso_ex_iva - coste, 2) if coste is not None else None

            filas_pedido.append({
                "pedido": order["name"],
                "fecha": fecha,
                "sku": sku,
                "titulo": item.get("title"),
                "unidades": qty,
                "precio_bruto": bruto,
                "descuento_linea": descuento_linea,
                "precio_catalogo": precio_catalogo(costs, sku, fecha),
                "coste_unitario": coste_unit,
                "ingreso_con_iva": ingreso_con_iva,
                "iva_implicito": iva_implicito,
                "ingreso_neto": ingreso_ex_iva,
                "coste_total": coste,
                "margen_contribucion": margen,
                "margen_pct": round(100.0 * margen / ingreso_ex_iva, 1) if margen is not None
                              and ingreso_ex_iva else None,
                "taxable": 1 if gravada else 0,
                "codigos_descuento": codigos,
                "estado_financiero": order.get("displayFinancialStatus"),
                "iva_pedido_declarado": money(order, "currentTotalTaxSet"),
                "envio_pedido": money(order, "totalShippingPriceSet"),
            })
        descontar_reembolso(order, filas_pedido, devuelto, envio, envio_original, excluidas)
        rows.extend(filas_pedido)
    aplicar_costes_variables(rows, envio_por_pedido, costs, cobrado_original)
    return rows


def descontar_reembolso(order, filas, devuelto, envio, envio_original, excluidas):
    """Deduct money refunded without returning items, such as a goodwill refund.

    Returned units already left the line through currentQuantity, and refunded
    shipping through the current shipping price. Whatever else Shopify refunded
    reduces the order's sales in proportion to each line, so it is neither
    counted as revenue nor lost silently.
    """
    reembolsado = money(order, "totalRefundedSet")
    if not reembolsado or not filas:
        return
    resto = round(reembolsado - devuelto - max(envio_original - envio, 0.0), 2)
    pagado = sum(fila["ingreso_con_iva"] for fila in filas)
    if resto <= 0.01 or pagado <= 0:
        return
    resto = min(resto, pagado)
    excluidas["reembolsos_sin_devolucion"] = excluidas.get("reembolsos_sin_devolucion", 0) + 1
    excluidas["importe_reembolsado_sin_devolucion"] = round(
        excluidas.get("importe_reembolsado_sin_devolucion", 0.0) + resto, 2)
    for fila, parte in zip(filas, repartir(resto, [f["ingreso_con_iva"] for f in filas])):
        if not fila["ingreso_con_iva"]:
            continue
        factor = (fila["ingreso_con_iva"] - parte) / fila["ingreso_con_iva"]
        fila["ingreso_con_iva"] = round(fila["ingreso_con_iva"] - parte, 2)
        fila["ingreso_neto"] = round(fila["ingreso_neto"] * factor, 2)
        fila["iva_implicito"] = round(fila["ingreso_con_iva"] - fila["ingreso_neto"], 2)
        if fila["coste_total"] is not None:
            fila["margen_contribucion"] = round(fila["ingreso_neto"] - fila["coste_total"], 2)
            fila["margen_pct"] = (round(100.0 * fila["margen_contribucion"] / fila["ingreso_neto"], 1)
                                  if fila["ingreso_neto"] else None)

def repartir(total, pesos):
    """Split an amount into cents by weight, so the parts add up to the total exactly.

    Rounding each share independently leaves a cent or two unexplained on a busy
    order; the largest remainders absorb those cents instead.
    """
    centimos = int(round(total * 100))
    suma = sum(pesos)
    if suma <= 0:
        pesos, suma = [1.0] * len(pesos), float(len(pesos))
    brutos = [centimos * peso / suma for peso in pesos]
    partes = [int(valor) for valor in brutos]
    orden = sorted(range(len(pesos)), key=lambda i: (-(brutos[i] - partes[i]), i))
    for indice in orden[:centimos - sum(partes)]:
        partes[indice] += 1
    return [parte / 100.0 for parte in partes]


def aplicar_costes_variables(rows, envio_por_pedido, costs, cobrado_original=None):
    """Add the optional per-order and monthly costs to each line.

    Order-level amounts (shipping charged, fulfilment, payment fees) follow each
    line's share of what the customer paid. Monthly advertising follows each line's
    share of that month's net revenue. Both are allocations, stated as such, so a
    SKU or promotion filter still adds up to the store total.
    """
    modelo = variable_costs(costs)
    campos = ("ingreso_envio", "coste_logistica", "comision_pago", "coste_publicidad",
              "resultado_variable")
    for row in rows:
        for campo in campos:
            row[campo] = None
    if modelo is None or not rows:
        return

    por_pedido = {}
    for row in rows:
        por_pedido.setdefault(row["pedido"], []).append(row)
    for pedido, lineas in por_pedido.items():
        pesos = [max(linea["ingreso_con_iva"], 0.0) for linea in lineas]
        if not any(pesos):
            pesos = [1.0] * len(lineas)  # a fully returned order still carries its costs
        envio_cobrado, envio_neto = envio_por_pedido.get(pedido, (0.0, 0.0))
        # Payment providers charge on everything the customer paid, VAT and shipping
        # included, and keep the fee when the order is later refunded.
        cobrado = (cobrado_original or {}).get(pedido)
        if cobrado is None:
            cobrado = sum(linea["ingreso_con_iva"] for linea in lineas) + envio_cobrado
        comision = cobrado * modelo["comision_pago_pct"] / 100.0 + modelo["comision_pago_fija"]
        for campo, importe in (("ingreso_envio", envio_neto),
                               ("coste_logistica", modelo["logistica_por_pedido"]),
                               ("comision_pago", comision)):
            for linea, parte in zip(lineas, repartir(importe, pesos)):
                linea[campo] = parte

    por_mes = {}
    for row in rows:
        por_mes.setdefault(row["fecha"][:7], []).append(row)
    for row in rows:
        row["coste_publicidad"] = 0.0
    for mes, importe in modelo["publicidad"].items():
        lineas = por_mes.get(mes)
        if not lineas:
            continue  # checks.py reports advertising that has no sales to land on.
        pesos = [max(linea["ingreso_neto"], 0.0) for linea in lineas]
        for linea, parte in zip(lineas, repartir(importe, pesos)):
            linea["coste_publicidad"] = parte

    for row in rows:
        if row["margen_contribucion"] is None:
            continue
        row["resultado_variable"] = round(
            row["margen_contribucion"] + row["ingreso_envio"] - row["coste_logistica"]
            - row["comision_pago"] - row["coste_publicidad"], 2)


def write_db(rows, excluidas=None):
    validate_finite_values(rows)  # Also catch arithmetic overflow before replacing data.
    os.makedirs(DATA_DIR, exist_ok=True)
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)   # se reconstruye siempre desde el snapshot crudo
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE lineas (
            pedido TEXT, fecha TEXT, sku TEXT, titulo TEXT, unidades INTEGER,
            precio_bruto REAL, descuento_linea REAL, precio_catalogo REAL,
            coste_unitario REAL, ingreso_con_iva REAL, iva_implicito REAL,
            ingreso_neto REAL, coste_total REAL,
            margen_contribucion REAL, margen_pct REAL,
            taxable INTEGER, codigos_descuento TEXT, estado_financiero TEXT,
            iva_pedido_declarado REAL, envio_pedido REAL,
            ingreso_envio REAL, coste_logistica REAL, comision_pago REAL,
            coste_publicidad REAL, resultado_variable REAL
        )
    """)
    columns = ["pedido", "fecha", "sku", "titulo", "unidades", "precio_bruto", "descuento_linea",
               "precio_catalogo", "coste_unitario", "ingreso_con_iva", "iva_implicito",
               "ingreso_neto", "coste_total", "margen_contribucion", "margen_pct", "taxable",
               "codigos_descuento", "estado_financiero", "iva_pedido_declarado", "envio_pedido",
               "ingreso_envio", "coste_logistica", "comision_pago", "coste_publicidad",
               "resultado_variable"]
    conn.executemany(
        "INSERT INTO lineas VALUES (%s)" % ",".join("?" * len(columns)),
        [tuple(row[c] for c in columns) for row in rows],
    )
    # What was left out, and why, stays queryable so checks.py can report it.
    conn.execute("CREATE TABLE exclusiones (motivo TEXT, cantidad REAL)")
    conn.executemany("INSERT INTO exclusiones VALUES (?, ?)", sorted((excluidas or {}).items()))
    conn.commit()
    conn.close()
    return columns


def write_csv(rows, costs):
    os.makedirs(DATA_DIR, exist_ok=True)
    tabla = catalogo(costs)
    resumen = {}
    for row in rows:
        entry = resumen.setdefault(row["sku"], {
            "sku": row["sku"],
            "nombre": (tabla.get(row["sku"]) or {}).get("nombre", "DESCONOCIDO"),
            "unidades": 0, "ingreso_neto": 0.0, "coste_total": 0.0, "margen": 0.0,
            "resultado_variable": None,
        })
        entry["unidades"] += row["unidades"]
        entry["ingreso_neto"] += row["ingreso_neto"]
        entry["coste_total"] += row["coste_total"] or 0.0
        entry["margen"] += row["margen_contribucion"] or 0.0
        if row["resultado_variable"] is not None:
            entry["resultado_variable"] = (entry["resultado_variable"] or 0.0) + row["resultado_variable"]

    filas = sorted(resumen.values(), key=lambda r: -r["unidades"])
    for fila in filas:
        for key in ("ingreso_neto", "coste_total", "margen", "resultado_variable"):
            if fila[key] is not None:
                fila[key] = round(fila[key], 2)
        fila["margen_pct"] = (round(100.0 * fila["margen"] / fila["ingreso_neto"], 1)
                              if fila["ingreso_neto"] else None)

    with open(CSV_PATH, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["sku", "nombre", "unidades", "ingreso_neto",
                                                "coste_total", "margen", "margen_pct",
                                                "resultado_variable"])
        writer.writeheader()
        writer.writerows(filas)
    return filas


def contador_objetivo(rows, costs):
    objetivo = costs["objetivo"]
    desde = objetivo["desde"]
    hasta = objetivo["hasta"]
    desde = desde.isoformat() if hasattr(desde, "isoformat") else str(desde)
    hasta = hasta.isoformat() if hasattr(hasta, "isoformat") else str(hasta)
    vendidas = sum(r["unidades"] for r in rows if desde <= r["fecha"] <= hasta)
    # Target pacing belongs to the snapshot. Rebuilding an old snapshot next week
    # must not silently change its reported outlook.
    as_of = max((r["fecha"] for r in rows), default=desde)
    as_of_date = datetime.date(*[int(p) for p in as_of.split("-")])
    dias = (datetime.date(*[int(p) for p in hasta.split("-")]) - as_of_date).days
    return objetivo["unidades"], vendidas, max(dias, 0), desde, hasta, as_of


def main():
    try:
        costs = load_costs(COSTS_PATH)
    except ConfigError as exc:
        raise SystemExit("COST MODEL ERROR: %s" % exc)

    path = latest_snapshot()
    with open(path, "r", encoding="utf-8") as fh:
        snapshot = json.load(fh)

    print("Snapshot: %s" % os.path.basename(path))
    try:
        excluidas = {}
        rows = build_rows(snapshot, costs, excluidas)
    except ConfigError as exc:
        raise SystemExit("INPUT ERROR: %s" % exc) from None
    write_db(rows, excluidas)
    for motivo, cantidad in sorted(excluidas.items()):
        print("%s: %s" % (EXCLUSION_LABELS.get(motivo, motivo), cantidad))
    filas = write_csv(rows, costs)

    print("Lines processed: %d" % len(rows))
    print()
    print("%-8s %-28s %6s %10s %10s %10s %8s"
          % ("SKU", "Product", "Units", "Revenue", "Cost", "Margin", "Margin%"))
    total_u = total_i = total_m = 0
    for f in filas:
        print("%-8s %-28s %6d %10.2f %10.2f %10.2f %7s"
              % (f["sku"] or "(sin sku)", f["nombre"][:28], f["unidades"], f["ingreso_neto"],
                 f["coste_total"], f["margen"],
                 ("%.1f" % f["margen_pct"]) if f["margen_pct"] is not None else "-"))
        total_u += f["unidades"]
        total_i += f["ingreso_neto"]
        total_m += f["margen"]
    print("%-8s %-28s %6d %10.2f %10s %10.2f %7s"
          % ("TOTAL", "", total_u, total_i, "", total_m,
             "%.1f" % (100.0 * total_m / total_i) if total_i else "-"))

    if variable_costs(costs) is not None:
        resultado = sum(f["resultado_variable"] or 0.0 for f in filas)
        print("After shipping, fulfilment, payment fees and advertising: %.2f" % resultado)

    if not costs.get("objetivo"):
        print()
        print("Written: data/pipeline.db · data/margins.csv")
        print("Next: python3 src/checks.py")
        return 0
    meta, vendidas, dias, desde, hasta, as_of = contador_objetivo(rows, costs)
    print()
    print("TARGET %d units (%s to %s; data through %s)" % (meta, desde, hasta, as_of))
    print("   sold in window: %d · remaining: %d · days remaining: %d"
          % (vendidas, meta - vendidas, dias))
    if dias:
        print("   required pace: %.1f units/week" % ((meta - vendidas) / (dias / 7.0)))

    print()
    print("Written: data/pipeline.db · data/margins.csv")
    print("Next: python3 src/checks.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
