# Contributing to Margin Map

Thanks for improving the project. The public repository must stay safe to clone,
run and show in a portfolio: never add Shopify credentials, supplier costs, real
customer data or private dashboards.

## Before opening a pull request

1. Keep the public path dependency-free on Python 3.8+.
2. Rebuild the Excel demo and dashboard:

   ```bash
   python3 src/make_demo_workbook.py
   python3 src/run_excel_dashboard.py --output docs/index.html
   ```

3. Run the verification suite:

   ```bash
   python3 src/check_public_release.py --history
   python3 -m unittest discover -s tests -v
   node --test tests/test_*.js
   ```

4. If you change an input column, update `USER_GUIDE.md`, its workbook generator,
   parser and tests together.

Node.js 22+ is used only for browser calculation tests. Running the dashboard and
Excel workflow still requires only Python and its standard library.

## Project conventions

- Keep user-facing text and documentation in English.
- Treat raw order snapshots as immutable input; do not edit transformed output to
  force a KPI.
- Prefer a documented source for every cost, price, stock figure and discount rule.
- Keep the static dashboard self-contained so GitHub Pages can serve it without a
  build step.
- Keep publication reproducible: the same workbook must produce byte-identical
  `docs/index.html` and `docs/executive-summary.pdf`.
- Escape imported store text before inserting it into HTML and neutralise
  formula-like text before writing spreadsheet-compatible exports.

## Dashboard design checks

- **Report filters and navigation.** Use a visible focus ring, 44px control targets
  and text sizes that follow the browser's font setting. Check phone and tablet
  layouts and 200% text size. A date draft keeps the last applied range until
  the user applies it.
- **Product economics, Promotions, Inventory health and Data controls.** Keep
  titles and actions outside scrollable tables. Give each wide table a named,
  keyboard-focusable scroll region. Selecting a product keeps focus on its row.
- **Overview and Sales performance charts.** Pair the drawing with readable values
  that can be reached by keyboard. Chart text should stay legible at the rendered
  width. Give long labels room to wrap.
- **Overview.** Give the selected margin the strongest weight among historical
  KPIs. The sample offer belongs before report filters and should show a calculable
  result immediately. State the full-period scope at the action.
- **Scenario lab.** Show the change from the selected baseline, the modelled
  result and the recovery threshold together. Keep report filters reachable.
  A preset changes its assumptions, and the explicitly labelled Overview action
  opens the complete sample case.
- **Dashboard surfaces.** Use restrained borders and a single emphasis per
  section. Reserve status colours for meaning and pair them with explicit text.
  Use the dashboard stylesheet tokens for type, spacing and focus.

For private Shopify usage, use local `.env` and `costs.private.json` files. They
are excluded from Git by design.
