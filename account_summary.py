from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Any
from tabulate import tabulate
from pathlib import Path
from parse_all_transactions import parse_all_account_folders
import os

@dataclass
class AccountSummary:
    """Summary of an account's transactions"""
    folder_name: str
    total_income: Decimal
    total_expense: Decimal
    first_transaction: datetime
    last_transaction: datetime
    num_transactions: int

class AccountSummarizer:
    """Creates summaries of account transactions"""
    
    def __init__(self, statements_by_folder: Dict[str, List[Any]]):
        self.statements_by_folder = statements_by_folder
        self.summaries = self._create_summaries()
    
    def _create_summaries(self) -> List[AccountSummary]:
        """Create summary for each account folder"""
        summaries = []
        
        for folder_name, statements in self.statements_by_folder.items():
            total_income = Decimal('0')
            total_expense = Decimal('0')
            all_transactions_dates = []
            num_transactions = 0
            
            for statement in statements:
                for trans in statement.transactions:
                    amount = abs(trans.amount)
                    if trans.amount>=0:
                        total_income += amount
                    else:
                        total_expense += amount
                    
                    all_transactions_dates.append(trans.date)
                    num_transactions += 1
            
            if all_transactions_dates:
                summaries.append(AccountSummary(
                    folder_name=folder_name,
                    total_income=total_income,
                    total_expense=total_expense,
                    first_transaction=min(all_transactions_dates),
                    last_transaction=max(all_transactions_dates),
                    num_transactions=num_transactions
                ))
        
        return sorted(summaries, key=lambda x: abs(x.total_expense - x.total_income), reverse=True)
    
    def print_summary_table(self) -> None:
        """Write formatted table of account summaries to a file"""
        table_data = []
        total_income = Decimal('0')
        total_expense = Decimal('0')
        
        for summary in self.summaries:
            table_data.append([
                summary.folder_name,
                f"£{summary.total_income:,.2f}",
                f"£{summary.total_expense:,.2f}",
                f"£{summary.total_income - summary.total_expense:,.2f}",
                summary.first_transaction.date(),
                summary.last_transaction.date(),
                summary.num_transactions
            ])
            total_income += summary.total_income
            total_expense += summary.total_expense
        
        # Add totals row
        table_data.append([
            "TOTAL",
            f"£{total_income:,.2f}",
            f"£{total_expense:,.2f}",
            f"£{total_income - total_expense:,.2f}",
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
            f.write("=" * 100 + "\n")
            f.write(tabulate(
                table_data,
                headers=['Account', 'Income', 'Expense', 'Net', 'First Trans', 'Last Trans', 'Num Trans'],
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