from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Any
from pathlib import Path
from parse_all_transactions import parse_all_account_folders  # Import the function to parse account folders

class DailySummary:
    """Class to summarize daily maximum running totals from parsed transactions."""
    
    def __init__(self, statements_by_folder: Dict[str, List[Any]]):
        self.statements_by_folder = statements_by_folder 

    def _calculate_daily_totals(self, folder_date_totals: Dict[str, Dict[datetime, float]]) -> Dict[str, float]:
        """Calculate the maximum running total for each date across all subfolders."""
        daily_max = defaultdict(list)  # Dictionary to hold max running totals

        for folder_name, date_totals in folder_date_totals.items():
            for date, total in date_totals.items():
                daily_max[date].append(total)

        daily_sums = {date: sum(totals) for date, totals in daily_max.items()}
        return daily_sums
    
    def get_summary(self) -> Dict[str, float]:
        """Return the daily summary of maximum running totals."""
        folder_totals = self.folder_day_end_summary()
        daily_totals = self._calculate_daily_totals(folder_totals)
        return daily_totals

    def folder_day_end_summary(self) -> Dict[str, Dict[datetime, float]]:
        """Calculate the last running total for each day across all statements."""
        folder_maps = {}
        one_day = timedelta(days=1)
        for folder_name, statements in self.statements_by_folder.items():
            day_end_totals = {}  # Dictionary to hold the last running total for each day
            last_total, last_date = 0, None
            for statement in statements:
                for trans in statement.transactions:
                    if hasattr(trans, 'running_total'):
                        date_str = trans.date.strftime('%Y-%m-%d')  # Format date as string
                        # convert back to date object
                        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                        if last_date:
                            while last_date < date_obj:
                                day_end_totals[last_date] = last_total
                                last_date += one_day
                        last_total = trans.running_total
                        last_date = date_obj
            folder_maps[folder_name] = day_end_totals
        return folder_maps

    @staticmethod
    def main():
        """Main function to parse account folders and display daily summaries."""
        base_path = Path("financial-data")
        statements_by_folder = parse_all_account_folders(base_path)
        
        if not statements_by_folder:
            print("No statements found.")
            return
        
        daily_summary = DailySummary(statements_by_folder)
        summary = daily_summary.get_summary()

        # Display the summary
        print("Daily Summary of Maximum Running Totals:")
        for date, total in sorted(summary.items()):
            print(f"{date}: £{total:.2f}")

if __name__ == "__main__":
    DailySummary.main() 