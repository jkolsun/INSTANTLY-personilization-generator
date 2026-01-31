"""
Personalization line generator using templates.

Implements the artifact hierarchy:
- Tier S: Direct "Insider" signals (CLIENT_OR_PROJECT, TOOL_PLATFORM, EXACT_PHRASE)
- Tier A: Market & Operator context (COMPETITOR, SERVICE_PROGRAM, HIRING_SIGNAL)
- Tier B: Contextual fallback (LOCATION, COMPANY_DESCRIPTION, FALLBACK)

Selection logic: Stop at first valid artifact. Do NOT stack.
"""
import random
from dataclasses import dataclass
from typing import List, Optional

from artifact_extractor import Artifact
from config import (
    ArtifactType,
    ConfidenceTier,
    TEMPLATES,
    TIER_S_TYPES,
    TIER_A_TYPES,
    TIER_B_TYPES,
    ARTIFACT_CONFIDENCE,
)


@dataclass
class GeneratedLine:
    """A generated personalization line with metadata."""
    line: str
    artifact: Artifact
    confidence: ConfidenceTier
    template_used: str


class LineGenerator:
    """
    Generates personalization lines from artifacts using templates.

    Follows the tier-based hierarchy:
    1. Try Tier S artifacts first (creates "how did they know that?" reaction)
    2. Fall back to Tier A if Tier S fails (implies market familiarity)
    3. Fall back to Tier B if Tier A fails (contextual, use sparingly)
    4. Output safe fallback and tag confidence = B if all fail
    """

    def __init__(self, seed: Optional[int] = None):
        """
        Initialize the generator.

        Args:
            seed: Random seed for reproducible template selection
        """
        self.rng = random.Random(seed)

    def get_confidence(self, artifact: Artifact) -> ConfidenceTier:
        """
        Get confidence tier for an artifact.

        Args:
            artifact: The artifact to check

        Returns:
            ConfidenceTier (S, A, or B)
        """
        return ARTIFACT_CONFIDENCE.get(artifact.artifact_type, ConfidenceTier.B)

    def get_artifact_tier(self, artifact: Artifact) -> str:
        """
        Get the tier name for an artifact type.

        Args:
            artifact: The artifact to check

        Returns:
            Tier name: "S", "A", or "B"
        """
        if artifact.artifact_type in TIER_S_TYPES:
            return "S"
        elif artifact.artifact_type in TIER_A_TYPES:
            return "A"
        else:
            return "B"

    def select_best_artifact(self, artifacts: List[Artifact]) -> Optional[Artifact]:
        """
        Select the best artifact following the hierarchy.
        Stop at first valid artifact in the highest tier.

        Args:
            artifacts: List of candidate artifacts

        Returns:
            Best artifact or None
        """
        if not artifacts:
            return None

        # Group by tier and select highest priority tier with artifacts
        tier_s = [a for a in artifacts if a.artifact_type in TIER_S_TYPES]
        tier_a = [a for a in artifacts if a.artifact_type in TIER_A_TYPES]
        tier_b = [a for a in artifacts if a.artifact_type in TIER_B_TYPES]

        # Try each tier in order, return best from first non-empty tier
        for tier_artifacts in [tier_s, tier_a, tier_b]:
            if tier_artifacts:
                # Sort by score within tier (highest first)
                sorted_artifacts = sorted(tier_artifacts, key=lambda a: -a.score)
                return sorted_artifacts[0]

        return None

    def generate(self, artifact: Artifact) -> str:
        """
        Generate a personalization line from an artifact.

        Args:
            artifact: The artifact to use

        Returns:
            Generated personalization line
        """
        # Get templates for this artifact type
        templates = TEMPLATES.get(artifact.artifact_type, TEMPLATES[ArtifactType.FALLBACK])

        # Select a template (deterministic if seeded)
        template = self.rng.choice(templates)

        # Generate the line
        if artifact.artifact_type == ArtifactType.FALLBACK:
            return template

        # Replace placeholder with artifact text
        line = template.replace("{artifact_text}", artifact.text)

        return line

    def generate_with_metadata(self, artifact: Artifact) -> GeneratedLine:
        """
        Generate a personalization line with full metadata.

        Args:
            artifact: The artifact to use

        Returns:
            GeneratedLine with line, artifact, confidence, and template
        """
        templates = TEMPLATES.get(artifact.artifact_type, TEMPLATES[ArtifactType.FALLBACK])
        template = self.rng.choice(templates)

        if artifact.artifact_type == ArtifactType.FALLBACK:
            line = template
        else:
            line = template.replace("{artifact_text}", artifact.text)

        return GeneratedLine(
            line=line,
            artifact=artifact,
            confidence=self.get_confidence(artifact),
            template_used=template,
        )

    def generate_all_variants(self, artifact: Artifact) -> list[str]:
        """
        Generate all possible line variants for an artifact.
        Useful for validation/retry logic.

        Args:
            artifact: The artifact to use

        Returns:
            List of all possible personalization lines
        """
        templates = TEMPLATES.get(artifact.artifact_type, TEMPLATES[ArtifactType.FALLBACK])

        if artifact.artifact_type == ArtifactType.FALLBACK:
            return list(templates)

        return [t.replace("{artifact_text}", artifact.text) for t in templates]

    def create_fallback_line(self) -> GeneratedLine:
        """
        Create a safe fallback line when no valid artifacts exist.

        Returns:
            GeneratedLine with confidence B
        """
        fallback_artifact = Artifact(
            text="",
            artifact_type=ArtifactType.FALLBACK,
            evidence_source="fallback",
            evidence_url="",
            score=0.0,
        )
        return self.generate_with_metadata(fallback_artifact)
