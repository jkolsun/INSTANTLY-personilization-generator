"""
AI-powered personalization line generator using Claude API.

Replaces rigid templates with intelligent, context-aware line generation.
"""
import logging
import re
from dataclasses import dataclass
from typing import Optional

import anthropic

logger = logging.getLogger(__name__)


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

    SYSTEM_PROMPT = """You write cold email openers that make business owners WANT to open the email. Your goal: stroke their ego and create curiosity.

POWERFUL HOOKS BY DATA TYPE:

REVENUE ($2M+):
- "Building a $2M+ plumbing operation in this market tells me you've figured something out."
- "Scaling past $2M in revenue while most plumbers stay stuck — that caught my attention."

REVIEWS/RATINGS (4.5+ stars, 100+ reviews):
- "Your 4.8-star rating across 200+ reviews means you're doing something 90% of plumbers aren't."
- "150 five-star reviews don't happen by accident — you've clearly built something special."

YEARS IN BUSINESS (10+ years):
- "Surviving 25 years in plumbing while others come and go? That's earned respect."
- "Building a business that's thrived since 1998 takes serious operational discipline."

TECH STACK (Freshdesk, ServiceTitan, etc.):
- "The Freshdesk setup tells me you're more sophisticated than most in your industry."
- "Running ServiceTitan for dispatching puts you ahead of 95% of your competitors."

MULTIPLE LOCATIONS / EXPANSION:
- "Growing to 3 locations in this economy? Most can't even keep one running."
- "Expanding while others are contracting — that takes confidence and cash flow."

SPECIFIC SERVICES / NICHE:
- "Specializing in tankless water heaters while everyone else does everything — smart positioning."
- "Your focus on commercial plumbing sets you apart from the residential-only crowd."

FRANCHISE / SUBSIDIARY:
- "Being part of Threshold Brands gives you scale most independents can't match."

RULES:
- Make them feel IMPRESSIVE and SUCCESSFUL
- Be specific - the more specific, the more they'll open
- 12-20 words, COMPLETE sentences only
- Sound human and genuine, not salesy
- NEVER invent details - only use what's in the data
- ALWAYS write complete sentences - never leave words missing at the end"""

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

        try:
            logger.info(f"Calling Claude API with model={self.model} for {company_name}")
            logger.info(f"Context being sent to Claude:\n{context[:500]}...")

            response = self.client.messages.create(
                model=self.model,
                max_tokens=500,  # Increased to prevent any truncation
                system=self.SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )

            raw_response = response.content[0].text
            logger.info(f"Claude API SUCCESS for {company_name}")
            logger.info(f"Claude raw response:\n{raw_response}")
            result = self._parse_response(raw_response)

            # Validate and clean the output
            result = self._validate_and_clean(result, company_name)

            # If Claude returned generic fallback but we have location, use location-based line
            if result.line.lower().strip().rstrip('.') == "came across your company online":
                location = lead_data.get("location") if lead_data else None
                if location and location.strip():
                    result = AIGeneratedLine(
                        line=f"Noticed your team serves {location}.",
                        confidence_tier="B",
                        artifact_type="LOCATION",
                        artifact_used=location,
                        reasoning="Using location-based fallback",
                    )

            return result

        except anthropic.APIStatusError as e:
            # Specific API status errors (401, 403, 404, 429, 500, etc.)
            logger.error(f"Claude API Status Error: status={e.status_code}, message={e.message}")
            return AIGeneratedLine(
                line="Came across your company online.",
                confidence_tier="B",
                artifact_type="API_ERROR",
                artifact_used=f"HTTP {e.status_code}",
                reasoning=f"CLAUDE HTTP {e.status_code}: {e.message[:80]}",
            )
        except anthropic.APIConnectionError as e:
            logger.error(f"Claude API Connection Error: {e}")
            return AIGeneratedLine(
                line="Came across your company online.",
                confidence_tier="B",
                artifact_type="CONNECTION_ERROR",
                artifact_used="Connection failed",
                reasoning=f"CONNECTION ERROR: {str(e)[:80]}",
            )
        except anthropic.APIError as e:
            logger.error(f"Claude API error: {e}")
            return AIGeneratedLine(
                line="Came across your company online.",
                confidence_tier="B",
                artifact_type="API_ERROR",
                artifact_used=str(e)[:100],
                reasoning=f"CLAUDE API FAILED: {str(e)[:100]}",
            )
        except Exception as e:
            logger.error(f"Unexpected error in Claude generation: {type(e).__name__}: {e}")
            return AIGeneratedLine(
                line="Came across your company online.",
                confidence_tier="B",
                artifact_type="UNEXPECTED_ERROR",
                artifact_used=f"{type(e).__name__}",
                reasoning=f"{type(e).__name__}: {str(e)[:80]}",
            )

    def _build_prompt(self, company_name: str, context: str) -> str:
        """Build the prompt for Claude."""
        return f"""Company: {company_name}

=== RESEARCH DATA ===
{context}
=== END RESEARCH ===

Write ONE cold email opener that makes the owner of {company_name} feel IMPRESSIVE and want to read more.

PRIORITY (use the first one you find):
1. Annual Revenue ($2M+) — "Building a $2M+ operation tells me you've figured something out."
2. Reviews/Ratings — "Your 4.8 stars across 150+ reviews means you're doing something right."
3. Years in Business — "25 years in plumbing while others come and go? That's earned respect."
4. Tech Stack — "Running Freshdesk tells me you're more sophisticated than most."
5. Multiple Locations — "Growing to 3 locations in this economy takes serious confidence."
6. Specific Services — "Specializing in tankless installs while others do everything — smart."
7. Location — Only if nothing else!

BAD (will get deleted):
- "Noticed your team serves Denver."
- "I saw you offer plumbing services."
- Generic anything.

Find the MOST IMPRESSIVE detail and make it sound noteworthy.

Reply:
LINE: [your 12-20 word ego-stroking opener]
TIER: [S/A/B]
TYPE: [REVENUE/REVIEWS/YEARS/TOOL/SERVICE/LOCATION]
ARTIFACT: [the specific detail you used]"""

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
