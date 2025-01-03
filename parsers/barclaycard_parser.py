from parsers.ofx_parser import OFXParser
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import List, Optional
import re
import configparser
import hashlib

@dataclass
class CreditCardTransaction:
    """Represents a credit card transaction"""
    transaction_id: str
    date: datetime
    post_date: Optional[datetime]  # Date transaction was posted
    amount: Decimal
    description: str
    type: str
    account_name: str  # Add account_name field
    reference: Optional[str] = None
    merchant_category: Optional[str] = None
    running_total: Optional[Decimal] = None

@dataclass
class CreditCardStatement:
    """Represents a credit card statement"""
    account_id: str
    start_date: datetime
    end_date: datetime
    credit_limit: Optional[Decimal]
    current_balance: Decimal
    available_credit: Optional[Decimal]
    transactions: List[CreditCardTransaction]

class BarclaycardOFXParser(OFXParser):
    """Parser for Barclaycard OFX files"""
    
    def __init__(self, base_path: str = "financial-data", subfolder: str = "barclaycard-current"):
        super().__init__(base_path, subfolder)
        self.ledger_amounts_file = Path(base_path) / 'ledger_amounts.properties'
        self.subfolder = subfolder
    
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
    
    def _clean_description(self, desc: str) -> str:
        """Clean up transaction description"""
        desc = super()._clean_description(desc)
        # Remove common Barclaycard prefixes
        desc = re.sub(r'^(PAYMENT|PURCHASE|CASH|CREDIT|)\s*', '', desc)
        return desc.strip()
    
    def _parse_date(self, date_str: str) -> datetime:
        """Parse OFX date format (YYYYMMDDHHMMSS) to datetime"""
        return datetime.strptime(date_str[:8], '%Y%m%d')
    
    def _parse_amount(self, amount_str: str) -> Decimal:
        """Parse amount string to Decimal"""
        return Decimal(amount_str.strip())
    
    def _extract_tag_value(self, content: str, tag: str) -> Optional[str]:
        """Extract value between OFX tags"""
        pattern = f"<{tag}>([^<]+)"
        match = re.search(pattern, content)
        return match.group(1) if match else None
    
    def _parse_transaction_block(self, trans_block: str) -> Optional[CreditCardTransaction]:
        """Parse a transaction block into a CreditCardTransaction object"""
        try:
            # Extract and clean all fields
            trntype = (self._extract_tag_value(trans_block, 'TRNTYPE') or '').strip()
            date_str = (self._extract_tag_value(trans_block, 'DTPOSTED') or '').strip()
            trans_date_str = (self._extract_tag_value(trans_block, 'DTUSER') or '').strip()
            amount_str = (self._extract_tag_value(trans_block, 'TRNAMT') or '').strip()
            fitid = (self._extract_tag_value(trans_block, 'FITID') or '').strip()
            name = (self._extract_tag_value(trans_block, 'NAME') or '').strip()
            memo = (self._extract_tag_value(trans_block, 'MEMO') or '').strip()
            ref = (self._extract_tag_value(trans_block, 'REFNUM') or '').strip()
            category = (self._extract_tag_value(trans_block, 'SIC') or '').strip()
            
            if not all([trntype, date_str, amount_str, fitid]):
                return None
                
            # Combine and clean description
            description = f"{name} {memo}".strip()
            description = self._clean_description(description)
            
            # Generate transaction ID
            trans_id = self._generate_transaction_id(
                self._parse_date(trans_date_str if trans_date_str else date_str),
                self._parse_amount(amount_str),
                f"{name} {memo}".strip()
            )
            
            return CreditCardTransaction(
                transaction_id=trans_id,
                date=self._parse_date(trans_date_str if trans_date_str else date_str),
                post_date=self._parse_date(date_str),
                amount=self._parse_amount(amount_str),
                description=description,
                type=trntype,
                account_name=self.base_path.name,  # Add account name from folder name
                reference=ref if ref else None,
                merchant_category=category if category else None
            )
        except Exception as e:
            print(f"Error parsing transaction block: {str(e)}")
            return None
    
    def _parse_ofx_file(self, file_path: Path) -> Optional[CreditCardStatement]:
        """Parse an OFX file and return a CreditCardStatement object"""
        try:
            with open(file_path, 'r', encoding='iso-8859-1') as file:
                content = file.read()
                
            # Get account info
            acctid = self._extract_tag_value(content, 'ACCTID')
            if not acctid:
                return None
            
            # Get balance
            ledger_bal = self._parse_amount(self._extract_tag_value(content, 'BALAMT'))
            
            # Extract all transaction blocks
            trans_blocks = re.findall(r'<STMTTRN>(.*?)</STMTTRN>', content, re.DOTALL)
            
            # Parse transactions
            transactions = []
            for trans_block in trans_blocks:
                transaction = self._parse_transaction_block(trans_block)
                if transaction:
                    transactions.append(transaction)

            # sort transations by increasing date
            transactions.sort(key=lambda x: x.date)

            dtstart = transactions[0].date
            dtend = transactions[-1].date

            ledger_bal = self._read_ledger_amount(dtstart)
            if ledger_bal is None:
                print(f"Ledger amount not found for key: {dtstart.strftime('%Y-%m-%d')} in {self.subfolder}.")
                return None

            # set running total to ledger balance and updates all transactions with running total
            running_total = ledger_bal
            for transaction in transactions:
                running_total += transaction.amount
                transaction.running_total = running_total

            
            return CreditCardStatement(
                account_id=acctid,
                start_date=dtstart,
                end_date=dtend,
                credit_limit=self._parse_amount(self._extract_tag_value(content, 'CREDITLIMIT')) if self._extract_tag_value(content, 'CREDITLIMIT') else None,
                current_balance=ledger_bal,
                available_credit=self._parse_amount(self._extract_tag_value(content, 'AVAILBAL')) if self._extract_tag_value(content, 'AVAILBAL') else None,
                transactions=sorted(transactions, key=lambda x: x.date)
            )
            
        except Exception as e:
            print(f"Error parsing file {file_path}: {str(e)}")
            return None
    
    def parse_all_statements(self) -> List[CreditCardStatement]:
        """Parse all OFX files in the Barclaycard folder and remove duplicate transactions"""
        statements = []
        seen_transactions = set()  # Keep track of transaction IDs we've seen
        
        if not self.base_path.exists():
            print(f"Barclaycard folder not found at {self.base_path}")
            return statements
        
        # First collect all statements
        for file_path in self.base_path.glob("*.ofx"):
            statement = self._parse_ofx_file(file_path)
            if statement:
                # Filter out transactions we've already seen
                unique_transactions = []
                for trans in statement.transactions:
                    if trans.transaction_id not in seen_transactions:
                        seen_transactions.add(trans.transaction_id)
                        unique_transactions.append(trans)
                
                # Update statement with unique transactions only
                statement.transactions = unique_transactions
                if unique_transactions:  # Only add statement if it has unique transactions
                    statements.append(statement)
        
        return sorted(statements, key=lambda x: x.start_date)
    
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

def main():
    base_path = Path("financial-data")
    if not base_path.exists():
        print(f"Base folder {base_path} not found")
        return
        
    # Process Barclaycard folders
    parser = BarclaycardOFXParser()
    statements = parser.parse_all_statements()
    
    if not statements:
        print("No statements found")
        return
        
    for statement in statements:
        print(f"\nStatement for account {statement.account_id}")
        print(f"Period: {statement.start_date.date()} to {statement.end_date.date()}")
        if statement.credit_limit:
            print(f"Credit limit: £{statement.credit_limit:.2f}")
        print(f"Current balance: £{statement.current_balance:.2f}")
        if statement.available_credit:
            print(f"Available credit: £{statement.available_credit:.2f}")
        print("\nTransactions:")
        
        for trans in statement.transactions:
            post_date = f"(posted {trans.post_date.date()})" if trans.post_date != trans.date else ""
            category = f"[{trans.merchant_category}]" if trans.merchant_category else ""
            print(f"\n{trans.date.date()} {post_date} | {trans.type:<6} | £{trans.amount:>10.2f} | {trans.description} {category}")

if __name__ == "__main__":
    main() 