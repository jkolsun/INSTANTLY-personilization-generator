"""
Instantly API V2 Client for personalization integration.

API Documentation: https://developer.instantly.ai/api/v2
"""
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests


@dataclass
class Lead:
    """Represents an Instantly lead."""
    id: str
    email: str
    first_name: Optional[str]
    last_name: Optional[str]
    company_name: Optional[str]
    company_domain: Optional[str]
    campaign_id: Optional[str]
    custom_variables: Dict[str, Any]
    # Additional fields from the API
    raw_data: Dict[str, Any]

    @classmethod
    def from_api_response(cls, data: Dict[str, Any]) -> "Lead":
        """Create a Lead from API response data."""
        return cls(
            id=data.get("id", ""),
            email=data.get("email", ""),
            first_name=data.get("first_name"),
            last_name=data.get("last_name"),
            company_name=data.get("company_name"),
            company_domain=data.get("company_domain"),
            campaign_id=data.get("campaign"),
            custom_variables=data.get("custom_variables", {}),
            raw_data=data,
        )


@dataclass
class Campaign:
    """Represents an Instantly campaign."""
    id: str
    name: str
    status: str

    @classmethod
    def from_api_response(cls, data: Dict[str, Any]) -> "Campaign":
        """Create a Campaign from API response data."""
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            status=data.get("status", ""),
        )


class InstantlyClient:
    """
    Client for Instantly API V2.

    Usage:
        client = InstantlyClient(api_key="your_api_key")
        campaigns = client.list_campaigns()
        leads = client.list_leads(campaign_id="campaign_id")
    """

    BASE_URL = "https://api.instantly.ai/api/v2"

    def __init__(self, api_key: str, rate_limit_delay: float = 0.5):
        """
        Initialize the Instantly client.

        Args:
            api_key: Instantly API V2 key
            rate_limit_delay: Seconds to wait between requests (default 0.5)
        """
        self.api_key = api_key
        self.rate_limit_delay = rate_limit_delay
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        })

    def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        json_data: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Make an API request.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint (e.g., "/campaigns")
            params: Query parameters
            json_data: JSON body data

        Returns:
            API response as dict

        Raises:
            requests.HTTPError: If request fails
        """
        url = f"{self.BASE_URL}{endpoint}"

        response = self.session.request(
            method=method,
            url=url,
            params=params,
            json=json_data,
        )

        # Rate limiting
        time.sleep(self.rate_limit_delay)

        response.raise_for_status()
        return response.json()

    def list_campaigns(self, limit: int = 100) -> List[Campaign]:
        """
        List all campaigns.

        Args:
            limit: Maximum number of campaigns to return

        Returns:
            List of Campaign objects
        """
        campaigns = []
        starting_after = None

        while True:
            params = {"limit": min(limit - len(campaigns), 100)}
            if starting_after:
                params["starting_after"] = starting_after

            response = self._request("GET", "/campaigns", params=params)

            items = response.get("items", [])
            if not items:
                break

            for item in items:
                campaigns.append(Campaign.from_api_response(item))

            # Check if we have more pages
            next_starting_after = response.get("next_starting_after")
            if not next_starting_after or len(campaigns) >= limit:
                break

            starting_after = next_starting_after

        return campaigns[:limit]

    def list_leads(
        self,
        campaign_id: Optional[str] = None,
        list_id: Optional[str] = None,
        limit: int = 1000,
        email_filter: Optional[str] = None,
    ) -> List[Lead]:
        """
        List leads from a campaign or list.

        Args:
            campaign_id: Filter by campaign ID
            list_id: Filter by list ID
            limit: Maximum number of leads to return
            email_filter: Filter by email address

        Returns:
            List of Lead objects
        """
        leads = []
        starting_after = None

        while True:
            # POST request for listing leads (per API docs)
            body = {"limit": min(limit - len(leads), 100)}

            if campaign_id:
                body["campaign_id"] = campaign_id
            if list_id:
                body["list_id"] = list_id
            if email_filter:
                body["email"] = email_filter
            if starting_after:
                body["starting_after"] = starting_after

            response = self._request("POST", "/leads/list", json_data=body)

            items = response.get("items", [])
            if not items:
                break

            for item in items:
                leads.append(Lead.from_api_response(item))

            # Check if we have more pages
            next_starting_after = response.get("next_starting_after")
            if not next_starting_after or len(leads) >= limit:
                break

            starting_after = next_starting_after

        return leads[:limit]

    def get_lead(self, lead_id: str) -> Lead:
        """
        Get a single lead by ID.

        Args:
            lead_id: The lead ID

        Returns:
            Lead object
        """
        response = self._request("GET", f"/leads/{lead_id}")
        return Lead.from_api_response(response)

    def update_lead(
        self,
        lead_id: str,
        custom_variables: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Lead:
        """
        Update a lead's data.

        Args:
            lead_id: The lead ID
            custom_variables: Custom variables to set/update
            **kwargs: Other fields to update (first_name, last_name, etc.)

        Returns:
            Updated Lead object
        """
        body = {}

        if custom_variables:
            body["custom_variables"] = custom_variables

        # Add any other fields
        for key, value in kwargs.items():
            if value is not None:
                body[key] = value

        response = self._request("PATCH", f"/leads/{lead_id}", json_data=body)
        return Lead.from_api_response(response)

    def update_lead_variables(
        self,
        lead_id: str,
        variables: Dict[str, Any],
        email: Optional[str] = None,
        campaign_id: Optional[str] = None,
    ) -> bool:
        """
        Update custom variables on a lead.

        In V2 API, the most reliable way to set custom variables is to use the
        add leads endpoint with skip_if_in_campaign=False, which acts as an upsert.

        Args:
            lead_id: The lead ID
            variables: Dictionary of variable name -> value
            email: Lead email (required for upsert approach)
            campaign_id: Campaign ID for the lead

        Returns:
            True if update was successful
        """
        # Primary approach: Re-add lead with custom variables (upsert)
        # This is the most reliable method for V2 API
        if email and campaign_id:
            try:
                lead_data = {
                    "email": email,
                    "custom_variables": variables,
                }
                body = {
                    "campaign_id": campaign_id,
                    "leads": [lead_data],
                    "skip_if_in_workspace": False,
                    "skip_if_in_campaign": False,
                }
                self._request("POST", "/leads", json_data=body)
                return True
            except requests.HTTPError:
                pass

        # Fallback: Try the standard PATCH on lead ID
        try:
            self.update_lead(lead_id, custom_variables=variables)
            return True
        except requests.HTTPError:
            pass

        return False

    def update_lead_by_email(
        self,
        email: str,
        variables: Dict[str, Any],
        campaign_id: Optional[str] = None,
    ) -> bool:
        """
        Update lead custom variables by email address.

        Tries multiple approaches to ensure the update works.

        Args:
            email: Lead email address
            variables: Dictionary of variable name -> value
            campaign_id: Optional campaign ID

        Returns:
            True if update was successful
        """
        # Approach 1: Re-add the lead with custom variables (upsert style)
        # In V2, adding a lead that exists will update its custom variables
        if campaign_id:
            try:
                lead_data = {
                    "email": email,
                    "custom_variables": variables,
                }
                body = {
                    "campaign_id": campaign_id,
                    "leads": [lead_data],
                    "skip_if_in_workspace": False,
                    "skip_if_in_campaign": False,  # This allows updating existing leads
                }
                self._request("POST", "/leads", json_data=body)
                return True
            except requests.HTTPError:
                pass

        # Approach 2: Try POST /leads/update endpoint
        try:
            body = {
                "email": email,
                "custom_variables": variables,
            }
            if campaign_id:
                body["campaign_id"] = campaign_id

            self._request("POST", "/leads/update", json_data=body)
            return True
        except requests.HTTPError:
            pass

        return False

    def add_leads_to_campaign(
        self,
        campaign_id: str,
        leads_data: List[Dict[str, Any]],
        skip_if_in_workspace: bool = True,
        skip_if_in_campaign: bool = True,
    ) -> Dict[str, Any]:
        """
        Add multiple leads to a campaign.

        Args:
            campaign_id: Target campaign ID
            leads_data: List of lead data dicts (must include 'email')
            skip_if_in_workspace: Skip if lead exists in workspace
            skip_if_in_campaign: Skip if lead already in campaign

        Returns:
            API response with upload status
        """
        body = {
            "campaign_id": campaign_id,
            "leads": leads_data,
            "skip_if_in_workspace": skip_if_in_workspace,
            "skip_if_in_campaign": skip_if_in_campaign,
        }

        return self._request("POST", "/leads", json_data=body)

    def test_connection(self) -> bool:
        """
        Test the API connection.

        Returns:
            True if connection successful
        """
        try:
            self._request("GET", "/campaigns", params={"limit": 1})
            return True
        except requests.HTTPError:
            return False


# Convenience function for quick testing
def test_api_key(api_key: str) -> bool:
    """Test if an API key is valid."""
    client = InstantlyClient(api_key)
    return client.test_connection()
