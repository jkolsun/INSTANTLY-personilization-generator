"""
Serper API client for comprehensive company information lookup.

Searches Google, LinkedIn, social media, podcasts, and news
to find the best personalization hooks for each company.
"""
import re
import requests
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


@dataclass
class SerperResult:
    """Structured result from Serper search."""
    title: str
    snippet: str
    link: str
    position: int


@dataclass
class CompanyInfo:
    """Aggregated company information from multiple search sources."""
    name: str
    description: str
    snippets: List[str] = field(default_factory=list)
    services: List[str] = field(default_factory=list)
    tools: List[str] = field(default_factory=list)
    clients: List[str] = field(default_factory=list)
    awards: List[str] = field(default_factory=list)
    podcasts: List[str] = field(default_factory=list)
    linkedin_info: List[str] = field(default_factory=list)
    social_mentions: List[str] = field(default_factory=list)
    news_mentions: List[str] = field(default_factory=list)
    recent_projects: List[str] = field(default_factory=list)
    location: Optional[str] = None
    knowledge_panel: Optional[Dict[str, Any]] = None


class SerperClient:
    """
    Client for Serper.dev Google Search API.

    Performs multiple targeted searches to find the best personalization hooks:
    - LinkedIn company info and posts
    - Social media mentions (Twitter, Facebook, Instagram)
    - Podcast appearances
    - News mentions and press releases
    - Company website and services
    """

    BASE_URL = "https://google.serper.dev/search"

    def __init__(self, api_key: str):
        """
        Initialize the Serper client.

        Args:
            api_key: Serper API key from serper.dev
        """
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
        Get comprehensive company information using multiple targeted searches.

        Args:
            company_name: Name of the company
            domain: Optional company domain for more specific results

        Returns:
            CompanyInfo with aggregated data from all sources
        """
        info = CompanyInfo(name=company_name, description="")

        # Clean up company name for searching
        clean_name = company_name.strip()

        # Search 1: LinkedIn company info - HIGHEST PRIORITY for B2B
        self._search_linkedin(clean_name, domain, info)

        # Search 2: Podcasts and video appearances
        self._search_podcasts(clean_name, info)

        # Search 3: Social media mentions
        self._search_social_media(clean_name, info)

        # Search 4: News and press releases
        self._search_news(clean_name, info)

        # Search 5: Company website and services
        self._search_company_site(clean_name, domain, info)

        # Search 6: Recent projects and case studies
        self._search_projects(clean_name, domain, info)

        # Build final description
        info.description = self._build_description(info)

        return info

    def _search_linkedin(self, company_name: str, domain: Optional[str], info: CompanyInfo):
        """Search LinkedIn for company info, posts, and employee insights."""
        try:
            # LinkedIn company page
            query = f'site:linkedin.com/company "{company_name}"'
            results = self.search(query, num_results=5)

            for item in results.get("organic", []):
                snippet = item.get("snippet", "")
                title = item.get("title", "")

                if snippet:
                    # Extract valuable LinkedIn info
                    info.linkedin_info.append(snippet)

                    # Look for employee count, industry, specialties
                    self._extract_linkedin_details(snippet, info)

            # Also search for recent LinkedIn posts/activity
            post_query = f'site:linkedin.com "{company_name}" post OR article OR announcement'
            post_results = self.search(post_query, num_results=3)

            for item in post_results.get("organic", []):
                snippet = item.get("snippet", "")
                if snippet and snippet not in info.linkedin_info:
                    info.linkedin_info.append(snippet)

        except Exception:
            pass

    def _search_podcasts(self, company_name: str, info: CompanyInfo):
        """Search for podcast appearances and video content."""
        try:
            # Podcasts
            query = f'"{company_name}" podcast OR interview OR episode OR "on the show"'
            results = self.search(query, num_results=5)

            for item in results.get("organic", []):
                snippet = item.get("snippet", "")
                title = item.get("title", "")
                link = item.get("link", "")

                # Check if it's actually a podcast/interview
                is_podcast = any(kw in (title + snippet + link).lower() for kw in
                               ["podcast", "episode", "interview", "show", "youtube", "spotify", "apple podcast"])

                if is_podcast and snippet:
                    info.podcasts.append(f"{title}: {snippet[:100]}")

        except Exception:
            pass

    def _search_social_media(self, company_name: str, info: CompanyInfo):
        """Search for social media presence and mentions."""
        try:
            # Twitter/X, Facebook, Instagram mentions
            query = f'"{company_name}" (site:twitter.com OR site:x.com OR site:facebook.com OR site:instagram.com)'
            results = self.search(query, num_results=5)

            for item in results.get("organic", []):
                snippet = item.get("snippet", "")
                if snippet:
                    info.social_mentions.append(snippet)

        except Exception:
            pass

    def _search_news(self, company_name: str, info: CompanyInfo):
        """Search for news mentions and press releases."""
        try:
            query = f'"{company_name}" news OR press release OR announcement OR featured'
            results = self.search(query, num_results=5)

            for item in results.get("organic", []):
                snippet = item.get("snippet", "")
                title = item.get("title", "")

                if snippet:
                    info.news_mentions.append(f"{title}: {snippet[:100]}")

            # Extract knowledge graph if available
            kg = results.get("knowledgeGraph", {})
            if kg:
                info.knowledge_panel = kg
                attrs = kg.get("attributes", {})
                info.location = attrs.get("Headquarters") or attrs.get("Address") or attrs.get("Service area")

        except Exception:
            pass

    def _search_company_site(self, company_name: str, domain: Optional[str], info: CompanyInfo):
        """Search the company website for services and tools."""
        try:
            if domain:
                # Services and offerings
                query = f'site:{domain} services OR offerings OR "we offer" OR "we specialize"'
                results = self.search(query, num_results=5)

                for item in results.get("organic", []):
                    snippet = item.get("snippet", "")
                    if snippet:
                        info.services.append(snippet)
                        self._extract_tools(snippet, info)

                # About page for company description
                about_query = f'site:{domain} about OR "about us" OR "who we are"'
                about_results = self.search(about_query, num_results=3)

                for item in about_results.get("organic", []):
                    snippet = item.get("snippet", "")
                    if snippet:
                        info.snippets.append(snippet)

        except Exception:
            pass

    def _search_projects(self, company_name: str, domain: Optional[str], info: CompanyInfo):
        """Search for case studies, projects, and client work."""
        try:
            query = f'"{company_name}" case study OR project OR client OR portfolio OR "worked with"'
            if domain:
                query = f'site:{domain} case study OR project OR portfolio OR clients'

            results = self.search(query, num_results=5)

            for item in results.get("organic", []):
                snippet = item.get("snippet", "")
                if snippet:
                    info.recent_projects.append(snippet)
                    self._extract_clients(snippet, info)

        except Exception:
            pass

    def _extract_linkedin_details(self, text: str, info: CompanyInfo):
        """Extract useful details from LinkedIn snippets."""
        # Look for employee counts
        employee_pattern = r'(\d+[\+,]?\d*)\s*(?:employees|staff|team members)'
        matches = re.findall(employee_pattern, text, re.IGNORECASE)
        if matches:
            info.snippets.append(f"Team size: {matches[0]} employees")

        # Look for specialties
        specialty_pattern = r'(?:specializ|focus|expert)\w*\s+(?:in\s+)?([^.]+)'
        matches = re.findall(specialty_pattern, text, re.IGNORECASE)
        for match in matches[:2]:
            if len(match) > 5 and len(match) < 100:
                info.services.append(match.strip())

    def _extract_tools(self, text: str, info: CompanyInfo):
        """Extract tools and platforms from text."""
        known_tools = [
            "ServiceTitan", "HubSpot", "Salesforce", "QuickBooks", "Jobber",
            "Housecall Pro", "Zendesk", "Monday.com", "Asana", "Slack",
            "Mailchimp", "ActiveCampaign", "Podium", "Birdeye", "Workiz",
            "FieldEdge", "Simpro", "Zoho", "Freshworks", "Pipedrive",
            "Shopify", "WooCommerce", "Squarespace", "WordPress", "Webflow",
            "Stripe", "Square", "PayPal", "Calendly", "Acuity",
        ]

        text_lower = text.lower()
        for tool in known_tools:
            if tool.lower() in text_lower and tool not in info.tools:
                info.tools.append(tool)

        # Also look for patterns like "powered by X", "built with X"
        patterns = [
            r'(?:powered by|built with|using|integrated with|runs on)\s+([A-Z][a-zA-Z0-9\s]+)',
        ]
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                clean = match.strip()[:30]
                if len(clean) > 2 and clean not in info.tools:
                    info.tools.append(clean)

    def _extract_clients(self, text: str, info: CompanyInfo):
        """Extract client/project mentions from text."""
        patterns = [
            r'(?:worked with|clients include|partnered with|serving|project for)\s+([A-Z][a-zA-Z0-9\s,&]+)',
            r'(?:case study|portfolio):\s*([A-Z][a-zA-Z0-9\s]+)',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                clean = match.strip()[:50]
                if len(clean) > 3 and clean not in info.clients:
                    info.clients.append(clean)

    def _build_description(self, info: CompanyInfo) -> str:
        """Build a comprehensive description from all gathered info."""
        parts = []

        # Knowledge panel description first
        if info.knowledge_panel and info.knowledge_panel.get("description"):
            parts.append(info.knowledge_panel["description"])

        # LinkedIn info (high value for B2B)
        for li in info.linkedin_info[:2]:
            if li not in parts:
                parts.append(li)

        # General snippets
        for snippet in info.snippets[:2]:
            if snippet not in parts:
                parts.append(snippet)

        return " ".join(parts)

    def test_connection(self) -> bool:
        """
        Test if the API key is valid.

        Returns:
            True if connection successful
        """
        try:
            self.search("test", num_results=1)
            return True
        except requests.HTTPError:
            return False


def extract_artifacts_from_serper(company_info: CompanyInfo) -> str:
    """
    Convert Serper results into a rich description string for artifact extraction.
    Prioritizes the most personalization-worthy content.

    Args:
        company_info: CompanyInfo from Serper lookup

    Returns:
        Combined description text optimized for artifact extraction
    """
    parts = []

    # HIGHEST PRIORITY: Podcast/interview appearances (creates great hooks)
    for podcast in company_info.podcasts[:2]:
        parts.append(f'Featured on podcast: {podcast}')

    # HIGH PRIORITY: Tools/platforms (Tier S - TOOL_PLATFORM)
    for tool in company_info.tools[:3]:
        parts.append(f'Uses {tool}. Powered by {tool} platform.')

    # HIGH PRIORITY: Clients/projects (Tier S - CLIENT_OR_PROJECT)
    for client in company_info.clients[:3]:
        parts.append(f'Worked with {client}. Client project: {client}.')

    # HIGH PRIORITY: Recent projects
    for project in company_info.recent_projects[:2]:
        parts.append(f'Recent work: {project}')

    # MEDIUM PRIORITY: LinkedIn info (great for B2B personalization)
    for li in company_info.linkedin_info[:2]:
        parts.append(li)

    # MEDIUM PRIORITY: News mentions (shows company is active/notable)
    for news in company_info.news_mentions[:2]:
        parts.append(f'In the news: {news}')

    # MEDIUM PRIORITY: Awards/certifications (Tier A - SERVICE_PROGRAM)
    for award in company_info.awards[:2]:
        parts.append(f'{award}.')

    # Knowledge graph info
    if company_info.knowledge_panel:
        kg = company_info.knowledge_panel
        if kg.get("description"):
            parts.append(kg["description"])
        if kg.get("attributes"):
            attrs = kg["attributes"]
            for key, value in attrs.items():
                if key.lower() not in ["website", "phone", "address", "founded"]:
                    parts.append(f"{key}: {value}")

    # Services (good for SERVICE_PROGRAM)
    for service in company_info.services[:2]:
        parts.append(service)

    # Social mentions (shows online presence)
    for social in company_info.social_mentions[:1]:
        parts.append(social)

    # Location (Tier B fallback)
    if company_info.location:
        parts.append(f"Located in {company_info.location}. Serving {company_info.location} area.")

    return " ".join(parts)
