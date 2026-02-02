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
    MIN_LINE_WORDS,
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

        # Use word boundaries to avoid false positives (VU-05)
        # e.g., "Greater Boston" should NOT match "great" from "great service"
        for pattern in generic_patterns:
            # Build regex with word boundaries
            pattern_regex = rf'\b{re.escape(pattern)}\b'
            if re.search(pattern_regex, text_lower):
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

    def _contains_experiential_claim(self, line: str) -> Optional[str]:
        """
        Check if line contains first-person experiential claims.

        These are claims that the sender personally attended events,
        met people, or witnessed things - which are unverifiable and
        immediately signal the email is fake.

        Args:
            line: The generated line

        Returns:
            The matched pattern if found, None otherwise
        """
        line_lower = line.lower()

        # Patterns that indicate fabricated first-person experiences
        experiential_patterns = [
            (r'\bi saw .* at the\b', "I saw ... at the"),
            (r'\bi saw .* at your\b', "I saw ... at your"),
            (r'\bi met\b', "I met"),
            (r'\bi attended\b', "I attended"),
            (r'\bi was at\b', "I was at"),
            (r'\bi stopped by\b', "I stopped by"),
            (r'\bi visited\b', "I visited"),
            (r'\bat the .* expo\b', "at the ... Expo"),
            (r'\bat the .* summit\b', "at the ... Summit"),
            (r'\bat the .* conference\b', "at the ... Conference"),
            (r'\bat the .* trade show\b', "at the ... Trade Show"),
            (r'\bat the .* convention\b', "at the ... Convention"),
            (r'\byour booth\b', "your booth"),
            (r'\bimpressed the [A-Z][a-z]+s?\b', "impressed the [Name]"),
            (r'\bspoke with .* from\b', "spoke with ... from"),
            (r'\btalked to .* at\b', "talked to ... at"),
        ]

        for pattern, description in experiential_patterns:
            if re.search(pattern, line_lower, re.IGNORECASE):
                return description

        return None

    def _is_complete_sentence(self, line: str) -> tuple[bool, Optional[str]]:
        """
        Check if line is a grammatically complete sentence.

        Args:
            line: The generated line

        Returns:
            Tuple of (is_complete, error_message)
        """
        line = line.strip()

        # Must end with proper punctuation
        if not line or line[-1] not in '.!?':
            return False, "Line must end with period, exclamation, or question mark"

        # Check for dangling predicates (incomplete sentences)
        dangling_patterns = [
            r'\bis\s*\.$',      # "expertise is ."
            r'\bare\s*\.$',     # "services are ."
            r'\bthe\s*\.$',     # "with the ."
            r'\ba\s*\.$',       # "is a ."
            r'\ban\s*\.$',      # "is an ."
            r'\band\s*\.$',     # "tools and ."
            r'\bfor\s*\.$',     # "solutions for ."
            r'\bwith\s*\.$',    # "work with ."
            r'\bin\s*\.$',      # "expertise in ."
            r'\bto\s*\.$',      # "ready to ."
        ]

        for pattern in dangling_patterns:
            if re.search(pattern, line, re.IGNORECASE):
                return False, "Incomplete sentence - ends with dangling word"

        # Check that line has at least one verb indicator
        # This is a simple heuristic - not perfect but catches obvious fragments
        verb_indicators = [
            r'\b(noticed|saw|seeing|see|serves|serving|serve|handles|handling|handle)\b',
            r'\b(uses|using|use|offers|offering|offer|provides|providing|provide)\b',
            r'\b(works|working|work|specializes|specializing|specialize)\b',
            r'\b(stood out|stands out|caught|catching|catch)\b',
            r'\b(is|are|was|were|has|have|had)\b',
            r'\b(came across|looking at|researching)\b',
        ]

        has_verb = False
        for pattern in verb_indicators:
            if re.search(pattern, line, re.IGNORECASE):
                has_verb = True
                break

        if not has_verb:
            # Check if it's just a noun phrase (fragment)
            # If line doesn't have common verbs and is short, likely a fragment
            word_count = len(line.split())
            if word_count < 10:
                return False, "Line appears to be a fragment - no verb detected"

        return True, None

    def _contains_placeholder(self, line: str) -> Optional[str]:
        """
        Check if line contains unreplaced template placeholders.

        Args:
            line: The generated line

        Returns:
            The placeholder if found, None otherwise
        """
        # Match any {placeholder} pattern
        match = re.search(r'\{[^}]+\}', line)
        if match:
            return match.group(0)
        return None

    def _is_valid_opener(self, line: str, company_name: Optional[str] = None) -> tuple[bool, Optional[str]]:
        """
        Check if line follows valid opener patterns (VU-08).

        Valid openers must:
        - Address the recipient directly ('your', 'you') within first 8 words, OR
        - Start with approved patterns: 'Noticed', 'Saw', 'Came across', 'Your'

        Invalid openers:
        - Use company name as grammatical subject doing an action
          (e.g., "Zephyr's range hoods are popular" - statement, not opener)

        Args:
            line: The generated line
            company_name: Optional company name to check for subject position

        Returns:
            Tuple of (is_valid, error_message)
        """
        line_lower = line.lower().strip()
        words = line_lower.split()

        if not words:
            return False, "Empty line"

        # Check for approved opener patterns (case-insensitive start)
        approved_starters = [
            "noticed your", "noticed that", "noticed",
            "saw your", "saw that", "saw",
            "came across your", "came across",
            "your team", "your company", "your work", "your",
            "seeing your", "seeing that",
        ]

        has_approved_start = any(line_lower.startswith(starter) for starter in approved_starters)

        # Check if 'your' or 'you' appears within first 8 words
        first_8_words = ' '.join(words[:8])
        has_recipient_address = 'your' in first_8_words or 'you ' in first_8_words

        # If neither approved start nor recipient address, it's invalid
        if not has_approved_start and not has_recipient_address:
            return False, "Opener must address recipient ('your'/'you') within first 8 words or use approved patterns (Noticed/Saw/Came across)"

        # Check if company name is used as grammatical subject (bad pattern)
        if company_name:
            company_lower = company_name.lower().strip()
            # Check for patterns like "CompanyName's X is/are..." or "CompanyName is/has..."
            # This is a statement about the company, not an opener addressing the recipient
            company_subject_patterns = [
                rf"^{re.escape(company_lower)}'s\s+\w+\s+(is|are|was|were|has|have)\b",
                rf"^{re.escape(company_lower)}\s+(is|are|was|were|has|have|offers|provides|specializes)\b",
                rf"^the\s+{re.escape(company_lower)}\s+(is|are|was|were|has|have)\b",
            ]

            for pattern in company_subject_patterns:
                if re.search(pattern, line_lower):
                    return False, f"Line uses company name as subject - should address recipient instead"

        return True, None

    def _contains_company_mismatch(self, line: str, expected_company: str) -> Optional[str]:
        """
        VU-09: Check if line mentions a different company name than expected.

        Looks for capitalized phrases that might be company names and checks
        if they match the expected company name.

        Args:
            line: The generated line
            expected_company: Expected company name

        Returns:
            The mismatched company name if found, None otherwise
        """
        if not expected_company:
            return None

        expected_lower = expected_company.lower().strip()
        # Extract key words from expected company name (remove common suffixes)
        expected_words = set(
            word.lower() for word in expected_company.split()
            if word.lower() not in ['inc', 'llc', 'co', 'corp', 'company', 'the', 'and', '&']
        )

        # Find potential company names in the line (capitalized words/phrases)
        # Look for patterns like "CompanyName", "Company Name", "Company Name Inc"
        company_patterns = [
            r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\b',  # "Green Mountain Solar"
            r'\b([A-Z][a-z]+\'s)\b',  # "Zephyr's"
        ]

        found_names = []
        for pattern in company_patterns:
            matches = re.findall(pattern, line)
            found_names.extend(matches)

        for found_name in found_names:
            found_lower = found_name.lower().strip().rstrip("'s")
            found_words = set(
                word.lower() for word in found_name.split()
                if word.lower() not in ['inc', 'llc', 'co', 'corp', 'company', 'the', 'and', '&']
            )

            # Skip if it's a common word that's not likely a company name
            common_words = {
                'noticed', 'saw', 'your', 'team', 'company', 'work', 'service',
                'area', 'location', 'project', 'commercial', 'residential',
                'hvac', 'plumbing', 'electrical', 'heating', 'cooling'
            }
            if found_words.issubset(common_words):
                continue

            # Check if found name matches expected company
            # Match if: exact match, or significant word overlap
            if found_lower == expected_lower:
                continue  # Exact match is fine

            # Check word overlap - if they share significant words, it's probably fine
            if expected_words and found_words:
                overlap = expected_words.intersection(found_words)
                if len(overlap) >= 1:
                    continue  # Has common words, probably same company

            # If we get here, it might be a different company name
            # Only flag if it looks like a real company name (2+ words or possessive)
            if len(found_name.split()) >= 2 or found_name.endswith("'s"):
                # Additional check: is this name NOT a subset of expected?
                if not any(word in expected_lower for word in found_words if len(word) > 3):
                    return found_name

        return None

    def validate(
        self,
        line: str,
        artifact: Artifact,
        all_artifacts: Optional[List[Artifact]] = None,
        company_name: Optional[str] = None,
    ) -> ValidationResult:
        """
        Validate a personalization line.

        Args:
            line: The generated line
            artifact: The artifact used
            all_artifacts: Optional list of all available artifacts (for stacking check)
            company_name: Optional company name for opener validation

        Returns:
            ValidationResult with is_valid and any errors
        """
        errors = []

        # Check word count (VU-02: both floor and ceiling)
        word_count = self._count_words(line)
        if word_count < MIN_LINE_WORDS:
            errors.append(f"Line has {word_count} words, min is {MIN_LINE_WORDS} (too short/fragment)")
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

        # FAIL CONDITION: Check for first-person experiential claims (VU-06)
        experiential_claim = self._contains_experiential_claim(line)
        if experiential_claim:
            errors.append(f"Contains fabricated experiential claim: '{experiential_claim}'")

        # FAIL CONDITION: Check for sentence completeness (VU-07)
        is_complete, completeness_error = self._is_complete_sentence(line)
        if not is_complete:
            errors.append(f"Incomplete sentence: {completeness_error}")

        # FAIL CONDITION: Check for unreplaced placeholders (VU-01)
        placeholder = self._contains_placeholder(line)
        if placeholder:
            errors.append(f"Contains unreplaced placeholder: '{placeholder}'")

        # FAIL CONDITION: Check opener pattern (VU-08)
        is_valid_opener, opener_error = self._is_valid_opener(line, company_name)
        if not is_valid_opener:
            errors.append(f"Invalid opener: {opener_error}")

        # FAIL CONDITION: Check for company name mismatch (VU-09)
        if company_name:
            mismatched_company = self._contains_company_mismatch(line, company_name)
            if mismatched_company:
                errors.append(f"Possible wrong company reference: '{mismatched_company}' (expected: '{company_name}')")

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
