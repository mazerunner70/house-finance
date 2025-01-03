from pathlib import Path
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Any
from collections import defaultdict
import json
from tabulate import tabulate
from parse_all_transactions import parse_all_account_folders
from rc_tracker import RC_Tracker
from credit_card_balance import CreditCardBalance

class OtherPayments:
    """Tracks transactions not matched by RC_Tracker or credit card interest"""
    
    def __init__(self, statements_by_folder: Dict[str, List[Any]], rc_patterns_path: Path = Path("config/rc_patterns.json")):
        self.statements_by_folder = statements_by_folder
        rc_tracker = RC_Tracker()
        self.recurring_charges = rc_tracker.track_recurring_charges(statements_by_folder)
        self.all_transactions = rc_tracker.all_transactions
        
        # Get credit card interest transactions
        cc_balance = CreditCardBalance()
        self.interest_charges = cc_balance.find_interest_charges(statements_by_folder)
        
    # get all transactions from all subfolders, then remove all trnsactions matched by rc_tracker track_recurring_charges to get the unmatched transactions
    def get_unmatched_transactions(self):
        """Get transactions not matched by RC patterns or interest charges"""
        # Build set of transaction IDs from recurring charges
        rc_transaction_ids = set()
        for charge_data in self.recurring_charges.values():
            for trans in charge_data['known_transactions'] + charge_data['new_transactions']:
                rc_transaction_ids.add(trans.transaction_id)
        
        # Build set of transaction IDs from interest charges
        interest_transaction_ids = set()
        for card_name, charges in self.interest_charges.items():
            for trans in charges:
                interest_transaction_ids.add(trans.transaction_id)
        
        # Filter out both recurring charges and interest transactions
        unmatched_transactions = [
            trans for trans in self.all_transactions 
            if trans.transaction_id not in rc_transaction_ids
            and trans.transaction_id not in interest_transaction_ids
        ]
        
        return unmatched_transactions

    
    def generate_report(self, output_dir: Path = Path("output/reports")) -> None:
        """Generate report of non-RC transactions by month"""
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / "other_payments.txt"
        
        # Get unmatched transactions
        unmatched_transactions = self.get_unmatched_transactions()
        
        # Collect transactions by month
        monthly_transactions = defaultdict(list)
        for trans in unmatched_transactions:
            month_key = trans.date.strftime('%Y-%m')
            monthly_transactions[month_key].append(trans)
        
        # Sort months
        sorted_months = sorted(monthly_transactions.keys())
        
        # Calculate monthly totals and collect transaction details
        monthly_data = {}
        for month in sorted_months:
            transactions = monthly_transactions[month]
            total_debit = sum(t.amount for t in transactions if t.amount < 0)
            total_credit = sum(t.amount for t in transactions if t.amount > 0)
            
            # Sort transactions by amount
            transactions.sort(key=lambda x: x.amount)
            
            monthly_data[month] = {
                'transactions': transactions,
                'total_debit': total_debit,
                'total_credit': total_credit,
                'net': total_credit + total_debit
            }
        
        # Write report
        with open(output_file, 'w') as f:
            f.write("Other Payments Report\n")
            f.write("=" * 100 + "\n\n")
            
            # Write monthly summary table
            summary_data = []
            total_debit = Decimal('0')
            total_credit = Decimal('0')
            
            for month in sorted_months:
                data = monthly_data[month]
                month_name = datetime.strptime(month, '%Y-%m').strftime('%b %Y')
                summary_data.append([
                    month_name,
                    f"£{abs(data['total_debit']):,.2f}",
                    f"£{data['total_credit']:,.2f}",
                    f"£{data['net']:,.2f}",
                    len(data['transactions'])
                ])
                total_debit += data['total_debit']
                total_credit += data['total_credit']
            
            # Add totals row
            summary_data.append([
                "TOTAL",
                f"£{abs(total_debit):,.2f}",
                f"£{total_credit:,.2f}",
                f"£{total_credit + total_debit:,.2f}",
                sum(len(d['transactions']) for d in monthly_data.values())
            ])
            
            f.write("Monthly Summary\n")
            f.write("-" * 80 + "\n")
            f.write(tabulate(
                summary_data,
                headers=['Month', 'Debits', 'Credits', 'Net', 'Count'],
                tablefmt='grid',
                stralign='right'
            ))
            f.write("\n\n")
            
            # Write detailed transactions for each month
            f.write("Monthly Details\n")
            f.write("=" * 80 + "\n\n")
            
            for month in sorted_months:
                data = monthly_data[month]
                month_name = datetime.strptime(month, '%Y-%m').strftime('%B %Y')
                f.write(f"\n{month_name}\n")
                f.write("-" * len(month_name) + "\n")
                
                # Sort transactions by date for this month
                sorted_transactions = sorted(data['transactions'], key=lambda x: x.date)
                
                trans_data = []
                for trans in sorted_transactions:  # Use sorted transactions
                    # Get subfolder name from transaction
                    subfolder = getattr(trans, 'account_name', None)  # Try account_name first
                    if not subfolder:
                        subfolder = getattr(trans, 'account_id', 'Unknown')  # Fall back to account_id
                    
                    trans_data.append([
                        trans.date.strftime('%d/%m/%Y'),
                        f"£{trans.amount:,.2f}",
                        trans.description,
                        trans.type,
                        subfolder,
                        trans.transaction_id
                    ])
                
                f.write(tabulate(
                    trans_data,
                    headers=['Date', 'Amount', 'Description', 'Type', 'Account', 'Transaction ID'],
                    tablefmt='grid',
                    stralign='right'
                ))
                f.write("\n")
        
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
    
    # Generate other payments report
    other_payments = OtherPayments(statements_by_folder)
    other_payments.get_unmatched_transactions()
    other_payments.generate_report()

if __name__ == "__main__":
    main() 