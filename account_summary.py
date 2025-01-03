from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Any, Optional
from tabulate import tabulate
from pathlib import Path
from parse_all_transactions import parse_all_account_folders
import json

@dataclass
class AccountSummary:
    """Summary of an account's transactions"""
    folder_name: str
    total_income: Decimal
    total_expense: Decimal
    first_transaction: datetime
    last_transaction: datetime
    num_transactions: int
    last_checked: Optional[datetime] = None
    running_total: Optional[Decimal] = None

class AccountSummarizer:
    """Creates summaries of account transactions"""
    
    def __init__(self, statements_by_folder: Dict[str, List[Any]]):
        self.statements_by_folder = statements_by_folder
        self.config_file = Path("config/account_dates.json")
        self.dates_config = self._load_dates_config()
        self.summaries = self._create_summaries()
        self._update_dates_config()
    
    def _load_dates_config(self) -> Dict[str, Dict[str, str]]:
        """Load or create dates configuration"""
        if self.config_file.exists():
            with open(self.config_file, 'r') as f:
                return json.load(f)
        return {}
    
    def _update_dates_config(self) -> None:
        """Update dates configuration with current date for processed folders"""
        today = datetime.now().strftime('%Y-%m-%d')
        updated = False
        
        for summary in self.summaries:
            if summary.folder_name not in self.dates_config:
                self.dates_config[summary.folder_name] = {}
                updated = True
        
        if updated:
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_file, 'w') as f:
                json.dump(self.dates_config, f, indent=4)
    
    def _create_summaries(self) -> List[AccountSummary]:
        """Create summary for each account folder"""
        summaries = []
        
        for folder_name, statements in self.statements_by_folder.items():
            total_income = Decimal('0')
            total_expense = Decimal('0')
            all_transactions_dates = []
            num_transactions = 0
            running_total = None
            
            for statement in statements:
                for trans in statement.transactions:
                    amount = abs(trans.amount)
                    if trans.amount >= 0:
                        total_income += amount
                    else:
                        total_expense += amount
                    
                    all_transactions_dates.append(trans.date)
                    num_transactions += 1
                    
                    if hasattr(trans, 'running_total'):
                        running_total = trans.running_total
            
            if all_transactions_dates:
                # Get last checked date from config
                last_checked = None
                if folder_name in self.dates_config:
                    try:
                        last_checked = datetime.strptime(
                            self.dates_config[folder_name]['last_checked'],
                            '%Y-%m-%d'
                        )
                    except (ValueError, KeyError):
                        pass
                
                summaries.append(AccountSummary(
                    folder_name=folder_name,
                    total_income=total_income,
                    total_expense=total_expense,
                    first_transaction=min(all_transactions_dates),
                    last_transaction=max(all_transactions_dates),
                    num_transactions=num_transactions,
                    last_checked=last_checked,
                    running_total=running_total
                ))
        
        return sorted(summaries, key=lambda x: abs(x.total_expense - x.total_income), reverse=True)
    
    def print_summary_table(self) -> None:
        """Write formatted table of account summaries to a file"""
        table_data = []
        total_income = Decimal('0')
        total_expense = Decimal('0')
        total_balance = Decimal('0')
        
        for summary in self.summaries:
            table_data.append([
                summary.folder_name,
                f"£{summary.total_income:,.2f}",
                f"£{summary.total_expense:,.2f}",
                f"£{summary.total_income - summary.total_expense:,.2f}",
                f"£{summary.running_total:,.2f}" if summary.running_total is not None else "N/A",
                summary.first_transaction.date(),
                summary.last_transaction.date(),
                summary.last_checked.date() if summary.last_checked else "Never",
                summary.num_transactions
            ])
            total_income += summary.total_income
            total_expense += summary.total_expense
            if summary.running_total is not None:
                total_balance += summary.running_total
        
        # Add totals row
        table_data.append([
            "TOTAL",
            f"£{total_income:,.2f}",
            f"£{total_expense:,.2f}",
            f"£{total_income - total_expense:,.2f}",
            f"£{total_balance:,.2f}",
            "",
            "",
            "",
            sum(s.num_transactions for s in self.summaries)
        ])
        
        # Create output directory if it doesn't exist
        output_dir = Path("output/summaries")
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Write to file
        output_file_path = output_dir / "account_summaries.txt"
        with open(output_file_path, 'w') as f:
            f.write("\nAccount Summaries\n")
            f.write("=" * 120 + "\n")
            f.write(tabulate(
                table_data,
                headers=['Account', 'Income', 'Expense', 'Net', 'Balance', 'First Trans', 'Last Trans', 'Last Checked', 'Num Trans'],
                tablefmt='grid'
            ))
        
        print(f"Summary written to {output_file_path}")

def main():
    """Process all accounts and show summary table"""
    base_path = Path("financial-data")
    if not base_path.exists():
        print("Financial data folder not found")
        return
        
    # Get all statements
    statements_by_folder = parse_all_account_folders(base_path)
    if not statements_by_folder:
        print("No statements found")
        return
    
    # Create and print summary
    summarizer = AccountSummarizer(statements_by_folder)
    summarizer.print_summary_table()

if __name__ == "__main__":
    main() 