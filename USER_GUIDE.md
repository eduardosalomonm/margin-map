# Margin Map · User guide

Margin Map reads a Shopify store's orders directly, or any other store's orders
from the Excel template. This guide covers the Excel template; to connect
Shopify, see [Connect a Shopify store](#connect-a-shopify-store).

**Read the margin correctly:** product margin is sales after discounts and VAT,
minus declared product costs. It is not net profit: shipping, payment fees and
advertising appear only when declared as variable costs, overhead is always
excluded. Enter returned orders with their final quantities.

For the shortest possible route, open [`TLDR.README/README.md`](TLDR.README/README.md).

## Fastest route: edit Excel, double-click, view dashboard

The template ships with Luma Vale, a sample store with 12 months of illustrative
orders (€83,755.43 gross sales after discounts). Replace its values with your
store's to analyse your own margins; no Shopify credentials are needed.

1. Install Python 3.8+ and verify it in Terminal, PowerShell or Command Prompt:

   ```bash
   python3 --version
   ```

2. Download or clone the repository. Open `assets/unit-economics-input.xlsx` in
   Microsoft Excel, Numbers or LibreOffice.
3. Start on **Dashboard** for the live Excel overview and native charts, then use **Read me** for the
   input instructions. Edit only the yellow cells in these sheets:

   | Sheet | What it controls |
   |---|---|
   | `Dashboard` | Formula-driven Excel view. It updates immediately and links to the interactive online dashboard. |
   | `Settings` | Store name, VAT, target window, the `Scenario` / `Actual` pricing mode and optional fulfilment, payment and advertising costs |
   | `Catalogue` | Products and bundles together, with costs, current prices and stock; edit yellow values |
   | `Pricing & promotions` | Promotion rules, price history and dated product costs; edit yellow values |
   | `Pricing planner` | Live Excel price, margin and bundle checks; blue cells calculate automatically |
   | `Orders` | One sold SKU per row. Blue unit-price and discount cells automatically react to the catalogue and promotion inputs in `Scenario` mode. |

4. Save the workbook without changing its sheet names or header row.
5. Double-click the matching launcher in the project root:

   - macOS: `Run dashboard.command`
   - Windows: `Run dashboard.bat`

   The launcher validates the workbook, calculates margins, runs integrity checks,
   creates `output/dashboard.html`, then opens it in the default browser.

If Windows shows a security prompt, choose **More info → Run anyway** only after
confirming the file came from this repository. On macOS, you might need to permit
the first run in **System Settings → Privacy & Security**. The launchers now keep
the window open when something fails and explain whether Python is missing or the
Excel input needs attention; copy that complete message when asking for help.

## Choose a reporting period

Use the period menu in the dashboard for the latest 7 calendar days, month to date
or the complete imported period. Select **Custom date range** to reveal two calendar inputs. Choose a start
and end date, then select **Apply**. Every tab, KPI, chart, promotion table and
CSV export refreshes to that selected range. The period-change card compares the
range with the immediately preceding range of the same length.

Use the **Refine the view** bar to filter any selected range by SKU, product versus
bundle, or promotion code. These filters refresh commercial KPIs, charts, product
economics, promotions and the CSV export; Inventory health remains the latest
stock-position view. The filter bar states the exact active scope; use **Reset
view** to return to the complete period and remove every filter.

The gross-sales benchmark remains global when a period, SKU or promotion filter
is active, so a narrow slice is never presented as company-wide target progress.
The unit target is separate and reports its own current and required weekly pace.

Use **Download all-time PDF** for a compact complete-period summary generated alongside
the dashboard as `output/executive-summary.pdf`.

## Input rules

### Test a decision in Scenario lab

Choose your period, SKU, product type or promotion first. Open **Scenario lab**,
then adjust selling price, volume or unit product cost. The baseline always
follows your current filters. **Reset assumptions** restores all three changes
to zero; changing filters keeps your assumptions so you can compare segments.

The final row shows the result after declared variable costs, or product margin
if no variable-cost model exists. Missing inputs produce a marked known-cost
subtotal, never a claim of full contribution or net profit. The required order
growth preserves that baseline while holding basket mix, discount rates and VAT
constant. Shipping, fulfilment and fixed fees scale with orders; percentage fees
also follow price. Advertising stays fixed, an assumption rather than proof of
customer acquisition. Experiments do not change Excel, CSV exports or the PDF.

In the sample store, **Explore the decision** opens an illustrative promotion case.
Its two preset buttons reset filters to the full imported period. Manual edits or
filter changes keep your scenario assumptions but no longer select a preset unless
they match it. See [the case study](CASE_STUDY.md) for the origin and evidence limits.

### Historical product costs

In **Actual** mode, dated product costs apply from their effective date until the
next entry. Bundles use each component's effective cost. Sales before a product's
first cost entry block the report rather than guessing a cost.

In Excel, use the `SKU | Cost effective from | Unit cost ex VAT | Cost evidence`
table in **Pricing & promotions**. Enter ISO dates (`YYYY-MM-DD`), oldest first
for each SKU, with one entry per SKU/date. A known zero cost is valid. Keep this
table last, within row 2000, for the native workbook formulas. The importer also
accepts old workbooks without this table, warning that undated Catalogue costs
apply across history. **Scenario** mode intentionally uses current Catalogue
costs and leaves dated entries intact.

The JSON equivalent inside a product is:

```json
"costes": [
  {"desde": "2025-10-01", "coste_unitario": 11.80, "fuente": "Supplier invoice"},
  {"desde": "2026-07-01", "coste_unitario": 12.80, "fuente": "New supplier invoice"}
]
```

These values are examples, not recommendations. Shopify's current *Cost per item*
is observed today; it cannot establish a past cost. Bootstrap and refresh record
new observations without rewriting earlier dates. Supply evidence for earlier
sales yourself. An old undated Shopify-owned model becomes dated from its first
refresh, so historical coverage may need to be completed before the next report.
Set a different `coste_fuente` when managing costs manually to keep refresh from
updating those costs.

### Catalogue

Native preview formulas use `LET`, `XLOOKUP` and `TEXTSPLIT`, available in
Excel 365 / Excel 2024. Recalculation is tested with LibreOffice 26.8.2;
native Excel recalculation has not been verified in this release. The Python dashboard
recalculates from inputs without a spreadsheet application. Native lookups cover
Catalogue rows 3–100 and cost history through row 2000; extend summary rows and formula ranges if enlarging the
template beyond its sample layout. Renaming SKUs and changing bundle components
within those ranges update costs and prices without editing formula code.

- Use `Type` to mark every row as either `Product` or `Bundle`.
- `SKU` is required and must be unique for products; bundle SKUs are also unique.
- For products, `Unit cost ex VAT` and `Web price incl VAT` must be numbers.
- Do not estimate a cost. A missing cost intentionally blocks the dashboard.
- `Stock on hand` is optional. Fill it in to switch on the Inventory health tab,
  which reports sell-through and weeks of cover. Leave it blank and the tab explains
  what is missing: stock is never inferred from sales.
- For bundles, write components as `SKU:quantity|SKU:quantity` in `Bundle contents`.
  Example: `SKU-A:1|SKU-B:2`. `Declared solo total` and `Claimed saving` are checked
  against the current product prices.
- Change the yellow **Web price incl VAT** cells for products and the yellow
  **Bundle discount %** cells for bundles. The blue bundle price, separate-item
  total and saving cells update by themselves. Do not type over blue cells.
- Open `Pricing planner` after changing a price. It immediately labels products
  and bundles as Healthy, Low margin or Below cost. A below-cost scenario still
  builds the dashboard so its commercial effect is visible; a zero or negative
  selling price is rejected with a clear message because it is not usable data.

### Pricing & promotions

- Start with **Promotion rules | live scenario inputs**. Each yellow percentage
  drives the blue discount calculation in `Orders` immediately in Scenario mode.
- In **Price history | reference for Actual mode**, every SKU must exist as a
  `Product` in `Catalogue`. Use dates in `YYYY-MM-DD` format and add a row when
  the shop price changes.
- In the default `Scenario` mode, blue `Orders` prices follow `Catalogue` and
  blue discounts follow Promotion rules. Switch `Settings → Pricing model` to
  `Actual` to use the yellow recorded price and discount values instead.
- For every promotion rule, declare the code, percentage and active dates.
  In Scenario mode, the blue order discount automatically equals `unit price ×
  quantity × declared percentage`. In Actual mode, the dashboard validates the
  yellow recorded allocation against that rule.

### Orders

The blue helper columns at the right show gross line sales, the first line of
each order and its payment fee. They calculate automatically. Payment fees are
rounded once per order, matching the browser dashboard; repeated order IDs do
not duplicate the fixed fee. Revenue excluding VAT respects each line's
`Taxable` value.

- Quantities must be positive whole numbers. Stock on hand may be zero but cannot
  be negative or fractional. Batch quantities and target units must also be
  positive whole numbers.
- Each catalogue SKU must be unique across products and bundles. Each promotion
  code has one rule; duplicate codes are rejected instead of silently replacing
  earlier entries. Catalogue types must be `Product` or `Bundle`.
- A line discount cannot be negative or exceed its unit price multiplied by its
  quantity. Invalid inputs stop the build with an explanation.

- Each row is one SKU in one order. An order containing two products needs two rows
  with the same `Order ID`.
- `Discount allocated incl VAT` is the final discount attributable to that line.
  Enter `0` if the line has no discount.
- `Discount code` is optional. If a line has both a code and an allocated discount,
  it must match the active rule in **Promotion rules**. Enter `0` and leave the code
  blank for an undiscounted line.
- Use `TRUE` or `FALSE` for `Taxable`.

### Variable costs (optional)

Fill these in on `Settings` to see what remains after the costs of selling, not
only after product cost. Leave them all blank to keep the product-margin view.
If you declare some but omit others, the report shows an incomplete known-cost
subtotal. A blank advertising month is unknown; enter `0` for confirmed zero spend.

| Setting | Enter |
|---|---|
| `Fulfilment cost per order ex VAT` | Pick, pack and postage the store pays for one order. |
| `Shipping charged per order incl VAT` | Average shipping customers pay per order. Use `0` for free shipping. |
| `Payment fee (%)` and `Payment fee per order` | Your payment provider's rate, for example `1.5` and `0.25`. |
| `Advertising by month` table | One row per month, `YYYY-MM` and the spend ex VAT. |

The workbook's `Dashboard` sheet shows the same breakdown beside the commercial
picture and updates as soon as you edit these cells. It can differ from the online
dashboard by a few cents, because the online version rounds payment fees order by order.

Per-order amounts are shared across an order's lines by value. Advertising is shared
across a month's lines by net revenue. A month of advertising with no sales is
listed under **Data controls**, because it has nothing to be allocated to.

## What the dashboard reports

| Metric | Read it as |
|---|---|
| Gross sales | What customers paid, after discounts, including VAT. |
| Product margin | Sales ex VAT minus product cost, before the costs of selling. |
| Discount rate | Share of list price given away, plus how many orders used a code. |
| Units and lines per order | Basket size. A store at 1.00 has no attach at all. |
| Margin per order | What one order is worth after cost and VAT. |
| After variable costs | Product margin plus shipping charged, minus declared fulfilment, fees and advertising. Incomplete inputs yield a known-cost subtotal; neither is net profit. |
| Break-even discount | The deepest discount on today's price that still covers the product's cost, VAT and payment fee. |
| Gross-sales benchmark | Complete imported-period sales against the declared benchmark; filters do not redefine it. |
| Unit run rate vs target | Units a week now, against the pace the target window needs. |
| From list price to contribution | Where the money goes: discounts, VAT, cost, what is left. |
| Weeks of cover | How long stock lasts at the last 90 days of demand, bundles included. |

## What the safeguards do

The launcher stops before publishing if it finds a blocking error:

| Check | Meaning |
|---|---|
| Unknown SKU | A sold SKU has no declared unit cost. |
| Catalogue price vs charged price | In Actual mode, an order price does not match the price history. Scenario mode follows Catalogue and reports an advisory instead. |
| Bundle pricing rules | A bundle is more expensive than its parts, its advertised saving is wrong, or it breaks the configured price rule. |
| Discount rule vs line allocation | A code is missing, inactive, outside its date range, or its percentage does not match the allocated discount. |
| VAT consistency | The same SKU was recorded both taxable and non-taxable. |

Correct the yellow input cells, save the workbook, and run the launcher again.

## Run from the command line

Use this when you want a different workbook or output file:

```bash
python3 src/run_excel_dashboard.py \
  --input assets/unit-economics-input.xlsx \
  --output output/dashboard.html \
  --open
```

## Build recovery and multiple stores

Each Excel build uses its own temporary database and clears its intermediate
files automatically. Calculation, validation and rendering errors leave the
previous dashboard and PDF intact. Those previous files still describe the last
successful build: fix the reported error and rerun before using them for new data.

For separate stores or scenarios, choose a separate output folder for each, such
as `--output output/store-a/dashboard.html`. Each folder has a single
`executive-summary.pdf`, so different HTML filenames in the same folder share
that PDF. If a file error appears, close apps locking the output files and check
that you can write to the destination folder.

## Connect a Shopify store

Shopify stores do not need the Orders sheet. Margin Map reads orders with
read-only access, drafts the cost model from each variant's *Cost per item*
(`python3 src/bootstrap_costs.py`), and builds the dashboard and PDF with one
command (`python3 src/run_shopify_dashboard.py`). Returns, gift cards, reduced VAT
rates and the shop's timezone are handled automatically. See
[README.md](README.md#connect-a-shopify-store) for the app setup.

## Contributors: verify before pushing

```bash
python3 src/make_demo_data.py
SNAPSHOT=data/raw/orders-demo.json python3 src/transform.py
SNAPSHOT=data/raw/orders-demo.json python3 src/checks.py
python3 src/make_demo_workbook.py
python3 src/run_excel_dashboard.py --output docs/index.html
python3 -m unittest discover -s tests -v
```

Do not commit `.env`, a private Excel workbook, real Shopify snapshots, generated
databases, local output dashboards or supplier costs.
