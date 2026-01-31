"""
AI-powered personalization line generator using Claude API.

Replaces rigid templates with intelligent, context-aware line generation.
"""
import logging
from dataclasses import dataclass
from typing import Optional

import anthropic

from config import ArtifactType, ConfidenceTier, ARTIFACT_CONFIDENCE

logger = logging.getLogger(__name__)


@dataclass
class AIGeneratedLine:
    """Result from AI line generation."""
    line: str
    confidence_tier: str
    artifact_type: str
    artifact_used: str
    reasoning: str


class AILineGenerator:
    """
    Generate personalization lines using Claude API.

    Uses Claude Haiku for fast, cost-effective generation (~$0.002/500 leads).
    """

    def __init__(self, api_key: str, model: str = "claude-3-5-haiku-20241022"):
        """
        Initialize the AI line generator.

        Args:
            api_key: Anthropic API key
            model: Model to use (default: claude-3-5-haiku for speed/cost)
        """
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

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
            context_parts.append(f"Research data:\n{serper_data}")

        if lead_data:
            if lead_data.get("industry"):
                context_parts.append(f"Industry: {lead_data['industry']}")
            if lead_data.get("location"):
                context_parts.append(f"Location: {lead_data['location']}")
            if lead_data.get("company_description"):
                context_parts.append(f"Description: {lead_data['company_description']}")

        context = "\n\n".join(context_parts)

        # If no context available, return a fallback
        if not context.strip() or context.strip() == f"Company: {company_name}":
            return AIGeneratedLine(
                line="Came across your company online.",
                confidence_tier="B",
                artifact_type="FALLBACK",
                artifact_used="",
                reasoning="No data available for personalization",
            )

        prompt = self._build_prompt(company_name, context)

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}],
            )

            return self._parse_response(response.content[0].text)

        except anthropic.APIError as e:
            logger.error(f"Claude API error: {e}")
            return AIGeneratedLine(
                line="Came across your company online.",
                confidence_tier="B",
                artifact_type="FALLBACK",
                artifact_used="",
                reasoning=f"API error: {str(e)[:50]}",
            )

    def _build_prompt(self, company_name: str, context: str) -> str:
        """Build the prompt for Claude."""
        return f"""You are writing a cold email personalization line for {company_name}.

Your goal: Write ONE short, specific opening line (under 15 words) that shows you actually researched them. The line should make them think "how did they know that?"

RESEARCH DATA:
{context}

RULES:
1. Pick the MOST SPECIFIC detail you can find (client names, tools they use, exact phrases from their site, podcast appearances, awards)
2. DO NOT use generic phrases like "impressive work" or "innovative approach"
3. DO NOT use timing words like "recently", "just launched", "new"
4. Keep it factual and conversational - like you're mentioning something you noticed
5. Under 15 words, ideally 8-12

ARTIFACT PRIORITY (use the highest tier you can find):
- Tier S (best): Client/project names, specific tools (ServiceTitan, HubSpot), exact quotes from their site, podcast appearances
- Tier A (good): Competitor mentions, specific service names, hiring signals
- Tier B (acceptable): Location focus, general industry description

OUTPUT FORMAT (exactly this format):
LINE: [your personalization line here]
TIER: [S, A, or B]
TYPE: [EXACT_PHRASE, CLIENT_OR_PROJECT, TOOL_PLATFORM, COMPETITOR, SERVICE_PROGRAM, HIRING_SIGNAL, LOCATION, COMPANY_DESCRIPTION, or FALLBACK]
ARTIFACT: [the specific text/detail you used]
REASON: [why you chose this - one sentence]

EXAMPLE OUTPUT:
LINE: Saw your ServiceTitan integration for HVAC dispatch.
TIER: S
TYPE: TOOL_PLATFORM
ARTIFACT: ServiceTitan
REASON: Specific tool mention shows insider knowledge of their tech stack.

Now write the line for {company_name}:"""

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
            if line.startswith("LINE:"):
                result["line"] = line[5:].strip()
            elif line.startswith("TIER:"):
                tier = line[5:].strip().upper()
                if tier in ["S", "A", "B"]:
                    result["tier"] = tier
            elif line.startswith("TYPE:"):
                result["type"] = line[5:].strip().upper()
            elif line.startswith("ARTIFACT:"):
                result["artifact"] = line[9:].strip()
            elif line.startswith("REASON:"):
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
