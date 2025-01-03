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
        self.all_transactions = sorted(
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
            new_matching_trans = []
            known_transactions = []
            new_transactions = []
            new_transaction_ids = []
            
            # for this charge, find all known transactions and all new transactions
            for trans in self.all_transactions:
                if trans.transaction_id in known_ids:
                    known_transactions.append(trans)
                elif re.search(pattern, trans.description, re.IGNORECASE):
                    new_matching_trans.append(trans)

            sanitised_transactions = self.sanitise(known_transactions)
            # Look for similar descriptions with similar intervals
            avg_amount = sum(t.amount for t in sanitised_transactions) / len(sanitised_transactions) if sanitised_transactions else None                   
            # Check for similar amount and description
            for trans in new_matching_trans:
                good_amount_diff = (abs(trans.amount - avg_amount) / abs(avg_amount) < 0.2) if known_transactions and avg_amount!= 0 else True
                good_interval = self._fits_interval_pattern(trans.date, sanitised_transactions, interval)
                if interval == 'irregular' or (good_amount_diff and good_interval):
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

    def generate_budget_report(self, recurring_charges: Dict[str, Dict[str, Any]], output_dir: Path = Path("output/reports")) -> None:
        """Generate budget report showing last 3 months, current month spend and targets"""
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / "budget_report.txt"
        
        # Load budget targets
        budget_file = Path("config/budget_targets.json")
        if budget_file.exists():
            with open(budget_file, 'r') as f:
                budget_targets = json.load(f)
        else:
            budget_targets = {}
        
        # Get current month and previous 3 complete months
        today = datetime.now()
        current_month_date = today.replace(day=1)
        current_month_key = current_month_date.strftime('%Y-%m')
        
        # Get the 3 complete months + the current month
        recent_months = []
        first_prev_month = current_month_date
        for _ in range(4):
            recent_months.append(first_prev_month)
            # Move to first day of previous month
            first_prev_month = (first_prev_month - timedelta(days=1)).replace(day=1)
        
        recent_months.reverse()  # Oldest first

        # get recent months keys
        recent_months_keys = [month.strftime('%Y-%m') for month in recent_months]
        
        # Calculate monthly totals for each charge
        budget_data = []
        targets_updated = False
        
        for name, data in recurring_charges.items():
            all_transactions = data['known_transactions'] + data['new_transactions']
            
            # Initialise monthly totals with the previous months as keys and empty lists as values
            monthly_totals = {key: [] for key in recent_months_keys}
            
            # Populate monthly totals with all transactions
            for trans in all_transactions:
                trans_month_key = trans.date.strftime('%Y-%m')
                # Store tuple of (amount, date) to track transaction order
                if trans_month_key in monthly_totals:
                    monthly_totals[trans_month_key].append((abs(trans.amount), trans.date))
            
            # Handle monthly interval charges with multiple entries in a month
            if data['interval'].lower() == 'monthly':
                # if there are zero amounts in a month, move the first amount from the next month to the current month
                for i in range(len(recent_months_keys)):
                    if not monthly_totals[recent_months_keys[i]] and i < len(recent_months_keys) - 1 and len(monthly_totals[recent_months_keys[i + 1]]) > 0:
                        next_month_key = recent_months_keys[i + 1]
                        monthly_totals[recent_months_keys[i]].append(monthly_totals[next_month_key][0])
                        monthly_totals[next_month_key] = monthly_totals[next_month_key][1:]
            
            # Convert lists to totals (sum only the amounts, not the dates)
            monthly_sums = {
                month: sum(amount for amount, _ in amounts)
                for month, amounts in monthly_totals.items()
            }
            
            # Calculate 3-month average if no target exists
            previous_amounts = [
                monthly_sums.get(m.strftime('%Y-%m'), Decimal('0')) 
                for m in recent_months[0:3]
            ]
            
            if previous_amounts:
                three_month_avg = sum(previous_amounts[0:3]) / Decimal('3')
            else:
                three_month_avg = Decimal('0')
            
            # If no target exists and we have history, create one
            if name not in budget_targets and three_month_avg > 0:
                budget_targets[name] = {
                    "target": float(three_month_avg.quantize(Decimal('0.01')))
                }
                targets_updated = True
            
            # Get target and calculate percentage
            target = Decimal(str(budget_targets.get(name, {}).get('target', '0')))
            current_month_spend = monthly_sums.get(current_month_key, Decimal('0'))
            percentage = (current_month_spend / target * 100) if target else 0
            
            budget_data.append({
                'name': name,
                'previous_months': previous_amounts,
                'three_month_avg': three_month_avg,
                'current_month': current_month_spend,
                'target': target,
                'percentage': percentage
            })
        
        # Save updated targets if new ones were added
        if targets_updated:
            budget_file.parent.mkdir(parents=True, exist_ok=True)
            with open(budget_file, 'w') as f:
                json.dump(budget_targets, f, indent=4)
        
        # Sort by percentage descending
        budget_data.sort(key=lambda x: x['percentage'], reverse=True)
        
        # Write report
        with open(output_file, 'w') as f:
            f.write("Budget Report\n")
            f.write("=" * 100 + "\n\n")
            
            # Create headers
            headers = ['Charge']
            headers.extend([m.strftime('%b %Y') for m in recent_months[0:3]])
            headers.extend(['3 month avg', 'Current', 'Target', 'Progress'])
            
            # Create table data
            table_data = []
            total_previous_months = [Decimal('0')] * 3
            total_three_month_avg = Decimal('0')
            total_current = Decimal('0')
            total_target = Decimal('0')
            
            for item in budget_data:
                if item['target'] > 0:  # Only show items with targets
                    row = [item['name']]
                    row.extend([f"£{float(amt):.2f}" for amt in item['previous_months']])
                    row.append(f"£{float(item['three_month_avg']):.2f}")
                    row.append(f"£{float(item['current_month']):.2f}")
                    row.append(f"£{float(item['target']):.2f}")
                    row.append(f"{float(item['percentage']):.1f}%")
                    table_data.append(row)
                    
                    # Add to totals
                    for i, amt in enumerate(item['previous_months']):
                        total_previous_months[i] += amt
                    total_three_month_avg += item['three_month_avg']
                    total_current += item['current_month']
                    total_target += item['target']
            
            # Add totals row
            total_row = ['TOTAL']
            total_row.extend([f"£{float(amt):.2f}" for amt in total_previous_months])
            total_row.append(f"£{float(total_three_month_avg):.2f}")
            total_row.append(f"£{float(total_current):.2f}")
            total_row.append(f"£{float(total_target):.2f}")
            total_percentage = (total_current / total_target * 100) if total_target else 0
            total_row.append(f"{float(total_percentage):.1f}%")
            
            # Add a separator before totals
            table_data.append(['-' * 15] * len(headers))
            table_data.append(total_row)
            
            f.write(tabulate(
                table_data,
                headers=headers,
                tablefmt='grid',
                stralign='right'
            ))

    def sanitise(self, transactions: List[Any]) -> List[Any]:
        """
        Remove pairs of transactions that cancel each other out
        
        Args:
            transactions: List of transactions to sanitise
            
        Returns:
            List of transactions with cancelling pairs removed
        """
        # Sort transactions by date
        sorted_trans = sorted(transactions, key=lambda x: x.date)
        
        # Track which transactions to remove
        to_remove = set()
        
        # Look for cancelling pairs
        for i in range(len(sorted_trans)-1):
            if i in to_remove:
                continue
            
            current = sorted_trans[i]
            
            # Look ahead for cancelling transaction within 7 days
            for j in range(i+1, len(sorted_trans)):
                if j in to_remove:
                    continue
                
                next_trans = sorted_trans[j]
                days_between = (next_trans.date - current.date).days
                
                # Stop looking if more than 7 days ahead
                if days_between > 7:
                    break
                
                # Check if transactions cancel each other out
                if abs(current.amount + next_trans.amount) < Decimal('0.01'):      
                    to_remove.add(i)
                    to_remove.add(j)
                    break
        
        # Return transactions that weren't removed
        return [t for i, t in enumerate(sorted_trans) if i not in to_remove]

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
    tracker.generate_budget_report(recurring_charges)

if __name__ == "__main__":
    main() 