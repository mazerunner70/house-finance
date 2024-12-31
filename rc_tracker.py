from pathlib import Path
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Any
import re
import json
from tabulate import tabulate
from parse_all_transactions import parse_all_account_folders
from collections import defaultdict
from Levenshtein import distance

class RC_Tracker:
    """Tracks Monthly Recurring Charges using regex patterns"""
    
    def __init__(self, config_path: Path = Path("config/rc_patterns.json")):
        self.config_path = config_path
        
    def _load_transactions(self, statements_by_folder: Dict[str, List[Any]]) -> Dict[str, Dict[str, Any]]:
        """
        Load transactions and update recurring charge patterns
        
        Returns:
            Dict mapping charge names to dict containing:
                - transactions: List of matching transactions
                - interval: String indicating frequency
                - amount_range: Dict with min/max/avg amounts
        """
        # Load existing patterns
        rc_file = Path("config/rc_patterns.json")
        if rc_file.exists():
            with open(rc_file, 'r') as f:
                rc_patterns = json.load(f)
        else:
            rc_patterns = {}

        # Get all transactions sorted by date
        all_transactions = sorted(
            self._combine_transactions(statements_by_folder),
            key=lambda x: x.date
        )
        
        recurring_charges = {}
        
        # Process known patterns
        for charge_name, config in rc_patterns.items():
            pattern = config.get('pattern', '')
            interval = config.get('interval', 'monthly')
            known_ids = set(config.get('transaction_ids', []))
            status = config.get('status', 'running')
            status_change_date = config.get('status_change_date', None)
            
            # Find matching transactions
            matching_trans = []
            known_transactions = []
            new_transactions = []
            new_transaction_ids = []
            
            # Only look for new transactions if status is 'running'
            is_active = status == 'running'
            
            for trans in all_transactions:
                if re.search(pattern, trans.description, re.IGNORECASE) and trans.transaction_id not in known_ids:
                    matching_trans.append(trans)
                if trans.transaction_id in known_ids:
                    known_transactions.append(trans)
            
            # Look for similar descriptions with similar intervals
            avg_amount = sum(t.amount for t in known_transactions) / len(known_transactions) if known_transactions else None                   
            # Check for similar amount and description
            for trans in matching_trans:
                good_amount_diff = (abs(trans.amount - avg_amount) / abs(avg_amount) < 0.2) if known_transactions and avg_amount!= 0 else True
                good_interval = self._fits_interval_pattern(trans.date, known_transactions, interval)
                if good_amount_diff and good_interval:
                    new_transactions.append(trans)
                    new_transaction_ids.append(trans.transaction_id)
            full_transactions = known_transactions + new_transactions
            # Sort transactions by date
            full_transactions.sort(key=lambda x: x.date)
            
            # Calculate amount ranges
            if full_transactions:
                amounts = [abs(t.amount) for t in full_transactions]
                amount_range = {
                    'min': str(min(amounts)),
                    'max': str(max(amounts)),
                    'avg': str(sum(amounts) / len(amounts))
                }
            else:
                amount_range = {
                    'min': '0',
                    'max': '0',
                    'avg': '0'
                }
            
            # Store results
            recurring_charges[charge_name] = {
                'known_transactions': known_transactions,
                'new_transactions': new_transactions,
                'interval': interval,
                'amount_range': amount_range,
                'transaction_ids': sorted(list(known_ids) + new_transaction_ids),
                'status': status,
                'status_change_date': status_change_date
            }
            
            # Update pattern file
            rc_patterns[charge_name].update({
                'transaction_ids': sorted(list(known_ids) + new_transaction_ids),
                'last_updated': datetime.now().isoformat(),
                'amount_range': amount_range,
                'status': status,
                'status_change_date': status_change_date
            })
        
        # Save updated patterns
        with open(rc_file, 'w') as f:
            json.dump(rc_patterns, f, indent=4)
        
        return recurring_charges

    def _calculate_avg_interval(self, dates: List[datetime]) -> timedelta:
        """Calculate average interval between dates"""
        if len(dates) < 2:
            return timedelta(days=30)  # Default to monthly
        
        intervals = []
        dates = sorted(dates)
        for i in range(1, len(dates)):
            intervals.append((dates[i] - dates[i-1]).days)
        
        return timedelta(days=sum(intervals) / len(intervals))

    def _fits_interval_pattern(self, date: datetime, existing_trans: List[Any], interval: str) -> bool:
        """
        Check if a date fits the existing transaction pattern
        
        Args:
            date: Date to check
            existing_trans: List of existing transactions
            interval: Configured interval ('monthly', 'quarterly', 'annual', 'irregular', etc)
        """
        if not existing_trans:
            return True
        
        # Always return True for irregular intervals
        if interval.lower() == 'irregular':
            return True
        
        # Convert interval to days
        interval_days = {
            'monthly': 30,
            'quarterly': 90,
            'biannual': 180,
            'annual': 365,
            'weekly': 7,
            'biweekly': 14
        }.get(interval.lower(), 30)  # Default to monthly if unknown
        
        # Get closest transaction date
        existing_dates = [t.date for t in existing_trans]
        closest_date = min(existing_dates, key=lambda d: abs(d - date))
        
        # Check if the interval is reasonable (allow 20% variation)
        days_diff = abs((date - closest_date).days)
        return abs(days_diff - interval_days) <= (interval_days * 0.2)
    
    def _combine_transactions(self, statements_by_folder: Dict[str, List[Any]]) -> List[Any]:
        """Combine all transactions from all statements into a single list"""
        all_transactions = []
        
        for statements in statements_by_folder.values():
            for statement in statements:
                all_transactions.extend(statement.transactions)
        
        return sorted(all_transactions, key=lambda x: x.date)
    
    def track_recurring_charges(self, statements_by_folder: Dict[str, List[Any]]) -> Dict[str, Dict[str, Any]]:
        """
        Find and track all recurring charges
        
        Returns:
            Dict mapping charge names to dict containing:
                - transactions: List of matching transactions
                - interval: String indicating frequency
                - amount_range: Dict with min/max/avg amounts
                - transaction_ids: List of matched transaction IDs
        """
        # Get full recurring charges data
        recurring_charges = self._load_transactions(statements_by_folder)
        
        # Return the complete data structure
        return recurring_charges
    
    def generate_report(self, recurring_charges: Dict[str, Dict[str, Any]], output_dir: Path = Path("output/reports")) -> None:
        """Generate report of recurring charges"""
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / "recurring_charges.txt"
        
        with open(output_file, 'w') as f:
            f.write("Recurring Charges Report\n")
            f.write("=" * 100 + "\n\n")
            
            for charge_name, charge_data in recurring_charges.items():
                known_transactions = charge_data['known_transactions']
                new_transactions = charge_data['new_transactions']
                
                if not (known_transactions or new_transactions):
                    continue
                    
                interval = charge_data['interval']
                amount_range = charge_data['amount_range']
                
                f.write(f"\n{charge_name} ({interval}) - {charge_data['status'].upper()}\n")
                if charge_data['status_change_date']:
                    f.write(f"Status changed: {charge_data['status_change_date']}\n")
                f.write("-" * (len(charge_name) + len(interval) + len(charge_data['status']) + 5) + "\n")
                
                # Write statistics with rounded amounts
                total_transactions = len(known_transactions) + len(new_transactions)
                f.write(f"Total occurrences: {total_transactions}\n")
                f.write(f"Known transactions: {len(known_transactions)}\n")
                f.write(f"New transactions: {len(new_transactions)}\n")
                f.write(f"Average amount: £{float(amount_range['avg']):.2f}\n")
                f.write(f"Min amount: £{float(amount_range['min']):.2f}\n")
                f.write(f"Max amount: £{float(amount_range['max']):.2f}\n\n")
                
                # Write known transactions table
                if known_transactions:
                    f.write("Known Transactions:\n")
                    table_data = [
                        [
                            t.date.date(),
                            t.transaction_id,
                            t.type,
                            f"£{t.amount:.2f}",
                            t.description
                        ]
                        for t in sorted(known_transactions, key=lambda x: x.date)
                    ]
                    
                    f.write(tabulate(
                        table_data,
                        headers=['Date', 'Transaction ID', 'Type', 'Amount', 'Description'],
                        tablefmt='grid'
                    ))
                    f.write("\n\n")
                
                # Write new transactions table
                if new_transactions:
                    f.write("New Transactions:\n")
                    table_data = [
                        [
                            t.date.date(),
                            t.transaction_id,
                            t.type,
                            f"£{t.amount:.2f}",
                            t.description
                        ]
                        for t in sorted(new_transactions, key=lambda x: x.date)
                    ]
                    
                    f.write(tabulate(
                        table_data,
                        headers=['Date', 'Transaction ID', 'Type', 'Amount', 'Description'],
                        tablefmt='grid'
                    ))
                    f.write("\n\n")
            
            # Write summary table with rounded amounts and status
            active_total = Decimal('0')
            cancelled_total = Decimal('0')
            
            summary_data = []
            for name, data in recurring_charges.items():
                if not (data['known_transactions'] or data['new_transactions']):
                    continue
                    
                avg_amount = Decimal(data['amount_range']['avg'])
                all_transactions = data['known_transactions'] + data['new_transactions']
                
                # Calculate monthly cost based on interval
                if data['interval'].lower() == 'irregular':
                    # Calculate days between first and last transaction
                    all_dates = [t.date for t in all_transactions]
                    first_date = min(all_dates)
                    last_date = max(all_dates)
                    days_diff = (last_date - first_date).days + 1  # Add 1 to include both start and end dates
                    months = Decimal(days_diff) / Decimal('30')
                    
                    # Calculate monthly cost based on actual period
                    total_spent = avg_amount * len(all_transactions)
                    monthly_cost = total_spent / max(months, Decimal('1'))  # Avoid division by zero
                else:
                    # Convert interval to months
                    interval_months = {
                        'weekly': Decimal('0.25'),  # 1/4 month
                        'biweekly': Decimal('0.5'),  # 1/2 month
                        'monthly': Decimal('1'),
                        'quarterly': Decimal('3'),
                        'biannual': Decimal('6'),
                        'annual': Decimal('12')
                    }.get(data['interval'].lower(), Decimal('1'))
                    
                    monthly_cost = avg_amount / interval_months
                
                if data['status'] == 'running':
                    active_total += monthly_cost
                else:
                    cancelled_total += monthly_cost
                
                summary_data.append([
                    f"{name} ({data['status'].upper()})",
                    len(data['known_transactions']),
                    len(data['new_transactions']),
                    f"£{float(avg_amount):.2f}",
                    f"£{float(monthly_cost):.2f}"
                ])
            
            f.write("\nSummary\n")
            f.write("=" * 50 + "\n")
            f.write(tabulate(
                summary_data,
                headers=['Charge (Status)', 'Known', 'New', 'Amount', 'Monthly Cost'],
                tablefmt='grid'
            ))
            
            # Write totals
            f.write(f"\n\nActive Monthly Total: £{float(active_total):.2f}")
            f.write(f"\nCancelled Monthly Total: £{float(cancelled_total):.2f}")
            f.write(f"\nOverall Monthly Total: £{float(active_total + cancelled_total):.2f}")
        
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
    tracker = RC_Tracker()
    recurring_charges = tracker.track_recurring_charges(statements_by_folder)
    
    # Generate report
    tracker.generate_report(recurring_charges)

if __name__ == "__main__":
    main() 