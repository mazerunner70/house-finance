from pathlib import Path
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Any
import re
import json
from tabulate import tabulate
from parse_all_transactions import parse_all_account_folders
from collections import defaultdict

class MRCTracker:
    """Tracks Monthly Recurring Charges using regex patterns"""
    
    def __init__(self, config_path: Path = Path("config/mrc_patterns.json")):
        self.config_path = config_path
        self.patterns = self._load_patterns()
        
    def _load_patterns(self) -> Dict[str, str]:
        """Load regex patterns from config file"""
        if not self.config_path.exists():
            # Create default patterns if file doesn't exist
            default_patterns = {
                "Netflix": r"NETFLIX.COM",
                "Amazon Prime": r"PRIME VIDEO|AMAZON PRIME",
                "Spotify": r"SPOTIFY",
                "Phone Bill": r"(EE|VODAFONE|O2|THREE)",
                "Gym Membership": r"(PURE GYM|FITNESS FIRST|VIRGIN ACTIVE)",
                "Council Tax": r"COUNCIL TAX",
                "Mortgage": r"MORTGAGE",
                "Energy Bill": r"(BRITISH GAS|EDF|EON|SCOTTISH POWER)",
                "Water Bill": r"(THAMES WATER|ANGLIAN|SEVERN TRENT)",
                "Internet": r"(BT INTERNET|VIRGIN MEDIA|SKY DIGITAL|TALKTALK)"
            }
            
            # Ensure config directory exists
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Save default patterns
            with open(self.config_path, 'w') as f:
                json.dump(default_patterns, f, indent=4)
            
            return default_patterns
        
        # Load existing patterns
        with open(self.config_path, 'r') as f:
            return json.load(f)
    
    def _combine_transactions(self, statements_by_folder: Dict[str, List[Any]]) -> List[Any]:
        """Combine all transactions from all statements into a single list"""
        all_transactions = []
        
        for statements in statements_by_folder.values():
            for statement in statements:
                all_transactions.extend(statement.transactions)
        
        return sorted(all_transactions, key=lambda x: x.date)
    
    def track_recurring_charges(self, statements_by_folder: Dict[str, List[Any]]) -> Dict[str, List[Any]]:
        """
        Find all recurring charges using regex patterns
        
        Returns:
            Dict mapping charge names to lists of matching transactions
        """
        all_transactions = self._combine_transactions(statements_by_folder)
        recurring_charges = defaultdict(list)
        
        # Check each transaction against each pattern
        for trans in all_transactions:
            for charge_name, pattern in self.patterns.items():
                if re.search(pattern, trans.description.upper()):
                    recurring_charges[charge_name].append(trans)
        
        return recurring_charges
    
    def generate_report(self, recurring_charges: Dict[str, List[Any]], output_dir: Path = Path("output/reports")) -> None:
        """Generate report of recurring charges"""
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / "monthly_recurring_charges.txt"
        
        with open(output_file, 'w') as f:
            f.write("Monthly Recurring Charges Report\n")
            f.write("=" * 100 + "\n\n")
            
            for charge_name, transactions in recurring_charges.items():
                if not transactions:
                    continue
                    
                f.write(f"\n{charge_name}\n")
                f.write("-" * len(charge_name) + "\n")
                
                # Calculate statistics
                amounts = [t.amount for t in transactions]
                avg_amount = sum(amounts) / len(amounts)
                min_amount = min(amounts)
                max_amount = max(amounts)
                
                # Prepare transaction table
                table_data = [
                    [t.date.date(), t.type, f"£{abs(t.amount):,.2f}", t.description]
                    for t in sorted(transactions, key=lambda x: x.date)
                ]
                
                # Write statistics
                f.write(f"Total occurrences: {len(transactions)}\n")
                f.write(f"Average amount: £{abs(avg_amount):,.2f}\n")
                f.write(f"Min amount: £{abs(min_amount):,.2f}\n")
                f.write(f"Max amount: £{abs(max_amount):,.2f}\n\n")
                
                # Write transactions table
                f.write(tabulate(
                    table_data,
                    headers=['Date', 'Type', 'Amount', 'Description'],
                    tablefmt='grid'
                ))
                f.write("\n\n")
            
            # Write summary table
            summary_data = [
                [
                    name,
                    len(trans),
                    f"£{abs(sum(t.amount for t in trans)/len(trans)):,.2f}",
                    f"£{abs(sum(t.amount for t in trans)):,.2f}"
                ]
                for name, trans in recurring_charges.items()
                if trans
            ]
            
            f.write("\nSummary\n")
            f.write("=" * 50 + "\n")
            f.write(tabulate(
                summary_data,
                headers=['Charge', 'Count', 'Average', 'Total'],
                tablefmt='grid'
            ))
        
        print(f"Report written to {output_file}")

def main():
    base_path = Path("financial-data")
    if not base_path.exists():
        print("Financial data folder not found")
        return
    
    # Get all statements
    statements_by_folder = parse_all_account_folders(base_path)
    if not statements_by_folder:
        print("No statements found")
        return
    
    # Track recurring charges
    tracker = MRCTracker()
    recurring_charges = tracker.track_recurring_charges(statements_by_folder)
    
    # Generate report
    tracker.generate_report(recurring_charges)

if __name__ == "__main__":
    main() 