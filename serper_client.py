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
    # SD-06: Confidence scoring fields
    domain_match_count: int = 0
    total_results: int = 0
    is_low_confidence: bool = False
    # SD-05: Industry mismatch detection
    industry_mismatch_detected: bool = False
    mismatched_industry: Optional[str] = None


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

# SD-05: Keywords that indicate wrong industry (for HVAC leads)
# If these appear but the lead is HVAC, it's likely wrong company data
WRONG_INDUSTRY_KEYWORDS = [
    # Different industries that might share company names
    "lawn care", "lawn service", "landscaping", "mowing",
    "solar panel", "solar installation", "solar energy", "photovoltaic",
    "robotics", "automation systems", "industrial robot",
    "dental", "dentist", "orthodontic",
    "veterinary", "vet clinic", "animal hospital",
    "real estate agent", "realtor", "property management",
    "restaurant", "catering", "food service",
    "car dealership", "auto sales", "used cars",
    "hair salon", "beauty salon", "spa services",
    "law firm", "attorney", "legal services",
    "accounting firm", "cpa services", "tax preparation",
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

    def _build_disambiguated_query(
        self,
        company_name: str,
        domain: Optional[str] = None,
        location: Optional[str] = None
    ) -> str:
        """
        Build a disambiguated search query using all available signals.

        Uses implicit AND (space) instead of OR to ensure results match
        ALL provided criteria, preventing wrong-company results.

        Args:
            company_name: Name of the company
            domain: Company domain for disambiguation
            location: Company location (city, state) for disambiguation

        Returns:
            Disambiguated search query string
        """
        parts = [f'"{company_name}"']

        # Add domain for disambiguation (most reliable signal)
        if domain:
            # Remove www. and protocol if present
            clean_domain = domain.replace("https://", "").replace("http://", "").replace("www.", "")
            parts.append(clean_domain)

        # Add location for additional disambiguation
        if location:
            # Extract city or first part of location (before comma)
            city_state = location.split(',')[0].strip() if ',' in location else location.strip()
            if city_state and len(city_state) > 2:
                parts.append(city_state)

        return ' '.join(parts)

    def get_company_info(
        self,
        company_name: str,
        domain: Optional[str] = None,
        location: Optional[str] = None
    ) -> CompanyInfo:
        """
        Get company information with MULTIPLE search queries for richer data.

        Args:
            company_name: Name of the company
            domain: Optional company domain for disambiguation (highly recommended)
            location: Optional company location for disambiguation

        Returns:
            CompanyInfo with aggregated data
        """
        info = CompanyInfo(name=company_name, description="")
        clean_name = company_name.strip()

        # Clean domain for searches
        clean_domain = ""
        if domain:
            clean_domain = domain.replace("https://", "").replace("http://", "").replace("www.", "")

        try:
            # SEARCH 1: Main company search
            query1 = self._build_disambiguated_query(clean_name, domain, location)
            logger.info(f"Serper query 1 for {company_name}: {query1}")
            results1 = self.search(query1, num_results=10)
            self._process_search_results(results1, info)

            # SEARCH 2: Reviews and testimonials (great for personalization)
            if clean_domain:
                query2 = f'"{clean_name}" reviews OR testimonials site:{clean_domain}'
                logger.info(f"Serper query 2 for {company_name}: {query2}")
                try:
                    results2 = self.search(query2, num_results=5)
                    self._process_search_results(results2, info)
                except Exception:
                    pass

            # SEARCH 3: News and press
            query3 = f'"{clean_name}" news OR press OR award'
            if location:
                query3 += f' {location.split(",")[0]}'
            logger.info(f"Serper query 3 for {company_name}: {query3}")
            try:
                results3 = self.search(query3, num_results=5)
                self._process_search_results(results3, info)
            except Exception:
                pass

            # Validate domain matches
            if domain:
                self._validate_domain_matches(results1, domain, info)

            # Check for industry mismatch
            self._check_industry_mismatch(info)

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

    def _validate_domain_matches(
        self,
        results: Dict[str, Any],
        expected_domain: str,
        info: CompanyInfo
    ):
        """
        SD-04 & SD-06: Validate that search results match expected domain.

        Counts how many results contain the expected domain.
        If fewer than 3 results match, marks as low confidence.

        Args:
            results: Raw Serper API response
            expected_domain: Expected company domain
            info: CompanyInfo to update with validation results
        """
        organic = results.get("organic", [])
        info.total_results = len(organic)

        if not expected_domain:
            return

        # Clean domain for matching
        clean_domain = expected_domain.lower().replace("https://", "").replace("http://", "").replace("www.", "")
        # Extract just the base domain (e.g., "example.com" from "example.com/page")
        base_domain = clean_domain.split('/')[0]

        domain_matches = 0
        for item in organic:
            link = item.get("link", "").lower()
            if base_domain in link:
                domain_matches += 1

        info.domain_match_count = domain_matches

        # SD-06: If fewer than 3 results contain the expected domain, flag as low confidence
        if domain_matches < 3:
            info.is_low_confidence = True
            logger.warning(
                f"Low confidence for {info.name}: only {domain_matches}/{info.total_results} "
                f"results match domain {base_domain}"
            )

    def _check_industry_mismatch(self, info: CompanyInfo):
        """
        SD-05: Check if Serper results indicate wrong industry.

        Scans all snippets for keywords that suggest the data is for
        a different company in a different industry.

        Args:
            info: CompanyInfo to check and update
        """
        # Combine all text content to scan
        all_text = " ".join([
            info.description,
            " ".join(info.snippets),
            " ".join(info.linkedin_info),
            " ".join(info.services),
        ]).lower()

        for keyword in WRONG_INDUSTRY_KEYWORDS:
            if keyword in all_text:
                info.industry_mismatch_detected = True
                info.mismatched_industry = keyword
                logger.warning(
                    f"Industry mismatch detected for {info.name}: "
                    f"found '{keyword}' in results"
                )
                break

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
