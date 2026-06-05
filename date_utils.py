"""
date_utils.py — Shared date parsing, formatting, and normalization utilities.
"""

from datetime import datetime, date as date_cls
import re

def parse_date(date_input) -> date_cls:
    """
    Parses a date input (date, datetime, or string in various formats)
    and returns a datetime.date object.
    
    Supported string formats:
    - YYYY-MM-DD
    - DD-MM-YYYY
    - DD/MM/YYYY
    - YYYY/MM/DD
    - MM-DD-YYYY (if separator is - and MM <= 12)
    - MM/DD/YYYY (if separator is / and MM <= 12)
    """
    if isinstance(date_input, (date_cls, datetime)):
        return date_input if isinstance(date_input, date_cls) else date_input.date()
        
    if not isinstance(date_input, str):
        raise ValueError(f"Invalid date input type: {type(date_input)}")
        
    date_str = date_input.strip()
    
    # Try YYYY-MM-DD or YYYY/MM/DD first (standard ISO formats)
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            pass
            
    # Try formats with year at the end
    # If it has hyphens
    if "-" in date_str:
        # Try MM-DD-YYYY first (to support 06-05-2026 as June 5), then DD-MM-YYYY
        for fmt in ("%m-%d-%Y", "%d-%m-%Y"):
            try:
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                pass
                
    # If it has slashes
    if "/" in date_str:
        # Try DD/MM/YYYY first (to support 05/06/2026 as June 5), then MM/DD/YYYY
        for fmt in ("%d/%m/%Y", "%m/%d/%Y"):
            try:
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                pass
                
    # Catch-all formatting attempt with any standard formats
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%m-%d-%Y", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            pass
            
    raise ValueError(f"Could not parse date string: {date_str}")


def normalize_date(date_input) -> str:
    """
    Parses date_input and returns standard YYYY-MM-DD string format.
    """
    return parse_date(date_input).strftime("%Y-%m-%d")


def is_valid_date(date_str: str) -> bool:
    """
    Checks if a string is a parsable date.
    """
    try:
        parse_date(date_str)
        return True
    except ValueError:
        return False
