"""
Comprehensive line quality validator.

Ensures NO broken, truncated, or low-quality lines ever make it to output.
This is the final gatekeeper before any line is accepted.
"""
import re
import logging
from dataclasses import dataclass
from typing import List, Tuple, Optional

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of line validation."""
    is_valid: bool
    issues: List[str]
    quality_score: int  # 0-100
    suggested_action: str  # "accept", "retry", "fallback"


class LineQualityValidator:
    """
    Validates personalization lines for quality and completeness.

    This is the FINAL check before any line goes to output.
    If it fails here, it gets rejected - no exceptions.
    """

    # Words that indicate generic/low-effort lines
    GENERIC_INDICATORS = [
        "came across",
        "found your",
        "noticed your company",
        "saw your website",
        "looking at your",
        "checked out your",
        "stumbled upon",
        "discovered your",
    ]

    # Banned words that make lines sound fake/salesy
    BANNED_WORDS = [
        "recently", "just", "new", "latest", "exciting", "impressive",
        "amazing", "incredible", "innovative", "cutting-edge", "groundbreaking",
        "revolutionary", "world-class", "best-in-class", "leading", "premier",
        "awesome", "fantastic", "wonderful", "great work", "love what you",
        "thrilled", "excited", "honored", "delighted", "pleased",
    ]

    # Articles/prepositions that shouldn't end a sentence (truncation indicators)
    TRUNCATION_ENDINGS = [
        "a", "an", "the", "to", "of", "in", "for", "with", "and", "or", "but",
        "that", "this", "your", "their", "its", "from", "by", "on", "at",
        "is", "are", "was", "were", "be", "been", "being",
        "has", "have", "had", "do", "does", "did",
        "will", "would", "could", "should", "may", "might", "must",
        "if", "when", "where", "which", "who", "whom", "whose",
        "as", "so", "than", "then", "into", "onto", "upon",
    ]

    # Minimum quality indicators - lines MUST have at least one
    QUALITY_INDICATORS = [
        r'\$[\d,]+[MKB]?\+?',  # Revenue figures ($2M+, $500K)
        r'\d+[\.\d]*\s*(?:star|review|rating)',  # Reviews/ratings (4.9 stars, 287 reviews)
        r'\d+[\+]?\s*(?:year|decade)',  # Years in business
        r'\d+[\+]?\s*(?:location|office|branch)',  # Multiple locations
        r'\d+[\+]?\s*(?:employee|team|staff|attorney|lawyer|technician|truck)',  # Team/fleet size
        r'(?:ServiceTitan|Freshdesk|HubSpot|Salesforce|Zendesk)',  # Tech stack
        r'(?:BBB|A\+|certified|accredited|licensed)',  # Certifications
        r'(?:franchise|subsidiary|part of)',  # Corporate structure
        # LEGAL FIRM S-TIER patterns
        r'(?:verdict|settlement|recovered|million|jury)',  # Case outcomes
        r'(?:avvo|super lawyer|best lawyer|martindale|preeminent)',  # Legal awards
        r'(?:attorney|lawyer|esquire|litigation)',  # Legal terms
        # RESTORATION S-TIER patterns
        r'(?:IICRC|WRT|ASD|FSRT|AMRT)',  # IICRC certifications
        r'(?:State Farm|Allstate|USAA|preferred vendor|insurance)',  # Insurance
        r'(?:24/7|24-hour|emergency response)',  # Response time
        r'(?:claim|restoration|water damage|fire damage)',  # Restoration terms
        # Quality conversation starters
        r'(?:stands out|speaks for itself|caught my attention|get noticed)',
        # General quality signals
        r'since\s+\d{4}',  # "since 1987"
        r'\d+\s*(?:county|counties|cities)',  # Service area
    ]

    def __init__(self):
        """Initialize the validator."""
        self.min_words = 8
        self.max_words = 22
        self.min_chars = 40
        self.max_chars = 200

    def validate(self, line: str, company_name: Optional[str] = None) -> ValidationResult:
        """
        Validate a personalization line.

        Args:
            line: The line to validate
            company_name: Optional company name for context

        Returns:
            ValidationResult with pass/fail and details
        """
        issues = []
        quality_score = 100

        # Strip and normalize
        line = line.strip()

        # === CRITICAL CHECKS (auto-fail) ===

        # Check 1: Empty or near-empty
        if not line or len(line) < 10:
            return ValidationResult(
                is_valid=False,
                issues=["Line is empty or too short"],
                quality_score=0,
                suggested_action="fallback"
            )

        # Check 2: Truncation detection - ends with article/preposition
        words = line.rstrip('.!?').split()
        if words:
            last_word = words[-1].lower().strip('.,!?')
            if last_word in self.TRUNCATION_ENDINGS:
                return ValidationResult(
                    is_valid=False,
                    issues=[f"Line appears truncated (ends with '{last_word}')"],
                    quality_score=0,
                    suggested_action="retry"
                )

        # Check 3: Unclosed quotes
        quote_chars = ['"', "'", '"', '"', ''', ''']
        for qc in ['"', "'"]:
            if line.count(qc) % 2 != 0:
                return ValidationResult(
                    is_valid=False,
                    issues=["Line has unclosed quotes"],
                    quality_score=0,
                    suggested_action="retry"
                )

        # Check 4: Unclosed parentheses/brackets
        if line.count('(') != line.count(')'):
            return ValidationResult(
                is_valid=False,
                issues=["Line has unclosed parentheses"],
                quality_score=0,
                suggested_action="retry"
            )

        # Check 5: Starts with lowercase (bad formatting)
        if line[0].islower():
            issues.append("Line starts with lowercase")
            quality_score -= 10

        # Check 6: Missing end punctuation
        if line[-1] not in '.!?':
            issues.append("Line missing end punctuation")
            quality_score -= 5

        # === WORD COUNT CHECKS ===

        word_count = len(line.split())

        if word_count < self.min_words:
            return ValidationResult(
                is_valid=False,
                issues=[f"Line too short ({word_count} words, min {self.min_words})"],
                quality_score=0,
                suggested_action="retry"
            )

        if word_count > self.max_words:
            return ValidationResult(
                is_valid=False,
                issues=[f"Line too long ({word_count} words, max {self.max_words})"],
                quality_score=0,
                suggested_action="retry"
            )

        # === CHARACTER COUNT CHECKS ===

        if len(line) < self.min_chars:
            issues.append(f"Line suspiciously short ({len(line)} chars)")
            quality_score -= 15

        if len(line) > self.max_chars:
            issues.append(f"Line too long ({len(line)} chars)")
            quality_score -= 10

        # === BANNED WORD CHECKS ===

        line_lower = line.lower()
        for banned in self.BANNED_WORDS:
            if banned in line_lower:
                return ValidationResult(
                    is_valid=False,
                    issues=[f"Line contains banned word: '{banned}'"],
                    quality_score=0,
                    suggested_action="retry"
                )

        # === GENERIC LINE DETECTION ===

        for generic in self.GENERIC_INDICATORS:
            if generic in line_lower:
                # This is a generic/low-effort line
                return ValidationResult(
                    is_valid=False,
                    issues=[f"Line is generic (contains '{generic}')"],
                    quality_score=20,
                    suggested_action="retry"
                )

        # === QUALITY SCORING ===

        # Check for quality indicators (specific data points)
        has_quality_indicator = False
        quality_indicator_count = 0
        for pattern in self.QUALITY_INDICATORS:
            if re.search(pattern, line, re.IGNORECASE):
                has_quality_indicator = True
                quality_indicator_count += 1

        # Reward lines with quality indicators
        if has_quality_indicator:
            quality_score += min(15, quality_indicator_count * 5)  # Up to +15 for multiple indicators
        else:
            # Only slightly penalize - the line might still be good
            quality_score -= 10
            issues.append("No specific data point detected in line")

        # Check for numbers (specificity indicator) - but don't penalize heavily
        if re.search(r'\d+', line):
            quality_score += 5
        # Don't penalize lines without numbers if they have other quality indicators
        elif not has_quality_indicator:
            quality_score -= 5
            issues.append("Line lacks specific numbers")

        # Check for company name if provided
        if company_name:
            if company_name.lower() not in line_lower:
                # Not necessarily bad, just note it
                pass

        # === GRAMMAR/STRUCTURE CHECKS ===

        # Check for repeated words (sign of generation error)
        words_lower = [w.lower().strip('.,!?') for w in words]
        for i in range(len(words_lower) - 1):
            if words_lower[i] == words_lower[i + 1] and len(words_lower[i]) > 2:
                issues.append(f"Repeated word detected: '{words_lower[i]}'")
                quality_score -= 15

        # Check for sentence fragments that don't make sense
        fragment_patterns = [
            r'^(And|But|Or|So|Because)\s',  # Starting with conjunction
            r'\s(And|But|Or)\s*[.!?]$',  # Ending with conjunction before punctuation
        ]
        for pattern in fragment_patterns:
            if re.search(pattern, line):
                issues.append("Possible sentence fragment detected")
                quality_score -= 10

        # Cap quality score
        quality_score = max(0, min(100, quality_score))

        # Determine suggested action based on quality score
        if quality_score >= 60:
            suggested_action = "accept"
        elif quality_score >= 35:
            suggested_action = "retry"
        else:
            suggested_action = "fallback"

        # Final validation - be more lenient to avoid too many fallbacks
        # A line is valid if it has a reasonable score and not too many critical issues
        is_valid = quality_score >= 45 and len(issues) < 4

        return ValidationResult(
            is_valid=is_valid,
            issues=issues,
            quality_score=quality_score,
            suggested_action=suggested_action
        )

    def validate_batch(self, lines: List[str]) -> List[Tuple[str, ValidationResult]]:
        """
        Validate a batch of lines.

        Args:
            lines: List of lines to validate

        Returns:
            List of (line, ValidationResult) tuples
        """
        return [(line, self.validate(line)) for line in lines]

    def get_quality_tier(self, score: int) -> str:
        """Convert quality score to tier."""
        if score >= 85:
            return "S"
        elif score >= 70:
            return "A"
        elif score >= 50:
            return "B"
        else:
            return "C"


# Singleton instance for easy import
validator = LineQualityValidator()


def validate_line(line: str, company_name: Optional[str] = None) -> ValidationResult:
    """Convenience function to validate a single line."""
    return validator.validate(line, company_name)


def is_line_acceptable(line: str) -> bool:
    """Quick check if a line is acceptable for output."""
    result = validator.validate(line)
    return result.is_valid
