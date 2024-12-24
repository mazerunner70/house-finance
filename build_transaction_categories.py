from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Set, Tuple, Optional
from decimal import Decimal
import re
import csv
from parse_all_transactions import parse_all_account_folders
from Levenshtein import distance

def clean_description(desc: str) -> str:
    """Further clean description to group similar transactions"""
    # Convert to uppercase for comparison
    desc = desc.upper()
    
    # Special handling for credit card payments
    if any(card in desc for card in [
        'MBNA PLATINUM',
        'BARCLAYCARD VISA',
        'HALIFAX DDR',
        'JOHN LEWIS',
        'VIRGIN MONEY',
        'MBNA CREDIT CARD',
        'BARCLAYCARD',
        'HALIFAX CREDIT',
        '4929153195605'
    ]):
        return 'CREDIT CARD PAYMENT'
    
    # Special handling for Aldi variations
    if 'ALDI' in desc:
        return 'ALDI STORE'
    
    # Special handling for Sainsbury's variations
    if any(s in desc for s in ['SAINSBURY', 'SAINSBURYS', "SAINSBURY'S"]):
        return 'SAINSBURYS STORE'
    
    # Special handling for Apsley Station
    if 'APSLEY STN' in desc:
        return 'APSLEY STATION'
    
    if  'SUPERCUTS' in desc:
        return 'SUPERCUTS'
    
    if 'MORTGAGE' in desc:
        return 'MORTGAGE'
    
    if 'ANIMAL HEALTHCARE' in desc:
        return 'ANIMAL HEALTHCARE'
    
    if desc.startswith('PRIME VIDEO'):
        return 'PRIME VIDEO'
    # Special handling for payment variations
    if any(word in desc for word in ['- THAN', 'THANK YOU']):
        # Extract the first part before PAYMENT/THANKYOU
        parts = re.split(r'\b(PAYMENT|THANKYOU|THANK YOU)\b', desc)
        if len(parts) > 1:
            return f"CREDIT CARD PAYMENT"

    
    # Remove dates, times, and reference numbers
    desc = re.sub(r'\d{2}(?::\d{2})?(?::\d{2})?', '', desc)
    desc = re.sub(r'\b\d{1,4}[-/.]\d{1,2}[-/.]\d{2,4}\b', '', desc)
    
    # Remove common variable parts
    desc = re.sub(r'\b\d+\b', '', desc)  # Remove standalone numbers
    desc = re.sub(r'[^\w\s]', '', desc)  # Remove punctuation
    desc = re.sub(r'\b(LTD|LIMITED|UK|GB|INT|INTL|INTERNATIONAL)\b', '', desc)  # Remove common company suffixes
    desc = re.sub(r'\b(THE|AND|OF|IN|AT|TO|FROM)\b', '', desc)  # Remove common words
    desc = re.sub(r'(LONDON|MANCHESTER|BIRMINGHAM|LEEDS|BRISTOL)', '', desc)  # Remove city names
    
    # Remove extra spaces and trim
    desc = ' '.join(desc.split())
    return desc.strip()

def find_similar_group(clean_desc: str, existing_groups: Dict[str, Tuple[List[str], Decimal]], threshold: int = 5) -> Optional[str]:
    """
    Find an existing group that's similar to the given description
    
    Args:
        clean_desc: Cleaned description to match
        existing_groups: Existing transaction groups
        threshold: Maximum Levenshtein distance to consider similar
        
    Returns:
        Key of matching group or None if no match found
    """
    for group_key in existing_groups.keys():
        if distance(clean_desc, group_key) <= threshold:
            return group_key
    return None

def group_transactions(statements_by_folder: Dict[str, List]) -> Dict[str, Tuple[List[str], Decimal]]:
    """
    Process all statements and group similar transactions using Levenshtein distance
    
    Returns:
        Dict mapping cleaned descriptions to tuple of (raw descriptions, total amount)
    """
    transaction_groups = defaultdict(lambda: ([], Decimal('0')))
    
    # Process all folders
    for statements in statements_by_folder.values():
        # Process all transactions
        for statement in statements:
            for trans in statement.transactions:
                clean_desc = clean_description(trans.description)
                if not clean_desc:
                    continue
                    
                # Find similar existing group or use current description
                group_key = find_similar_group(clean_desc, transaction_groups) or clean_desc
                
                # Get existing variations and total
                variations, total = transaction_groups[group_key]
                # Add new variation and update total
                variations.append(trans.description)
                amount = trans.amount
                transaction_groups[group_key] = (variations, total + amount)
    
    return transaction_groups

def write_categories_to_csv(groups: Dict[str, Tuple[List[str], Decimal]], total_spending: Decimal, total_income: Decimal, output_path: Path) -> None:
    """
    Write transaction categories to CSV file
    
    Args:
        groups: Dict of transaction groups
        total_spending: Total spending amount
        total_income: Total income amount
        output_path: Path to write CSV file
    """
    # Sort groups by absolute amount
    sorted_groups = sorted(
        groups.items(),
        key=lambda x: (abs(x[1][1]), len(x[1][0])),
        reverse=True
    )
    
    with open(output_path, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        # Write header
        writer.writerow([
            'Category',
            'Total Amount',
            'Percentage',
            'Type',
            'Occurrences',
            'Variations'
        ])
        
        # Write summary row
        writer.writerow([
            'TOTAL',
            f'£{abs(total_spending):.2f}',
            '100.0',
            'Spending',
            '',
            ''
        ])
        writer.writerow([
            'TOTAL',
            f'+£{total_income:.2f}',
            '100.0',
            'Income',
            '',
            ''
        ])
        writer.writerow([
            'NET',
            f'{"" if (total_income + total_spending) < 0 else "+"}£{abs(total_income + total_spending):.2f}',
            '',
            'Net',
            '',
            ''
        ])
        
        # Write category rows
        for clean_desc, (variations, total) in sorted_groups:
            percentage = (abs(total) / abs(total_spending if total < 0 else total_income)) * 100
            writer.writerow([
                clean_desc,
                f'{"" if total < 0 else "+"}£{abs(total):.2f}',
                f'{percentage:.1f}',
                'Spending' if total < 0 else 'Income',
                len(variations),
                ', '.join(sorted(set(variations)))
            ])

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
        
    # Group transactions
    groups = group_transactions(statements_by_folder)
    
    # Calculate totals
    total_spending = sum(total for _, (_, total) in groups.items() if total < 0)
    total_income = sum(total for _, (_, total) in groups.items() if total > 0)
    
    # Write to CSV
    output_path = base_path / 'transaction_categories.csv'
    write_categories_to_csv(groups, total_spending, total_income, output_path)
    print(f"\nCategories written to {output_path}")
    
    # Print console output
    print(f"\nTransaction Categories: {len(groups)}")
    print("=" * 50)
    
    print(f"Total spending: £{abs(total_spending):.2f}")
    print(f"Total income: +£{total_income:.2f}")
    print(f"Net: {'£' if (total_income + total_spending) < 0 else '+£'}{abs(total_income + total_spending):.2f}")
    print("=" * 50)
    
    # Sort and print categories
    sorted_groups = sorted(
        groups.items(),
        key=lambda x: (abs(x[1][1]), len(x[1][0])),
        reverse=True
    )
    
    for clean_desc, (variations, total) in sorted_groups:
        unique_variations = sorted(set(variations))
        print(f"\nCategory: {clean_desc}")
        print(f"Total amount: {'£' if total < 0 else '+£'}{abs(total):.2f}")
        percentage = (abs(total) / abs(total_spending if total < 0 else total_income)) * 100
        print(f"Percentage: {percentage:.1f}% of {'spending' if total < 0 else 'income'}")
        print("Variations:")
        for var in unique_variations:
            print(f"  - {var}")
        print(f"Total occurrences: {len(variations)}")
        print("-" * 50)

if __name__ == "__main__":
    main() 