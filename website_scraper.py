"""
Website scraper for extracting content from company websites.
"""
import re
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from config import (
    REQUEST_DELAY,
    REQUEST_TIMEOUT,
    SCRAPE_PAGES,
    USER_AGENT,
)


@dataclass
class ScrapedElement:
    """A single scraped element from a webpage."""
    text: str
    page_url: str
    element_type: str  # heading, cta, service, client, footer


class WebsiteScraper:
    """Scrapes company websites for personalization artifacts."""

    def __init__(self):
        self.cache: Dict[str, List[ScrapedElement]] = {}
        self.last_request_time: Dict[str, float] = {}
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        })

    def _get_domain(self, url: str) -> str:
        """Extract domain from URL."""
        parsed = urlparse(url)
        return parsed.netloc.lower().replace("www.", "")

    def _rate_limit(self, domain: str) -> None:
        """Enforce rate limiting per domain."""
        if domain in self.last_request_time:
            elapsed = time.time() - self.last_request_time[domain]
            if elapsed < REQUEST_DELAY:
                time.sleep(REQUEST_DELAY - elapsed)
        self.last_request_time[domain] = time.time()

    def _fetch_page(self, url: str) -> Optional[str]:
        """
        Fetch a single page and return its HTML content.

        Args:
            url: URL to fetch

        Returns:
            HTML content or None if fetch failed
        """
        domain = self._get_domain(url)
        self._rate_limit(domain)

        try:
            response = self.session.get(
                url,
                timeout=REQUEST_TIMEOUT,
                allow_redirects=True,
            )
            response.raise_for_status()

            # Only process HTML content
            content_type = response.headers.get("Content-Type", "")
            if "text/html" not in content_type.lower():
                return None

            return response.text

        except requests.RequestException:
            return None

    def _extract_headings(self, soup: BeautifulSoup, page_url: str) -> List[ScrapedElement]:
        """Extract H1, H2, H3 headings from page."""
        elements = []

        for tag in ["h1", "h2", "h3"]:
            for heading in soup.find_all(tag):
                text = self._clean_text(heading.get_text())
                if text and len(text) > 3:
                    elements.append(ScrapedElement(
                        text=text,
                        page_url=page_url,
                        element_type="heading",
                    ))

        return elements

    def _extract_ctas(self, soup: BeautifulSoup, page_url: str) -> List[ScrapedElement]:
        """Extract button and CTA text from page."""
        elements = []

        # Buttons
        for button in soup.find_all(["button", "a"]):
            # Check for CTA-like classes
            classes = " ".join(button.get("class", []))
            is_cta = any(kw in classes.lower() for kw in [
                "btn", "button", "cta", "action", "primary", "hero"
            ])

            # Check for CTA-like attributes
            if button.get("role") == "button" or button.get("data-action"):
                is_cta = True

            text = self._clean_text(button.get_text())
            if text and len(text) > 3 and (is_cta or button.name == "button"):
                elements.append(ScrapedElement(
                    text=text,
                    page_url=page_url,
                    element_type="cta",
                ))

        return elements

    def _extract_services(self, soup: BeautifulSoup, page_url: str) -> List[ScrapedElement]:
        """Extract service/offering names from page."""
        elements = []

        # Look for service-related sections
        service_sections = soup.find_all(
            ["section", "div", "ul"],
            class_=re.compile(r"service|offering|solution|what-we-do", re.I)
        )

        for section in service_sections:
            # Get list items
            for li in section.find_all("li"):
                text = self._clean_text(li.get_text())
                if text and 3 < len(text) < 100:
                    elements.append(ScrapedElement(
                        text=text,
                        page_url=page_url,
                        element_type="service",
                    ))

            # Get headings within service section
            for heading in section.find_all(["h3", "h4", "h5"]):
                text = self._clean_text(heading.get_text())
                if text and len(text) > 3:
                    elements.append(ScrapedElement(
                        text=text,
                        page_url=page_url,
                        element_type="service",
                    ))

        return elements

    def _extract_clients(self, soup: BeautifulSoup, page_url: str) -> List[ScrapedElement]:
        """Extract client/project names from page."""
        elements = []

        # Look for client-related sections
        client_sections = soup.find_all(
            ["section", "div", "ul"],
            class_=re.compile(r"client|partner|portfolio|work|project|case|testimonial|logo", re.I)
        )

        for section in client_sections:
            # Get image alt text (often client logos)
            for img in section.find_all("img"):
                alt = img.get("alt", "")
                if alt and len(alt) > 2 and "logo" not in alt.lower():
                    elements.append(ScrapedElement(
                        text=self._clean_text(alt),
                        page_url=page_url,
                        element_type="client",
                    ))

            # Get headings (often project/case study titles)
            for heading in section.find_all(["h2", "h3", "h4"]):
                text = self._clean_text(heading.get_text())
                if text and len(text) > 3:
                    elements.append(ScrapedElement(
                        text=text,
                        page_url=page_url,
                        element_type="client",
                    ))

            # Get strong/bold text (often client names)
            for strong in section.find_all(["strong", "b"]):
                text = self._clean_text(strong.get_text())
                if text and 2 < len(text) < 50:
                    elements.append(ScrapedElement(
                        text=text,
                        page_url=page_url,
                        element_type="client",
                    ))

        return elements

    def _extract_locations(self, soup: BeautifulSoup, page_url: str) -> List[ScrapedElement]:
        """Extract location/service area mentions from page."""
        elements = []

        # Look for footer and contact sections
        location_sections = soup.find_all(
            ["footer", "section", "div"],
            class_=re.compile(r"footer|contact|location|address|area|region", re.I)
        )

        # Also check for address tags
        location_sections.extend(soup.find_all("address"))

        for section in location_sections:
            text = self._clean_text(section.get_text())

            # Look for city/state patterns
            location_patterns = [
                r"serving\s+([A-Z][a-zA-Z\s,]+)",
                r"located\s+in\s+([A-Z][a-zA-Z\s,]+)",
                r"service\s+area[:\s]+([A-Z][a-zA-Z\s,]+)",
                r"([A-Z][a-z]+,\s*[A-Z]{2})",  # City, ST format
            ]

            for pattern in location_patterns:
                matches = re.findall(pattern, text)
                for match in matches:
                    cleaned = self._clean_text(match)
                    if cleaned and 3 < len(cleaned) < 50:
                        elements.append(ScrapedElement(
                            text=cleaned,
                            page_url=page_url,
                            element_type="location",
                        ))

        return elements

    def _extract_tools(self, soup: BeautifulSoup, page_url: str) -> List[ScrapedElement]:
        """Extract tool/platform mentions from page."""
        elements = []

        # Get full page text
        page_text = soup.get_text().lower()

        # Known tools to look for
        tools = [
            "ServiceTitan", "Service Titan",
            "Housecall Pro", "HousecallPro",
            "Jobber",
            "Calendly",
            "HubSpot",
            "Salesforce",
            "QuickBooks",
            "FreshBooks",
            "Zoho",
            "Monday.com",
            "Asana",
            "Slack",
            "Zendesk",
            "Intercom",
            "Drift",
            "Mailchimp",
            "Constant Contact",
            "ActiveCampaign",
            "Podium",
            "Birdeye",
            "Workiz",
            "FieldEdge",
            "SuccessWare",
            "Simpro",
            "Commusoft",
        ]

        for tool in tools:
            if tool.lower() in page_text:
                elements.append(ScrapedElement(
                    text=tool,
                    page_url=page_url,
                    element_type="tool",
                ))

        return elements

    def _clean_text(self, text: str) -> str:
        """Clean and normalize text."""
        import html

        if not text:
            return ""

        # Decode HTML entities
        text = html.unescape(text)

        # Remove extra whitespace
        text = " ".join(text.split())

        # Remove common artifacts
        text = text.strip("•·-–—|/\\")
        text = text.strip()

        return text

    def scrape_website(self, base_url: str) -> List[ScrapedElement]:
        """
        Scrape a website and extract all relevant elements.

        Args:
            base_url: Base URL of the website

        Returns:
            List of scraped elements
        """
        domain = self._get_domain(base_url)

        # Check cache
        if domain in self.cache:
            return self.cache[domain]

        all_elements: List[ScrapedElement] = []

        # Normalize base URL
        if not base_url.startswith(("http://", "https://")):
            base_url = "https://" + base_url

        # Remove trailing slash for consistency
        base_url = base_url.rstrip("/")

        # Scrape each page
        for page_path in SCRAPE_PAGES:
            page_url = base_url + page_path if page_path != "/" else base_url

            html = self._fetch_page(page_url)
            if not html:
                continue

            soup = BeautifulSoup(html, "lxml")

            # Extract different element types
            all_elements.extend(self._extract_headings(soup, page_url))
            all_elements.extend(self._extract_ctas(soup, page_url))
            all_elements.extend(self._extract_services(soup, page_url))
            all_elements.extend(self._extract_clients(soup, page_url))
            all_elements.extend(self._extract_locations(soup, page_url))
            all_elements.extend(self._extract_tools(soup, page_url))

        # Deduplicate by text (keep first occurrence)
        seen_texts = set()
        unique_elements = []
        for elem in all_elements:
            text_lower = elem.text.lower()
            if text_lower not in seen_texts:
                seen_texts.add(text_lower)
                unique_elements.append(elem)

        # Cache results
        self.cache[domain] = unique_elements

        return unique_elements
