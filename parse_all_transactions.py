from pathlib import Path
from parsers.barclays_parser import BarclaysOFXParser, BarclaysStatement
from parsers.barclaycard_parser import BarclaycardOFXParser, CreditCardStatement
from rename_data_files import rename_data_files
from parsers.qif_parser import QIFParser, QIFStatement
from parsers.pdf_parser import JohnLewisPDFParser, PDFStatement
from parsers.nationwide_parser import NationwideXMLParser, NationwideStatement
from typing import Dict, List, Union, Any
from parsers.virgin_parser import VirginCSVParser, VirginStatement


def parse_all_account_folders(base_path: Path) -> Dict[str, List[Union[BarclaysStatement, CreditCardStatement, QIFStatement, PDFStatement, NationwideStatement, VirginStatement]]]:
    """
    Parse all account folders and return their statements
    
    Args:
        base_path: Base directory containing account folders
        
    Returns:
        Dict mapping folder names to lists of statements
    """
    if not base_path.exists():
        print(f"Base folder {base_path} not found")
        return {}
    
    rename_data_files(base_path)
    
    # Process all subfolders
    statements_by_folder = {}
    subfolders = [f.name for f in base_path.iterdir() if f.is_dir()]
    
    for subfolder in subfolders:
        # Choose appropriate parser based on folder name
        if 'virgin' in subfolder.lower():
            parser = VirginCSVParser(base_path=str(base_path), subfolder=subfolder)
        elif 'barclaycard' in subfolder.lower():
            parser = BarclaycardOFXParser(base_path=str(base_path), subfolder=subfolder)
        elif 'barclays' in subfolder.lower():
            parser = BarclaysOFXParser(base_path=str(base_path), subfolder=subfolder)
        elif 'nationwide' in subfolder.lower():
            parser = NationwideXMLParser(base_path=str(base_path), subfolder=subfolder)
        elif any(name in subfolder.lower() for name in ['mbna', 'halifax']):
            parser = QIFParser(base_path=str(base_path), subfolder=subfolder)
        elif 'johnlewis' in subfolder.lower():
            parser = JohnLewisPDFParser(base_path=str(base_path), subfolder=subfolder)
        else:
            print(f"Skipping unknown folder: {subfolder}")
            continue
        
        statements = parser.parse_all_statements()
        if statements:
            statements_by_folder[subfolder] = statements
    
    return statements_by_folder

def main():
    base_path = Path("financial-data")
    statements_by_folder = parse_all_account_folders(base_path)
    
    # Print detailed statements if needed
    for subfolder, statements in statements_by_folder.items():
        process_folder_statements(statements, subfolder)

def process_folder_statements(statements: List[Any], subfolder: str) -> None:
    """Print statements for a folder"""
    print(f"\n=== Processing {subfolder} ===")
    
    if not statements:
        print(f"No statements found in {subfolder}")
        return
    
    for statement in statements:
        print(f"\nStatement for account {statement.account_id if hasattr(statement, 'account_id') else statement.account_name}")
        print(f"Statement end date: {statement.end_date}")
        print(f"Statement start date: {statement.start_date}")
        
        # Handle different statement types
        if hasattr(statement, 'credit_limit'):
            # Credit card statement
            if statement.credit_limit:
                print(f"Credit limit: £{statement.credit_limit:.2f}")
            print(f"Current balance: £{statement.current_balance:.2f}")
            if statement.available_credit:
                print(f"Available credit: £{statement.available_credit:.2f}")
        elif hasattr(statement, 'start_balance'):
            # Bank account statement
            print(f"Opening balance: £{statement.start_balance:.2f}")
            print(f"Closing balance: £{statement.end_balance:.2f}")
        
        print("\nTransactions:")
        for trans in statement.transactions:
            # Format transaction details
            if hasattr(trans, 'post_date') and trans.post_date != trans.date:
                post_date = f"(posted {trans.post_date.date()})"
            else:
                post_date = ""
                
            if hasattr(trans, 'merchant_category') and trans.merchant_category:
                category = f"[{trans.merchant_category}]"
            elif hasattr(trans, 'category') and trans.category:
                category = f"[{trans.category}]"
            else:
                category = ""
                
            print(f"\n{trans.date.date()} {post_date} | {trans.type:<6} | £{trans.amount:>10.2f} | {trans.description} {category}")

if __name__ == "__main__":
    main()
