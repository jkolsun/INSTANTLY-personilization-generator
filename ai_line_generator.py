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

    SYSTEM_PROMPT = """You are an expert at writing cold email opening lines that get responses.

Your output is the FIRST LINE of a cold email. It must:
1. Be a complete sentence (subject + verb + punctuation)
2. Flow naturally into the email body—write an OPENER, not a standalone fact
3. Address the RECIPIENT directly (use 'your', 'you') within the first few words
4. Be 8-18 words

STRICT RULES:
- Use ONLY information explicitly present in the data provided. Never invent names, clients, events, or details.
- NEVER claim to have attended events, met people, seen booths, or had experiences in person.
- Start with: 'Noticed your...', 'Saw your...', 'Saw that...', 'Your team's...', or 'Came across your...'
- Do NOT start with the company name as subject ('Zephyr's hoods are...' = WRONG)
- NEVER use timing words: recently, just, new, launched, upcoming, soon, now, this year
- NEVER use hype words: impressive, amazing, innovative, incredible, great, awesome, leading, best

If data is weak/generic, output: 'Noticed your team serves [location].' Do not embellish.

BAD (never write):
- 'Zephyr's range hoods are popular.' (statement, not opener)
- 'I saw your booth at the Expo.' (fabricated)
- 'Your work impressed the Smiths.' (invented name)
- 'Your expertise is .' (incomplete)"""

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
            logger.info(f"Context length: {len(context)} chars")

            response = self.client.messages.create(
                model=self.model,
                max_tokens=300,
                system=self.SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )

            logger.info(f"Claude API SUCCESS for {company_name}")
            result = self._parse_response(response.content[0].text)

            # Validate and clean the output
            result = self._validate_and_clean(result, company_name)

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
        return f"""Write a cold email opening line for {company_name}.

DATA (use ONLY what's here—do not invent):
{context}

INSTRUCTIONS:
1. Find the MOST SPECIFIC verifiable detail (tool name, client name, exact service, location)
2. Write ONE line, 8-18 words, that works as an email opener
3. Start with 'Noticed', 'Saw', or 'Your' — address the recipient, not the company
4. If data is generic, use: 'Noticed your team serves [location].'

CRITICAL RULES:
- ONLY use facts from the DATA above. Do NOT invent names, clients, events, or details.
- NEVER claim to have attended events, met people, or seen booths in person.
- Do NOT start with company name as subject (wrong: "Zephyr's hoods are popular")

TIER GUIDE:
S = Specific tools, named clients, exact quotes from site
A = Specific services, certifications, hiring signals
B = Location only, generic description

FORMAT (follow exactly):
LINE: [your opener here]
TIER: [S/A/B]
TYPE: [TOOL_PLATFORM/CLIENT_OR_PROJECT/EXACT_PHRASE/SERVICE_PROGRAM/LOCATION/COMPANY_DESCRIPTION/FALLBACK]
ARTIFACT: [specific detail used, or 'none' if generic]
REASON: [one sentence why this is verifiable]

Write for {company_name}:"""

    def _parse_response(self, response_text: str) -> AIGeneratedLine:
        """Parse Claude's response into structured output."""
        lines = response_text.strip().split("\n")

        result = {
            "line": "Came across your company online.",
            "tier": "B",
            "type": "FALLBACK",
            "artifact": "",
            "reason": "Parse error",
        }

        for line in lines:
            line = line.strip()
            if line.upper().startswith("LINE:"):
                result["line"] = line[5:].strip()
            elif line.upper().startswith("TIER:"):
                tier = line[5:].strip().upper()
                if tier in ["S", "A", "B"]:
                    result["tier"] = tier
            elif line.upper().startswith("TYPE:"):
                result["type"] = line[5:].strip().upper().replace(" ", "_")
            elif line.upper().startswith("ARTIFACT:"):
                result["artifact"] = line[9:].strip()
            elif line.upper().startswith("REASON:"):
                result["reason"] = line[7:].strip()

        # Clean up the line - remove quotes if present
        line = result["line"]
        if line.startswith('"') and line.endswith('"'):
            line = line[1:-1]
        if line.startswith("'") and line.endswith("'"):
            line = line[1:-1]

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

        # Remove any banned words
        line_lower = line.lower()
        for banned in BANNED_WORDS:
            if banned in line_lower:
                # Try to remove the banned word and surrounding context
                pattern = rf'\b{re.escape(banned)}\b\s*'
                line = re.sub(pattern, '', line, flags=re.IGNORECASE)
                logger.warning(f"Removed banned word '{banned}' from line")

        # Ensure line ends with proper punctuation
        line = line.strip()
        if line and not line[-1] in '.!?':
            line += '.'

        # Ensure line doesn't start with a lowercase letter
        if line and line[0].islower():
            line = line[0].upper() + line[1:]

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
