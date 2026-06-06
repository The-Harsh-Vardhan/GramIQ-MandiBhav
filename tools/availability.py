import argparse
import sys
from pathlib import Path

# Add root directory to python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import date
import config
from mandibhav.discovery import generate_availability_report

def main():
    parser = argparse.ArgumentParser(description="MandiBhav Availability Report Tool")
    parser.add_argument("--date", default=date.today().isoformat(), help="Target date in YYYY-MM-DD")
    parser.add_argument("--mode", default=None, help="Force PIPELINE_MODE ('dev' or 'live')")
    args = parser.parse_args()

    if args.mode:
        config.PIPELINE_MODE = args.mode

    print(f"Generating availability report for date {args.date} (mode={config.PIPELINE_MODE})...")
    report = generate_availability_report(args.date)

    print(f"\n--- Availability Report ({report['date']}) ---")
    if not report["commodities"]:
        print("No commodities found / OGD records are empty for today.")
    else:
        for commodity, count in sorted(report["commodities"].items(), key=lambda x: x[1], reverse=True):
            print(f"  - {commodity}: {count} records")

if __name__ == "__main__":
    main()
