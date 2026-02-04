"""
Google Sheets client for lead queue management.

Uses service account authentication for server-side access.
Requires: pip install gspread google-auth
"""
import logging
from typing import List, Dict, Optional, Any
from datetime import datetime

try:
    import gspread
    from google.oauth2.service_account import Credentials
    GSPREAD_AVAILABLE = True
except ImportError:
    GSPREAD_AVAILABLE = False

logger = logging.getLogger(__name__)

# Google Sheets API scopes
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive.readonly',
]


class GoogleSheetsClient:
    """
    Client for reading/writing leads from Google Sheets.

    Authentication options:
    1. Service account JSON file path
    2. Service account JSON dict (for environment variable storage)
    """

    def __init__(self, credentials_json: Optional[str] = None, credentials_dict: Optional[Dict] = None):
        """
        Initialize the Google Sheets client.

        Args:
            credentials_json: Path to service account JSON file
            credentials_dict: Service account credentials as dict
        """
        if not GSPREAD_AVAILABLE:
            raise ImportError(
                "gspread and google-auth are required. "
                "Install with: pip install gspread google-auth"
            )

        self.client = None
        self._connect(credentials_json, credentials_dict)

    def _connect(self, credentials_json: Optional[str], credentials_dict: Optional[Dict]):
        """Establish connection to Google Sheets API."""
        try:
            if credentials_dict:
                creds = Credentials.from_service_account_info(credentials_dict, scopes=SCOPES)
            elif credentials_json:
                creds = Credentials.from_service_account_file(credentials_json, scopes=SCOPES)
            else:
                raise ValueError("Either credentials_json or credentials_dict must be provided")

            self.client = gspread.authorize(creds)
            logger.info("Successfully connected to Google Sheets API")
        except Exception as e:
            logger.error(f"Failed to connect to Google Sheets: {e}")
            raise

    def open_spreadsheet(self, spreadsheet_id: str) -> gspread.Spreadsheet:
        """
        Open a spreadsheet by ID.

        Args:
            spreadsheet_id: The ID from the Google Sheets URL

        Returns:
            gspread.Spreadsheet object
        """
        try:
            return self.client.open_by_key(spreadsheet_id)
        except gspread.SpreadsheetNotFound:
            raise ValueError(f"Spreadsheet {spreadsheet_id} not found or not shared with service account")

    def get_pending_leads(
        self,
        spreadsheet_id: str,
        sheet_name: str = "Lead Queue",
        limit: int = 150,
    ) -> List[Dict[str, Any]]:
        """
        Get pending leads from the queue.

        Args:
            spreadsheet_id: Google Sheets ID
            sheet_name: Name of the sheet/tab
            limit: Maximum number of leads to return

        Returns:
            List of lead dictionaries
        """
        spreadsheet = self.open_spreadsheet(spreadsheet_id)
        worksheet = spreadsheet.worksheet(sheet_name)

        # Get all records
        all_records = worksheet.get_all_records()

        # Filter to pending only
        pending_leads = []
        for idx, record in enumerate(all_records):
            status = str(record.get("status", "")).lower().strip()
            if status == "pending":
                record["_row_number"] = idx + 2  # +2 for header row and 0-indexing
                pending_leads.append(record)

                if len(pending_leads) >= limit:
                    break

        logger.info(f"Found {len(pending_leads)} pending leads (limit: {limit})")
        return pending_leads

    def get_queue_stats(
        self,
        spreadsheet_id: str,
        sheet_name: str = "Lead Queue",
    ) -> Dict[str, int]:
        """
        Get statistics about the lead queue.

        Returns:
            Dict with counts: pending, processed, error, total
        """
        spreadsheet = self.open_spreadsheet(spreadsheet_id)
        worksheet = spreadsheet.worksheet(sheet_name)

        all_records = worksheet.get_all_records()

        stats = {"pending": 0, "processed": 0, "error": 0, "total": len(all_records)}

        for record in all_records:
            status = str(record.get("status", "")).lower().strip()
            if status == "pending":
                stats["pending"] += 1
            elif status == "processed":
                stats["processed"] += 1
            elif status == "error":
                stats["error"] += 1

        return stats

    def mark_leads_processed(
        self,
        spreadsheet_id: str,
        sheet_name: str,
        row_numbers: List[int],
        personalization_data: List[Dict[str, str]],
    ):
        """
        Mark leads as processed and add personalization data.

        Args:
            spreadsheet_id: Google Sheets ID
            sheet_name: Sheet name
            row_numbers: List of row numbers to update
            personalization_data: List of dicts with personalization_line, etc.
        """
        spreadsheet = self.open_spreadsheet(spreadsheet_id)
        worksheet = spreadsheet.worksheet(sheet_name)

        # Get headers to find column indices
        headers = worksheet.row_values(1)
        headers_lower = [h.lower() for h in headers]

        # Find column indices (1-indexed for gspread)
        status_col = headers_lower.index("status") + 1 if "status" in headers_lower else None
        date_col = headers_lower.index("date_processed") + 1 if "date_processed" in headers_lower else None
        line_col = headers_lower.index("personalization_line") + 1 if "personalization_line" in headers_lower else None
        tier_col = headers_lower.index("confidence_tier") + 1 if "confidence_tier" in headers_lower else None
        type_col = headers_lower.index("artifact_type") + 1 if "artifact_type" in headers_lower else None

        current_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Batch update for efficiency
        cells_to_update = []

        for row_num, data in zip(row_numbers, personalization_data):
            if status_col:
                cells_to_update.append(gspread.Cell(row_num, status_col, "processed"))
            if date_col:
                cells_to_update.append(gspread.Cell(row_num, date_col, current_date))
            if line_col and "personalization_line" in data:
                cells_to_update.append(gspread.Cell(row_num, line_col, data["personalization_line"]))
            if tier_col and "confidence_tier" in data:
                cells_to_update.append(gspread.Cell(row_num, tier_col, data["confidence_tier"]))
            if type_col and "artifact_type" in data:
                cells_to_update.append(gspread.Cell(row_num, type_col, data["artifact_type"]))

        if cells_to_update:
            worksheet.update_cells(cells_to_update)
            logger.info(f"Updated {len(row_numbers)} rows as processed")

    def mark_leads_error(
        self,
        spreadsheet_id: str,
        sheet_name: str,
        row_numbers: List[int],
        error_messages: List[str],
    ):
        """Mark leads as having an error."""
        spreadsheet = self.open_spreadsheet(spreadsheet_id)
        worksheet = spreadsheet.worksheet(sheet_name)

        headers = worksheet.row_values(1)
        headers_lower = [h.lower() for h in headers]

        status_col = headers_lower.index("status") + 1 if "status" in headers_lower else None
        error_col = headers_lower.index("error_message") + 1 if "error_message" in headers_lower else None

        cells_to_update = []

        for row_num, error_msg in zip(row_numbers, error_messages):
            if status_col:
                cells_to_update.append(gspread.Cell(row_num, status_col, "error"))
            if error_col:
                cells_to_update.append(gspread.Cell(row_num, error_col, error_msg[:200]))

        if cells_to_update:
            worksheet.update_cells(cells_to_update)
            logger.info(f"Marked {len(row_numbers)} rows as error")

    def test_connection(self) -> bool:
        """Test if the connection is working."""
        try:
            # Try to list spreadsheets (will fail if not authorized)
            self.client.openall()
            return True
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False


def parse_spreadsheet_id(url_or_id: str) -> str:
    """
    Extract spreadsheet ID from URL or return as-is if already an ID.

    Args:
        url_or_id: Google Sheets URL or spreadsheet ID

    Returns:
        Spreadsheet ID
    """
    if "docs.google.com" in url_or_id:
        # Extract ID from URL
        # Format: https://docs.google.com/spreadsheets/d/SPREADSHEET_ID/edit
        parts = url_or_id.split("/")
        for i, part in enumerate(parts):
            if part == "d" and i + 1 < len(parts):
                return parts[i + 1]
        raise ValueError(f"Could not extract spreadsheet ID from URL: {url_or_id}")
    else:
        # Assume it's already an ID
        return url_or_id
