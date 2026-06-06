import argparse
import sys
import sqlite3
from pathlib import Path

# Add root directory and mandibhav directory to python path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "mandibhav"))

import config

def main():
    parser = argparse.ArgumentParser(description="MandiBhav Market Search Tool")
    parser.add_argument("--market", required=True, help="Market name keyword (e.g. Nagpur)")
    args = parser.parse_args()
    
    db_path = config.DB_PATH
    if not db_path.exists():
        print(f"Database not found at {db_path}")
        return
        
    print(f"Searching database for historical records matching market keyword: '{args.market}'...")
    
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    query = """
        SELECT commodity_slug, market_date, state, district, market_name, variety, min_price, max_price, modal_price, arrival_tonnes, source
        FROM market_data
        WHERE market_name LIKE ?
        ORDER BY market_date DESC, commodity_slug ASC
    """
    
    keyword = f"%{args.market}%"
    rows = cursor.execute(query, (keyword,)).fetchall()
    
    print(f"\nFound {len(rows)} matching historical records:")
    print("=" * 105)
    print(f"{'Date':<12} | {'Commodity':<10} | {'State':<15} | {'Market Name':<20} | {'Variety':<12} | {'Modal Price':<12} | {'Arrivals (t)':<12}")
    print("=" * 105)
    for row in rows:
        print(f"{row['market_date']:<12} | {row['commodity_slug'].upper():<10} | {row['state']:<15} | {row['market_name']:<20} | {row['variety']:<12} | {row['modal_price']:<12.2f} | {row['arrival_tonnes']:<12.2f}")
    print("=" * 105)
    
    conn.close()

if __name__ == "__main__":
    main()
