#!/usr/bin/env python3
import sqlite3
import argparse
import shutil
from pathlib import Path
from datetime import date as date_cls

def clear_date_data(target_date: str, db_path: Path, output_dir: Path) -> None:
    print(f"=== Clearing data for date: {target_date} ===")
    
    # 1. Clear database records
    if db_path.exists():
        print(f"Connecting to database: {db_path}")
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        try:
            # Delete from market_data
            cursor.execute("DELETE FROM market_data WHERE market_date = ?", (target_date,))
            market_deleted = cursor.rowcount
            
            # Delete from articles
            cursor.execute("DELETE FROM articles WHERE article_date = ?", (target_date,))
            articles_deleted = cursor.rowcount
            
            # Delete from pipeline_runs
            cursor.execute("DELETE FROM pipeline_runs WHERE run_date = ?", (target_date,))
            runs_deleted = cursor.rowcount
            
            conn.commit()
            print(f"Deleted from database:")
            print(f"  - market_data: {market_deleted} row(s)")
            print(f"  - articles: {articles_deleted} row(s)")
            print(f"  - pipeline_runs: {runs_deleted} row(s)")
        except Exception as e:
            conn.rollback()
            print(f"Database error: {e}")
        finally:
            conn.close()
    else:
        print(f"Database file not found: {db_path}")
        
    # 2. Clear output files/directories
    date_output_dir = output_dir / target_date
    if date_output_dir.exists():
        print(f"Removing output directory: {date_output_dir}")
        try:
            shutil.rmtree(date_output_dir)
            print("Successfully removed output directory.")
        except Exception as e:
            print(f"Error removing output directory: {e}")
    else:
        print(f"No output directory found at: {date_output_dir}")

    # 3. Clear cached demo json files if target_date is today or latest
    # (these cache hits can prevent regenerating articles in demo mode)
    latest_cache_files = list(output_dir.glob("json/article_*.json"))
    if latest_cache_files:
        print("Found cached articles in output/json/ (demo mode cache).")
        for f in latest_cache_files:
            try:
                f.unlink()
                print(f"  - Removed cache file: {f.name}")
            except Exception as e:
                print(f"  - Error removing cache file {f.name}: {e}")

def main():
    parser = argparse.ArgumentParser(description="Clear MandiBhav pipeline data for a specific date.")
    parser.add_argument(
        "--date",
        default=date_cls.today().isoformat(),
        help="Date to clear in YYYY-MM-DD format (default: today)",
    )
    parser.add_argument(
        "--db",
        default="mandibhav.db",
        help="Path to SQLite database file (default: mandibhav.db)",
    )
    parser.add_argument(
        "--output",
        default="output",
        help="Path to output directory (default: output)",
    )
    
    args = parser.parse_args()
    
    db_path = Path(args.db).resolve()
    output_dir = Path(args.output).resolve()
    
    clear_date_data(args.date, db_path, output_dir)
    print("=== Clear complete ===")

if __name__ == "__main__":
    main()
