"""
Validator for personalization lines.

Implements FAIL CONDITIONS (AUTO-REJECT):
- Generic phrases that could apply to 80%+ of companies
- Any invented timing language ("recently", "just", "rolled out")
- Multiple artifacts in one line
- Anything the owner would not immediately recognize
"""
import re
from dataclasses import dataclass
from typing import List, Optional

from artifact_extractor import Artifact
from config import (
    ArtifactType,
    BANNED_HYPE_ADJECTIVES,
    BANNED_TIMING_WORDS,
    GENERIC_PHRASES,
    MAX_LINE_WORDS,
)


@dataclass
class ValidationResult:
    """Result of line validation."""
    is_valid: bool
    errors: List[str]


class Validator:
    """
    Validates personalization lines against rules.

    FAIL CONDITIONS (AUTO-REJECT):
    - Generic phrases that could apply to 80%+ of companies
    - Any invented timing language ("recently", "just", "rolled out")
    - Multiple artifacts in one line
    - Anything the owner would not immediately recognize
    """

    def __init__(self):
        self.banned_timing_lower = [w.lower() for w in BANNED_TIMING_WORDS]
        self.banned_hype_lower = [w.lower() for w in BANNED_HYPE_ADJECTIVES]
        self.generic_phrases_lower = set(p.lower() for p in GENERIC_PHRASES)

    def _count_words(self, text: str) -> int:
        """Count words in text."""
        return len(text.split())

    def _contains_banned_timing(self, line: str) -> Optional[str]:
        """Check if line contains banned timing words."""
        line_lower = line.lower()
        for word in self.banned_timing_lower:
            if word in line_lower:
                return word
        return None

    def _contains_banned_hype(self, line: str) -> Optional[str]:
        """Check if line contains banned hype adjectives (whole words only)."""
        line_lower = line.lower()
        for word in self.banned_hype_lower:
            # Use word boundaries to avoid false positives like "Greater" matching "great"
            if re.search(rf"\b{re.escape(word)}\b", line_lower):
                return word
        return None

    def _is_generic_artifact(self, text: str) -> bool:
        """
        Check if artifact text is too generic (could apply to 80%+ of companies).

        Args:
            text: Artifact text to check

        Returns:
            True if generic, False otherwise
        """
        text_lower = text.lower().strip()

        # Exact match with known generic phrases
        if text_lower in self.generic_phrases_lower:
            return True

        # Reject country-only or overly generic locations
        generic_locations = [
            "united states",
            "usa",
            "us",
            "canada",
            "uk",
            "united kingdom",
            "australia",
        ]
        if text_lower in generic_locations:
            return True

        # Check for generic industry phrases that apply too broadly
        generic_patterns = [
            "quality service",
            "customer satisfaction",
            "best service",
            "great service",
            "professional service",
            "trusted",
            "reliable",
            "experienced",
            "family owned",
            "family-owned",
            "locally owned",
            "serving the",
            "proudly serving",
            "your trusted",
            "your local",
            "we provide",
            "we offer",
            "full service",
            "full-service",
        ]

        # Generic standalone terms (must be exact or near-exact match)
        generic_standalone = [
            "air conditioning",
            "heating and cooling",
            "heating & cooling",
            "hvac",
            "plumbing",
            "electrical",
            "home services",
            "residential",
            "commercial",
            "construction",
            "contractor",
            "maintenance",
            "installation",
            "repair",
            "service area",
        ]
        # Only reject if the artifact IS the generic term (not contains it)
        if text_lower in generic_standalone:
            return True

        for pattern in generic_patterns:
            if pattern in text_lower:
                return True

        return False

    def _has_multiple_artifacts(self, line: str, artifacts: List[Artifact]) -> bool:
        """
        Check if line contains multiple distinct artifacts (stacking).

        Args:
            line: The generated line
            artifacts: List of all available artifacts

        Returns:
            True if multiple artifacts detected, False otherwise
        """
        line_lower = line.lower()
        found_count = 0

        for artifact in artifacts:
            if artifact.artifact_type == ArtifactType.FALLBACK:
                continue
            if artifact.text and artifact.text.lower() in line_lower:
                found_count += 1
                if found_count > 1:
                    return True

        return False

    def _contains_artifact(self, line: str, artifact: Artifact) -> bool:
        """Check if line contains the artifact text verbatim."""
        if artifact.artifact_type == ArtifactType.FALLBACK:
            return True  # Fallback doesn't need artifact text

        return artifact.text.lower() in line.lower()

    def validate(
        self,
        line: str,
        artifact: Artifact,
        all_artifacts: Optional[List[Artifact]] = None,
    ) -> ValidationResult:
        """
        Validate a personalization line.

        Args:
            line: The generated line
            artifact: The artifact used
            all_artifacts: Optional list of all available artifacts (for stacking check)

        Returns:
            ValidationResult with is_valid and any errors
        """
        errors = []

        # Check word count
        word_count = self._count_words(line)
        if word_count > MAX_LINE_WORDS:
            errors.append(f"Line has {word_count} words, max is {MAX_LINE_WORDS}")

        # FAIL CONDITION: Check for banned timing words
        banned_timing = self._contains_banned_timing(line)
        if banned_timing:
            errors.append(f"Contains banned timing word: '{banned_timing}'")

        # FAIL CONDITION: Check for banned hype adjectives
        banned_hype = self._contains_banned_hype(line)
        if banned_hype:
            errors.append(f"Contains banned hype adjective: '{banned_hype}'")

        # Check artifact is present (unless fallback)
        if not self._contains_artifact(line, artifact):
            errors.append(f"Artifact text not found in line: '{artifact.text}'")

        # FAIL CONDITION: Check for multiple artifacts in one line (stacking)
        if all_artifacts and self._has_multiple_artifacts(line, all_artifacts):
            errors.append("Multiple artifacts detected in one line (stacking not allowed)")

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
        )

    def validate_artifact(self, artifact: Artifact) -> ValidationResult:
        """
        Validate an artifact before line generation.

        FAIL CONDITIONS checked:
        - Generic phrases that could apply to 80%+ of companies
        - Invented timing language
        - Hype adjectives

        Args:
            artifact: The artifact to validate

        Returns:
            ValidationResult with is_valid and any errors
        """
        errors = []

        if artifact.artifact_type == ArtifactType.FALLBACK:
            return ValidationResult(is_valid=True, errors=[])

        # FAIL CONDITION: Check for banned timing words
        banned_timing = self._contains_banned_timing(artifact.text)
        if banned_timing:
            errors.append(f"Artifact contains banned timing word: '{banned_timing}'")

        # FAIL CONDITION: Check for banned hype adjectives
        banned_hype = self._contains_banned_hype(artifact.text)
        if banned_hype:
            errors.append(f"Artifact contains banned hype adjective: '{banned_hype}'")

        # FAIL CONDITION: Check for generic phrases (would not be immediately recognized)
        if self._is_generic_artifact(artifact.text):
            errors.append(f"Artifact is too generic: '{artifact.text}'")

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
        )
