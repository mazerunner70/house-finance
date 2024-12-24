from pathlib import Path
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Any
from tabulate import tabulate
from parse_all_transactions import parse_all_account_folders

class AccountDetailer:
    """Creates detailed transaction reports for accounts"""
    
    def __init__(self, statements_by_folder: Dict[str, List[Any]], output_dir: Path = Path("output/details/accounts")):
        self.statements_by_folder = statements_by_folder
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def generate_account_detail(self, folder_name: str) -> None:
        """
        Generate detailed transaction report for a specific account
        
        Args:
            folder_name: Name of the account folder to process
        """
        if folder_name not in self.statements_by_folder:
            print(f"No statements found for {folder_name}")
            return
            
        statements = self.statements_by_folder[folder_name]
        output_file = self.output_dir / f"{folder_name}_transactions.txt"
        
        with open(output_file, 'w') as f:
            f.write(f"Transaction Details for {folder_name}\n")
            f.write("=" * 100 + "\n\n")
            
            for statement in statements:
                # Write statement header
                f.write(f"Statement Period: {statement.start_date.date()} to {statement.end_date.date()}\n")
                
                # Write balance information
                if hasattr(statement, 'credit_limit'):
                    if statement.credit_limit:
                        f.write(f"Credit limit: £{statement.credit_limit:.2f}\n")
                    f.write(f"Current balance: £{statement.current_balance:.2f}\n")
                    if statement.available_credit:
                        f.write(f"Available credit: £{statement.available_credit:.2f}\n")
                elif hasattr(statement, 'start_balance'):
                    f.write(f"Opening balance: £{statement.start_balance:.2f}\n")
                    f.write(f"Closing balance: £{statement.end_balance:.2f}\n")
                
                # Prepare transaction data for table
                table_data = []
                for trans in statement.transactions:
                    # Format post date if exists
                    post_date = ""
                    if hasattr(trans, 'post_date') and trans.post_date != trans.date:
                        post_date = f"(posted {trans.post_date.date()})"
                    
                    # Format category if exists
                    category = ""
                    if hasattr(trans, 'merchant_category') and trans.merchant_category:
                        category = f"[{trans.merchant_category}]"
                    elif hasattr(trans, 'category') and trans.category:
                        category = f"[{trans.category}]"
                    
                    # Prepare transaction row
                    transaction_row = [
                        trans.date.date(),
                        post_date,
                        f"ID: {trans.transaction_id}",  # Include transaction_id
                        trans.type,
                        f"£{trans.amount:,.2f}",
                        f"{trans.description} {category}"
                    ]
                    
                    # Include running_total only if it exists
                    if hasattr(trans, 'running_total'):
                        transaction_row.append(f"£{trans.running_total:,.2f}")
                    else:
                        transaction_row.append("")  # Add an empty string if running_total is not present
                    
                    table_data.append(transaction_row)
                
                # Write transaction table
                f.write("\nTransactions:\n")
                f.write(tabulate(
                    table_data,
                    headers=['Date', 'Posted', 'Transaction ID', 'Type', 'Amount', 'Description', 'Running Total'],
                    tablefmt='grid'
                ))
                f.write("\n\n" + "=" * 100 + "\n\n")
    
    def generate_all_details(self) -> None:
        """Generate detailed reports for all accounts"""
        for folder_name in self.statements_by_folder:
            self.generate_account_detail(folder_name)

def main():
    """Generate detailed reports for all accounts"""
    base_path = Path("financial-data")
    if not base_path.exists():
        print("Financial data folder not found")
        return
        
    # Get all statements
    statements_by_folder = parse_all_account_folders(base_path)
    if not statements_by_folder:
        print("No statements found")
        return
    
    # Generate detailed reports
    detailer = AccountDetailer(statements_by_folder)
    detailer.generate_all_details()
    print(f"\nDetailed reports generated in {detailer.output_dir}")

if __name__ == "__main__":
    main() 
