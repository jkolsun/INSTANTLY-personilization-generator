"""
Serper API client for company information lookup.

Optimized for efficiency: 1-2 API calls per company instead of 6.
Focuses on finding the BEST personalization hooks fast.
"""
import re
import logging
import requests
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)


@dataclass
class SerperResult:
    """Structured result from Serper search."""
    title: str
    snippet: str
    link: str
    position: int


@dataclass
class CompanyInfo:
    """Aggregated company information from search."""
    name: str
    description: str
    snippets: List[str] = field(default_factory=list)
    services: List[str] = field(default_factory=list)
    tools: List[str] = field(default_factory=list)
    clients: List[str] = field(default_factory=list)
    awards: List[str] = field(default_factory=list)
    podcasts: List[str] = field(default_factory=list)
    linkedin_info: List[str] = field(default_factory=list)
    news_mentions: List[str] = field(default_factory=list)
    recent_projects: List[str] = field(default_factory=list)
    location: Optional[str] = None
    knowledge_panel: Optional[Dict[str, Any]] = None


# Known tools/platforms to look for (Tier S artifacts)
KNOWN_TOOLS = [
    "ServiceTitan", "HubSpot", "Salesforce", "QuickBooks", "Jobber",
    "Housecall Pro", "Zendesk", "Monday.com", "Asana", "Slack",
    "Mailchimp", "ActiveCampaign", "Podium", "Birdeye", "Workiz",
    "FieldEdge", "Simpro", "Zoho", "Freshworks", "Pipedrive",
    "Shopify", "WooCommerce", "Squarespace", "WordPress", "Webflow",
    "Stripe", "Square", "PayPal", "Calendly", "Acuity", "Intercom",
    "Drift", "Klaviyo", "Marketo", "Pardot", "Outreach", "Gong",
    "Chorus", "ZoomInfo", "Apollo", "Lusha", "Clearbit", "6sense",
]


class SerperClient:
    """
    Efficient Serper.dev Google Search API client.

    Makes only 1-2 API calls per company to minimize cost while
    maximizing personalization hook quality.
    """

    BASE_URL = "https://google.serper.dev/search"

    def __init__(self, api_key: str):
        """Initialize the Serper client."""
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            "X-API-KEY": api_key,
            "Content-Type": "application/json",
        })

    def search(self, query: str, num_results: int = 10) -> Dict[str, Any]:
        """
        Perform a Google search via Serper.

        Args:
            query: Search query
            num_results: Number of results to return

        Returns:
            Raw API response

        Raises:
            requests.HTTPError: If API call fails
        """
        payload = {
            "q": query,
            "num": num_results,
        }

        response = self.session.post(self.BASE_URL, json=payload)
        response.raise_for_status()
        return response.json()

    def get_company_info(self, company_name: str, domain: Optional[str] = None) -> CompanyInfo:
        """
        Get company information with ONE optimized search query.

        Uses a single, comprehensive search query that returns
        LinkedIn, website, and other valuable data in one call.

        Args:
            company_name: Name of the company
            domain: Optional company domain for more specific results

        Returns:
            CompanyInfo with aggregated data
        """
        info = CompanyInfo(name=company_name, description="")
        clean_name = company_name.strip()

        # SINGLE optimized search query that captures everything important
        # This query is designed to return LinkedIn, website, news, and other results
        if domain:
            query = f'"{clean_name}" OR site:{domain}'
        else:
            query = f'"{clean_name}" company'

        try:
            results = self.search(query, num_results=15)
            self._process_search_results(results, info)
        except requests.HTTPError as e:
            logger.error(f"Serper API error for {company_name}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error searching for {company_name}: {e}")

        # Build final description from all found data
        info.description = self._build_description(info)

        return info

    def _process_search_results(self, results: Dict[str, Any], info: CompanyInfo):
        """Process all results from a single search query."""

        # Extract knowledge graph if available (high-quality data)
        kg = results.get("knowledgeGraph", {})
        if kg:
            info.knowledge_panel = kg
            if kg.get("description"):
                info.snippets.append(kg["description"])

            attrs = kg.get("attributes", {})
            info.location = (
                attrs.get("Headquarters") or
                attrs.get("Address") or
                attrs.get("Service area")
            )

            # Extract other valuable attributes
            for key, value in attrs.items():
                if key.lower() not in ["website", "phone", "address", "founded"]:
                    info.snippets.append(f"{key}: {value}")

        # Process organic results
        for item in results.get("organic", []):
            snippet = item.get("snippet", "")
            title = item.get("title", "")
            link = item.get("link", "").lower()

            if not snippet:
                continue

            # Categorize result by source
            if "linkedin.com" in link:
                info.linkedin_info.append(snippet)
                self._extract_linkedin_details(snippet, info)
            elif "podcast" in link or "podcast" in title.lower() or "episode" in snippet.lower():
                info.podcasts.append(f"{title}: {snippet[:100]}")
            elif any(news in link for news in ["news", "press", "pr.", "businesswire", "prnewswire"]):
                info.news_mentions.append(f"{title}: {snippet[:100]}")
            else:
                info.snippets.append(snippet)

            # Extract tools and clients from ALL results
            self._extract_tools(snippet, info)
            self._extract_clients(snippet, info)

    def _extract_linkedin_details(self, text: str, info: CompanyInfo):
        """Extract useful details from LinkedIn snippets."""
        # Look for employee counts
        employee_pattern = r'(\d+[\+,]?\d*)\s*(?:employees|staff|team members)'
        matches = re.findall(employee_pattern, text, re.IGNORECASE)
        if matches:
            info.snippets.append(f"Team size: {matches[0]} employees")

        # Look for specialties/focus areas
        specialty_pattern = r'(?:specializ|focus|expert)\w*\s+(?:in\s+)?([^.]+)'
        matches = re.findall(specialty_pattern, text, re.IGNORECASE)
        for match in matches[:2]:
            if 5 < len(match) < 100:
                info.services.append(match.strip())

    def _extract_tools(self, text: str, info: CompanyInfo):
        """Extract tools and platforms from text."""
        text_lower = text.lower()
        for tool in KNOWN_TOOLS:
            if tool.lower() in text_lower and tool not in info.tools:
                info.tools.append(tool)

        # Also look for patterns like "powered by X", "built with X"
        patterns = [
            r'(?:powered by|built with|using|integrated with|runs on)\s+([A-Z][a-zA-Z0-9]+)',
        ]
        for pattern in patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                clean = match.strip()[:30]
                if len(clean) > 2 and clean not in info.tools:
                    info.tools.append(clean)

    def _extract_clients(self, text: str, info: CompanyInfo):
        """Extract client/project mentions from text."""
        patterns = [
            r'(?:worked with|clients include|partnered with|serving|project for)\s+([A-Z][a-zA-Z0-9\s,&]+?)(?:\.|,|$)',
            r'(?:case study|portfolio):\s*([A-Z][a-zA-Z0-9\s]+)',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                clean = match.strip()[:50]
                if len(clean) > 3 and clean not in info.clients:
                    info.clients.append(clean)

    def _build_description(self, info: CompanyInfo) -> str:
        """Build comprehensive description from gathered info."""
        parts = []

        # Knowledge panel description first (highest quality)
        if info.knowledge_panel and info.knowledge_panel.get("description"):
            parts.append(info.knowledge_panel["description"])

        # LinkedIn info (high value for B2B)
        for li in info.linkedin_info[:2]:
            if li not in parts:
                parts.append(li)

        # General snippets
        for snippet in info.snippets[:3]:
            if snippet not in parts:
                parts.append(snippet)

        return " ".join(parts)

    def test_connection(self) -> bool:
        """Test if the API key is valid."""
        try:
            self.search("test", num_results=1)
            return True
        except requests.HTTPError:
            return False


def extract_artifacts_from_serper(company_info: CompanyInfo) -> str:
    """
    Convert Serper results into a rich description for AI line generation.
    Prioritizes the most personalization-worthy content.

    Args:
        company_info: CompanyInfo from Serper lookup

    Returns:
        Combined description text optimized for personalization
    """
    parts = []

    # HIGHEST PRIORITY: Podcast/interview appearances (creates AMAZING hooks)
    for podcast in company_info.podcasts[:2]:
        parts.append(f'Featured on podcast: {podcast}')

    # HIGH PRIORITY: Tools/platforms (Tier S - very specific)
    for tool in company_info.tools[:3]:
        parts.append(f'Uses {tool}.')

    # HIGH PRIORITY: Clients/projects (Tier S - very specific)
    for client in company_info.clients[:3]:
        parts.append(f'Worked with {client}.')

    # HIGH PRIORITY: Recent projects
    for project in company_info.recent_projects[:2]:
        parts.append(f'Recent work: {project}')

    # MEDIUM PRIORITY: LinkedIn info
    for li in company_info.linkedin_info[:2]:
        parts.append(li)

    # MEDIUM PRIORITY: News mentions
    for news in company_info.news_mentions[:2]:
        parts.append(f'In the news: {news}')

    # Knowledge graph info
    if company_info.knowledge_panel:
        kg = company_info.knowledge_panel
        if kg.get("description"):
            parts.append(kg["description"])

    # Services
    for service in company_info.services[:2]:
        parts.append(service)

    # Location (Tier B fallback)
    if company_info.location:
        parts.append(f"Located in {company_info.location}.")

    # General snippets as fallback
    for snippet in company_info.snippets[:2]:
        if snippet not in parts:
            parts.append(snippet)

    return " ".join(parts)
