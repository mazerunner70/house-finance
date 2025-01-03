from parsers.ofx_parser import OFXParser
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import List, Optional
import xml.etree.ElementTree as ET
import configparser
import hashlib

@dataclass
class NationwideTransaction:
    """Represents a Nationwide bank transaction"""
    transaction_id: str
    date: datetime
    amount: Decimal
    description: str
    type: str
    account_name: str
    balance_after: Optional[Decimal] = None
    reference: Optional[str] = None
    running_total: Optional[Decimal] = None
@dataclass
class NationwideStatement:
    """Represents a Nationwide bank statement"""
    account_id: str
    start_date: datetime
    end_date: datetime
    start_balance: Decimal
    end_balance: Decimal
    transactions: List[NationwideTransaction]

class NationwideXMLParser(OFXParser):
    """Parser for Nationwide XML-format OFX files"""
    
    def __init__(self, base_path: str = "financial-data", subfolder: str = "nationwide-current"):
        super().__init__(base_path, subfolder)
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

    def _parse_transaction_element(self, trans_elem: ET.Element) -> Optional[NationwideTransaction]:
        """Parse a transaction XML element"""
        try:
            trntype = trans_elem.find('.//TRNTYPE').text.strip()
            date_str = trans_elem.find('.//DTPOSTED').text.strip()
            amount_str = trans_elem.find('.//TRNAMT').text.strip()
            fitid = trans_elem.find('.//FITID').text.strip()
            
            # Get description from NAME and MEMO
            name = trans_elem.find('.//NAME')
            memo = trans_elem.find('.//MEMO')
            description = ' '.join(filter(None, [
                name.text.strip() if name is not None else None,
                memo.text.strip() if memo is not None else None
            ]))
            
            # Generate transaction ID
            trans_id = self._generate_transaction_id(
                self._parse_date(date_str),
                self._parse_amount(amount_str),
                self._clean_description(description)
            )
            
            return NationwideTransaction(
                transaction_id=trans_id,
                date=self._parse_date(date_str),
                amount=self._parse_amount(amount_str),
                description=self._clean_description(description),
                type=trntype,
                account_name=self.base_path.name
            )
        except Exception as e:
            print(f"Error parsing transaction element: {str(e)}")
            return None
    
    def _parse_ofx_file(self, file_path: Path) -> Optional[NationwideStatement]:
        """Parse an XML-format OFX file"""
        try:
            tree = ET.parse(file_path)
            root = tree.getroot()
            
            # Get statement transaction section
            stmtrs = root.find('.//STMTRS')
            if stmtrs is None:
                return None
            
            # Get account info
            acctid = stmtrs.find('.//ACCTID').text.strip()
            
                        
            # Parse transactions
            transactions = []
            for trans_elem in stmtrs.findall('.//STMTTRN'):
                transaction = self._parse_transaction_element(trans_elem)
                if transaction:
                    transactions.append(transaction)

            # Get statement period
            dtstart = transactions[0].date
            dtend = transactions[-1].date

            ledger_bal = self._read_ledger_amount(dtstart)
            if ledger_bal is None:
                print(f"Ledger amount not found for key: {dtstart.strftime('%Y-%m-%d')} in {self.subfolder}.")
                return None
            
            running_total = ledger_bal
            for t in transactions:
                running_total += t.amount
                t.running_total = running_total
            
            return NationwideStatement(
                account_id=acctid,
                start_date=dtstart,
                end_date=dtend,
                start_balance=ledger_bal - sum(t.amount for t in transactions),
                end_balance=ledger_bal,
                transactions=sorted(transactions, key=lambda x: x.date)
            )
            
        except Exception as e:
            print(f"Error parsing file {file_path}: {str(e)}")
            return None
    
    def parse_all_statements(self) -> List[NationwideStatement]:
        """Parse all OFX files and remove duplicates"""
        statements = []
        seen_transactions = set()
        
        if not self.base_path.exists():
            print(f"Nationwide folder not found at {self.base_path}")
            return statements
        
        for file_path in self.base_path.glob("*.ofx"):
            statement = self._parse_ofx_file(file_path)
            if statement:
                unique_transactions = []
                for trans in statement.transactions:
                    if trans.transaction_id not in seen_transactions:
                        seen_transactions.add(trans.transaction_id)
                        unique_transactions.append(trans)
                
                statement.transactions = unique_transactions
                if unique_transactions:
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