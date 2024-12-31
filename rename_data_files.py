from pathlib import Path
from datetime import datetime
import re

def rename_data_files(base_path: Path) -> None:
    """
    Recursively search through folders and rename data files
    
    Args:
        base_path: Base directory to start search from
    """
    # Walk through all subfolders
    for folder_path in base_path.rglob('*'):
        if not folder_path.is_dir():
            continue
            
        # Get folder name for prefix
        folder_name = folder_path.name.lower()
        
        # Look for data files in this folder
        for file_path in folder_path.glob('data*'):
            try:
                if file_path.suffix.lower() in ['.qif', '.pdf', '.csv']:
                    # For QIF files, use current date/time
                    date_formatted = datetime.now().strftime('%Y-%m-%d-%H-%M-%S-%f')
                else:
                    # For OFX files, extract date from content
                    with open(file_path, 'r', encoding='iso-8859-1') as file:
                        content = file.read()
                        
                    # Look for DTSERVER tag with date
                    match = re.search(r'<DTSERVER>(\d{14})', content)
                    if not match:
                        continue
                        
                    date_str = match.group(1)
                    date_obj = datetime.strptime(date_str, '%Y%m%d%H%M%S')
                    date_formatted = date_obj.strftime('%Y-%m-%d-%H-%M-%S')
                
                # Create new filename
                new_name = f"{folder_name}-{date_formatted}{file_path.suffix}"
                new_path = file_path.parent / new_name
                
                # Rename file
                file_path.rename(new_path)
                print(f"Renamed {file_path.name} to {new_name}")
                
            except Exception as e:
                print(f"Error processing {file_path}: {str(e)}")

def main():
    base_path = Path("financial-data")
    if not base_path.exists():
        print(f"Base folder {base_path} not found")
        return
    
    print("=== Renaming data files ===")
    rename_data_files(base_path)

if __name__ == "__main__":
    main()