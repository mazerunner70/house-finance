from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import List, Optional
import pdfplumber
import re
import hashlib
import configparser

@dataclass
class PDFTransaction:
    """Represents a transaction from a PDF statement"""
    transaction_id: str
    date: datetime
    amount: Decimal
    description: str
    type: str
    reference: Optional[str] = None
    running_total: Optional[Decimal] = None
@dataclass
class PDFStatement:
    """Represents a PDF statement"""
    account_name: str
    start_balance: Decimal
    end_balance: Decimal
    start_date: datetime
    end_date: datetime
    transactions: List[PDFTransaction]
    ledger_balance: Optional[Decimal] = None

class JohnLewisPDFParser:
    """Parser for John Lewis PDF statements"""
    
    def __init__(self, base_path: str = "financial-data", subfolder: str = "johnlewis"):
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
    
    def _parse_amount(self, amount_str: str) -> Decimal:
        """Parse amount string to Decimal"""
        # Remove currency symbols and convert to Decimal
        amount_str = re.sub(r'[£$,]', '', amount_str)
        return Decimal(amount_str.strip())
    
    def _parse_date(self, date_str: str) -> datetime:
        """Parse date string (DD MMM YYYY)"""
        return datetime.strptime(date_str.strip(), '%d %b %Y')
    
    def _extract_balances(self, page) -> tuple[Decimal, Decimal]:
        """Extract previous and new balance from first page"""
        text = page.extract_text()
        
        # Look for balance lines
        prev_match = re.search(r'Balance last month[:\s]+£([\d,.]+)', text)
        new_match = re.search(r'Your new balance[:\s]+£([\d,.]+)', text)
        
        if not prev_match or not new_match:
            raise ValueError("Could not find balance information")
            
        prev_balance = self._parse_amount(prev_match.group(1)) * -1
        new_balance = self._parse_amount(new_match.group(1)) * -1
        
        return prev_balance, new_balance
    
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
    
    def _parse_transactions(self, pdf) -> List[PDFTransaction]:
        """Extract transactions from pages starting from page 2 until a page has no transactions"""
        transactions = []
        capturepattern = r'(\d{2} \w{3} \d{4}) (.*) ([+-]) £(\d+\.\d+)'
        
        for page in pdf.pages[1:]:  # Start from page 2 (index 1)
            textlines = page.extract_text_lines()
            page_transactions = []
            
            for line in textlines:
                try:
                    match = re.match(capturepattern, line['text'])
                    if match:
                        date_str, desc, amount_sign, amount_str = match.groups()
                        amount = Decimal(amount_str) if amount_sign == '-' else -Decimal(amount_str)
                        trans_type = 'DEBIT' if amount < 0 else 'CREDIT'
                        
                        # Generate transaction ID
                        transaction_id = self._generate_transaction_id(
                            self._parse_date(date_str),
                            amount,
                            desc.strip()
                        )
                        
                        page_transactions.append(PDFTransaction(
                            transaction_id=transaction_id,
                            date=self._parse_date(date_str),
                            amount=amount,  
                            description=desc.strip(),
                            type=trans_type
                        ))

                except (ValueError, IndexError) as e:
                    print(f"Error parsing row {line['text']}: {str(e)}")
                    continue
            
            if not page_transactions:  # Stop if no transactions found on the page
                break
            
            transactions.extend(page_transactions)  # Add found transactions to the list
        
        return transactions
    
    def _parse_pdf_file(self, file_path: Path) -> Optional[PDFStatement]:
        """Parse a PDF file and return a PDFStatement object"""
        try:
            with pdfplumber.open(file_path) as pdf:

                transactions = self._parse_transactions(pdf)
                
                if not transactions:
                    return None
                
                # Get the start date from the first transaction
                start_date = transactions[0].date
                
                # Read ledger amount from properties file
                ledger_bal = self._read_ledger_amount(start_date)
                if ledger_bal is None:
                    print(f"Ledger amount not found for key: {start_date.strftime('%Y-%m-%d')} in {self.subfolder}.")
                    return None
                
                running_total = ledger_bal
                for t in transactions:
                    running_total += t.amount
                    t.running_total = running_total
                
                return PDFStatement(
                    account_name=file_path.parent.name,
                    start_balance=ledger_bal,
                    end_balance=running_total,
                    start_date=start_date,
                    end_date=transactions[-1].date,
                    transactions=transactions,
                    ledger_balance=ledger_bal
                )
                
        except Exception as e:
            print(f"Error parsing file {file_path}: {str(e)}")
            return None
    
    def parse_all_statements(self) -> List[PDFStatement]:
        """Parse all PDF files in the folder"""
        statements = []
        
        if not self.base_path.exists():
            print(f"Folder not found at {self.base_path}")
            return statements
        
        for file_path in self.base_path.glob("*.pdf"):
            statement = self._parse_pdf_file(file_path)
            if statement:
                statements.append(statement)
        
        return sorted(statements, key=lambda x: x.start_date) 