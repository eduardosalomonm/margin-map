"""One command from a Shopify store to its margin dashboard and executive PDF.

Runs the same steps the README lists by hand: extract orders, calculate margins,
run the integrity checks, then render the dashboard and the PDF next to it. It
stops at the first step that fails, so a reconciliation mismatch or a blocking
data error never produces a report.

Usage:  python3 src/run_shopify_dashboard.py --since 2025-01-01
        python3 src/run_shopify_dashboard.py --since 2025-01-01 --expected-units 1240
"""

import argparse
import os
import subprocess
import sys
import webbrowser

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run(script, environment, arguments=()):
    result = subprocess.run([sys.executable, os.path.join(BASE, "src", script), *arguments],
                            cwd=BASE, env=environment)
    if result.returncode:
        raise SystemExit(result.returncode)


def main():
    parser = argparse.ArgumentParser(description="Build the margin dashboard from a Shopify store.")
    parser.add_argument("--since", help="first order date to include, e.g. 2025-01-01")
    parser.add_argument("--expected-units", help="stop unless Shopify's own unit total matches")
    parser.add_argument("--costs", default="costs.private.json", help="the store's cost model")
    parser.add_argument("--output", default=os.path.join("output", "shopify", "dashboard.html"))
    parser.add_argument("--open", action="store_true", help="open the dashboard when done")
    args = parser.parse_args()

    costs = args.costs if os.path.isabs(args.costs) else os.path.join(BASE, args.costs)
    if not os.path.exists(costs):
        print("No cost model at %s. Draft one from the store with:\n"
              "  python3 src/bootstrap_costs.py" % os.path.relpath(costs, BASE))
        return 1
    output = os.path.abspath(args.output if os.path.isabs(args.output) else os.path.join(BASE, args.output))
    environment = dict(os.environ, COSTS_FILE=costs, PANEL_OUT=output)
    environment.pop("SNAPSHOT", None)  # always the extraction made by this run

    extract_args = []
    if args.since:
        extract_args += ["--since", args.since]
    if args.expected_units:
        extract_args += ["--expected-units", args.expected_units]
    print("0/4  Refreshing stock, prices and new SKUs from Shopify...", flush=True)
    refresh = subprocess.run([sys.executable, os.path.join(BASE, "src", "bootstrap_costs.py"),
                              "--update", "--output", costs], cwd=BASE, env=environment)
    if refresh.returncode:
        print("     Continuing with the cost model as it is (stock may be out of date).")
    print("1/4  Extracting orders from Shopify...", flush=True)
    run("extract.py", environment, extract_args)
    print("2/4  Calculating margins...", flush=True)
    run("transform.py", environment)
    print("3/4  Running integrity checks...", flush=True)
    run("checks.py", environment)
    print("4/4  Generating dashboard and executive PDF...", flush=True)
    run("publish.py", environment)
    pdf = os.path.join(os.path.dirname(output), "executive-summary.pdf")
    run("export_executive_pdf.py", environment, ("--output", pdf))
    print("DONE: %s\nPDF:  %s" % (output, pdf))
    if args.open:
        webbrowser.open("file://" + output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
