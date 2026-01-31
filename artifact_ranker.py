"""
Artifact ranker for selecting the best personalization artifact.
"""
from typing import List, Optional

from artifact_extractor import Artifact
from config import (
    ARTIFACT_CONFIDENCE,
    ARTIFACT_PRIORITY,
    ArtifactType,
    ConfidenceTier,
)


class ArtifactRanker:
    """Ranks and selects the best artifact following the hierarchy."""

    def _get_type_priority(self, artifact_type: ArtifactType) -> int:
        """
        Get priority index for an artifact type.
        Lower index = higher priority.
        """
        try:
            return ARTIFACT_PRIORITY.index(artifact_type)
        except ValueError:
            return len(ARTIFACT_PRIORITY)  # Unknown type, lowest priority

    def rank_artifacts(self, artifacts: List[Artifact]) -> List[Artifact]:
        """
        Rank artifacts by priority and quality score.

        Args:
            artifacts: List of candidate artifacts

        Returns:
            Sorted list (best first)
        """
        if not artifacts:
            return []

        # Sort by: (1) type priority, (2) quality score (descending)
        return sorted(
            artifacts,
            key=lambda a: (self._get_type_priority(a.artifact_type), -a.score)
        )

    def select_best(self, artifacts: List[Artifact]) -> Optional[Artifact]:
        """
        Select the best artifact from candidates.
        Follows the hierarchy: stop at first valid artifact type.

        Args:
            artifacts: List of candidate artifacts

        Returns:
            Best artifact or None if none available
        """
        if not artifacts:
            return None

        ranked = self.rank_artifacts(artifacts)

        # Return the top-ranked artifact
        # The ranking already ensures we get the best artifact type first
        return ranked[0] if ranked else None

    def get_confidence_tier(self, artifact: Optional[Artifact]) -> ConfidenceTier:
        """
        Get the confidence tier for an artifact.

        Args:
            artifact: The selected artifact (or None for fallback)

        Returns:
            Confidence tier (S, A, or B)
        """
        if artifact is None:
            return ConfidenceTier.B

        return ARTIFACT_CONFIDENCE.get(artifact.artifact_type, ConfidenceTier.B)

    def get_fallback_artifact(self) -> Artifact:
        """
        Create a fallback artifact when no good candidates exist.

        Returns:
            Fallback artifact
        """
        return Artifact(
            text="",
            artifact_type=ArtifactType.FALLBACK,
            evidence_source="fallback",
            evidence_url="",
            score=0.0,
        )

    def select_with_fallback(self, artifacts: List[Artifact]) -> Artifact:
        """
        Select the best artifact, using fallback if none available.

        Args:
            artifacts: List of candidate artifacts

        Returns:
            Best artifact or fallback
        """
        best = self.select_best(artifacts)

        if best is None:
            return self.get_fallback_artifact()

        return best
