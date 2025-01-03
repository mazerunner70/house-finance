from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import List, Optional
import re
import hashlib
import configparser

@dataclass
class QIFTransaction:
    """Represents a QIF transaction"""
    transaction_id: str
    date: datetime
    amount: Decimal
    description: str
    type: str
    account_name: str
    reference: Optional[str] = None
    category: Optional[str] = None
    running_total: Optional[Decimal] = None
@dataclass
class QIFStatement:
    """Represents a QIF statement"""
    account_name: str
    transactions: List[QIFTransaction]
    start_date: datetime
    end_date: datetime

class QIFParser:
    """Parser for QIF files"""
    
    def __init__(self, base_path: str = "financial-data", subfolder: str = "mbna-credit"):
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
            return Decimal(config['LedgerAmounts'][key])
        else:
            # If the key is absent, add it as an empty property
            config['LedgerAmounts'][key] = ''
            with open(self.ledger_amounts_file, 'w') as configfile:
                config.write(configfile)
            return None  # Return None if the key was absent

    def _parse_date(self, date_str: str) -> datetime:
        """Parse QIF date format (DD/MM/YYYY)"""
        try:
            return datetime.strptime(date_str, '%d/%m/%Y')
        except ValueError:
            # Try alternate format MM/DD/YYYY
            return datetime.strptime(date_str, '%m/%d/%Y')
    
    def _parse_amount(self, amount_str: str) -> Decimal:
        """Parse amount string to Decimal"""
        # Remove currency symbols and convert to Decimal
        amount_str = re.sub(r'[£$]', '', amount_str)
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
    
    def _parse_qif_file(self, file_path: Path) -> Optional[QIFStatement]:
        """Parse a QIF file and return a QIFStatement object"""
        try:
            transactions = []
            current_trans = {}
            
            with open(file_path, 'r', encoding='utf-8') as file:
                account_name = file_path.parent.name
                
                for line in file:
                    line = line.strip()
                    if not line:
                        continue
                    
                    identifier = line[0]
                    value = line[1:].strip()
                    
                    if identifier == '^':  # End of transaction
                        if current_trans:
                            # Generate transaction ID
                            transaction_id = self._generate_transaction_id(
                                current_trans.get('date'),
                                current_trans.get('amount', Decimal('0')),
                                current_trans.get('description', '')
                            )
                            transactions.append(QIFTransaction(
                                transaction_id=transaction_id,
                                date=current_trans.get('date'),
                                amount=current_trans.get('amount', Decimal('0')),
                                description=current_trans.get('description', ''),
                                type=current_trans.get('type', 'OTHER'),
                                account_name=self.base_path.name,
                                reference=current_trans.get('reference'),
                                category=current_trans.get('category')
                            ))
                            current_trans = {}
                    elif identifier == 'D':  # Date
                        current_trans['date'] = self._parse_date(value)
                    elif identifier == 'T':  # Amount
                        amt = -self._parse_amount(value)
                        current_trans['amount'] = amt
                        current_trans['type'] = 'CREDIT' if amt >= 0 else 'DEBIT'
                    elif identifier == 'P':  # Payee/Description
                        current_trans['description'] = value
                    elif identifier == 'N':  # Reference number
                        current_trans['reference'] = value
                    elif identifier == 'L':  # Category
                        current_trans['category'] = value
                
                # Handle last transaction if exists
                if current_trans:
                    transaction_id = self._generate_transaction_id(
                        current_trans.get('date'),
                        current_trans.get('amount', Decimal('0')),
                        current_trans.get('description', '')
                    )
                    transactions.append(QIFTransaction(
                        transaction_id=transaction_id,
                        date=current_trans.get('date'),
                        amount=current_trans.get('amount', Decimal('0')),
                        description=current_trans.get('description', ''),
                        type=current_trans.get('type', 'OTHER'),
                        account_name=self.base_path.name,
                        reference=current_trans.get('reference'),
                        category=current_trans.get('category')
                    ))
            
            if not transactions:
                return None
            

                
            # Sort transactions by date
            transactions.reverse()

            ledger_bal = self._read_ledger_amount(transactions[0].date)
            if ledger_bal is None:
                    print(f"Ledger amount not found for key: {current_trans['date'].strftime('%Y-%m-%d')} in {self.subfolder}.")
                    return None
            
            running_total = ledger_bal
            for t in transactions:
                running_total += t.amount
                t.running_total = running_total
            
            return QIFStatement(
                account_name=account_name,
                transactions=transactions,
                start_date=transactions[0].date,
                end_date=transactions[-1].date
            )
            
        except Exception as e:
            print(f"Error parsing file {file_path}: {str(e)}")
            return None
    
    def parse_all_statements(self) -> List[QIFStatement]:
        """Parse all QIF files in the folder and remove duplicate transactions"""
        statements = []
        seen_transactions = set()  # Keep track of transaction IDs we've seen
        
        if not self.base_path.exists():
            print(f"Folder not found at {self.base_path}")
            return statements
        
        # First collect all files and sort by name to ensure consistent processing order
        qif_files = sorted(self.base_path.glob("*.qif"))
      
        # Process each file
        for file_path in qif_files:
            statement = self._parse_qif_file(file_path)
            if statement and statement.transactions:
                # Filter out duplicates while preserving order
                unique_transactions = []  
                for trans in statement.transactions:
                    if trans.transaction_id not in seen_transactions:
                        seen_transactions.add(trans.transaction_id)
                        unique_transactions.append(trans)
                
                # Only create statement if we have unique transactions
                if unique_transactions:
                    # Sort transactions by date
                    unique_transactions.sort(key=lambda x: x.date)
                    
                    # Calculate running totals
                    ledger_bal = self._read_ledger_amount(unique_transactions[0].date)
                    if ledger_bal is not None:
                        running_total = ledger_bal
                        for t in unique_transactions:
                            running_total += t.amount
                            t.running_total = running_total
                        
                        statements.append(QIFStatement(
                            account_name=self.base_path.name,
                            transactions=unique_transactions,
                            start_date=unique_transactions[0].date,
                            end_date=unique_transactions[-1].date
                        ))
        
        return sorted(statements, key=lambda x: x.start_date) 