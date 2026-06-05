# MandiBhav Data Management Guide

This document explains date normalization, cleanup procedures, and historical backfill execution in the MandiBhav by GramIQ pipeline.

---

## Date Standardization & Normalization

All internal date handling, database records, and output folders are standardized to use the `YYYY-MM-DD` ISO format.

### Supported Input Formats
When providing date inputs via the CLI, the system supports:
- `YYYY-MM-DD` (e.g., `2026-06-05`)
- `YYYY/MM/DD` (e.g., `2026/06/05`)
- `DD-MM-YYYY` (e.g., `05-06-2026`)
- `MM-DD-YYYY` (e.g., `06-05-2026`)
- `DD/MM/YYYY` (e.g., `05/06/2026`)
- `MM/DD/YYYY` (e.g., `06/05/2026`)

### Resolution Rules
To handle ambiguous formats (like `05-06-2026` vs `06-05-2026`):
1. **Hyphen Separators (`-`)**: Prioritizes `MM-DD-YYYY` parsing first to handle inputs like `06-05-2026` as June 5, then falls back to `DD-MM-YYYY`.
2. **Slash Separators (`/`)**: Prioritizes `DD/MM/YYYY` parsing first to handle inputs like `05/06/2026` as June 5, then falls back to `MM/DD/YYYY`.
3. **Unambiguous Fallback**: If the day/month component values exceed 12, the standard parser automatically resolves the date without ambiguity.

---

## Data Cleanup Workflows

The `clear_date.py` script allows developers to safely clean up pipeline artifacts.

### CLI Syntax
```bash
python clear_date.py --date <TARGET_DATE> [options]
```

### Options
| Flag | Description |
|---|---|
| `--date` | Target date to clear (defaults to today). Supports all multi-format input formats. |
| `--dry-run` | Previews the cleanup actions (database rows, output folder, cache files) without deleting them. |
| `--all` | Removes matching database rows, output folders, and cache files (default behavior). |
| `--db-only` | Removes matching database rows only. |
| `--cache-only` | Removes matching output directories and cache JSON files only. |
| `--db` | Path to the SQLite database (defaults to `mandibhav.db`). |
| `--output` | Path to output directory (defaults to `output`). |

### Examples
1. **Preview cleanup for June 5, 2026:**
   ```bash
   python clear_date.py --date 05-06-2026 --dry-run
   ```
2. **Remove only database records for June 5, 2026:**
   ```bash
   python clear_date.py --date 2026-06-05 --db-only
   ```
3. **Remove only cache and folder outputs for June 5, 2026:**
   ```bash
   python clear_date.py --date 05/06/2026 --cache-only
   ```
4. **Complete cleanup for today:**
   ```bash
   python clear_date.py
   ```

---

## Historical Backfill Execution

Historical Backfill mode allows populating the site with reports over a range of past dates.

### CLI Options
| Flag | Description |
|---|---|
| `--backfill-days <N>` | Backfill `<N>` days ending at the target date. |
| `--start-date <DATE>` | Start date for backfill range. |
| `--end-date <DATE>` | End date for backfill range. |

### Behavior & Performance Optimization
- **Database Cache Hit (OGD Skip)**: To minimize execution time and avoid hit limits on the OGD API, if the database already contains records for a given date, the OGD API fetch is skipped entirely. Instead, the local DB records are loaded and the run source is marked as `CACHE`.
- **Deferred Publishing**: During a multi-date backfill run, the static site generation and publishing (`stage_publish`) is skipped within the loop. A single final static site generation is triggered at the end of the loop using the latest date.

### Examples
1. **Backfill 3 days ending on June 5, 2026 in Demo Mode (without deploying):**
   ```bash
   python main.py --mode demo --backfill-days 3 --date 2026-06-05 --skip-publish
   ```
2. **Backfill a specific range of dates in Live Mode and deploy to GitHub Pages:**
   ```bash
   python main.py --mode live --start-date 2026-06-01 --end-date 2026-06-05 --publish
   ```
