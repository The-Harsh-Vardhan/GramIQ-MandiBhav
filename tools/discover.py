import argparse
import sys
from pathlib import Path

# Add root directory and mandibhav directory to python path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "mandibhav"))

import config
from mandibhav.discovery import discover_metadata

def main():
    parser = argparse.ArgumentParser(description="MandiBhav Dataset Discovery Tool")
    parser.add_argument("--limit", type=int, default=5000, help="Number of records to fetch (default: 5000)")
    parser.add_argument("--date", default=None, help="Target date in YYYY-MM-DD (default: latest)")
    parser.add_argument("--mode", default=None, help="Force PIPELINE_MODE ('dev' or 'live')")
    args = parser.parse_args()

    if args.mode:
        config.PIPELINE_MODE = args.mode

    print(f"Running discovery (mode={config.PIPELINE_MODE}, limit={args.limit}, date={args.date or 'latest'})...")
    meta = discover_metadata(limit=args.limit, target_date=args.date)

    print("\n--- DISCOVERED DATASETS ---")
    print(f"\nStates ({len(meta['states'])}):")
    print("  " + ", ".join(meta["states"][:20]) + ("..." if len(meta["states"]) > 20 else ""))
    
    print(f"\nMarkets ({len(meta['markets'])}):")
    print("  " + ", ".join(meta["markets"][:20]) + ("..." if len(meta["markets"]) > 20 else ""))
    
    print(f"\nCommodities ({len(meta['commodities'])}):")
    print("  " + ", ".join(meta["commodities"]))
    
    print(f"\nVarieties ({len(meta['varieties'])}):")
    print("  " + ", ".join(meta["varieties"][:20]) + ("..." if len(meta["varieties"]) > 20 else ""))
    
    print(f"\nGrades ({len(meta['grades'])}):")
    print("  " + ", ".join(meta["grades"]))

if __name__ == "__main__":
    main()
