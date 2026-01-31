"""
Instantly API V2 Client for personalization integration.

API Documentation: https://developer.instantly.ai/api/v2
"""
import time
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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
    raw_data: Dict[str, Any]

    @classmethod
    def from_api_response(cls, data: Dict[str, Any]) -> "Lead":
        """Create a Lead from API response data.

        Note: Instantly API V2 stores custom variables in the 'payload' field,
        not in a separate 'custom_variables' field. We check both for compatibility.
        """
        # Instantly API V2 stores custom variables in the 'payload' field
        # Check payload first (V2), then fall back to custom_variables for compatibility
        custom_vars = data.get("payload") or data.get("custom_variables") or {}

        # If payload is a dict, use it directly; otherwise default to empty dict
        if not isinstance(custom_vars, dict):
            custom_vars = {}

        return cls(
            id=data.get("id", ""),
            email=data.get("email", ""),
            first_name=data.get("first_name"),
            last_name=data.get("last_name"),
            company_name=data.get("company_name"),
            company_domain=data.get("website") or data.get("company_domain"),
            campaign_id=data.get("campaign"),  # V2 uses "campaign" not "campaign_id"
            custom_variables=custom_vars,
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
        """Initialize the Instantly client."""
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
        """Make an API request with detailed logging."""
        url = f"{self.BASE_URL}{endpoint}"

        logger.info(f"=== API Request: {method} {url} ===")
        if params:
            logger.info(f"Query params: {params}")
        if json_data:
            logger.info(f"Request body: {json_data}")

        try:
            response = self.session.request(
                method=method,
                url=url,
                params=params,
                json=json_data,
            )
        except requests.RequestException as e:
            logger.error(f"Request failed with exception: {e}")
            raise

        # Rate limiting
        time.sleep(self.rate_limit_delay)

        # Log response details
        logger.info(f"Response status: {response.status_code}")

        if not response.ok:
            logger.error(f"=== API ERROR {response.status_code} ===")
            logger.error(f"Error response body: {response.text}")
            logger.error(f"Request was: {method} {endpoint}")
            if json_data:
                logger.error(f"Request body was: {json_data}")

        response.raise_for_status()

        result = response.json()
        logger.info(f"Response has {len(result.get('items', []))} items" if 'items' in result else f"Response: {str(result)[:200]}")
        return result

    def list_campaigns(self, limit: int = 100) -> List[Campaign]:
        """List all campaigns."""
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

            next_starting_after = response.get("next_starting_after")
            if not next_starting_after or len(campaigns) >= limit:
                break

            starting_after = next_starting_after

        return campaigns[:limit]

    def list_leads(
        self,
        campaign_id: Optional[str] = None,
        limit: int = 1000,
    ) -> List[Lead]:
        """
        List leads from a campaign.

        Args:
            campaign_id: Filter by campaign ID
            limit: Maximum number of leads to return

        Returns:
            List of Lead objects
        """
        leads = []
        starting_after = None

        logger.info(f"=== Listing leads for campaign: {campaign_id}, limit: {limit} ===")

        while True:
            # Build request body - V2 uses "campaign" parameter
            body = {"limit": min(limit - len(leads), 100)}

            if campaign_id:
                body["campaign"] = campaign_id

            if starting_after:
                body["starting_after"] = starting_after

            logger.info(f"Fetching batch with body: {body}")

            try:
                response = self._request("POST", "/leads/list", json_data=body)
            except requests.HTTPError as e:
                logger.error(f"Failed to list leads with 'campaign': {e}")
                # Fallback: Try with campaign_id instead
                if campaign_id and "campaign" in body:
                    logger.info("Retrying with 'campaign_id' parameter instead...")
                    body["campaign_id"] = campaign_id
                    del body["campaign"]
                    try:
                        response = self._request("POST", "/leads/list", json_data=body)
                    except requests.HTTPError as e2:
                        logger.error(f"Also failed with 'campaign_id': {e2}")
                        break
                else:
                    break

            items = response.get("items", [])
            logger.info(f"Batch returned {len(items)} leads")

            if items:
                # Log first lead's campaign to verify filtering
                first_lead = items[0]
                logger.info(f"First lead email: {first_lead.get('email')}, campaign: {first_lead.get('campaign')}")

            if not items:
                break

            for item in items:
                leads.append(Lead.from_api_response(item))

            next_starting_after = response.get("next_starting_after")
            if not next_starting_after or len(leads) >= limit:
                break

            starting_after = next_starting_after

        logger.info(f"=== Total leads fetched: {len(leads)} ===")
        return leads[:limit]

    def get_lead(self, lead_id: str) -> Lead:
        """Get a single lead by ID."""
        response = self._request("GET", f"/leads/{lead_id}")
        return Lead.from_api_response(response)

    def update_lead(
        self,
        lead_id: str,
        custom_variables: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Lead:
        """Update a lead's data via PATCH."""
        body = {}

        if custom_variables:
            body["custom_variables"] = custom_variables

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
    ) -> tuple:
        """
        Update custom variables on a lead.

        Tries multiple approaches to ensure success.

        Returns:
            Tuple of (success: bool, error_message: str or None)
        """
        errors = []
        logger.info(f"=== Updating lead: email={email}, id={lead_id}, campaign={campaign_id} ===")
        logger.info(f"Variables to set: {variables}")

        # Approach 1: PATCH on lead ID (preferred method for updates)
        if lead_id:
            try:
                logger.info(f"Approach 1: PATCH /leads/{lead_id}")
                self.update_lead(lead_id, custom_variables=variables)
                logger.info("SUCCESS: PATCH method worked!")
                return (True, None)
            except requests.HTTPError as e:
                status = e.response.status_code if e.response else "unknown"
                body = e.response.text[:200] if e.response else str(e)
                error = f"PATCH failed ({status}): {body}"
                logger.warning(error)
                errors.append(error)
            except Exception as e:
                error = f"PATCH exception: {str(e)}"
                logger.warning(error)
                errors.append(error)

        # Approach 2: POST /leads to upsert with campaign_id
        if email and campaign_id:
            try:
                logger.info(f"Approach 2: POST /leads upsert (campaign_id) for {email}")
                body = {
                    "campaign_id": campaign_id,
                    "leads": [{
                        "email": email,
                        "custom_variables": variables,
                    }],
                    "skip_if_in_workspace": False,
                    "skip_if_in_campaign": False,
                }
                self._request("POST", "/leads", json_data=body)
                logger.info("SUCCESS: POST /leads with campaign_id worked!")
                return (True, None)
            except requests.HTTPError as e:
                status = e.response.status_code if e.response else "unknown"
                body = e.response.text[:200] if e.response else str(e)
                error = f"POST campaign_id failed ({status}): {body}"
                logger.warning(error)
                errors.append(error)
            except Exception as e:
                error = f"Upsert exception: {str(e)}"
                logger.warning(error)
                errors.append(error)

        # Approach 3: POST /leads with "campaign" parameter (V2 alternative)
        if email and campaign_id:
            try:
                logger.info(f"Approach 3: POST /leads upsert (campaign) for {email}")
                body = {
                    "campaign": campaign_id,
                    "leads": [{
                        "email": email,
                        "custom_variables": variables,
                    }],
                    "skip_if_in_workspace": False,
                    "skip_if_in_campaign": False,
                }
                self._request("POST", "/leads", json_data=body)
                logger.info("SUCCESS: POST /leads with campaign worked!")
                return (True, None)
            except requests.HTTPError as e:
                status = e.response.status_code if e.response else "unknown"
                body = e.response.text[:200] if e.response else str(e)
                error = f"POST campaign failed ({status}): {body}"
                logger.warning(error)
                errors.append(error)

        logger.error(f"ALL APPROACHES FAILED for {email}: {errors}")
        return (False, "; ".join(errors))

    def test_connection(self) -> bool:
        """Test the API connection."""
        logger.info("=== Testing Instantly API connection ===")
        try:
            self._request("GET", "/campaigns", params={"limit": 1})
            logger.info("Connection test successful!")
            return True
        except requests.HTTPError as e:
            logger.error(f"Connection test FAILED: {e}")
            if e.response:
                logger.error(f"Response: {e.response.text}")
            return False


def test_api_key(api_key: str) -> bool:
    """Test if an API key is valid."""
    client = InstantlyClient(api_key)
    return client.test_connection()
