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
    # HIGH-VALUE personalization data
    google_rating: Optional[str] = None  # "4.8 stars"
    review_count: Optional[str] = None   # "150+ reviews"
    years_in_business: Optional[str] = None  # "since 1985" or "25 years"
    bbb_rating: Optional[str] = None     # "A+ BBB"
    is_hiring: bool = False              # Growth signal
    hiring_roles: List[str] = field(default_factory=list)
    certifications: List[str] = field(default_factory=list)
    team_size: Optional[str] = None      # "15 employees"
    jobs_completed: Optional[str] = None  # "10,000+ jobs completed"
    customers_served: Optional[str] = None  # "5,000+ happy customers"
    service_area_size: Optional[str] = None  # "Serving 15 cities"
    response_time: Optional[str] = None  # "Same-day service"
    owner_name: Optional[str] = None  # Owner/founder name
    founding_story: Optional[str] = None  # "Family-owned since..."
    community_involvement: List[str] = field(default_factory=list)
    media_features: List[str] = field(default_factory=list)
    special_achievements: List[str] = field(default_factory=list)
    niche_specialty: Optional[str] = None
    fleet_size: Optional[str] = None
    warranty_guarantee: Optional[str] = None
    # LEGAL FIRM specific fields
    case_verdicts: List[str] = field(default_factory=list)  # "$2.3M verdict"
    avvo_rating: Optional[str] = None  # "10.0 Superb"
    super_lawyers: Optional[str] = None  # "Super Lawyers 2024"
    best_lawyers: Optional[str] = None  # "Best Lawyers in America"
    martindale_rating: Optional[str] = None  # "AV Preeminent"
    practice_areas: List[str] = field(default_factory=list)
    bar_memberships: List[str] = field(default_factory=list)
    notable_cases: List[str] = field(default_factory=list)
    attorney_count: Optional[str] = None  # "12 attorneys"
    # RESTORATION specific fields
    iicrc_certs: List[str] = field(default_factory=list)  # WRT, ASD, FSRT
    insurance_partners: List[str] = field(default_factory=list)  # State Farm preferred
    response_guarantee: Optional[str] = None  # "45-minute arrival"
    claims_handled: Optional[str] = None  # "2,000+ claims annually"
    # SD-06: Confidence scoring fields
    domain_match_count: int = 0
    total_results: int = 0
    is_low_confidence: bool = False
    # SD-05: Industry mismatch detection
    industry_mismatch_detected: bool = False
    mismatched_industry: Optional[str] = None


# Known tools/platforms to look for (Tier S artifacts)
KNOWN_TOOLS = [
    # Legal-specific software
    "Clio", "MyCase", "PracticePanther", "Smokeball", "Filevine",
    "Lawmatics", "CASEpeer", "Litify", "Needles", "TrialWorks",
    "AbacusLaw", "PCLaw", "CosmoLex", "Legal Files", "Rocket Matter",
    # Restoration-specific software
    "Xactimate", "DASH", "Next Gear", "CoreLogic", "Encircle",
    "JobNimbus", "RestorationManager", "iRestore", "PSA",
    # General business tools
    "HubSpot", "Salesforce", "QuickBooks", "Zendesk", "Monday.com",
    "Mailchimp", "ActiveCampaign", "Podium", "Birdeye",
    "Calendly", "Acuity", "Intercom", "Drift",
]

# SD-05: Keywords that indicate wrong industry (for legal/restoration leads)
WRONG_INDUSTRY_KEYWORDS = [
    # Different industries that might share company names
    "lawn care", "lawn service", "landscaping", "mowing",
    "solar panel", "solar installation", "solar energy",
    "dental", "dentist", "orthodontic",
    "veterinary", "vet clinic", "animal hospital",
    "restaurant", "catering", "food service",
    "car dealership", "auto sales", "used cars",
    "hair salon", "beauty salon", "spa services",
    "hvac", "air conditioning", "heating and cooling",
    "plumbing", "plumber", "drain cleaning",
    "roofing", "roofer", "roof repair",
    "pest control", "exterminator",
]


class SerperClient:
    """
    Deep research Serper.dev Google Search API client.

    Performs comprehensive research on LEGAL FIRMS and RESTORATION COMPANIES
    with multiple targeted searches to find the best personalization hooks.
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
        location: Optional[str] = None,
        industry: Optional[str] = None
    ) -> CompanyInfo:
        """
        Get company information with DEEP RESEARCH for LEGAL and RESTORATION firms.

        Performs 5-6 targeted searches to find the best personalization hooks:
        - Main company search
        - Google reviews/testimonials
        - Awards and news
        - Legal-specific: Avvo, Super Lawyers, case verdicts
        - Restoration-specific: IICRC, insurance partnerships

        Args:
            company_name: Name of the company
            domain: Optional company domain for disambiguation (highly recommended)
            location: Optional company location for disambiguation
            industry: Optional industry hint ("legal", "restoration", or auto-detect)

        Returns:
            CompanyInfo with aggregated data
        """
        info = CompanyInfo(name=company_name, description="")
        clean_name = company_name.strip()

        # Clean domain for searches
        clean_domain = ""
        if domain:
            clean_domain = domain.replace("https://", "").replace("http://", "").replace("www.", "")

        # Auto-detect industry from company name if not provided
        detected_industry = industry
        if not detected_industry:
            name_lower = clean_name.lower()
            if any(kw in name_lower for kw in ["law", "legal", "attorney", "lawyer", "esq", "llp", "pllc", "firm"]):
                detected_industry = "legal"
            elif any(kw in name_lower for kw in ["restoration", "restore", "water damage", "fire damage", "mold", "cleanup", "disaster", "emergency"]):
                detected_industry = "restoration"

        try:
            # SEARCH 1: Main company search with disambiguation
            query1 = self._build_disambiguated_query(clean_name, domain, location)
            logger.info(f"[DEEP RESEARCH] Query 1 - Main: {query1}")
            results1 = self.search(query1, num_results=10)
            self._process_search_results(results1, info)

            # SEARCH 2: Google reviews (S-TIER data)
            query2 = f'"{clean_name}" "google reviews" OR "reviews" OR "stars"'
            if location:
                query2 += f' {location.split(",")[0]}'
            logger.info(f"[DEEP RESEARCH] Query 2 - Reviews: {query2}")
            try:
                results2 = self.search(query2, num_results=8)
                self._process_search_results(results2, info)
            except Exception:
                pass

            # SEARCH 3: Awards, recognition, news (S-TIER data)
            query3 = f'"{clean_name}" "award" OR "best of" OR "top" OR "winner" OR "featured"'
            if location:
                query3 += f' {location.split(",")[0]}'
            logger.info(f"[DEEP RESEARCH] Query 3 - Awards: {query3}")
            try:
                results3 = self.search(query3, num_results=5)
                self._process_search_results(results3, info)
            except Exception:
                pass

            # ===== LEGAL FIRM DEEP RESEARCH =====
            if detected_industry == "legal" or not detected_industry:
                # SEARCH 4: Avvo ratings (S-TIER for attorneys)
                query4 = f'"{clean_name}" site:avvo.com OR "avvo" OR "avvo rating"'
                logger.info(f"[DEEP RESEARCH] Query 4 - Avvo: {query4}")
                try:
                    results4 = self.search(query4, num_results=5)
                    self._process_search_results(results4, info)
                except Exception:
                    pass

                # SEARCH 5: Super Lawyers / Best Lawyers / Martindale (S-TIER)
                query5 = f'"{clean_name}" "super lawyers" OR "best lawyers" OR "martindale" OR "AV preeminent"'
                logger.info(f"[DEEP RESEARCH] Query 5 - Legal Awards: {query5}")
                try:
                    results5 = self.search(query5, num_results=5)
                    self._process_search_results(results5, info)
                except Exception:
                    pass

                # SEARCH 6: Case verdicts and settlements (MEGA S-TIER)
                query6 = f'"{clean_name}" "verdict" OR "settlement" OR "recovered" OR "million" OR "jury"'
                if location:
                    query6 += f' {location.split(",")[0]}'
                logger.info(f"[DEEP RESEARCH] Query 6 - Verdicts: {query6}")
                try:
                    results6 = self.search(query6, num_results=5)
                    self._process_search_results(results6, info)
                except Exception:
                    pass

            # ===== RESTORATION COMPANY DEEP RESEARCH =====
            if detected_industry == "restoration" or not detected_industry:
                # SEARCH 7: IICRC certifications (S-TIER for restoration)
                query7 = f'"{clean_name}" "IICRC" OR "certified" OR "WRT" OR "ASD" OR "FSRT"'
                logger.info(f"[DEEP RESEARCH] Query 7 - IICRC: {query7}")
                try:
                    results7 = self.search(query7, num_results=5)
                    self._process_search_results(results7, info)
                except Exception:
                    pass

                # SEARCH 8: Insurance partnerships (S-TIER - shows trust)
                query8 = f'"{clean_name}" "preferred vendor" OR "insurance approved" OR "State Farm" OR "Allstate" OR "USAA"'
                logger.info(f"[DEEP RESEARCH] Query 8 - Insurance: {query8}")
                try:
                    results8 = self.search(query8, num_results=5)
                    self._process_search_results(results8, info)
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

            # Extract ALL valuable data from results
            self._extract_tools(snippet, info)
            self._extract_clients(snippet, info)
            self._extract_reviews_and_ratings(snippet, info)
            self._extract_years_in_business(snippet, info)
            self._extract_certifications(snippet, info)
            self._extract_hiring_signals(snippet, info)
            self._extract_team_size(snippet, info)
            # Additional high-impact extractions
            self._extract_volume_metrics(snippet, info)
            self._extract_awards_recognition(snippet, title, info)
            self._extract_community_media(snippet, title, info)
            self._extract_owner_info(snippet, info)
            self._extract_service_differentiators(snippet, info)
            # Legal and Restoration specific extractions
            self._extract_legal_data(snippet, title, info)
            self._extract_restoration_data(snippet, info)

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

    def _extract_reviews_and_ratings(self, text: str, info: CompanyInfo):
        """Extract Google reviews, ratings, and social proof."""
        text_lower = text.lower()

        # Star ratings (4.8 stars, 4.9/5, etc.)
        rating_patterns = [
            r'(\d\.\d)\s*(?:star|/5|out of 5)',
            r'(\d\.\d)-star',
            r'rating[:\s]+(\d\.\d)',
        ]
        for pattern in rating_patterns:
            match = re.search(pattern, text_lower)
            if match and not info.google_rating:
                info.google_rating = f"{match.group(1)} stars"
                break

        # Review counts (150 reviews, 200+ reviews, etc.)
        review_patterns = [
            r'(\d{2,})\+?\s*(?:reviews|google reviews|customer reviews)',
            r'(\d{2,})\+?\s*(?:5-star|five star)\s*reviews',
        ]
        for pattern in review_patterns:
            match = re.search(pattern, text_lower)
            if match and not info.review_count:
                info.review_count = f"{match.group(1)}+ reviews"
                break

    def _extract_years_in_business(self, text: str, info: CompanyInfo):
        """Extract years in business, founding date."""
        text_lower = text.lower()

        # "Since 1985", "established 1990", "founded in 2005"
        year_patterns = [
            r'(?:since|established|founded|serving since|in business since)\s*(\d{4})',
            r'(\d{4})\s*-\s*present',
            r'for\s+(?:over\s+)?(\d{1,2})\+?\s*years',
        ]
        for pattern in year_patterns:
            match = re.search(pattern, text_lower)
            if match and not info.years_in_business:
                val = match.group(1)
                if len(val) == 4:  # It's a year
                    info.years_in_business = f"since {val}"
                else:  # It's number of years
                    info.years_in_business = f"{val}+ years"
                break

    def _extract_certifications(self, text: str, info: CompanyInfo):
        """Extract brand certifications and partnerships."""
        # Common HVAC/Plumbing brand partnerships
        brands = [
            "Rheem", "Carrier", "Trane", "Lennox", "Goodman", "American Standard",
            "Mitsubishi", "Daikin", "Fujitsu", "Bryant", "Ruud", "York",
            "Kohler", "Moen", "Delta", "Rinnai", "Navien", "Bradford White",
        ]

        for brand in brands:
            if brand.lower() in text.lower():
                cert = f"{brand} dealer/certified"
                if cert not in info.certifications:
                    info.certifications.append(cert)

        # Other certifications
        cert_patterns = [
            r'(licensed|bonded|insured)',
            r'(BBB\s*A\+?|A\+?\s*BBB|Better Business Bureau)',
            r'(NATE certified|EPA certified|certified technicians)',
        ]
        for pattern in cert_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                if match and match not in info.certifications:
                    info.certifications.append(match)

    def _extract_hiring_signals(self, text: str, info: CompanyInfo):
        """Extract hiring/growth signals."""
        text_lower = text.lower()

        hiring_keywords = [
            r'(hiring|now hiring|we\'re hiring|join our team)',
            r'(career|careers|job opening|job posting)',
            r'(looking for|seeking)\s+(?:a\s+)?(\w+\s*\w*)',
        ]

        for pattern in hiring_keywords:
            if re.search(pattern, text_lower):
                info.is_hiring = True
                break

        # Specific roles
        role_patterns = [
            r'hiring\s+(?:a\s+)?(\w+\s*(?:technician|plumber|hvac|installer|manager))',
            r'looking for\s+(?:a\s+)?(\w+\s*(?:technician|plumber|hvac|installer))',
        ]
        for pattern in role_patterns:
            matches = re.findall(pattern, text_lower)
            for match in matches:
                if match and match not in info.hiring_roles:
                    info.hiring_roles.append(match)

    def _extract_team_size(self, text: str, info: CompanyInfo):
        """Extract team/company size."""
        patterns = [
            r'(\d{1,3})\+?\s*(?:employees|team members|technicians|staff)',
            r'team of\s+(\d{1,3})',
            r'(\d{1,3})\s*(?:service )?(?:trucks|vans|vehicles)',
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match and not info.team_size:
                info.team_size = match.group(0)
                break

        # Also extract fleet size separately
        fleet_patterns = [
            r'(\d{1,3})\+?\s*(?:service\s+)?(?:trucks|vans|vehicles|fleet)',
            r'fleet of\s+(\d{1,3})',
        ]
        for pattern in fleet_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match and not info.fleet_size:
                info.fleet_size = match.group(0)
                break

    def _extract_volume_metrics(self, text: str, info: CompanyInfo):
        """Extract impressive volume metrics - jobs completed, customers served."""
        text_lower = text.lower()

        # Jobs/projects completed
        job_patterns = [
            r'(\d{1,3}[,\d]*)\+?\s*(?:jobs?|projects?|service calls?)\s*(?:completed|done|finished)',
            r'completed\s+(?:over\s+)?(\d{1,3}[,\d]*)\+?\s*(?:jobs?|projects?)',
            r'(\d{1,3}[,\d]*)\+?\s*(?:installations?|repairs?)',
        ]
        for pattern in job_patterns:
            match = re.search(pattern, text_lower)
            if match and not info.jobs_completed:
                num = match.group(1).replace(',', '')
                if int(num) >= 100:  # Only impressive numbers
                    info.jobs_completed = f"{match.group(1)}+ jobs completed"
                break

        # Customers served
        customer_patterns = [
            r'(\d{1,3}[,\d]*)\+?\s*(?:happy|satisfied)?\s*(?:customers?|clients?|homeowners?)',
            r'served\s+(?:over\s+)?(\d{1,3}[,\d]*)\+?\s*(?:customers?|families?)',
            r'trusted by\s+(\d{1,3}[,\d]*)\+?',
        ]
        for pattern in customer_patterns:
            match = re.search(pattern, text_lower)
            if match and not info.customers_served:
                num = match.group(1).replace(',', '')
                if int(num) >= 100:  # Only impressive numbers
                    info.customers_served = f"{match.group(1)}+ customers served"
                break

        # Service area size
        area_patterns = [
            r'serving\s+(\d{1,2})\+?\s*(?:cities|counties|areas|communities)',
            r'(\d{1,2})\+?\s*(?:locations?|branches?|offices?)',
        ]
        for pattern in area_patterns:
            match = re.search(pattern, text_lower)
            if match and not info.service_area_size:
                info.service_area_size = match.group(0)
                break

    def _extract_awards_recognition(self, text: str, title: str, info: CompanyInfo):
        """Extract awards, recognition, and 'best of' mentions."""
        combined = f"{title} {text}".lower()

        # Best of / Top X awards
        award_patterns = [
            r'(best (?:of|in) [\w\s]+\d{4})',
            r'(top \d+ [\w\s]+)',
            r'(#\d+ [\w\s]+)',
            r'(\d+(?:st|nd|rd|th) best [\w\s]+)',
            r'(award[- ]?winning)',
            r'(winner[:\s]+[\w\s]+award)',
            r'(angie\'?s? list[:\s]+[\w]+)',
            r'(super service award)',
            r'(home advisor[:\s]+[\w\s]+)',
            r'(elite service)',
        ]

        for pattern in award_patterns:
            matches = re.findall(pattern, combined)
            for match in matches:
                clean = match.strip()[:60]
                if clean and clean not in [a.lower() for a in info.awards]:
                    info.awards.append(clean.title())

    def _extract_community_media(self, text: str, title: str, info: CompanyInfo):
        """Extract community involvement and media features."""
        combined = f"{title} {text}".lower()

        # Community involvement
        community_patterns = [
            r'(sponsor(?:s|ed|ing)?\s+[\w\s]+(?:team|league|event|charity))',
            r'(supports?\s+[\w\s]+(?:foundation|charity|nonprofit))',
            r'(donates?\s+to\s+[\w\s]+)',
            r'(community\s+(?:partner|supporter|sponsor))',
            r'(proud\s+sponsor)',
            r'(gives?\s+back\s+to)',
        ]
        for pattern in community_patterns:
            matches = re.findall(pattern, combined)
            for match in matches:
                clean = match.strip()[:60]
                if clean and clean not in info.community_involvement:
                    info.community_involvement.append(clean.title())

        # Media features
        media_patterns = [
            r'(featured (?:on|in)\s+[\w\s]+(?:tv|news|radio|channel|magazine))',
            r'(as seen on\s+[\w\s]+)',
            r'(interviewed (?:on|by)\s+[\w\s]+)',
            r'(appeared on\s+[\w\s]+)',
        ]
        for pattern in media_patterns:
            matches = re.findall(pattern, combined)
            for match in matches:
                clean = match.strip()[:60]
                if clean and clean not in info.media_features:
                    info.media_features.append(clean.title())

    def _extract_owner_info(self, text: str, info: CompanyInfo):
        """Extract owner/founder information if impressive."""
        # Owner name patterns
        owner_patterns = [
            r'(?:owner|founder|ceo|president)[:\s]+([A-Z][a-z]+ [A-Z][a-z]+)',
            r'([A-Z][a-z]+ [A-Z][a-z]+),?\s+(?:owner|founder|ceo)',
            r'founded by\s+([A-Z][a-z]+ [A-Z][a-z]+)',
        ]
        for pattern in owner_patterns:
            match = re.search(pattern, text)
            if match and not info.owner_name:
                info.owner_name = match.group(1)
                break

        # Family-owned story
        family_patterns = [
            r'(family[- ]owned(?:\s+(?:and|&)\s+operated)?(?:\s+(?:since|for)\s+[\w\s]+)?)',
            r'(\d+(?:rd|th|nd|st)?\s+generation)',
            r'(father[- ](?:and[- ])?son)',
            r'(husband[- ](?:and[- ])?wife)',
        ]
        for pattern in family_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match and not info.founding_story:
                info.founding_story = match.group(1)
                break

    def _extract_service_differentiators(self, text: str, info: CompanyInfo):
        """Extract unique selling points and differentiators."""
        text_lower = text.lower()

        # Response time / availability
        response_patterns = [
            r'(same[- ]day\s+(?:service|response|appointments?))',
            r'(24[/\s]?7\s+(?:service|emergency|availability))',
            r'(\d+[- ]?(?:hour|minute)\s+(?:response|arrival))',
            r'(emergency\s+(?:service|response)\s+available)',
        ]
        for pattern in response_patterns:
            match = re.search(pattern, text_lower)
            if match and not info.response_time:
                info.response_time = match.group(1)
                break

        # Warranties/guarantees
        warranty_patterns = [
            r'(lifetime\s+(?:warranty|guarantee))',
            r'(\d+[- ]?year\s+(?:warranty|guarantee))',
            r'(100%\s+(?:satisfaction|money[- ]back)\s+guarantee)',
            r'(satisfaction\s+guaranteed)',
        ]
        for pattern in warranty_patterns:
            match = re.search(pattern, text_lower)
            if match and not info.warranty_guarantee:
                info.warranty_guarantee = match.group(1)
                break

        # Niche specialty (what they're KNOWN for)
        specialty_patterns = [
            r'(?:speciali[sz](?:e|es|ing)\s+in|known for|experts?\s+in)\s+([^.]{10,50})',
            r'#1\s+(?:in|for)\s+([^.]{10,40})',
            r'(?:the|your)\s+([^.]{5,30})\s+(?:specialists?|experts?|professionals?)',
        ]
        for pattern in specialty_patterns:
            match = re.search(pattern, text_lower)
            if match and not info.niche_specialty:
                specialty = match.group(1).strip()
                if len(specialty) > 5:
                    info.niche_specialty = specialty
                break

    def _extract_legal_data(self, text: str, title: str, info: CompanyInfo):
        """Extract legal firm specific data - verdicts, ratings, awards."""
        combined = f"{title} {text}"
        combined_lower = combined.lower()

        # Case verdicts and settlements (S-TIER for legal)
        verdict_patterns = [
            r'\$(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*(?:million|m)\s*(?:verdict|settlement|recovery|judgment)',
            r'(?:verdict|settlement|recovery|judgment)\s*(?:of|for)?\s*\$(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*(?:million|m)',
            r'\$(\d{1,3}(?:,\d{3})*)\s*(?:verdict|settlement|recovery)',
            r'(\d{1,3}(?:\.\d+)?)\s*million\s*(?:dollar)?\s*(?:verdict|settlement|recovery)',
            r'recovered\s*\$(\d{1,3}(?:,\d{3})*(?:\.\d+)?(?:\s*(?:million|m))?)',
        ]
        for pattern in verdict_patterns:
            matches = re.findall(pattern, combined_lower)
            for match in matches:
                # Format the verdict amount
                if 'million' in combined_lower or 'm' in match.lower():
                    verdict = f"${match}M verdict/settlement"
                else:
                    verdict = f"${match} verdict/settlement"
                if verdict not in info.case_verdicts and len(info.case_verdicts) < 3:
                    info.case_verdicts.append(verdict)

        # Avvo rating (S-TIER)
        avvo_patterns = [
            r'avvo\s*(?:rating)?[:\s]*(\d{1,2}(?:\.\d)?)\s*(?:/10|superb|excellent)?',
            r'(\d{1,2}(?:\.\d)?)\s*(?:/10)?\s*(?:on\s+)?avvo',
            r'avvo\s*superb\s*(?:rating)?',
            r'avvo\s*10\.0',
        ]
        for pattern in avvo_patterns:
            match = re.search(pattern, combined_lower)
            if match and not info.avvo_rating:
                if 'superb' in combined_lower or '10' in match.group(0):
                    info.avvo_rating = "10.0 Superb on Avvo"
                else:
                    rating = match.group(1) if match.lastindex else "10.0"
                    info.avvo_rating = f"{rating} on Avvo"
                break

        # Super Lawyers (S-TIER)
        if 'super lawyer' in combined_lower:
            year_match = re.search(r'super lawyer[s]?\s*(\d{4})', combined_lower)
            if year_match:
                info.super_lawyers = f"Super Lawyers {year_match.group(1)}"
            else:
                info.super_lawyers = "Super Lawyers"

        # Best Lawyers in America (S-TIER)
        if 'best lawyer' in combined_lower:
            year_match = re.search(r'best lawyer[s]?\s*(?:in america)?\s*(\d{4})', combined_lower)
            if year_match:
                info.best_lawyers = f"Best Lawyers {year_match.group(1)}"
            else:
                info.best_lawyers = "Best Lawyers in America"

        # Martindale-Hubbell rating (S-TIER)
        martindale_patterns = [
            r'(av\s*preeminent)',
            r'martindale[- ]hubbell\s*(av|bv)',
            r'(preeminent)\s*rating',
        ]
        for pattern in martindale_patterns:
            match = re.search(pattern, combined_lower)
            if match and not info.martindale_rating:
                info.martindale_rating = "AV Preeminent - Martindale-Hubbell"
                break

        # Attorney/lawyer count
        attorney_patterns = [
            r'(\d{1,3})\s*(?:attorneys?|lawyers?|partners?|associates?)',
            r'team of\s*(\d{1,3})\s*(?:attorneys?|lawyers?)',
            r'firm of\s*(\d{1,3})',
        ]
        for pattern in attorney_patterns:
            match = re.search(pattern, combined_lower)
            if match and not info.attorney_count:
                count = match.group(1)
                if int(count) > 1:
                    info.attorney_count = f"{count} attorneys"
                break

        # Practice areas (for specialization hooks)
        practice_patterns = [
            r'(?:practice areas?|specializ\w+\s+in|focus\w*\s+on)[:\s]+([^.]{10,60})',
            r'(personal injury|family law|criminal defense|estate planning|bankruptcy|immigration|employment law|medical malpractice|workers.?\s*comp)',
        ]
        for pattern in practice_patterns:
            matches = re.findall(pattern, combined_lower)
            for match in matches:
                clean = match.strip().title()[:40]
                if clean and clean not in info.practice_areas and len(info.practice_areas) < 3:
                    info.practice_areas.append(clean)

    def _extract_restoration_data(self, text: str, info: CompanyInfo):
        """Extract restoration company specific data - certs, insurance, response."""
        text_lower = text.lower()

        # IICRC Certifications (S-TIER for restoration)
        iicrc_certs = {
            'wrt': 'WRT (Water Restoration)',
            'asd': 'ASD (Applied Structural Drying)',
            'fsrt': 'FSRT (Fire & Smoke Restoration)',
            'amrt': 'AMRT (Applied Microbial Remediation)',
            'cct': 'CCT (Carpet Cleaning)',
            'ocr': 'OCR (Odor Control Restoration)',
            'rrt': 'RRT (Rug Restoration)',
        }
        for cert_code, cert_name in iicrc_certs.items():
            if cert_code in text_lower or cert_name.lower() in text_lower:
                if cert_name not in info.iicrc_certs:
                    info.iicrc_certs.append(cert_name)

        if 'iicrc certified' in text_lower or 'iicrc' in text_lower:
            if 'IICRC Certified' not in info.iicrc_certs and not info.iicrc_certs:
                info.iicrc_certs.append('IICRC Certified')

        # Insurance company partnerships (S-TIER)
        insurance_companies = [
            'State Farm', 'Allstate', 'USAA', 'Liberty Mutual', 'Farmers',
            'Nationwide', 'Progressive', 'Geico', 'Travelers', 'American Family',
            'Erie Insurance', 'Auto-Owners', 'Chubb', 'Hartford', 'Amica',
        ]
        for company in insurance_companies:
            if company.lower() in text_lower:
                partner = f"{company} preferred vendor"
                if partner not in info.insurance_partners:
                    info.insurance_partners.append(partner)

        # Preferred vendor / approved contractor status
        preferred_patterns = [
            r'(preferred\s+(?:vendor|contractor|provider))',
            r'(approved\s+(?:vendor|contractor))',
            r'(insurance\s+(?:approved|preferred))',
        ]
        for pattern in preferred_patterns:
            match = re.search(pattern, text_lower)
            if match:
                status = match.group(1).title()
                if status not in info.insurance_partners:
                    info.insurance_partners.append(status)

        # Response time guarantee (S-TIER)
        response_patterns = [
            r'(\d{1,2})[- ]?(?:minute|min)\s*(?:response|arrival|guarantee)',
            r'respond\s*(?:within)?\s*(\d{1,2})\s*(?:minutes?|mins?)',
            r'on[- ]?site\s*(?:within)?\s*(\d{1,2})\s*(?:minutes?|hours?)',
            r'(60|45|30)\s*(?:minute|min)\s*(?:response|arrival)',
        ]
        for pattern in response_patterns:
            match = re.search(pattern, text_lower)
            if match and not info.response_guarantee:
                mins = match.group(1)
                info.response_guarantee = f"{mins}-minute response guarantee"
                break

        # Claims/jobs handled annually
        claims_patterns = [
            r'(\d{1,3}[,\d]*)\+?\s*(?:claims?|jobs?|projects?)\s*(?:per year|annually|each year)',
            r'handle[sd]?\s*(?:over\s+)?(\d{1,3}[,\d]*)\+?\s*(?:claims?|projects?)',
        ]
        for pattern in claims_patterns:
            match = re.search(pattern, text_lower)
            if match and not info.claims_handled:
                count = match.group(1).replace(',', '')
                if int(count) >= 100:
                    info.claims_handled = f"{match.group(1)}+ claims handled annually"
                break

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
    Prioritizes the most EGO-STROKING, CURIOSITY-INDUCING content.
    Optimized for LEGAL FIRMS and RESTORATION COMPANIES.

    Args:
        company_info: CompanyInfo from Serper lookup

    Returns:
        Combined description text optimized for personalization
    """
    parts = []

    # ===== TIER S: LEGAL FIRM MEGA HOOKS =====

    # Case verdicts/settlements - THE BEST hook for attorneys
    for verdict in company_info.case_verdicts[:2]:
        parts.append(f'VERDICT: {verdict}')

    # Avvo rating - Attorneys LOVE this
    if company_info.avvo_rating:
        parts.append(f'RATING: {company_info.avvo_rating}')

    # Super Lawyers - Major ego stroke
    if company_info.super_lawyers:
        parts.append(f'AWARD: {company_info.super_lawyers}')

    # Best Lawyers in America
    if company_info.best_lawyers:
        parts.append(f'AWARD: {company_info.best_lawyers}')

    # Martindale-Hubbell
    if company_info.martindale_rating:
        parts.append(f'RATING: {company_info.martindale_rating}')

    # ===== TIER S: RESTORATION MEGA HOOKS =====

    # IICRC Certifications - Shows expertise
    if company_info.iicrc_certs:
        certs = ", ".join(company_info.iicrc_certs[:3])
        parts.append(f'CERTIFIED: {certs}')

    # Insurance partnerships - Trust signal
    for partner in company_info.insurance_partners[:2]:
        parts.append(f'INSURANCE: {partner}')

    # Response guarantee - Operational excellence
    if company_info.response_guarantee:
        parts.append(f'RESPONSE: {company_info.response_guarantee}')

    # Claims handled - Scale
    if company_info.claims_handled:
        parts.append(f'SCALE: {company_info.claims_handled}')

    # ===== TIER S: UNIVERSAL MEGA HOOKS =====

    # Awards and recognition
    for award in company_info.awards[:3]:
        parts.append(f'AWARD: {award}')

    # Jobs/customers served
    if company_info.jobs_completed:
        parts.append(f'SCALE: {company_info.jobs_completed}')
    if company_info.customers_served:
        parts.append(f'SCALE: {company_info.customers_served}')

    # Media features
    for media in company_info.media_features[:2]:
        parts.append(f'MEDIA: {media}')

    # Google reviews/ratings - Social proof
    if company_info.google_rating and company_info.review_count:
        parts.append(f'REVIEWS: {company_info.google_rating} with {company_info.review_count}')
    elif company_info.google_rating:
        parts.append(f'REVIEWS: {company_info.google_rating}')
    elif company_info.review_count:
        parts.append(f'REVIEWS: {company_info.review_count} on Google')

    # ===== TIER A: STRONG HOOKS =====

    # Attorney/team count - Shows firm size
    if company_info.attorney_count:
        parts.append(f'TEAM: {company_info.attorney_count}')

    # Years in business - Longevity = trust
    if company_info.years_in_business:
        parts.append(f'LONGEVITY: In business {company_info.years_in_business}')

    # Family-owned story - Emotional connection
    if company_info.founding_story:
        parts.append(f'STORY: {company_info.founding_story}')

    # Fleet/team size - Shows scale
    if company_info.fleet_size:
        parts.append(f'SCALE: {company_info.fleet_size}')
    if company_info.team_size:
        parts.append(f'SCALE: Team of {company_info.team_size}')

    # Service area expansion
    if company_info.service_area_size:
        parts.append(f'GROWTH: {company_info.service_area_size}')

    # Hiring signals - Growth
    if company_info.is_hiring:
        if company_info.hiring_roles:
            parts.append(f'GROWTH: Currently hiring {", ".join(company_info.hiring_roles[:2])}')
        else:
            parts.append('GROWTH: Currently hiring/expanding')

    # Niche specialty / Practice areas - What they're known for
    if company_info.niche_specialty:
        parts.append(f'SPECIALTY: Known for {company_info.niche_specialty}')
    for area in company_info.practice_areas[:2]:
        parts.append(f'SPECIALTY: {area}')

    # Tools/platforms - Shows sophistication
    for tool in company_info.tools[:3]:
        parts.append(f'TECH: Uses {tool}')

    # Certifications/partnerships
    for cert in company_info.certifications[:3]:
        parts.append(f'CERTIFIED: {cert}')

    # Warranty/guarantee - Confidence signal
    if company_info.warranty_guarantee:
        parts.append(f'CONFIDENCE: {company_info.warranty_guarantee}')

    # Response time - Operational excellence
    if company_info.response_time:
        parts.append(f'SERVICE: {company_info.response_time}')

    # ===== TIER B: GOOD HOOKS =====

    # Podcast appearances
    for podcast in company_info.podcasts[:2]:
        parts.append(f'MEDIA: Featured on {podcast}')

    # Community involvement
    for community in company_info.community_involvement[:2]:
        parts.append(f'COMMUNITY: {community}')

    # Clients/projects
    for client in company_info.clients[:3]:
        parts.append(f'CLIENTS: Worked with {client}')

    # News mentions
    for news in company_info.news_mentions[:2]:
        parts.append(f'NEWS: {news}')

    # Recent projects
    for project in company_info.recent_projects[:2]:
        parts.append(f'PROJECT: {project}')

    # Owner name (if found)
    if company_info.owner_name:
        parts.append(f'OWNER: {company_info.owner_name}')

    # Knowledge graph info
    if company_info.knowledge_panel:
        kg = company_info.knowledge_panel
        if kg.get("description"):
            parts.append(f'BIO: {kg["description"]}')

    # Services
    for service in company_info.services[:2]:
        parts.append(f'SERVICE: {service}')

    # ===== TIER C: FALLBACK ONLY =====

    # Location - Only if nothing else
    if company_info.location and len(parts) < 3:
        parts.append(f"LOCATION: {company_info.location}")

    # General snippets as last resort
    if len(parts) < 3:
        for snippet in company_info.snippets[:2]:
            if snippet not in parts:
                parts.append(f'INFO: {snippet}')

    return " | ".join(parts)
