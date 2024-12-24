from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import List, Optional
import re

class OFXParser:
    """Base parser for OFX files"""
    
    def __init__(self, base_path: str = "financial-data", subfolder: str = ""):
        """
        Initialize the parser
        
        Args:
            base_path: Base directory containing bank folders
            subfolder: Name of the subfolder containing OFX files
        """
        self.base_path = Path(base_path) / subfolder
    
    def _clean_description(self, desc: str) -> str:
        """Clean up transaction description"""
        # Remove multiple spaces and trim
        desc = ' '.join(desc.split())
        return desc.strip()
    
    def _parse_date(self, date_str: str) -> datetime:
        """Parse OFX date format (YYYYMMDDHHMMSS) to datetime"""
        return datetime.strptime(date_str[:8], '%Y%m%d')
    
    def _parse_amount(self, amount_str: str) -> Decimal:
        """Parse amount string to Decimal"""
        return Decimal(amount_str.strip())
    
    def _extract_tag_value(self, content: str, tag: str) -> Optional[str]:
        """Extract value between OFX tags"""
        pattern = f"<{tag}>([^<]+)"
        match = re.search(pattern, content)
        return match.group(1) if match else None 