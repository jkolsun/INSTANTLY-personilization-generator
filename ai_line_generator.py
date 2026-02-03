"""
AI-powered personalization line generator using Claude API.

Replaces rigid templates with intelligent, context-aware line generation.
"""
import logging
import re
from dataclasses import dataclass
from typing import Optional, List

import anthropic

from line_quality_validator import LineQualityValidator, ValidationResult

logger = logging.getLogger(__name__)

# Initialize the quality validator
quality_validator = LineQualityValidator()


@dataclass
class AIGeneratedLine:
    """Result from AI line generation."""
    line: str
    confidence_tier: str
    artifact_type: str
    artifact_used: str
    reasoning: str


# Words that should NEVER appear in a personalization line
BANNED_WORDS = [
    "recently", "just", "new", "latest", "exciting", "impressive",
    "amazing", "incredible", "innovative", "cutting-edge", "groundbreaking",
    "revolutionary", "world-class", "best-in-class", "leading", "premier",
    "awesome", "fantastic", "wonderful", "great work", "love what you",
]


class AILineGenerator:
    """
    Generate personalization lines using Claude API.

    Uses Claude Haiku for fast, cost-effective generation.
    """

    SYSTEM_PROMPT = """You write cold email openers that psychologically compel business owners to open the email.

PSYCHOLOGY OF WHAT WORKS:
1. EGO - Make them feel like a success story others admire
2. CURIOSITY - Create an open loop they need to close
3. SPECIFICITY - Exact numbers/details prove you did research
4. EXCLUSIVITY - They're in a small % who achieved this
5. VALIDATION - Someone noticed their hard work

===== S-TIER HOOKS (Use if data available) =====

AWARDS/RECOGNITION:
- "Best of Phoenix 2024 winner — that's a title most never earn."
- "Seeing you ranked #1 in Austin for plumbing, I had to reach out."

VOLUME/SCALE (Jobs, Customers):
- "10,000 jobs completed means you've built real operational systems."
- "Serving 5,000+ homeowners tells me you've cracked customer acquisition."

MEDIA/PRESS:
- "Caught your feature on Channel 5 — not many contractors get that visibility."
- "Your interview on the Trade Secrets podcast stood out."

REVIEWS/RATINGS (with specific numbers):
- "Your 4.9 stars across 300+ reviews? That's rare — most hover at 4.2."
- "287 five-star reviews don't happen by accident."

===== A-TIER HOOKS =====

YEARS IN BUSINESS:
- "Still thriving after 30 years when most don't make it past 5? That's serious."
- "Building since 1992 puts you in rare company."

FAMILY/ORIGIN STORY:
- "Third-generation family business — that legacy means something."
- "Family-owned since '85 tells me this isn't just a job for you."

GROWTH SIGNALS (Hiring, Expanding):
- "Hiring technicians while others are cutting back — smart timing."
- "Growing to 4 locations in this economy takes real confidence."

TECH/SOPHISTICATION:
- "ServiceTitan for dispatch and Podium for reviews — you're running this like a real business."
- "The HubSpot integration tells me you think differently than most."

FLEET/TEAM SIZE:
- "25 trucks on the road means you've built something substantial."
- "A team of 40 technicians isn't built overnight."

===== B-TIER HOOKS (Only if no A/S data) =====

NICHE/SPECIALTY:
- "Specializing only in tankless water heaters — smart positioning."
- "Going all-in on commercial while others chase residential scraps."

CERTIFICATIONS:
- "Carrier Factory Authorized — they don't give that to everyone."
- "Rheem Pro Partner puts you in the top tier."

WARRANTY/GUARANTEE:
- "Lifetime warranty on labor? That's confidence most don't have."

===== ABSOLUTE RULES =====
- 12-20 words, COMPLETE SENTENCES ONLY
- Use EXACT numbers/names from data (4.9 stars, 287 reviews, since 1992)
- Sound like a human who genuinely noticed something impressive
- NEVER invent facts — only use what's in the research data
- NEVER use: recently, just, new, exciting, impressive, amazing, innovative, incredible"""

    def __init__(self, api_key: str, model: str = "claude-3-haiku-20240307"):
        """Initialize the AI line generator."""
        # Use older Claude 3 Haiku which is definitely available
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        logger.info(f"AI Generator initialized with model: {self.model}")

    def generate_line(
        self,
        company_name: str,
        serper_data: str,
        lead_data: Optional[dict] = None,
    ) -> AIGeneratedLine:
        """
        Generate a personalization line using Claude.

        Args:
            company_name: Name of the company
            serper_data: Rich text from Serper research
            lead_data: Optional additional lead data dict

        Returns:
            AIGeneratedLine with the generated line and metadata
        """
        # Build context from all available data
        context_parts = []

        if company_name:
            context_parts.append(f"Company: {company_name}")

        if serper_data:
            context_parts.append(f"Research:\n{serper_data}")

        if lead_data:
            # HIGH VALUE: Technologies they use (great for personalization)
            if lead_data.get("technologies"):
                techs = lead_data["technologies"]
                # Filter out generic web techs, keep business tools
                useful_techs = [t.strip() for t in techs.split(",") if t.strip() and
                               t.strip().lower() not in ["mobile friendly", "google font api", "bootstrap framework",
                                                         "apache", "nginx", "remote", "google tag manager",
                                                         "google analytics", "wordpress.org", "google maps",
                                                         "google maps (non paid users)", "recaptcha", "facebook widget"]]
                if useful_techs:
                    context_parts.append(f"Tools/Software they use: {', '.join(useful_techs[:5])}")

            # HIGH VALUE: Keywords/Services (specific services they offer)
            if lead_data.get("keywords"):
                context_parts.append(f"Services/Specialties: {lead_data['keywords'][:300]}")

            # HIGH VALUE: Annual revenue (shows scale/success)
            if lead_data.get("annual_revenue"):
                try:
                    rev = float(lead_data["annual_revenue"])
                    if rev >= 1000000:
                        context_parts.append(f"Annual Revenue: ${rev/1000000:.1f}M+")
                    elif rev >= 100000:
                        context_parts.append(f"Annual Revenue: ${rev/1000:.0f}K+")
                except (ValueError, TypeError):
                    pass

            # HIGH VALUE: Part of larger company (franchise/subsidiary)
            if lead_data.get("subsidiary_of"):
                context_parts.append(f"Part of: {lead_data['subsidiary_of']}")

            # HIGH VALUE: Multiple locations (growth signal)
            if lead_data.get("num_locations"):
                try:
                    num = int(float(lead_data["num_locations"]))
                    if num > 1:
                        context_parts.append(f"Number of locations: {num}")
                except (ValueError, TypeError):
                    pass

            # Person's title/role
            if lead_data.get("person_title"):
                context_parts.append(f"Contact's role: {lead_data['person_title']}")

            if lead_data.get("industry"):
                context_parts.append(f"Industry: {lead_data['industry']}")
            if lead_data.get("location"):
                context_parts.append(f"Location: {lead_data['location']}")
            if lead_data.get("company_description"):
                context_parts.append(f"Description: {lead_data['company_description']}")

        context = "\n\n".join(context_parts)

        # If no context at all, return a fallback
        if not context.strip():
            return AIGeneratedLine(
                line="Came across your company online.",
                confidence_tier="B",
                artifact_type="FALLBACK",
                artifact_used="",
                reasoning="No data available for personalization",
            )

        prompt = self._build_prompt(company_name, context)

        # Retry loop with quality validation
        max_attempts = 3
        last_issues: List[str] = []

        for attempt in range(max_attempts):
            try:
                logger.info(f"Calling Claude API (attempt {attempt + 1}/{max_attempts}) for {company_name}")
                if attempt == 0:
                    logger.info(f"Context being sent to Claude:\n{context[:500]}...")

                # Build messages with retry feedback if applicable
                messages = [{"role": "user", "content": prompt}]
                if attempt > 0 and last_issues:
                    retry_feedback = (
                        f"\n\nYour previous attempt failed validation: {', '.join(last_issues)}. "
                        f"Please write a NEW complete sentence (12-20 words) that avoids these issues."
                    )
                    messages = [{"role": "user", "content": prompt + retry_feedback}]

                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=500,
                    system=self.SYSTEM_PROMPT,
                    messages=messages,
                )

                raw_response = response.content[0].text
                logger.info(f"Claude API SUCCESS for {company_name}")
                logger.info(f"Claude raw response:\n{raw_response}")
                result = self._parse_response(raw_response)

                # Validate and clean the output
                result = self._validate_and_clean(result, company_name)

                # Run through quality validator
                validation = quality_validator.validate(result.line, company_name)
                logger.info(f"Quality validation: valid={validation.is_valid}, score={validation.quality_score}, issues={validation.issues}")

                if validation.is_valid:
                    # Passed validation - return the result
                    logger.info(f"Line passed validation on attempt {attempt + 1}")
                    return result
                else:
                    # Failed validation - store issues for retry
                    last_issues = validation.issues
                    logger.warning(f"Line failed validation (attempt {attempt + 1}): {validation.issues}")

                    if validation.suggested_action == "fallback":
                        # Don't retry, go straight to fallback
                        break

            except anthropic.APIStatusError as e:
                logger.error(f"Claude API Status Error: status={e.status_code}, message={e.message}")
                last_issues = [f"API error: {e.status_code}"]
            except anthropic.APIConnectionError as e:
                logger.error(f"Claude API Connection Error: {e}")
                last_issues = ["Connection error"]
            except anthropic.APIError as e:
                logger.error(f"Claude API error: {e}")
                last_issues = [f"API error: {str(e)[:50]}"]
            except Exception as e:
                logger.error(f"Unexpected error: {type(e).__name__}: {e}")
                last_issues = [f"{type(e).__name__}"]

        # All attempts failed - use fallback
        logger.warning(f"All {max_attempts} attempts failed for {company_name}, using fallback")
        location = lead_data.get("location") if lead_data else None
        if location and location.strip():
            return AIGeneratedLine(
                line=f"Noticed your team serves {location}.",
                confidence_tier="B",
                artifact_type="LOCATION",
                artifact_used=location,
                reasoning=f"Fallback after {max_attempts} failed attempts: {', '.join(last_issues)}",
            )

        # Final fallback - generic line
        return AIGeneratedLine(
            line="Came across your company online.",
            confidence_tier="B",
            artifact_type="FALLBACK",
            artifact_used="",
            reasoning=f"All {max_attempts} generation attempts failed",
        )

    def _build_prompt(self, company_name: str, context: str) -> str:
        """Build the prompt for Claude."""
        return f"""Company: {company_name}

=== RESEARCH DATA ===
{context}
=== END RESEARCH ===

Write ONE cold email opener for {company_name} that triggers CURIOSITY and EGO.

SCAN THE DATA FOR (in priority order):
S-TIER (if found, use immediately):
- Awards/Rankings ("Best of...", "#1 in...", "Top 10...")
- Volume metrics (10,000 jobs, 5,000 customers)
- Media/Press mentions (TV, podcasts, news)
- Reviews with specific numbers (4.9 stars, 287 reviews)

A-TIER:
- Years in business (since 1985, 30 years)
- Family story (3rd generation, family-owned)
- Growth signals (hiring, expanding, new location)
- Tech stack (ServiceTitan, HubSpot)
- Team/Fleet size (25 trucks, 40 technicians)

B-TIER (only if nothing above):
- Specialty/niche focus
- Certifications (Carrier, Rheem)
- Warranty/guarantees

NEVER USE:
- Location alone ("Noticed you serve Denver")
- Generic services ("I saw you do plumbing")
- Vague praise ("Great company")

CRITICAL: Use EXACT numbers and names from the data. "4.9 stars" not "high rating". "Since 1992" not "many years".

Reply format:
LINE: [Complete 12-20 word opener that would make YOU want to respond]
TIER: [S/A/B based on data quality used]
TYPE: [AWARD/SCALE/MEDIA/REVIEWS/YEARS/STORY/GROWTH/TECH/TEAM/SPECIALTY/CERT]
ARTIFACT: [exact data point used, e.g., "4.9 stars, 287 reviews"]"""

    def _parse_response(self, response_text: str) -> AIGeneratedLine:
        """Parse Claude's response into structured output."""
        result = {
            "line": "Came across your company online.",
            "tier": "B",
            "type": "FALLBACK",
            "artifact": "",
            "reason": "Parse error",
        }

        # Use regex to extract fields - handles multi-line responses properly
        # Extract LINE: content (everything until TIER:, TYPE:, ARTIFACT:, or end)
        line_match = re.search(
            r'LINE:\s*(.+?)(?=\n\s*(?:TIER:|TYPE:|ARTIFACT:|REASON:)|$)',
            response_text,
            re.IGNORECASE | re.DOTALL
        )
        if line_match:
            # Clean up the line - remove newlines, extra whitespace
            extracted_line = line_match.group(1).strip()
            extracted_line = re.sub(r'\s+', ' ', extracted_line)  # Normalize whitespace
            result["line"] = extracted_line

        # Extract TIER
        tier_match = re.search(r'TIER:\s*([SAB])', response_text, re.IGNORECASE)
        if tier_match:
            result["tier"] = tier_match.group(1).upper()

        # Extract TYPE
        type_match = re.search(
            r'TYPE:\s*(\w+(?:[_\s]\w+)?)',
            response_text,
            re.IGNORECASE
        )
        if type_match:
            result["type"] = type_match.group(1).strip().upper().replace(" ", "_")

        # Extract ARTIFACT
        artifact_match = re.search(
            r'ARTIFACT:\s*(.+?)(?=\n\s*(?:TIER:|TYPE:|LINE:|REASON:)|$)',
            response_text,
            re.IGNORECASE | re.DOTALL
        )
        if artifact_match:
            result["artifact"] = artifact_match.group(1).strip()

        # Extract REASON
        reason_match = re.search(
            r'REASON:\s*(.+?)(?=\n\s*(?:TIER:|TYPE:|LINE:|ARTIFACT:)|$)',
            response_text,
            re.IGNORECASE | re.DOTALL
        )
        if reason_match:
            result["reason"] = reason_match.group(1).strip()

        # Clean up the line - remove quotes if present
        line = result["line"]
        if line.startswith('"') and line.endswith('"'):
            line = line[1:-1]
        elif line.startswith("'") and line.endswith("'"):
            line = line[1:-1]
        # Also handle case where only opening quote exists (truncation artifact)
        elif line.startswith('"') and '"' not in line[1:]:
            line = line[1:]
        elif line.startswith("'") and "'" not in line[1:]:
            line = line[1:]

        # Final validation - ensure line ends with proper punctuation
        line = line.strip()
        if line and line[-1] not in '.!?':
            line += '.'

        return AIGeneratedLine(
            line=line,
            confidence_tier=result["tier"],
            artifact_type=result["type"],
            artifact_used=result["artifact"],
            reasoning=result["reason"],
        )

    def _validate_and_clean(self, result: AIGeneratedLine, company_name: str) -> AIGeneratedLine:
        """Validate and clean the generated line."""
        line = result.line

        # Check for banned words - if found, use fallback instead of breaking the sentence
        line_lower = line.lower()
        has_banned_word = False
        for banned in BANNED_WORDS:
            if banned in line_lower:
                has_banned_word = True
                logger.warning(f"Line contains banned word '{banned}', will use fallback")
                break

        if has_banned_word:
            return AIGeneratedLine(
                line="Came across your company online.",
                confidence_tier="B",
                artifact_type="FALLBACK",
                artifact_used="",
                reasoning=f"Line contained banned word, regeneration needed",
            )

        # Ensure line ends with proper punctuation
        line = line.strip()
        if line and line[-1] not in '.!?':
            line += '.'

        # Ensure line doesn't start with a lowercase letter
        if line and line[0].islower():
            line = line[0].upper() + line[1:]

        # Check for incomplete sentences (missing words at end)
        # These patterns indicate likely truncation - articles/prepositions at end with no object
        truncation_endings = [
            r'\s+(a|an|the|to|of|in|for|with|and|or|but|that|this|your|their|its|from|by|on|at)\s*[.!?]?$',
        ]
        for pattern in truncation_endings:
            if re.search(pattern, line, re.IGNORECASE):
                logger.warning(f"Line appears truncated (ends with article/preposition): {line}")
                return AIGeneratedLine(
                    line="Came across your company online.",
                    confidence_tier="B",
                    artifact_type="FALLBACK",
                    artifact_used="",
                    reasoning="Generated line appeared truncated",
                )

        # Check for unclosed quotes (sign of truncation)
        quote_count = line.count('"') + line.count("'") + line.count('"') + line.count('"')
        if quote_count % 2 != 0:
            logger.warning(f"Line has unclosed quotes: {line}")
            return AIGeneratedLine(
                line="Came across your company online.",
                confidence_tier="B",
                artifact_type="FALLBACK",
                artifact_used="",
                reasoning="Generated line had unclosed quotes",
            )

        # Check word count - if too long, this is likely a bad generation
        word_count = len(line.split())
        if word_count > 20:
            logger.warning(f"Line too long ({word_count} words), using fallback")
            return AIGeneratedLine(
                line="Came across your company online.",
                confidence_tier="B",
                artifact_type="FALLBACK",
                artifact_used="",
                reasoning="Generated line was too long",
            )

        # If the line is empty or just punctuation
        if not line or len(line.strip('.,!? ')) < 5:
            return AIGeneratedLine(
                line="Came across your company online.",
                confidence_tier="B",
                artifact_type="FALLBACK",
                artifact_used="",
                reasoning="Generated line was empty or too short",
            )

        # Check for minimum word count (catches very truncated lines)
        if word_count < 5:
            logger.warning(f"Line too short ({word_count} words), using fallback")
            return AIGeneratedLine(
                line="Came across your company online.",
                confidence_tier="B",
                artifact_type="FALLBACK",
                artifact_used="",
                reasoning="Generated line was too short",
            )

        return AIGeneratedLine(
            line=line,
            confidence_tier=result.confidence_tier,
            artifact_type=result.artifact_type,
            artifact_used=result.artifact_used,
            reasoning=result.reasoning,
        )

    def test_connection(self) -> bool:
        """Test if the API key is valid."""
        try:
            self.client.messages.create(
                model=self.model,
                max_tokens=10,
                messages=[{"role": "user", "content": "Hi"}],
            )
            return True
        except anthropic.AuthenticationError:
            return False
        except anthropic.APIError:
            # Other API errors still mean the key is valid
            return True


def test_api_key(api_key: str) -> bool:
    """Test if an Anthropic API key is valid."""
    try:
        generator = AILineGenerator(api_key)
        return generator.test_connection()
    except Exception:
        return False
