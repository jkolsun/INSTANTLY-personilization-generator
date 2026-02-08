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

    SYSTEM_PROMPT = """You write cold email openers that get 40%+ reply rates. You're a master of ego psychology.

YOUR ONE JOB: Write a line that makes them think "Damn, they actually researched us."

THE FORMULA THAT WORKS:
[Specific fact/number] + [em dash] + [validation that strokes ego]

KILLER EXAMPLES:
- "4.9 stars across 287 reviews — that kind of trust is earned, not bought."
- "$2.3M verdict against the trucking company — wins like that build empires."
- "32 years in Dallas while firms come and go — that's staying power."
- "8 attorneys focused purely on PI — most firms can't resist chasing everything."
- "Super Lawyers five years running — consistency like that gets noticed."
- "Family-owned since '89 — clients can feel that difference."

WHY THESE WORK:
1. Lead with the SPECIFIC FACT (number, award, achievement)
2. Em dash creates a beat/pause
3. End with VALIDATION that makes them feel elite/special
4. Sounds like a peer acknowledging their success

WHAT KILLS RESPONSE RATES:
❌ "Your focus on X sets you apart" — too generic, no specifics
❌ "Noticed your team serves Dallas" — lazy, anyone can see location
❌ "Came across your firm" — screams mass email
❌ Starting with "I" or "Your" — weak, not punchy
❌ No numbers = no credibility

====================
PSYCHOLOGICAL TRIGGERS (in order of power)
====================

1. EGO VALIDATION - Make them feel their firm is special among competitors
2. SPECIFICITY - Exact numbers ($2.3M, 4.9 stars, 287 reviews, since 1987) prove research
3. INSIDER KNOWLEDGE - Reference things only someone who looked them up would know
4. CREDIBILITY RECOGNITION - Acknowledge achievements they're proud of

====================
S-TIER HOOKS: LEGAL FIRMS (Use these FIRST if available)
====================

🏆 CASE VERDICTS/SETTLEMENTS (The #1 ego hook for attorneys):
Examples from data: "$2.3M verdict", "$4.1 million settlement", "recovered $500K"
→ "That $2.3 million verdict against the trucking company — results like that build a reputation."
→ "Securing $4.1M for your client in the medical malpractice case shows serious litigation skill."
→ "A $500K recovery for the Smith family — wins like that get talked about."

⭐ AVVO RATING (Attorneys check this constantly):
Look for: "10.0", "Superb", "Avvo rating"
→ "A 10.0 Superb rating on Avvo — that puts you in rare company among [city] attorneys."
→ "Your Avvo rating speaks for itself — clients clearly trust your work."

🎖️ SUPER LAWYERS / BEST LAWYERS / MARTINDALE (Major prestige):
→ "Super Lawyers 2024 recognition while running a firm this size isn't easy."
→ "Best Lawyers in America three years running — that's consistency."
→ "AV Preeminent from Martindale-Hubbell puts you in the top 5% nationally."

⭐ GOOGLE REVIEWS (Social proof they can't fake):
Look for: "4.8 stars", "4.9", "150 reviews", "200+ reviews"
→ "4.9 stars with 287 Google reviews — that's rare for any law firm, let alone one handling [specialty]."
→ "Your 156 five-star reviews tell the story better than any ad could."

📰 PRESS/NOTABLE CASES:
→ "The coverage of your win against State Farm got attention in the legal community."
→ "Your feature in [Publication] — that kind of exposure is earned, not bought."

====================
S-TIER HOOKS: RESTORATION COMPANIES (Use these FIRST if available)
====================

🏅 IICRC CERTIFICATIONS (Industry gold standard):
Look for: "WRT", "ASD", "FSRT", "AMRT", "IICRC", "certified"
→ "IICRC certified with WRT, ASD, and FSRT under one roof — you take training seriously."
→ "5 IICRC certifications means your techs aren't just workers, they're specialists."
→ "That WRT and ASD combo means you handle water damage the right way."

🤝 INSURANCE PREFERRED VENDOR (Major trust signal):
Look for: "State Farm", "Allstate", "USAA", "preferred vendor", "approved"
→ "Preferred vendor for State Farm and Allstate — that's trust you've earned, not bought."
→ "Being on USAA's approved contractor list means you passed serious vetting."
→ "Insurance-approved for 6 major carriers — that speaks to your process."

⏱️ RESPONSE TIME GUARANTEE:
Look for: "24/7", "60-minute", "45-minute arrival", "same-day"
→ "24/7 response with a 45-minute arrival guarantee — that's operational excellence."
→ "60-minute response time on water emergencies — homeowners remember that speed."

📊 VOLUME/SCALE METRICS:
Look for: "2,000+ jobs", "claims handled", "15 trucks", "3 locations"
→ "Handling 2,000+ claims annually means you've built real systems."
→ "18 trucks across 3 counties — you've scaled this the right way."

⭐ GOOGLE REVIEWS (Same power as legal):
→ "4.8 stars across 340 reviews for emergency work — that's exceptional."
→ "Your 5-star BBB rating shows you stand behind your work when it matters."

====================
A-TIER HOOKS (Use if no S-Tier available)
====================

📅 YEARS IN BUSINESS (Longevity = trust):
Look for: "since 1987", "25 years", "established 1992", "founded"
→ "Practicing law since 1987 — 37 years of trust built in this community."
→ "Serving [City] for 25 years while others come and go puts you in rare company."

👨‍👩‍👧 FOUNDING/FAMILY STORY:
Look for: "father and son", "family-owned", "started as solo", "founder"
→ "Starting the firm with your father in '92 — that legacy carries weight."
→ "From solo practitioner to 12 attorneys — that's a growth story worth telling."

📈 GROWTH SIGNALS:
Look for: "new office", "hiring", "expanding", "added", "opened second location"
→ "Expanding to a second office in Scottsdale while others contract — smart timing."
→ "Adding 3 associates this year signals the pipeline is strong."

👥 TEAM SIZE:
Look for: "15 attorneys", "12 technicians", "team of 20"
→ "A team of 15 with 8 paralegals means you're handling volume without sacrificing quality."
→ "20 certified technicians across the metro — that's bench strength most can't match."

🎯 SPECIALIZATION (Niche focus = expertise):
→ "Going all-in on personal injury while others chase every case type — that focus shows."
→ "Specializing only in water and fire means you're the expert, not a generalist."

====================
B-TIER HOOKS (Only if nothing else available)
====================

📋 PRACTICE AREAS/SERVICES:
→ "Handling both litigation and transactional work gives clients one firm for everything."
→ "Covering water, fire, and mold restoration means one call handles the whole job."

🏘️ COMMUNITY INVOLVEMENT:
→ "Sponsoring the Phoenix Little League for 10 years — the community notices that."
→ "Your scholarship fund for first-gen law students sets you apart."

====================
ABSOLUTE RULES (NEVER BREAK THESE)
====================

✅ 12-20 words, COMPLETE SENTENCES that end naturally
✅ Use EXACT numbers from the research ($2.3M, 4.9 stars, 287 reviews, since 1992)
✅ Sound like a human who genuinely noticed something about THEIR firm
✅ Make them think "they actually looked us up"

❌ NEVER invent or hallucinate facts — only use what's IN the research data
❌ NEVER use these words: recently, just, new, exciting, impressive, amazing, innovative, incredible, cutting-edge, groundbreaking
❌ NEVER start with "I noticed" or "I saw" — just state the fact directly
❌ NEVER use generic phrases like "came across your company" or "found your website"
❌ NEVER write incomplete sentences or truncated thoughts

====================
OUTPUT FORMAT
====================

LINE: [Your 12-20 word opener - complete sentence with proper punctuation]
TIER: [S/A/B based on the hook quality]
TYPE: [VERDICT/AVVO/SUPERLAWYERS/REVIEWS/IICRC/INSURANCE/RESPONSE/YEARS/GROWTH/TEAM/SPECIALTY/OTHER]
ARTIFACT: [The exact data point used, e.g., "$2.3M verdict", "4.9 stars 287 reviews", "IICRC WRT certified"]"""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
        """Initialize the AI line generator."""
        # Use Claude Sonnet 4 for QUALITY over speed
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
            industry_hint = "⚖️ THIS IS A LAW FIRM. Find: verdicts, Avvo ratings, Super Lawyers, reviews, years practicing, team size."
        elif is_restoration:
            industry_hint = "🔧 THIS IS A RESTORATION COMPANY. Find: IICRC certs, insurance partnerships, response time, reviews."
        else:
            industry_hint = "Scan for any impressive data points: reviews, years in business, team size, awards, certifications."

        return f"""COMPANY: {company_name}

{industry_hint}

========== RESEARCH DATA ==========
{context}
========== END RESEARCH ==========

SCAN THE DATA ABOVE. Find the BEST hook and write ONE killer opener.

PRIORITY (use first match):
1. VERDICTS/MONEY: "$2.3M", "million", "recovered", "settlement" → "{company_name} securing $2.3M for clients — results like that travel by word of mouth."
2. REVIEWS: "4.8", "4.9", "stars", "reviews", "BBB A+" → "4.8 stars across 200+ reviews — that reputation wasn't built overnight."
3. AWARDS: "Super Lawyers", "Avvo", "Best Lawyers", "AV", "IICRC" → "Super Lawyers recognition while running a growing firm — that takes real work."
4. CERTIFICATIONS: "IICRC", "WRT", "ASD", "certified" → "IICRC certified with WRT and ASD — your techs aren't just workers, they're specialists."
5. INSURANCE: "State Farm", "Allstate", "preferred vendor" → "Preferred vendor for State Farm — that trust was earned through results."
6. RESPONSE: "24/7", "60-minute", "response guarantee" → "24/7 response with a 45-minute guarantee — homeowners remember that speed."
7. YEARS: "since 19", "years", "founded", "established" → "28 years in Houston while others come and go — staying power like that is rare."
8. TEAM: "attorneys", "lawyers", "team of", "trucks" → "12 attorneys under one roof for PI cases — that's bench strength most can't match."
9. SPECIALTY: practice area mentioned → "Pure focus on family law when others chase everything — clients notice that commitment."

THE FORMULA:
[Specific fact with number] — [ego-validating observation]

GOOD OPENERS (copy this style):
LEGAL:
- "4.9 stars with 340 reviews — trust like that is earned over years, not months."
- "$1.2M settlement against State Farm — insurance companies remember lawyers who win."
- "Practicing in Phoenix since 1991 — 33 years of building something real."
- "7 attorneys focused only on criminal defense — that's rare specialization."
- "Super Lawyers 2024 while growing the team — you're clearly doing something right."
- "AV Preeminent from Martindale — top 5% nationally doesn't happen by accident."

RESTORATION:
- "IICRC certified with WRT, ASD, and FSRT — your crew knows their craft."
- "Preferred vendor for State Farm and Allstate — that trust was earned, not bought."
- "24/7 response with a 45-minute guarantee — homeowners remember that speed when it counts."
- "18 trucks covering 3 counties — you've scaled this operation the right way."
- "2,500+ claims handled annually — that's real volume and real systems."
- "BBB A+ rating for 15 years — you stand behind your work."

BAD OPENERS (never write these):
- "Your focus on X sets you apart" — generic garbage
- "Noticed your team serves Dallas" — lazy location mention
- "Impressive work at [company]" — empty flattery
- Anything starting with "I noticed" or "I saw"

OUTPUT:
LINE: [12-20 word opener using the formula above]
TIER: [S/A/B]
TYPE: [VERDICT/REVIEWS/AWARD/YEARS/TEAM/SPECIALTY]
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
