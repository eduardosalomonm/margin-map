# Margin Map · 60-second setup

## I only want to see the finished dashboard

Open `../docs/index.html`, then choose **Explore the decision**. Compare the two
illustrative offers and change the order-growth assumption. No installation is
required. [Read the story and its limits](../CASE_STUDY.md).

`OPEN ONLINE DASHBOARD.html` opens the public release, which may differ from the
current local walkthrough.

## I want to change the Excel data

1. Open `../assets/unit-economics-input.xlsx`.
2. Start on the **Dashboard** tab. Its charts and KPIs update in Excel.
3. Edit only yellow cells, then save the workbook.
4. Double-click the launcher in the project root:
   - macOS: `Run dashboard.command`
   - Windows: `Run dashboard.bat`
5. The interactive dashboard opens in your browser.

The launcher requires Python 3. If it is missing, the launcher now stays open and
shows the installation link or the exact input error to fix.

## If double-clicking is blocked

- macOS: right-click `Run dashboard.command`, choose **Open**, then confirm **Open**.
- Windows: choose **More info → Run anyway** only if you downloaded this project
  from its official GitHub repository.
- If the window shows an error, keep it open and copy the complete message.

The Excel Dashboard is the instant view. The online dashboard adds filters, the
Scenario lab and the executive PDF.

## I have a Shopify store

Margin Map can read your orders straight from Shopify with read-only access. See
"Connect a Shopify store" in `../README.md`.
