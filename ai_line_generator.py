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
    Optimized for LEGAL FIRMS and RESTORATION COMPANIES.
    """

    SYSTEM_PROMPT = """Write a cold email opener that sounds personal and conversational.

You're writing TO the person, not ABOUT their company. Use "you/your" language.

WRONG (sounds like a news article):
- "The McGuire Firm has secured over $29M in verdicts."
- "Smith Law boasts a 4.9 star rating."

RIGHT (sounds like a personal email):
- "Securing $29M in verdicts for your clients, that kind of track record speaks for itself."
- "Your 4.9 stars across 200+ reviews caught my eye, that's rare in this space."
- "30 years building your practice in Dallas, you've clearly figured something out."

RULES:
1. Use "you/your" to address them directly
2. Use EXACT data from the research (don't invent numbers)
3. Sound like a human who did their homework, not a robot reading stats
4. 12-20 words, conversational tone

OUTPUT:
LINE: [personal opener using "you/your"]
TIER: [S/A/B]
TYPE: [data type]
ARTIFACT: [exact data from research]

If no data: LINE: NO_DATA_FOUND"""

    def __init__(self, api_key: str, model: str = "claude-3-haiku-20240307"):
        """Initialize the AI line generator."""
        # Use Claude 3 Haiku - stable and proven model
        # Sonnet produces better, more thoughtful personalization than Haiku
        self.api_key = api_key
        self.model = model

        # Log API key status (masked for security)
        if not api_key:
            logger.error("ANTHROPIC API KEY IS EMPTY - Claude calls will fail!")
        else:
            masked = f"{api_key[:10]}...{api_key[-4:]}" if len(api_key) > 14 else "***"
            logger.info(f"AI Generator initialized with key: {masked}, model: {self.model}")

        self.client = anthropic.Anthropic(api_key=api_key)

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
        # FAIL FAST if API key is missing
        if not self.api_key:
            logger.error(f"Cannot generate line for {company_name} - ANTHROPIC_API_KEY is not set!")
            return AIGeneratedLine(
                line=f"Firms like {company_name} don't survive by accident — you've earned your spot.",
                confidence_tier="B",
                artifact_type="NO_API_KEY",
                artifact_used="",
                reasoning="ANTHROPIC_API_KEY not configured - using fallback",
            )

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
            logger.warning(f"No research data for {company_name}, using fallback")
            return AIGeneratedLine(
                line="Came across your company online.",
                confidence_tier="B",
                artifact_type="FALLBACK",
                artifact_used="",
                reasoning="No data available for personalization",
            )

        # Check if research has ANY useful data points (numbers, ratings, awards)
        # If not, skip Claude call and go straight to fallback
        import re
        has_useful_data = bool(
            re.search(r'\$[\d,]+', context) or  # Dollar amounts
            re.search(r'\d+\.?\d*\s*(?:star|review|rating)', context, re.IGNORECASE) or  # Reviews
            re.search(r'(?:avvo|super lawyer|martindale|best lawyer)', context, re.IGNORECASE) or  # Legal awards
            re.search(r'(?:IICRC|WRT|ASD|BBB)', context, re.IGNORECASE) or  # Certifications
            re.search(r'(?:since|founded|established)\s*\d{4}', context, re.IGNORECASE) or  # Years
            re.search(r'\d+\s*(?:attorney|lawyer|truck|technician|employee)', context, re.IGNORECASE)  # Team size
        )

        if not has_useful_data:
            logger.warning(f"Research for {company_name} has no useful data points, skipping Claude")
            # Go straight to smart fallback (will be handled at end of function)
            return self._generate_smart_fallback(company_name, lead_data)

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

                # Check if Claude couldn't find usable data - go straight to fallback
                if result.artifact_type == "NO_DATA" or "NO_DATA_FOUND" in result.line.upper():
                    logger.warning(f"Claude found no usable data for {company_name}, using smart fallback")
                    last_issues = ["No usable research data found"]
                    break  # Exit retry loop and use smart fallback

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

            except anthropic.AuthenticationError as e:
                logger.error(f"AUTHENTICATION FAILED - Invalid API key! {e}")
                last_issues = ["Invalid API key - check ANTHROPIC_API_KEY"]
                break  # Don't retry auth errors
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
                import traceback
                logger.error(f"Full traceback: {traceback.format_exc()}")
                last_issues = [f"{type(e).__name__}"]

        # All attempts failed - use smart fallback
        logger.warning(f"All {max_attempts} attempts failed for {company_name}, using smart fallback")
        return self._generate_smart_fallback(company_name, lead_data)

    def _generate_smart_fallback(self, company_name: str, lead_data: Optional[dict]) -> AIGeneratedLine:
        """Generate a smart fallback when no research data is available."""
        import random

        location = lead_data.get("location") if lead_data else None
        person_title = lead_data.get("person_title") if lead_data else None
        keywords = lead_data.get("keywords") if lead_data else None

        fallback_templates = []

        if keywords:
            practice = keywords.split(",")[0].strip() if "," in keywords else keywords.strip()
            if practice and len(practice) > 3 and len(practice) < 35:
                fallback_templates.extend([
                    f"Your focus on {practice} really sets the firm apart from generalists.",
                    f"Specializing in {practice} takes discipline, and clients notice that commitment.",
                    f"Going deep on {practice} instead of chasing everything shows real expertise.",
                ])

        if location and location.strip():
            city = location.split(",")[0].strip() if "," in location else location.strip()
            if city and len(city) > 2:
                fallback_templates.extend([
                    f"Building a strong reputation in {city} takes years of solid work.",
                    f"You've clearly become a trusted name in {city}, that takes time.",
                    f"Being a go-to firm in {city} doesn't happen by accident.",
                ])

        fallback_templates.extend([
            f"{company_name} has clearly built something that stands the test of time.",
            f"Firms like {company_name} don't last without doing things the right way.",
            f"Running {company_name} in this market shows real entrepreneurial grit.",
        ])

        chosen_line = random.choice(fallback_templates)

        return AIGeneratedLine(
            line=chosen_line,
            confidence_tier="B",
            artifact_type="SMART_FALLBACK",
            artifact_used=location or keywords or company_name,
            reasoning="No useful research data found",
        )

    def _build_prompt(self, company_name: str, context: str) -> str:
        """Build the prompt for Claude with industry-specific guidance."""
        # Detect industry from context
        context_lower = context.lower()
        is_legal = any(kw in context_lower for kw in ["attorney", "lawyer", "law firm", "legal", "verdict", "avvo", "martindale", "settlement", "litigation", "practice", "esquire"])
        is_restoration = any(kw in context_lower for kw in ["restoration", "water damage", "fire damage", "iicrc", "mold", "cleanup", "insurance claim"])

        industry_hint = ""
        if is_legal:
            industry_hint = "⚖️ THIS IS A LAW FIRM. Look for: verdicts, Avvo ratings, Super Lawyers, Google reviews, years practicing, team size."
        elif is_restoration:
            industry_hint = "🔧 THIS IS A RESTORATION COMPANY. Look for: IICRC certs, insurance partnerships, response time, reviews."
        else:
            industry_hint = "Look for: reviews, years in business, team size, awards, certifications."

        return f"""COMPANY: {company_name}
{industry_hint}

RESEARCH DATA:
{context}

Write a personal cold email opener (12-20 words) using a fact from above.

IMPORTANT:
- Write TO them using "you/your", not ABOUT them in third person
- Use the exact numbers from the research
- Sound like a human sending a personal email, not a news headline

EXAMPLES OF TONE:
✓ "Your $29M in verdicts tells me you know how to win the cases that matter."
✓ "4.9 stars with 340 reviews, your clients clearly trust you with their cases."
✓ "Building your practice since 1987, that's 37 years of earning trust in this market."

✗ "The firm has secured $29M in verdicts." (third person, sounds like news)
✗ "Smith Law boasts impressive results." (no specific data, generic)

OUTPUT:
LINE: [personal opener with "you/your"]
TIER: [S/A/B]
TYPE: [data type]
ARTIFACT: [exact data used]"""

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

        # Check if Claude returned NO_DATA_FOUND - signal that we need fallback
        if "NO_DATA_FOUND" in line.upper() or result["type"] == "NONE":
            return AIGeneratedLine(
                line="NO_DATA_FOUND",
                confidence_tier="B",
                artifact_type="NO_DATA",
                artifact_used="",
                reasoning="Claude found no usable data in research",
            )

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
