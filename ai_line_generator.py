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

    SYSTEM_PROMPT = """You write cold email openers. Your job: extract REAL facts from research data and write personalized lines.

⚠️ CRITICAL RULE: You must ONLY use facts that appear in the research data provided.
NEVER invent, guess, or copy example numbers. If you can't find real data, output NO_DATA_FOUND.

THE FORMULA:
[Real fact from research] — [ego-validating observation]

STRUCTURE (copy this pattern, NOT the numbers):
- "[X] stars across [Y] reviews — trust like that is earned."
- "Serving [City] since [Year] — [Z] years of building something real."
- "[Certification] certified — your crew knows their craft."
- "[Award name] recognition — that's consistency."

WHAT TO EXTRACT FROM RESEARCH:
1. VERDICTS/SETTLEMENTS: Dollar amounts from cases (look for "$", "million", "verdict", "settlement", "recovered")
2. REVIEWS: Star ratings and review counts (look for "stars", "reviews", "rating")
3. AWARDS: Super Lawyers, Avvo, Best Lawyers, BBB A+ (look for award names)
4. CERTIFICATIONS: IICRC, WRT, ASD (look for cert names)
5. YEARS: Founding date or years in business (look for "since", "founded", "established", years like "1987")
6. TEAM: Number of attorneys, technicians, trucks (look for numbers + role names)
7. RESPONSE: 24/7 availability, response guarantees (look for "24/7", "minute response")

BANNED BEHAVIORS:
❌ Using numbers NOT in the research (like inventing "$2.3M" or "287 reviews")
❌ Generic phrases: "came across", "noticed your company", "found your website"
❌ Starting with "I noticed" or "I saw"
❌ These words: recently, just, new, exciting, impressive, amazing, innovative, incredible

OUTPUT FORMAT:
LINE: [12-20 word opener using ONLY facts from research]
TIER: [S/A/B]
TYPE: [VERDICT/REVIEWS/AWARD/YEARS/TEAM/SPECIALTY/NONE]
ARTIFACT: [exact fact you extracted from research]

If no usable data found:
LINE: NO_DATA_FOUND
TIER: B
TYPE: NONE
ARTIFACT: none"""

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

        # All attempts failed - use PUNCHY fallbacks based on available data
        logger.warning(f"All {max_attempts} attempts failed for {company_name}, using smart fallback")

        location = lead_data.get("location") if lead_data else None
        person_title = lead_data.get("person_title") if lead_data else None
        keywords = lead_data.get("keywords") if lead_data else None

        import random

        # PUNCHY fallback templates - follow the formula: [Fact] — [Ego validation]
        fallback_templates = []

        if keywords:
            # Use practice area/services
            practice = keywords.split(",")[0].strip() if "," in keywords else keywords.strip()
            if practice and len(practice) > 3 and len(practice) < 35:
                fallback_templates.extend([
                    f"Pure focus on {practice} when others chase everything — that discipline pays off.",
                    f"{practice} only, no distractions — clients can tell you're not spread thin.",
                    f"All-in on {practice} while competitors dabble — expertise like that compounds.",
                    f"Dedicating a practice to {practice} — that's how you become the go-to.",
                ])

        if location and location.strip():
            city = location.split(",")[0].strip() if "," in location else location.strip()
            if city and len(city) > 2:
                fallback_templates.extend([
                    f"Building a reputation in {city} takes years — you've put in the work.",
                    f"Still standing in {city} while others come and go — that's staying power.",
                    f"Deep roots in {city} — clients can feel that local commitment.",
                    f"{city} trusts {company_name} — that wasn't handed to you.",
                ])

        if person_title:
            title_lower = person_title.lower()
            if "partner" in title_lower:
                fallback_templates.append(f"Making partner means you've proven yourself — that track record matters.")
            elif "founder" in title_lower or "owner" in title_lower:
                fallback_templates.append(f"Building {company_name} from scratch — founders know what real work looks like.")
            elif "director" in title_lower:
                fallback_templates.append(f"Running operations at {company_name} — the firm depends on leaders like you.")

        # Strong generic fallbacks with company name
        fallback_templates.extend([
            f"{company_name} — a name that didn't build itself overnight.",
            f"Firms like {company_name} don't survive by accident — you've earned your spot.",
            f"Running {company_name} in this market takes grit — that shows.",
            f"The fact that {company_name} is still growing says something about leadership.",
        ])

        # Pick a random fallback for variety
        chosen_line = random.choice(fallback_templates)

        return AIGeneratedLine(
            line=chosen_line,
            confidence_tier="B",
            artifact_type="SMART_FALLBACK",
            artifact_used=location or keywords or company_name,
            reasoning=f"Smart fallback after {max_attempts} attempts: {', '.join(last_issues)}",
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

╔══════════════════════════════════════════════════════════════════╗
║  ⚠️  CRITICAL: ONLY USE DATA FROM THE RESEARCH BELOW  ⚠️         ║
║  DO NOT INVENT OR MAKE UP ANY FACTS, NUMBERS, OR AWARDS          ║
║  If you can't find real data below, say "NO_DATA_FOUND"          ║
╚══════════════════════════════════════════════════════════════════╝

========== RESEARCH DATA FOR {company_name} ==========
{context}
========== END RESEARCH DATA ==========

YOUR TASK:
1. CAREFULLY READ the research data above
2. FIND a specific fact (number, rating, award, year) that is ACTUALLY IN THE DATA
3. Write a 12-20 word opener using ONLY facts from the research

FORMULA: [Exact fact from research] — [ego-validating observation]

WHAT TO LOOK FOR (in priority order):
- Dollar amounts: verdicts, settlements, recovered amounts
- Star ratings: "4.8 stars", "4.9", review counts
- Awards: Super Lawyers, Avvo rating, Best Lawyers, BBB A+
- Certifications: IICRC, WRT, ASD
- Years: "since 1987", "25 years", founding dates
- Team size: number of attorneys, technicians, trucks
- Response time: "24/7", "60-minute response"

STYLE GUIDE:
✅ "4.8 stars across 156 reviews — trust like that is earned."
✅ "Serving Dallas since 1992 — 32 years of building something real."
✅ "IICRC certified with WRT credentials — your crew knows their craft."

❌ NEVER invent verdicts, dollar amounts, or awards not in the data
❌ NEVER use generic phrases like "came across your company"
❌ NEVER start with "I noticed" or "I saw"

OUTPUT FORMAT:
LINE: [your 12-20 word opener with REAL data from above]
TIER: [S if verdict/award/rating, A if years/team, B if only location/generic]
TYPE: [VERDICT/REVIEWS/AWARD/YEARS/TEAM/SPECIALTY/NONE]
ARTIFACT: [copy the EXACT data point you used from the research]

If NO useful data found, output:
LINE: NO_DATA_FOUND
TIER: B
TYPE: NONE
ARTIFACT: none"""

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
