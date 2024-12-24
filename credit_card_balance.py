from pathlib import Path
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Any
import re
import json
from tabulate import tabulate
from parse_all_transactions import parse_all_account_folders
from collections import defaultdict

class CreditCardBalance:
    """Tracks credit card balances and interest charges"""
    
    def __init__(self, config_path: Path = Path("config/credit_cards.json")):
        self.config_path = config_path
        self.card_configs = self._load_config()
        
    def _load_config(self) -> Dict[str, str]:
        """Load credit card configurations"""
        if not self.config_path.exists():
            # Create default config if file doesn't exist
            default_config = {
                "barclaycard": {
                    "folder_pattern": "barclaycard",
                    "interest_pattern": r"Interest On Your Standard"
                },
                "mbna": {
                    "folder_pattern": "mbna",
                    "interest_pattern": r"INTEREST"
                },
                "halifax": {
                    "folder_pattern": "halifax",
                    "interest_pattern": r"INTEREST"
                },
                "john-lewis": {
                    "folder_pattern": "johnlewis",
                    "interest_pattern": r"INTEREST"
                },
                "barclays": {
                    "folder_pattern": "barclays",
                    "interest_pattern": r"INTEREST CHARGED"
                }
            }
            
            # Ensure config directory exists
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Save default config
            with open(self.config_path, 'w') as f:
                json.dump(default_config, f, indent=4)
            
            return default_config
        
        # Load existing config
        with open(self.config_path, 'r') as f:
            return json.load(f)
    
    def find_interest_charges(self, statements_by_folder: Dict[str, List[Any]]) -> Dict[str, List[Any]]:
        """
        Find interest charges for each credit card
        
        Returns:
            Dict mapping card names to lists of interest transactions
        """
        interest_by_card = defaultdict(list)
        
        for card_name, config in self.card_configs.items():
            folder_pattern = config['folder_pattern']
            interest_pattern = config['interest_pattern']
            
            # Find matching folder
            for folder_name, statements in statements_by_folder.items():
                if re.search(folder_pattern, folder_name, re.IGNORECASE):
                    # Process statements for this folder
                    for statement in statements:
                        for trans in statement.transactions:
                            if re.search(interest_pattern, trans.description, re.IGNORECASE):
                                interest_by_card[folder_name].append(trans)
        
        return interest_by_card
    
    def generate_report(self, interest_by_card: Dict[str, List[Any]], output_dir: Path = Path("output/reports")) -> None:
        """Generate credit card interest reports"""
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate detailed report
        self.generate_detailed_report(interest_by_card, output_dir)
        
        # Generate monthly summary
        self.generate_monthly_summary(interest_by_card, output_dir)
    
    def generate_detailed_report(self, interest_by_card: Dict[str, List[Any]], output_dir: Path = Path("output/reports")) -> None:
        """Generate credit card interest report"""
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / "credit_card_interest.txt"
        
        with open(output_file, 'w') as f:
            f.write("Credit Card Interest Report\n")
            f.write("=" * 100 + "\n\n")
            
            total_interest = Decimal('0')
            total_charges = 0
            summary_data = []
            
            for card_name, transactions in interest_by_card.items():
                if not transactions:
                    continue
                    
                f.write(f"\n{card_name}\n")
                f.write("-" * len(card_name) + "\n")
                
                # Calculate statistics
                total_card_interest = sum(t.amount for t in transactions)
                avg_interest = total_card_interest / len(transactions)
                min_interest = min(t.amount for t in transactions)
                max_interest = max(t.amount for t in transactions)
                
                total_interest += total_card_interest
                total_charges += len(transactions)
                
                # Prepare transaction table
                table_data = [
                    [t.date.date(), f"£{abs(t.amount):,.2f}", t.description]
                    for t in sorted(transactions, key=lambda x: x.date)
                ]
                
                # Write statistics
                f.write(f"Total interest charges: £{abs(total_card_interest):,.2f}\n")
                f.write(f"Average monthly interest: £{abs(avg_interest):,.2f}\n")
                f.write(f"Min interest: £{abs(min_interest):,.2f}\n")
                f.write(f"Max interest: £{abs(max_interest):,.2f}\n")
                f.write(f"Number of charges: {len(transactions)}\n\n")
                
                # Write transactions table
                f.write(tabulate(
                    table_data,
                    headers=['Date', 'Amount', 'Description'],
                    tablefmt='grid'
                ))
                f.write("\n\n")
                
                # Add to summary data
                summary_data.append([
                    card_name,
                    len(transactions),
                    f"£{abs(avg_interest):,.2f}",
                    f"£{abs(total_card_interest):,.2f}"
                ])
            
            # Add totals row to summary data
            avg_total = total_interest / total_charges if total_charges > 0 else Decimal('0')
            summary_data.append([
                "TOTAL",
                total_charges,
                f"£{abs(avg_total):,.2f}",
                f"£{abs(total_interest):,.2f}"
            ])
            
            # Write overall summary
            f.write("\nOverall Summary\n")
            f.write("=" * 50 + "\n")
            f.write(f"Total interest paid across all cards: £{abs(total_interest):,.2f}\n")
            f.write(f"Total number of interest charges: {total_charges}\n")
            f.write(f"Average interest per charge: £{abs(avg_total):,.2f}\n\n")
            
            # Write summary table with totals row
            f.write(tabulate(
                summary_data,
                headers=['Card', 'Charges', 'Avg Monthly', 'Total Interest'],
                tablefmt='grid'
            ))
        
        print(f"Report written to {output_file}")
    
    def generate_monthly_summary(self, interest_by_card: Dict[str, List[Any]], output_dir: Path = Path("output/reports")) -> None:
        """Generate monthly summary chart of interest charges"""
        output_file = output_dir / "monthly_interest_summary.txt"
        
        # Collect all months and cards
        months_set = set()
        monthly_data = defaultdict(lambda: defaultdict(list))
        
        for card_name, transactions in interest_by_card.items():
            for trans in transactions:
                month_key = trans.date.strftime('%Y-%m')
                months_set.add(month_key)
                monthly_data[card_name][month_key].append(trans)

        # for each card, if there are two entries for a month, move the second entry to the month after
        for card_name, transactions in monthly_data.items():
            for month_key in sorted(transactions.keys()):
                if len(transactions[month_key]) == 2 and month_key != max(transactions.keys()):
                    next_month_key = datetime.strptime(month_key, '%Y-%m').replace(day=1) + timedelta(days=32)
                    next_month_key = next_month_key.strftime('%Y-%m')
                    if next_month_key not in transactions:
                        transactions[next_month_key] = [transactions[month_key][1]]
                        del transactions[month_key][1]
        
        # Sort months chronologically
        months = sorted(list(months_set))
        
        # Prepare table data
        table_data = []
        card_totals = defaultdict(Decimal)
        month_totals = defaultdict(Decimal)
        
        for card_name in sorted(interest_by_card.keys()):
            row = [card_name]
            card_total = Decimal('0')
            
            for month in months:
                interest_trans = monthly_data[card_name][month]
                interest_tran = interest_trans[0] if interest_trans else None
                if interest_tran:
                    card_total += interest_tran.amount
                    month_totals[month] += interest_tran.amount
                    amttext = f"£{abs(interest_tran.amount):,.2f}"
                    if interest_tran.running_total:
                        amttext += f"({interest_tran.amount/interest_tran.running_total:.2%})"
                    row.append(amttext)
                else:
                    row.append("-")       
            card_totals[card_name] = card_total
            row.append(f"£{abs(card_total):,.2f}")
            table_data.append(row)
        
        # Add totals row
        totals_row = ["TOTAL"]
        grand_total = Decimal('0')
        
        for month in months:
            total = month_totals[month]
            grand_total += total
            totals_row.append(f"£{abs(total):,.2f}" if total != 0 else "-")
        
        totals_row.append(f"£{abs(grand_total):,.2f}")
        table_data.append(totals_row)
        
        # Write to file
        with open(output_file, 'w') as f:
            f.write("Monthly Interest Charges Summary\n")
            f.write("=" * 100 + "\n\n")
            
            # Create headers with month names
            headers = ['Card'] + [datetime.strptime(m, '%Y-%m').strftime('%b %Y') for m in months] + ['Total']
            
            f.write(tabulate(
                table_data,
                headers=headers,
                tablefmt='grid',
                stralign='right'
            ))
            
            # Add analysis section
            f.write("\n\nAnalysis\n")
            f.write("=" * 50 + "\n")
            f.write(f"Period covered: {headers[1]} to {headers[-2]}\n")
            f.write(f"Total interest paid: £{abs(grand_total):,.2f}\n")
            
            # Find highest month
            highest_month = max(month_totals.items(), key=lambda x: abs(x[1]))
            highest_month_name = datetime.strptime(highest_month[0], '%Y-%m').strftime('%b %Y')
            f.write(f"Highest interest month: {highest_month_name} (£{abs(highest_month[1]):,.2f})\n")
            
            # Find highest card
            highest_card = max(card_totals.items(), key=lambda x: abs(x[1]))
            f.write(f"Highest interest card: {highest_card[0]} (£{abs(highest_card[1]):,.2f})\n")
        
        print(f"Monthly summary written to {output_file}")

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
    
    # Track credit card interest
    tracker = CreditCardBalance()
    interest_charges = tracker.find_interest_charges(statements_by_folder)
    
    # Generate reports
    tracker.generate_report(interest_charges)

if __name__ == "__main__":
    main() 