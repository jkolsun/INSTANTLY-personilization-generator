"""
Column normalizer for CSV inputs.
Maps common column name variants to standardized names.
"""
from typing import Dict, Optional
import pandas as pd


# Column name mappings (variant -> standard)
COLUMN_MAPPINGS: Dict[str, str] = {
    # Website URL
    "website": "site_url",
    "site_url": "site_url",
    "domain": "site_url",
    "site": "site_url",
    "company_website": "site_url",
    "companywebsite": "site_url",
    "companydomain": "site_url",
    "company_domain": "site_url",
    "url": "site_url",
    "web": "site_url",

    # Company name
    "company": "company_name",
    "company_name": "company_name",
    "companyname": "company_name",
    "organization": "company_name",
    "organization name": "company_name",  # Apollo
    "organization_name": "company_name",  # Apollo
    "org": "company_name",
    "business": "company_name",
    "business_name": "company_name",
    "account name": "company_name",  # Salesforce
    "account_name": "company_name",

    # First name
    "first_name": "first_name",
    "firstname": "first_name",
    "first name": "first_name",
    "fname": "first_name",

    # Last name
    "last_name": "last_name",
    "lastname": "last_name",
    "last name": "last_name",
    "lname": "last_name",

    # Email
    "email": "email",
    "email_address": "email",
    "emailaddress": "email",
    "contact_email": "email",

    # LinkedIn
    "linkedin": "linkedin_url",
    "linkedin_url": "linkedin_url",
    "linkedinurl": "linkedin_url",
    "linkedin_profile": "linkedin_url",
    "person linkedin url": "linkedin_url",  # Apollo
    "person_linkedin_url": "linkedin_url",  # Apollo
    "linkedin url": "linkedin_url",  # Apollo

    # Company description
    "company_description": "company_description",
    "companydescription": "company_description",
    "description": "company_description",
    "about": "company_description",
    "company_about": "company_description",

    # Location
    "location": "location",
    "city": "city",
    "state": "state",
    "country": "country",

    # Industry
    "industry": "industry",

    # Title/Role
    "title": "job_title",
    "job_title": "job_title",
    "jobtitle": "job_title",
    "role": "job_title",
    "position": "job_title",

    # LinkedIn headline/summary
    "headline": "headline",
    "summary": "summary",
    "linkedin_headline": "headline",
    "linkedin_summary": "summary",
}


def normalize_column_name(col: str) -> str:
    """
    Normalize a single column name to its standard form.

    Args:
        col: Original column name

    Returns:
        Normalized column name
    """
    # Convert to lowercase and strip whitespace
    normalized = col.lower().strip()

    # Check if it's in our mappings
    if normalized in COLUMN_MAPPINGS:
        return COLUMN_MAPPINGS[normalized]

    # Return original (lowercase) if no mapping found
    return normalized


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize all column names in a DataFrame.

    Args:
        df: Input DataFrame with original column names

    Returns:
        DataFrame with normalized column names
    """
    # Create mapping of old names to new names
    rename_map = {}
    for col in df.columns:
        new_name = normalize_column_name(col)
        rename_map[col] = new_name

    # Rename columns
    df = df.rename(columns=rename_map)

    return df


def get_value(row: pd.Series, *column_names: str) -> Optional[str]:
    """
    Get a value from a row, trying multiple possible column names.

    Args:
        row: DataFrame row
        *column_names: Column names to try in order

    Returns:
        First non-empty value found, or None
    """
    for col in column_names:
        if col in row.index:
            val = row[col]
            # Handle case where val might be a Series (duplicate columns)
            if isinstance(val, pd.Series):
                val = val.iloc[0] if len(val) > 0 else None
            # Check if value is valid
            try:
                if val is not None and pd.notna(val):
                    str_val = str(val).strip()
                    if str_val:
                        return str_val
            except (ValueError, TypeError):
                continue
    return None


def get_site_url(row: pd.Series) -> Optional[str]:
    """
    Get the website URL from a row, normalizing the format.

    Args:
        row: DataFrame row

    Returns:
        Normalized website URL or None
    """
    url = get_value(row, "site_url", "companywebsite", "companydomain")

    if not url:
        return None

    # Clean up the URL
    url = url.strip()

    # Skip if it's "No data found" or similar
    if url.lower() in ["no data found", "n/a", "na", "none", "skipped", "-"]:
        return None

    # Add https:// if no scheme
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    return url


def get_company_name(row: pd.Series) -> Optional[str]:
    """
    Get the company name from a row.

    Args:
        row: DataFrame row

    Returns:
        Company name or None
    """
    return get_value(row, "company_name", "companyname")


def get_company_description(row: pd.Series) -> Optional[str]:
    """
    Get the company description from a row.

    Args:
        row: DataFrame row

    Returns:
        Company description or None
    """
    desc = get_value(row, "company_description", "companydescription")

    if not desc:
        return None

    # Skip if it's "No data found" or similar
    if desc.lower() in ["no data found", "n/a", "na", "none", "skipped", "-"]:
        return None

    return desc


def _clean_location(location: str) -> Optional[str]:
    """
    Clean up a location string for better personalization.

    Removes country suffixes like "United States" and formats more concisely.

    Args:
        location: Raw location string

    Returns:
        Cleaned location or None if too generic
    """
    if not location:
        return None

    # Remove common country suffixes
    location = location.strip()
    suffixes_to_remove = [
        ", United States",
        ", USA",
        ", US",
        ", Canada",
        ", United Kingdom",
        ", UK",
        ", Australia",
    ]
    for suffix in suffixes_to_remove:
        if location.endswith(suffix):
            location = location[:-len(suffix)]

    # Check if it's just a country (too generic)
    generic_locations = [
        "united states", "usa", "us", "canada", "uk",
        "united kingdom", "australia", "worldwide", "global",
    ]
    if location.lower().strip() in generic_locations:
        return None

    # If still empty after cleaning, return None
    if not location.strip():
        return None

    return location.strip()


def get_location(row: pd.Series) -> Optional[str]:
    """
    Get the location from a row, combining city/state if needed.

    Args:
        row: DataFrame row

    Returns:
        Location string or None
    """
    # Try direct location field first
    location = get_value(row, "location")
    if location and location.lower() not in ["no data found", "n/a", "na", "none", "skipped", "-"]:
        cleaned = _clean_location(location)
        if cleaned:
            return cleaned

    # Build from city/state
    city = get_value(row, "city")
    state = get_value(row, "state")

    parts = []
    if city and city.lower() not in ["no data found", "n/a", "na", "none", "skipped", "-"]:
        parts.append(city)
    if state and state.lower() not in ["no data found", "n/a", "na", "none", "skipped", "-"]:
        parts.append(state)

    if parts:
        return ", ".join(parts)

    return None


def get_linkedin_url(row: pd.Series) -> Optional[str]:
    """
    Get the LinkedIn URL from a row.

    Args:
        row: DataFrame row

    Returns:
        LinkedIn URL or None
    """
    url = get_value(row, "linkedin_url", "linkedin")

    if not url:
        return None

    # Skip if it's "No data found" or similar
    if url.lower() in ["no data found", "n/a", "na", "none", "skipped", "-"]:
        return None

    # Add https:// if needed
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    return url
