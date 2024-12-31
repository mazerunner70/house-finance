from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation as DecimalInvalidOperation
from pathlib import Path
from typing import List, Optional, Dict
import csv
import configparser
import hashlib

@dataclass
class VirginTransaction:
    """Represents a Virgin Money credit card transaction"""
    transaction_id: str
    date: datetime
    post_date: datetime
    amount: Decimal
    description: str
    type: str
    merchant_category: Optional[str] = None
    merchant_city: Optional[str] = None
    merchant_state: Optional[str] = None
    merchant_postcode: Optional[str] = None
    currency: Optional[str] = None
    card_holder: Optional[str] = None
    card_used: Optional[str] = None
    status: Optional[str] = None
    running_total: Optional[Decimal] = None

@dataclass
class VirginStatement:
    """Represents a Virgin Money credit card statement"""
    account_name: str
    start_date: datetime
    end_date: datetime
    transactions: List[VirginTransaction]

class VirginCSVParser:
    """Parser for Virgin Money CSV files"""
    
    def __init__(self, base_path: str = "financial-data", subfolder: str = "virgin-credit"):
        self.base_path = Path(base_path) / subfolder
        self.subfolder = subfolder
        self.ledger_amounts_file = Path(base_path) / 'ledger_amounts.properties'
    
    def _read_ledger_amount(self, start_date: datetime) -> Optional[Decimal]:
        """Read the ledger amount from the properties file"""
        config = configparser.ConfigParser()
        config.read(self.ledger_amounts_file)

        # Create the key using subfolder name and statement start date
        key = f"{self.subfolder}|{start_date.strftime('%Y-%m-%d')}"
        
        if 'LedgerAmounts' not in config:
            config['LedgerAmounts'] = {}

        if key in config['LedgerAmounts']:
            v = config['LedgerAmounts'][key].strip()
            if v == '':
                return Decimal(0)
            else:
                return Decimal(v)
        else:
            # If the key is absent, add it as an empty property
            config['LedgerAmounts'][key] = ''
            with open(self.ledger_amounts_file, 'w') as configfile:
                config.write(configfile)
            return None  # Return None if the key was absent
    
    def _parse_date(self, date_str: str) -> datetime:
        """Parse date from CSV format"""
        try:
            return datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            return datetime.strptime(date_str, '%d/%m/%Y')
    
    def _parse_amount(self, amount_str: str) -> Decimal:
        """Parse amount string to Decimal"""
        # Remove currency symbols and convert to Decimal
        amount_str = amount_str.replace('£', '').replace(',', '')
        return Decimal(amount_str.strip())
    
    def _generate_transaction_id(self, date: datetime, amount: Decimal, description: str) -> str:
        """
        Generate a unique transaction ID based on transaction details and subfolder
        
        Args:
            date: Transaction date
            amount: Transaction amount
            description: Transaction description
        
        Returns:
            String hash uniquely identifying the transaction
        """
        # Create a string combining key transaction attributes
        id_string = (
            f"{self.subfolder}|"
            f"{date.strftime('%Y%m%d')}|"
            f"{abs(amount):.2f}|"
            f"{description}"
        )
        
        # Generate SHA-256 hash and take first 12 characters
        return hashlib.sha256(id_string.encode()).hexdigest()[:12]
    
    def _parse_csv_file(self, file_path: Path) -> Optional[VirginStatement]:
        """Parse a CSV file and return a VirginStatement object"""
        try:
            transactions = []
            
            with open(file_path, 'r', encoding='utf-8-sig') as csvfile:
                reader = csv.DictReader(csvfile)
                
                for row in reader:
                    if row['Debit or Credit'] not in ['DBIT', 'CRDT']:
                        row['Debit or Credit'] = row['SICMCC Code']
                    # Parse amount and determine transaction type
                    amount = self._parse_amount(row['Billing Amount'])
                    trans_type = row['Debit or Credit'].upper()
                    if trans_type == 'DBIT':
                        amount = -amount
                    
                    # Get transaction date for ledger lookup
                    trans_date = self._parse_date(row['Transaction Date'])
                    trans_date_key = trans_date.strftime('%Y%m%d')
                    
                    # Create transaction object
                    transaction = VirginTransaction(
                        transaction_id=self._generate_transaction_id(
                            trans_date,
                            amount,
                            row['Merchant'].strip()
                        ),
                        date=trans_date,
                        post_date=self._parse_date(row['Posting Date']),
                        amount=amount,
                        description=row['Merchant'].strip(),
                        type=trans_type,
                        merchant_category=row['SICMCC Code'].strip() if row['SICMCC Code'] else None,
                        merchant_city=row['Merchant City'].strip() if row['Merchant City'] else None,
                        merchant_state=row['Merchant State'].strip() if row['Merchant State'] else None,
                        merchant_postcode=row['Merchant Postcode'].strip() if row['Merchant Postcode'] else None,
                        currency=row['Transaction Currency'].strip() if row['Transaction Currency'] else None,
                        card_holder=row['Additional Card Holder'].strip() if row['Additional Card Holder'] else None,
                        card_used=row['Card Used'].strip() if row['Card Used'] else None,
                        status=row['Status'].strip() if row['Status'] else None
                    )
                    transactions.append(transaction)
            
            if not transactions:
                return None
                
            # Sort transactions by date
            transactions.sort(key=lambda x: x.date)

            ledger_bal = self._read_ledger_amount(transactions[0].date)
            if ledger_bal is None:
                    print(f"Ledger amount not found for key: {transactions[0].date.strftime('%Y-%m-%d')} in {self.subfolder}.")
                    return None
            
            running_total = ledger_bal
            for t in transactions:
                running_total += t.amount
                t.running_total = running_total
            
            # Create statement
            return VirginStatement(
                account_name=file_path.parent.name,
                start_date=transactions[0].date,
                end_date=transactions[-1].date,
                transactions=transactions
            )
            
        except Exception as e:
            print(f"Error parsing file {file_path}: {str(e)}")
            return None
    
    def parse_all_statements(self) -> List[VirginStatement]:
        """Parse all CSV files in the Virgin folder"""
        statements = []
        
        if not self.base_path.exists():
            print(f"Virgin folder not found at {self.base_path}")
            return statements
        
        # Process all CSV files
        for file_path in self.base_path.glob("*.csv"):
            statement = self._parse_csv_file(file_path)
            if statement:
                statements.append(statement)
        
        return sorted(statements, key=lambda x: x.start_date) 