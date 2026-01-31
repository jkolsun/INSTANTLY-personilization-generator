"""
Configuration constants for the Personalization Line Engine.
"""
from enum import Enum
from typing import Dict, List


class ArtifactType(Enum):
    """Types of artifacts that can be extracted for personalization."""
    # Tier S - Direct "Insider" Signals
    CLIENT_OR_PROJECT = "CLIENT_OR_PROJECT"
    TOOL_PLATFORM = "TOOL_PLATFORM"
    EXACT_PHRASE = "EXACT_PHRASE"

    # Tier A - Market & Operator Context
    COMPETITOR = "COMPETITOR"
    SERVICE_PROGRAM = "SERVICE_PROGRAM"
    HIRING_SIGNAL = "HIRING_SIGNAL"

    # Tier B - Contextual Fallback
    LOCATION = "LOCATION"
    COMPANY_DESCRIPTION = "COMPANY_DESCRIPTION"

    # Fallback
    FALLBACK = "FALLBACK"


class ConfidenceTier(Enum):
    """Confidence tiers for generated lines."""
    S = "S"  # Website exact phrase, client/project, tool/platform
    A = "A"  # Service/program, location (specific), competitor
    B = "B"  # Fallback or weak artifact


# Artifact type to confidence tier mapping
# Tier S: Direct "Insider" signals - creates "how did they know that?" reaction
# Tier A: Market & Operator context - implies real market familiarity
# Tier B: Contextual fallback - acceptable but weaker, use sparingly
ARTIFACT_CONFIDENCE: Dict[ArtifactType, ConfidenceTier] = {
    # Tier S - Direct "Insider" Signals (highest priority)
    ArtifactType.CLIENT_OR_PROJECT: ConfidenceTier.S,  # Recent work/project/case study
    ArtifactType.TOOL_PLATFORM: ConfidenceTier.S,      # Explicit implementation/system mention
    ArtifactType.EXACT_PHRASE: ConfidenceTier.S,       # Exact copy phrase pulled verbatim
    # Tier A - Market & Operator Context (strong, safe)
    ArtifactType.COMPETITOR: ConfidenceTier.A,         # Obvious, top-of-market competitor
    ArtifactType.SERVICE_PROGRAM: ConfidenceTier.A,    # Named service/program/offering
    ArtifactType.HIRING_SIGNAL: ConfidenceTier.A,      # Public job postings
    # Tier B - Contextual Fallback (use only if needed)
    ArtifactType.LOCATION: ConfidenceTier.B,           # Location/service area focus
    ArtifactType.COMPANY_DESCRIPTION: ConfidenceTier.B,# SuperSearch description phrase
    ArtifactType.FALLBACK: ConfidenceTier.B,
}


# Artifact selection priority (stop at first valid)
ARTIFACT_PRIORITY: List[ArtifactType] = [
    # Tier S - Direct "Insider" Signals
    ArtifactType.CLIENT_OR_PROJECT,
    ArtifactType.TOOL_PLATFORM,
    ArtifactType.EXACT_PHRASE,
    # Tier A - Market & Operator Context
    ArtifactType.COMPETITOR,
    ArtifactType.SERVICE_PROGRAM,
    ArtifactType.HIRING_SIGNAL,
    # Tier B - Contextual Fallback
    ArtifactType.LOCATION,
    ArtifactType.COMPANY_DESCRIPTION,
    # Fallback
    ArtifactType.FALLBACK,
]


# Banned timing words (never use)
BANNED_TIMING_WORDS: List[str] = [
    "recently",
    "just",
    "rolled out",
    "implemented",
    "launched",
    "new",
    "latest",
]


# Banned hype adjectives
BANNED_HYPE_ADJECTIVES: List[str] = [
    "impressive",
    "amazing",
    "innovative",
    "best",
    "leading",
    "incredible",
    "outstanding",
    "excellent",
    "fantastic",
    "wonderful",
    "great",
    "awesome",
]


# Generic phrases to reject as artifacts
GENERIC_PHRASES: List[str] = [
    "contact",
    "contact us",
    "get in touch",
    "get in touch with us",
    "reach out",
    "reach out to us",
    "home",
    "learn more",
    "get started",
    "welcome",
    "call now",
    "call us",
    "read more",
    "click here",
    "submit",
    "send",
    "about",
    "about us",
    "services",
    "our services",
    "products",
    "our products",
    "solutions",
    "our solutions",
    "free quote",
    "get a quote",
    "request a quote",
    "schedule",
    "book now",
    "sign up",
    "subscribe",
    "login",
    "log in",
    "menu",
    "search",
    "privacy policy",
    "terms of service",
    "terms and conditions",
    "copyright",
    "all rights reserved",
    "follow us",
    "connect with us",
    "stay connected",
    "newsletter",
    "careers",
    "jobs",
    "faq",
    "help",
    "support",
    "testimonials",
    "reviews",
    "blog",
    "news",
]


# Known tools/platforms to look for
KNOWN_TOOLS: List[str] = [
    "servicetitan",
    "service titan",
    "housecall pro",
    "housecallpro",
    "jobber",
    "calendly",
    "hubspot",
    "salesforce",
    "quickbooks",
    "freshbooks",
    "zoho",
    "monday.com",
    "asana",
    "slack",
    "zendesk",
    "intercom",
    "drift",
    "mailchimp",
    "constant contact",
    "activecampaign",
    "podium",
    "birdeye",
    "yelp",
    "google my business",
    "workiz",
    "fieldedge",
    "successware",
    "simpro",
    "commusoft",
]


# Line templates by artifact type - clear, concise, compelling hooks
TEMPLATES: Dict[ArtifactType, List[str]] = {
    ArtifactType.EXACT_PHRASE: [
        'Loved this on your site: {artifact_text}',
        'This stood out: {artifact_text}',
        'Great line on your site about {artifact_text}',
    ],
    ArtifactType.CLIENT_OR_PROJECT: [
        'Saw your work with {artifact_text}.',
        'The {artifact_text} project caught my eye.',
        'Impressive work on {artifact_text}.',
        'Noticed the {artifact_text} case study.',
    ],
    ArtifactType.TOOL_PLATFORM: [
        'Saw you use {artifact_text}.',
        'Noticed {artifact_text} in your stack.',
        'Fellow {artifact_text} user here.',
    ],
    ArtifactType.COMPETITOR: [
        'Noticed you compete with {artifact_text}.',
        'Saw {artifact_text} in your space.',
    ],
    ArtifactType.SERVICE_PROGRAM: [
        'Your {artifact_text} service looks solid.',
        'Noticed you offer {artifact_text}.',
        'The {artifact_text} program caught my eye.',
    ],
    ArtifactType.HIRING_SIGNAL: [
        'Saw you are hiring for {artifact_text}.',
        'Noticed the {artifact_text} role.',
        'Looks like you are scaling with {artifact_text}.',
    ],
    ArtifactType.LOCATION: [
        'Noticed you serve {artifact_text}.',
        'Saw your focus on {artifact_text}.',
        'Fellow {artifact_text} business here.',
    ],
    ArtifactType.COMPANY_DESCRIPTION: [
        'Liked this about you: {artifact_text}',
        'This stood out: {artifact_text}',
    ],
    ArtifactType.FALLBACK: [
        'Came across your company online.',
        'Found your site and wanted to connect.',
        'Your company caught my attention.',
    ],
}


# Website scraping configuration
SCRAPE_PAGES: List[str] = [
    "/",
    "/services",
    "/service",
    "/about",
    "/about-us",
    "/contact",
    "/contact-us",
    "/portfolio",
    "/work",
    "/our-work",
    "/projects",
    "/case-studies",
    "/clients",
    "/testimonials",
]


# Request configuration
REQUEST_TIMEOUT: int = 10  # seconds
REQUEST_DELAY: float = 1.5  # seconds between requests to same domain
USER_AGENT: str = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


# Artifact constraints
MIN_ARTIFACT_WORDS: int = 2
MAX_ARTIFACT_WORDS: int = 8  # Ideal: 2-6 words
MAX_LINE_WORDS: int = 18

# Tier definitions for selection logic
TIER_S_TYPES: List[ArtifactType] = [
    ArtifactType.CLIENT_OR_PROJECT,
    ArtifactType.TOOL_PLATFORM,
    ArtifactType.EXACT_PHRASE,
]

TIER_A_TYPES: List[ArtifactType] = [
    ArtifactType.COMPETITOR,
    ArtifactType.SERVICE_PROGRAM,
    ArtifactType.HIRING_SIGNAL,
]

TIER_B_TYPES: List[ArtifactType] = [
    ArtifactType.LOCATION,
    ArtifactType.COMPANY_DESCRIPTION,
]
