"""
Serper API client for fast company information lookup.

Uses Google Search API to quickly gather company information
without needing to scrape individual websites.
"""
import re
import requests
from dataclasses import dataclass
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
    """Aggregated company information from search results."""
    name: str
    description: str
    snippets: List[str]
    services: List[str]
    tools: List[str]
    clients: List[str]
    awards: List[str]
    location: Optional[str]
    knowledge_panel: Optional[Dict[str, Any]]


class SerperClient:
    """
    Client for Serper.dev Google Search API.

    Much faster than web scraping - returns results in ~500ms.
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

    def search(self, query: str, num_results: int = 5) -> Dict[str, Any]:
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
        Get company information using Google Search.

        Args:
            company_name: Name of the company
            domain: Optional company domain for more specific results

        Returns:
            CompanyInfo with aggregated data
        """
        snippets = []
        services = []
        tools = []
        clients = []
        awards = []
        location = None
        knowledge_graph = {}

        # Search 1: General company info
        query = f'"{company_name}"' if domain else company_name
        if domain:
            query = f'site:{domain} OR "{company_name}"'

        try:
            results = self.search(query, num_results=5)

            # Extract organic results
            organic = results.get("organic", [])
            for item in organic:
                snippet = item.get("snippet", "")
                if snippet:
                    snippets.append(snippet)

            # Extract knowledge graph if available
            knowledge_graph = results.get("knowledgeGraph", {})
            if knowledge_graph:
                kg_attrs = knowledge_graph.get("attributes", {})
                location = kg_attrs.get("Headquarters") or kg_attrs.get("Address") or kg_attrs.get("Service area")
        except Exception:
            pass

        # Search 2: Services/offerings (if we have domain)
        if domain:
            try:
                results2 = self.search(f'site:{domain} services OR offerings OR "we offer" OR "we provide"', num_results=3)
                for item in results2.get("organic", []):
                    snippet = item.get("snippet", "")
                    if snippet and snippet not in snippets:
                        services.append(snippet)
            except Exception:
                pass

        # Extract tools/platforms from snippets
        tool_patterns = [
            r'(?:using|powered by|built with|runs on|integrated with)\s+([A-Z][a-zA-Z0-9\s]+)',
            r'(ServiceTitan|HubSpot|Salesforce|QuickBooks|Jobber|Housecall Pro|Zendesk|Monday\.com)',
        ]
        all_text = " ".join(snippets + services)
        for pattern in tool_patterns:
            matches = re.findall(pattern, all_text, re.IGNORECASE)
            for match in matches:
                if isinstance(match, str) and len(match) > 2 and match not in tools:
                    tools.append(match.strip())

        # Extract client/project mentions
        client_patterns = [
            r'(?:worked with|clients include|partnered with|serving)\s+([A-Z][a-zA-Z0-9\s,&]+)',
            r'(?:projects for|completed for)\s+([A-Z][a-zA-Z0-9\s]+)',
        ]
        for pattern in client_patterns:
            matches = re.findall(pattern, all_text, re.IGNORECASE)
            for match in matches:
                if isinstance(match, str) and len(match) > 3 and match not in clients:
                    clients.append(match.strip()[:50])  # Limit length

        # Extract awards/certifications
        award_patterns = [
            r'([\w\s]+ certified)',
            r'(award[- ]winning)',
            r'(BBB A\+|5-star|top-rated)',
            r'(\d+ years? (?:of )?experience)',
        ]
        for pattern in award_patterns:
            matches = re.findall(pattern, all_text, re.IGNORECASE)
            for match in matches:
                if isinstance(match, str) and match not in awards:
                    awards.append(match.strip())

        # Build description from best sources
        description_parts = []
        kg_description = knowledge_graph.get("description", "")
        if kg_description:
            description_parts.append(kg_description)
        description_parts.extend(snippets[:3])

        return CompanyInfo(
            name=company_name,
            description=" ".join(description_parts),
            snippets=snippets,
            services=services,
            tools=tools[:3],
            clients=clients[:3],
            awards=awards[:3],
            location=location,
            knowledge_panel=knowledge_graph if knowledge_graph else None,
        )

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
    Formats data to maximize artifact detection.

    Args:
        company_info: CompanyInfo from Serper lookup

    Returns:
        Combined description text optimized for artifact extraction
    """
    parts = []

    # Add tools/platforms (Tier S - TOOL_PLATFORM)
    for tool in company_info.tools:
        parts.append(f'Uses {tool}. Powered by {tool}.')

    # Add clients (Tier S - CLIENT_OR_PROJECT)
    for client in company_info.clients:
        parts.append(f'Worked with {client}. Client: {client}.')

    # Add awards/certifications (Tier A - SERVICE_PROGRAM)
    for award in company_info.awards:
        parts.append(f'{award}.')

    # Add knowledge graph info
    if company_info.knowledge_panel:
        kg = company_info.knowledge_panel
        if kg.get("description"):
            parts.append(kg["description"])
        if kg.get("attributes"):
            attrs = kg["attributes"]
            for key, value in attrs.items():
                if key.lower() not in ["website", "phone", "address", "founded"]:
                    parts.append(f"{key}: {value}")

    # Add service snippets (good for SERVICE_PROGRAM)
    for service in company_info.services[:2]:
        parts.append(service)

    # Add general snippets
    for snippet in company_info.snippets[:2]:
        if snippet not in parts:
            parts.append(snippet)

    # Add location (Tier B fallback)
    if company_info.location:
        parts.append(f"Located in {company_info.location}. Serving {company_info.location}.")

    return " ".join(parts)
