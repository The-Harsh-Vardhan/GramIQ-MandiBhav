#!/usr/bin/env python3
import sqlite3
import argparse
import shutil
from pathlib import Path
from datetime import date as date_cls
from date_utils import normalize_date

def clear_date_data(
    target_date_input: str,
    db_path: Path,
    output_dir: Path,
    dry_run: bool = False,
    clear_db: bool = True,
    clear_cache: bool = True,
) -> None:
    # Normalize the target date
    try:
        target_date = normalize_date(target_date_input)
    except ValueError as e:
        print(f"Error parsing date: {e}")
        return

    print(f"=== Clearing data for date: {target_date} (Dry Run: {dry_run}) ===")
    
    total_matched = 0
    
    market_deleted = 0
    articles_deleted = 0
    runs_deleted = 0
    
    # 1. Clear database records
    if clear_db:
        if db_path.exists():
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            try:
                # Query counts first
                cursor.execute("SELECT COUNT(*) FROM market_data WHERE market_date = ?", (target_date,))
                market_matched = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM articles WHERE article_date = ?", (target_date,))
                articles_matched = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM pipeline_runs WHERE run_date = ?", (target_date,))
                runs_matched = cursor.fetchone()[0]
                
                db_matched = market_matched + articles_matched + runs_matched
                total_matched += db_matched
                
                if dry_run:
                    print(f"[Dry Run] Would delete from database:")
                    print(f"  - market_data: {market_matched} row(s)")
                    print(f"  - articles: {articles_matched} row(s)")
                    print(f"  - pipeline_runs: {runs_matched} row(s)")
                else:
                    if db_matched > 0:
                        cursor.execute("DELETE FROM market_data WHERE market_date = ?", (target_date,))
                        market_deleted = cursor.rowcount
                        
                        cursor.execute("DELETE FROM articles WHERE article_date = ?", (target_date,))
                        articles_deleted = cursor.rowcount
                        
                        cursor.execute("DELETE FROM pipeline_runs WHERE run_date = ?", (target_date,))
                        runs_deleted = cursor.rowcount
                        
                        conn.commit()
                        print(f"Deleted from database:")
                        print(f"  - market_data: {market_deleted} row(s)")
                        print(f"  - articles: {articles_deleted} row(s)")
                        print(f"  - pipeline_runs: {runs_deleted} row(s)")
                    else:
                        print("No matching database records found.")
            except Exception as e:
                conn.rollback()
                print(f"Database error: {e}")
            finally:
                conn.close()
        else:
            print(f"Database file not found: {db_path}")
            
    # 2. Clear output files/directories
    if clear_cache:
        date_output_dir = output_dir / target_date
        dir_matched = 0
        if date_output_dir.exists():
            dir_matched = 1
            total_matched += 1
            if dry_run:
                print(f"[Dry Run] Would remove output directory: {date_output_dir}")
            else:
                print(f"Removing output directory: {date_output_dir}")
                try:
                    shutil.rmtree(date_output_dir)
                    print("Successfully removed output directory.")
                except Exception as e:
                    print(f"Error removing output directory: {e}")
        else:
            print(f"No output directory found at: {date_output_dir}")
            
        # 3. Clear cached demo json files
        latest_cache_files = (
            list(output_dir.glob("json/article_*.json")) +
            list(output_dir.glob("json/demo/*.json")) +
            list(output_dir.glob("json/production/*.json"))
        )
        cache_matched = len(latest_cache_files)
        total_matched += cache_matched
        if latest_cache_files:
            if dry_run:
                print(f"[Dry Run] Would remove {cache_matched} cache file(s) in output/json/")
                for f in latest_cache_files:
                    print(f"  - [Dry Run] Would remove: {f.relative_to(output_dir)}")
            else:
                print(f"Found {cache_matched} cached articles in output/json/. Removing...")
                for f in latest_cache_files:
                    try:
                        f.unlink()
                        print(f"  - Removed cache file: {f.relative_to(output_dir)}")
                    except Exception as e:
                        print(f"  - Error removing cache file {f.name}: {e}")
        else:
            print("No cached JSON files found in output/json/.")

    if total_matched == 0:
        print("0 records matched the requested date")

def main():
    parser = argparse.ArgumentParser(description="Clear MandiBhav pipeline data for a specific date.")
    parser.add_argument(
        "--date",
        default=date_cls.today().isoformat(),
        help="Date to clear in YYYY-MM-DD or other supported formats (default: today)",
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
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview deletions without modifying database or files",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Clear both database and output/cache files (default behavior)",
    )
    parser.add_argument(
        "--cache-only",
        action="store_true",
        help="Clear only output/cache files",
    )
    parser.add_argument(
        "--db-only",
        action="store_true",
        help="Clear only database records",
    )
    
    args = parser.parse_args()
    
    db_path = Path(args.db).resolve()
    output_dir = Path(args.output).resolve()
    
    clear_db = True
    clear_cache = True
    
    if args.db_only or args.cache_only:
        clear_db = args.db_only
        clear_cache = args.cache_only
    
    clear_date_data(
        target_date_input=args.date,
        db_path=db_path,
        output_dir=output_dir,
        dry_run=args.dry_run,
        clear_db=clear_db,
        clear_cache=clear_cache,
    )
    print("=== Clear complete ===")

if __name__ == "__main__":
    main()
