# Changelog

All notable public changes to Margin Map are recorded here.

## 1.3.0 - 2026-11-03

- Reject malformed imported currency codes and encode currency values correctly
  in HTML and JavaScript, preventing imported text from becoming executable code.
- Native Excel costs and bundle prices now resolve editable SKUs and component
  quantities, not the sample catalogue. Array formulas use `LET`, `XLOOKUP` and
  `TEXTSPLIT` (Excel 365 / 2024), with cache-free recalculation tested in LibreOffice
  26.8.2. Native Excel was not tested; Python import does not require Excel.

- Added an honest portfolio case and guided promotion comparison: more sales can
  leave less after costs. Sample decisions are illustrative, not claimed outcomes.
- Actual mode resolves effective-dated product and bundle costs; Shopify cost
  observations preserve earlier entries. Scenario mode keeps current-cost what-ifs.
- Missing variable costs are distinguished from explicit zero in controls and
  exports. Scenario lab now models declared variable costs, fixed advertising and
  the order-growth threshold required to preserve the baseline after-cost result.
- Two independent critique rounds drove adversarial analytical fixes: preserve
  losses across the revenue flow and variable-cost bridge, retain free products
  with costs, show undefined margin rates as unavailable, expose warning details,
  and distinguish missing comparison baselines from zero growth.
- Chart ranges retain quiet days at the boundaries of the selected period.
- Repositioned Margin Map as margin analytics for Shopify stores: the dashboard,
  PDF and workbook name their data source, label the sample store once, and no
  longer show version numbers or demo wording on the reading surface.
- Fixed the online-dashboard links, which now point to https://marginmap.eilvi.com/.
- Shopify path: returns, refunds and order edits count by current quantity; real
  VAT per line from tax lines, including tax-exclusive stores; shipping after
  discounts; shop timezone; gift cards and voided or expired orders excluded and
  reported; price changes warn per SKU instead of blocking.
- Shopify client retries outages and timeouts, shows Shopify's error codes and
  shrinks pages when a query is too large.
- Added `bootstrap_costs.py` (cost model drafted from Shopify's cost per item) and
  `run_shopify_dashboard.py` (one command, dashboard and PDF). A sales target is optional.
- "Contribution margin" is now "Product margin"; a Recommended actions card and PDF
  priority actions name the next steps; overstock is flagged; the PDF uses the
  store's currency.
- Critique round 2: an empty Shopify tax list means no tax (not the default rate);
  money refunded without a return is deducted; returned orders keep their
  fulfilment and payment fee, which is charged on the original amount; stock cover
  uses the days actually observed; no target means no benchmark instead of a
  self-referential 100%; "Sales incl. VAT" replaces "Gross sales"; discount and
  VAT warnings are summarised for live stores; `bootstrap_costs.py --update`
  refreshes stock, prices and new SKUs on every Shopify run.
- Critique round 3: fully returned orders no longer count as orders in AOV, basket
  size or promotion counts; a refunded gift card is not deducted from product
  sales; warning wording and the no-target hint follow the data source.

## 1.2.0 - 2026-10-31

- Reconciled Excel payment fees with per-order rounding in the pipeline, made
  line revenue respect Taxable, and improved summary column widths.
- Added `--as-of YYYY-MM-DD` for reproducible workbook generation.

- Reject fractional counts, negative stock, unknown catalogue types, duplicate
  bundle/product SKUs and promotion codes, and impossible line discounts before
  they can silently change imported results.

- Added a browser-only Scenario lab for price, volume and supplier-cost experiments,
  including the volume needed to preserve product margin and explicit assumptions.
- Fixed sales charts hiding negative results after variable costs. Losses now sit
  below a visible zero line; individual points expose their values.
- Included empty calendar buckets between recorded sales and year labels on monthly charts.
- Added executable JavaScript checks alongside Python verification in CI.

## 1.1.0 - 2026-10-23

- Added optional variable costs (fulfilment, shipping charged, payment fees and monthly
  advertising) and a result after variable costs across the overview, products,
  promotions, trend chart, CSV export, insights and executive PDF.
- Added the same breakdown to the workbook's live `Dashboard` sheet.
- Added a break-even discount per product and catalogue bundle.
- Added a variable-cost allocation control that reports advertising with no sales to land on.
- Excel builds now run in an isolated temporary folder and keep the previous report on failure.

## 1.0.0 - 2026-09-05

- Introduced the Margin Map product name while keeping Luma Vale as the synthetic demo store.
- Added an editable Excel workflow, formula-driven workbook dashboard and one-click launchers.
- Added interactive date, SKU, product-type and promotion filters across six dashboard views.
- Added data-driven insights, a revenue-flow Sankey diagram and an executive PDF export.
- Added finite-number validation, provider-error redaction and a public-release privacy guard.
- Clarified that contribution means product margin and excludes shipping, payment fees, acquisition and overhead.
