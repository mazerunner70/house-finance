import traceback
from parsers.ofx_parser import OFXParser
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import List, Optional
import re
import hashlib
import configparser

@dataclass
class BarclaysTransaction:
    """Represents a Barclays bank transaction"""
    transaction_id: str
    date: datetime
    amount: Decimal
    description: str
    type: str
    account_name: str
    running_total: Optional[Decimal] = None

@dataclass
class BarclaysStatement:
    """Represents a Barclays bank statement"""
    account_id: str
    start_date: datetime
    end_date: datetime
    start_balance: Decimal
    end_balance: Decimal
    transactions: List[BarclaysTransaction]

class BarclaysOFXParser(OFXParser):
    """Parser for Barclays OFX files"""
    
    def __init__(self, base_path: str = "financial-data", subfolder: str = "barclays-current"):
        self.base_path = Path(base_path) / subfolder
        self.subfolder = subfolder
        self.ledger_amounts_file = Path(base_path) / 'ledger_amounts.properties'
    
    def _generate_transaction_id(self, date: datetime, amount: Decimal, description: str, trans_type: str) -> str:
        """
        Generate a unique transaction ID based on transaction details and subfolder
        
        Args:
            date: Transaction date
            amount: Transaction amount
            description: Transaction description
            trans_type: Transaction type (e.g. DEBIT, CREDIT)
        
        Returns:
            String hash uniquely identifying the transaction
        """
        # Create a string combining key transaction attributes
        id_string = (
            f"{self.subfolder}|"
            f"{date.strftime('%Y%m%d')}|"
            f"{amount:.2f}|"
            f"{description}|"
            f"{trans_type}"
        )
        
        # Generate SHA-256 hash and take first 12 characters
        return hashlib.sha256(id_string.encode()).hexdigest()[:12]
    
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

    def _clean_description(self, desc: str) -> str:
        """Clean up transaction description"""
        desc = super()._clean_description(desc)
        # Remove common Barclays prefixes
        desc = re.sub(r'^(BGC|BBP|CWP|TFR|DD|SO|DEB|CRD|)\s*', '', desc)
        return desc.strip()
    
    def _parse_transaction_block(self, trans_block: str) -> Optional[BarclaysTransaction]:
        """Parse a transaction block into a BarclaysTransaction object"""
        try:
            # Extract transaction details
            trntype = self._extract_tag_value(trans_block, 'TRNTYPE')
            date_str = self._extract_tag_value(trans_block, 'DTPOSTED')
            amount_str = self._extract_tag_value(trans_block, 'TRNAMT')
            name = self._extract_tag_value(trans_block, 'NAME')
            memo = self._extract_tag_value(trans_block, 'MEMO')
            
            if not all([trntype, date_str, amount_str]):
                return None
            
            # Parse date and amount
            date = self._parse_date(date_str)
            amount = self._parse_amount(amount_str)
            
            # Clean and combine description
            description = f"{name} {memo}".strip()
            description = self._clean_description(description)
            
            # Generate transaction ID including type
            trans_id = self._generate_transaction_id(
                date,
                amount,
                description,
                trntype
            )
            
            return BarclaysTransaction(
                transaction_id=trans_id,
                date=date,
                amount=amount,
                description=description,
                type=trntype,
                account_name=self.base_path.name
            )
            
        except Exception as e:
            print(f"Error parsing transaction block: {str(e)}")
            return None
    
    def _parse_ofx_file(self, file_path: Path) -> Optional[BarclaysStatement]:
        """Parse an OFX file and return a BarclaysStatement object"""
        try:
            with open(file_path, 'r', encoding='cp1252') as file:
                content = file.read()
                
                # Get account info
                acctid = self._extract_tag_value(content, 'ACCTID')
                if not acctid:
                    return None
                
                
                # Extract all transaction blocks
                trans_blocks = re.findall(r'<STMTTRN>(.*?)</STMTTRN>', content, re.DOTALL)
                
                # Parse transactions
                transactions = []
                for trans_block in trans_blocks:
                    transaction = self._parse_transaction_block(trans_block)
                    if transaction:
                        transactions.append(transaction)

                # reverse list so oldest first
                transactions.reverse()
                dtstart = transactions[0].date
                dtend = transactions[-1].date

                # Read ledger amount from properties file
                ledger_bal = self._read_ledger_amount(dtstart)
                if ledger_bal is None:
                    print(f"Ledger amount not found for key: {dtstart.strftime('%Y-%m-%d')} in {self.subfolder}.")
                    return None
                            # set running total to ledger balance and updates all transactions with running total
                running_total = ledger_bal
                for transaction in transactions:
                    running_total += transaction.amount
                    transaction.running_total = running_total                


                return BarclaysStatement(
                    account_id=acctid,
                    start_date=dtstart,
                    end_date=dtend,
                    start_balance=ledger_bal - sum(t.amount for t in transactions),
                    end_balance=ledger_bal,
                    transactions=sorted(transactions, key=lambda x: x.date)
                )
                
        except Exception as e:
            print(f"Error parsing file {file_path}: {str(e)}")
            print (traceback.format_exc())
            return None
    
    def parse_all_statements(self) -> List[BarclaysStatement]:
        """Parse all OFX files in the Barclays folder and remove duplicate transactions"""
        statements = []
        seen_transactions = set()  # Keep track of transaction IDs we've seen
        
        if not self.base_path.exists():
            print(f"Barclays folder not found at {self.base_path}")
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
                    # Calculate dtstart and dtend from transactions
                    statement.start_date = min(t.date for t in unique_transactions)
                    statement.end_date = max(t.date for t in unique_transactions)
                    statements.append(statement)
        
        return sorted(statements, key=lambda x: x.start_date) 