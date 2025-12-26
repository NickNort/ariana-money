#!/usr/bin/env python3
"""Generate visual charts for the trading bot."""

from src.charts import generate_all_charts

if __name__ == "__main__":
    print("Generating charts...")
    paths = generate_all_charts()
    for name, path in paths.items():
        print(f"  {name}: {path}")
    print("\nDone! Open the charts in the 'charts/' directory.")
