"""
Artifact extractor for finding personalization candidates.
"""
import re
from dataclasses import dataclass
from typing import List, Optional

from config import (
    ArtifactType,
    GENERIC_PHRASES,
    KNOWN_TOOLS,
    MAX_ARTIFACT_WORDS,
    MIN_ARTIFACT_WORDS,
)
from website_scraper import ScrapedElement


@dataclass
class Artifact:
    """A candidate artifact for personalization."""
    text: str
    artifact_type: ArtifactType
    evidence_source: str  # website, company_description
    evidence_url: str  # URL where found (blank for description)
    score: float  # Quality score for ranking


class ArtifactExtractor:
    """Extracts and filters artifacts from website content and descriptions."""

    def __init__(self):
        self.generic_phrases_lower = set(p.lower() for p in GENERIC_PHRASES)
        self.known_tools_lower = set(t.lower() for t in KNOWN_TOOLS)

    def _count_words(self, text: str) -> int:
        """Count words in text."""
        return len(text.split())

    def _is_generic(self, text: str) -> bool:
        """Check if text is a generic/rejected phrase."""
        text_lower = text.lower().strip()

        # Exact match
        if text_lower in self.generic_phrases_lower:
            return True

        # Partial match (starts with generic phrase)
        for generic in self.generic_phrases_lower:
            if text_lower.startswith(generic) or text_lower.endswith(generic):
                return True

        # Check for common generic patterns
        generic_patterns = [
            r"^\d+$",  # Just numbers
            r"^[A-Z]{2,3}$",  # Just abbreviations
            r"^(click|tap|press|call|email|visit)\b",
            r"^(our|the|a|an)\s+(company|team|mission|vision|values)$",
            r"^(view|see|read|learn|discover|explore)\s",
            r"^(get|request|schedule|book)\s+(a|your|free)\s",
            r"(all rights reserved|copyright|privacy|terms)",
        ]

        for pattern in generic_patterns:
            if re.search(pattern, text_lower):
                return True

        return False

    def _is_valid_length(self, text: str) -> bool:
        """Check if text has valid word count."""
        word_count = self._count_words(text)
        return MIN_ARTIFACT_WORDS <= word_count <= MAX_ARTIFACT_WORDS

    def _calculate_score(self, text: str, element_type: str) -> float:
        """
        Calculate quality score for an artifact.
        Higher is better.
        """
        score = 0.0
        text_lower = text.lower()
        word_count = self._count_words(text)

        # Prefer 3-5 word phrases
        if 3 <= word_count <= 5:
            score += 2.0
        elif word_count == 2 or word_count == 6:
            score += 1.0

        # Boost for proper nouns (capitalized words)
        capitals = len(re.findall(r"\b[A-Z][a-z]+\b", text))
        score += capitals * 0.5

        # Boost for element type
        type_scores = {
            "client": 3.0,
            "tool": 3.0,
            "service": 2.0,
            "heading": 1.5,
            "cta": 1.0,
            "location": 1.0,
        }
        score += type_scores.get(element_type, 0.0)

        # Boost for quotes or distinctive punctuation
        if '"' in text or "'" in text or "®" in text or "™" in text:
            score += 1.0

        # Penalty for all lowercase
        if text == text.lower():
            score -= 1.0

        # Penalty for very common words
        common_words = ["the", "and", "for", "your", "our", "with"]
        common_count = sum(1 for w in text_lower.split() if w in common_words)
        score -= common_count * 0.3

        return score

    def extract_from_website(self, elements: List[ScrapedElement]) -> List[Artifact]:
        """
        Extract artifacts from scraped website elements.

        Args:
            elements: List of scraped elements

        Returns:
            List of candidate artifacts
        """
        artifacts = []

        for elem in elements:
            # Skip generic phrases
            if self._is_generic(elem.text):
                continue

            # Skip invalid length
            if not self._is_valid_length(elem.text):
                continue

            # Determine artifact type based on element type
            if elem.element_type == "client":
                artifact_type = ArtifactType.CLIENT_OR_PROJECT
            elif elem.element_type == "tool":
                artifact_type = ArtifactType.TOOL_PLATFORM
            elif elem.element_type == "service":
                artifact_type = ArtifactType.SERVICE_PROGRAM
            elif elem.element_type == "location":
                artifact_type = ArtifactType.LOCATION
            else:  # heading, cta
                artifact_type = ArtifactType.EXACT_PHRASE

            score = self._calculate_score(elem.text, elem.element_type)

            artifacts.append(Artifact(
                text=elem.text,
                artifact_type=artifact_type,
                evidence_source="website",
                evidence_url=elem.page_url,
                score=score,
            ))

        return artifacts

    def extract_from_description(self, description: str) -> List[Artifact]:
        """
        Extract artifacts from company description text.

        Args:
            description: Company description text

        Returns:
            List of candidate artifacts
        """
        if not description:
            return []

        artifacts = []

        # Clean description
        description = description.replace("<br>", " ")
        description = re.sub(r"<[^>]+>", " ", description)  # Remove HTML tags
        description = " ".join(description.split())  # Normalize whitespace

        # Extract distinctive phrases (2-6 words)
        # Look for phrases in quotes
        quoted = re.findall(r'"([^"]{10,60})"', description)
        quoted.extend(re.findall(r"'([^']{10,60})'", description))

        for phrase in quoted:
            phrase = phrase.strip()
            if self._is_valid_length(phrase) and not self._is_generic(phrase):
                artifacts.append(Artifact(
                    text=phrase,
                    artifact_type=ArtifactType.EXACT_PHRASE,  # Quoted phrases are Tier S
                    evidence_source="company_description",
                    evidence_url="",
                    score=self._calculate_score(phrase, "description") + 2.0,  # Boost for quotes
                ))

        # Extract brand names mentioned with context phrases
        # Patterns like "brands like X", "using X", "powered by X", "products from X"
        brand_patterns = [
            r"(?:brands? like|products? from|powered by|using|partner with|certified by)\s+([A-Z][a-zA-Z0-9\s&]+?)(?:\.|,|$|\s+and\s|\s+we)",
            r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+(?:certified|accredited|trained)",  # X-certified
            r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+(?:partner|member|dealer)",  # X partner
        ]

        for pattern in brand_patterns:
            matches = re.findall(pattern, description)
            for match in matches:
                match = match.strip().rstrip(".,")
                if 2 <= len(match.split()) <= 4 and not self._is_generic(match):
                    if not any(a.text.lower() == match.lower() for a in artifacts):
                        artifacts.append(Artifact(
                            text=match,
                            artifact_type=ArtifactType.TOOL_PLATFORM,  # Brand mentions are Tier S
                            evidence_source="company_description",
                            evidence_url="",
                            score=6.0,  # High score for brand mentions
                        ))

        # Extract certifications (NATE-certified, EPA certified, etc.)
        cert_patterns = [
            r"([A-Z]{2,10})-?certified",
            r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+certified",
        ]

        for pattern in cert_patterns:
            matches = re.findall(pattern, description)
            for match in matches:
                cert_name = match.strip()
                if cert_name and not self._is_generic(cert_name):
                    cert_text = f"{cert_name}-certified"
                    if not any(a.text.lower() == cert_text.lower() for a in artifacts):
                        artifacts.append(Artifact(
                            text=cert_text,
                            artifact_type=ArtifactType.SERVICE_PROGRAM,  # Certifications are Tier A
                            evidence_source="company_description",
                            evidence_url="",
                            score=4.0,
                        ))

        # Extract named programs/memberships (e.g., "Comfort Club", "Service Partner Plan")
        program_patterns = [
            r"(?:our|the)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\s+(?:program|plan|membership|club)",
            r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\s+(?:Program|Plan|Membership|Club)",
        ]

        for pattern in program_patterns:
            matches = re.findall(pattern, description)
            for match in matches:
                match = match.strip()
                if self._is_valid_length(match) and not self._is_generic(match):
                    if not any(a.text.lower() == match.lower() for a in artifacts):
                        artifacts.append(Artifact(
                            text=match,
                            artifact_type=ArtifactType.SERVICE_PROGRAM,  # Programs are Tier A
                            evidence_source="company_description",
                            evidence_url="",
                            score=4.5,
                        ))

        # Extract phrases with proper nouns (likely company/brand names)
        proper_noun_phrases = re.findall(
            r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,4})\b",
            description
        )

        for phrase in proper_noun_phrases:
            phrase = phrase.strip()
            if self._is_valid_length(phrase) and not self._is_generic(phrase):
                # Avoid duplicates
                if not any(a.text.lower() == phrase.lower() for a in artifacts):
                    artifacts.append(Artifact(
                        text=phrase,
                        artifact_type=ArtifactType.COMPANY_DESCRIPTION,
                        evidence_source="company_description",
                        evidence_url="",
                        score=self._calculate_score(phrase, "description"),
                    ))

        # Extract tool/platform mentions
        desc_lower = description.lower()
        for tool in KNOWN_TOOLS:
            if tool.lower() in desc_lower:
                # Avoid duplicates
                if not any(a.text.lower() == tool.lower() for a in artifacts):
                    artifacts.append(Artifact(
                        text=tool,
                        artifact_type=ArtifactType.TOOL_PLATFORM,
                        evidence_source="company_description",
                        evidence_url="",
                        score=5.0,  # High score for tools
                    ))

        # Extract location mentions
        location_patterns = [
            r"(?:serving|located in|based in)\s+([A-Z][a-zA-Z\s,]+?)(?:\.|,|$)",
            r"([A-Z][a-z]+,\s*[A-Z]{2})\b",  # City, ST format
        ]

        for pattern in location_patterns:
            matches = re.findall(pattern, description)
            for match in matches:
                match = match.strip().rstrip(".,")
                if 3 < len(match) < 40 and not self._is_generic(match):
                    if not any(a.text.lower() == match.lower() for a in artifacts):
                        artifacts.append(Artifact(
                            text=match,
                            artifact_type=ArtifactType.LOCATION,
                            evidence_source="company_description",
                            evidence_url="",
                            score=2.0,
                        ))

        return artifacts

    def extract_all(
        self,
        website_elements: Optional[List[ScrapedElement]],
        description: Optional[str],
    ) -> List[Artifact]:
        """
        Extract all artifacts from both website and description.

        Args:
            website_elements: Scraped website elements (or None)
            description: Company description (or None)

        Returns:
            Combined list of artifacts
        """
        artifacts = []

        if website_elements:
            artifacts.extend(self.extract_from_website(website_elements))

        if description:
            artifacts.extend(self.extract_from_description(description))

        return artifacts
