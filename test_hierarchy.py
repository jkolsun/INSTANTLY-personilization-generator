"""
Comprehensive tests for the Personalization Artifact Hierarchy.

Tests the updated hierarchy:
- Tier S: Direct "Insider" signals (CLIENT_OR_PROJECT, TOOL_PLATFORM, EXACT_PHRASE)
- Tier A: Market & Operator context (COMPETITOR, SERVICE_PROGRAM, HIRING_SIGNAL)
- Tier B: Contextual fallback (LOCATION, COMPANY_DESCRIPTION, FALLBACK)

FAIL CONDITIONS tested:
- Generic phrases that could apply to 80%+ of companies
- Any invented timing language ("recently", "just", "rolled out")
- Multiple artifacts in one line (stacking)
- Hype adjectives
"""
import pytest

from artifact_extractor import Artifact
from artifact_ranker import ArtifactRanker
from config import (
    ArtifactType,
    ConfidenceTier,
    ARTIFACT_CONFIDENCE,
    TIER_S_TYPES,
    TIER_A_TYPES,
    TIER_B_TYPES,
)
from line_generator import LineGenerator, GeneratedLine
from validator import Validator, ValidationResult


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def generator():
    """Create a seeded line generator for reproducible tests."""
    return LineGenerator(seed=42)


@pytest.fixture
def validator():
    """Create a validator instance."""
    return Validator()


@pytest.fixture
def ranker():
    """Create a ranker instance."""
    return ArtifactRanker()


def make_artifact(
    text: str,
    artifact_type: ArtifactType,
    score: float = 5.0,
    source: str = "website",
) -> Artifact:
    """Helper to create test artifacts."""
    return Artifact(
        text=text,
        artifact_type=artifact_type,
        evidence_source=source,
        evidence_url="https://example.com",
        score=score,
    )


# =============================================================================
# Tier Configuration Tests
# =============================================================================

class TestTierConfiguration:
    """Test that tier configurations are correct."""

    def test_tier_s_types(self):
        """Tier S should contain insider signal types."""
        assert ArtifactType.CLIENT_OR_PROJECT in TIER_S_TYPES
        assert ArtifactType.TOOL_PLATFORM in TIER_S_TYPES
        assert ArtifactType.EXACT_PHRASE in TIER_S_TYPES
        assert len(TIER_S_TYPES) == 3

    def test_tier_a_types(self):
        """Tier A should contain market context types."""
        assert ArtifactType.COMPETITOR in TIER_A_TYPES
        assert ArtifactType.SERVICE_PROGRAM in TIER_A_TYPES
        assert ArtifactType.HIRING_SIGNAL in TIER_A_TYPES
        assert len(TIER_A_TYPES) == 3

    def test_tier_b_types(self):
        """Tier B should contain contextual fallback types."""
        assert ArtifactType.LOCATION in TIER_B_TYPES
        assert ArtifactType.COMPANY_DESCRIPTION in TIER_B_TYPES
        assert len(TIER_B_TYPES) == 2

    def test_confidence_mapping_tier_s(self):
        """Tier S artifacts should have confidence S."""
        for atype in TIER_S_TYPES:
            assert ARTIFACT_CONFIDENCE[atype] == ConfidenceTier.S

    def test_confidence_mapping_tier_a(self):
        """Tier A artifacts should have confidence A."""
        for atype in TIER_A_TYPES:
            assert ARTIFACT_CONFIDENCE[atype] == ConfidenceTier.A

    def test_confidence_mapping_tier_b(self):
        """Tier B artifacts should have confidence B."""
        for atype in TIER_B_TYPES:
            assert ARTIFACT_CONFIDENCE[atype] == ConfidenceTier.B

    def test_fallback_is_tier_b(self):
        """FALLBACK should have confidence B."""
        assert ARTIFACT_CONFIDENCE[ArtifactType.FALLBACK] == ConfidenceTier.B


# =============================================================================
# Tier Selection Tests (Stop at First Valid)
# =============================================================================

class TestTierSelection:
    """Test tier-based artifact selection."""

    def test_tier_s_selected_over_tier_a(self, generator):
        """Tier S artifact should be selected over Tier A."""
        artifacts = [
            make_artifact("ServiceTitan", ArtifactType.TOOL_PLATFORM, score=3.0),
            make_artifact("Home Services", ArtifactType.SERVICE_PROGRAM, score=5.0),
        ]
        best = generator.select_best_artifact(artifacts)
        assert best.artifact_type == ArtifactType.TOOL_PLATFORM

    def test_tier_s_selected_over_tier_b(self, generator):
        """Tier S artifact should be selected over Tier B."""
        artifacts = [
            make_artifact("Phoenix, AZ", ArtifactType.LOCATION, score=5.0),
            make_artifact("Acme Corp Project", ArtifactType.CLIENT_OR_PROJECT, score=2.0),
        ]
        best = generator.select_best_artifact(artifacts)
        assert best.artifact_type == ArtifactType.CLIENT_OR_PROJECT

    def test_tier_a_selected_over_tier_b(self, generator):
        """Tier A artifact should be selected over Tier B."""
        artifacts = [
            make_artifact("Phoenix, AZ", ArtifactType.LOCATION, score=5.0),
            make_artifact("Roto-Rooter", ArtifactType.COMPETITOR, score=2.0),
        ]
        best = generator.select_best_artifact(artifacts)
        assert best.artifact_type == ArtifactType.COMPETITOR

    def test_highest_score_within_tier(self, generator):
        """Within same tier, highest score wins."""
        artifacts = [
            make_artifact("Project Alpha", ArtifactType.CLIENT_OR_PROJECT, score=3.0),
            make_artifact("Project Beta", ArtifactType.CLIENT_OR_PROJECT, score=5.0),
        ]
        best = generator.select_best_artifact(artifacts)
        assert best.text == "Project Beta"

    def test_only_tier_b_returns_tier_b(self, generator):
        """If only Tier B artifacts, return Tier B."""
        artifacts = [
            make_artifact("Phoenix, AZ", ArtifactType.LOCATION, score=3.0),
            make_artifact("Leading HVAC provider", ArtifactType.COMPANY_DESCRIPTION, score=5.0),
        ]
        best = generator.select_best_artifact(artifacts)
        assert best.artifact_type in TIER_B_TYPES

    def test_empty_artifacts_returns_none(self, generator):
        """Empty artifact list should return None."""
        best = generator.select_best_artifact([])
        assert best is None


# =============================================================================
# Line Generation Tests
# =============================================================================

class TestLineGeneration:
    """Test line generation functionality."""

    def test_generate_tier_s_line(self, generator):
        """Generate line from Tier S artifact."""
        artifact = make_artifact("ServiceTitan", ArtifactType.TOOL_PLATFORM)
        line = generator.generate(artifact)
        assert "ServiceTitan" in line
        assert "question" in line.lower()

    def test_generate_with_metadata(self, generator):
        """Generate line with full metadata."""
        artifact = make_artifact("ServiceTitan", ArtifactType.TOOL_PLATFORM)
        result = generator.generate_with_metadata(artifact)

        assert isinstance(result, GeneratedLine)
        assert "ServiceTitan" in result.line
        assert result.artifact == artifact
        assert result.confidence == ConfidenceTier.S
        assert "{artifact_text}" in result.template_used

    def test_fallback_line_generation(self, generator):
        """Fallback line should not contain placeholder."""
        result = generator.create_fallback_line()

        assert isinstance(result, GeneratedLine)
        assert result.confidence == ConfidenceTier.B
        assert "{artifact_text}" not in result.line
        assert "site" in result.line.lower()

    def test_exact_phrase_quoted(self, generator):
        """Exact phrase artifacts should appear in quotes."""
        artifact = make_artifact("Your Comfort Is Our Priority", ArtifactType.EXACT_PHRASE)
        line = generator.generate(artifact)
        assert '"Your Comfort Is Our Priority"' in line

    def test_all_variants_generated(self, generator):
        """All template variants should be generated."""
        artifact = make_artifact("ServiceTitan", ArtifactType.TOOL_PLATFORM)
        variants = generator.generate_all_variants(artifact)

        assert len(variants) >= 2
        for v in variants:
            assert "ServiceTitan" in v


# =============================================================================
# Fail Condition Tests
# =============================================================================

class TestFailConditions:
    """Test FAIL CONDITIONS (AUTO-REJECT)."""

    def test_banned_timing_words_rejected(self, validator):
        """Artifacts with timing words should be rejected."""
        timing_artifacts = [
            make_artifact("recently expanded services", ArtifactType.SERVICE_PROGRAM),
            make_artifact("just launched program", ArtifactType.SERVICE_PROGRAM),
            make_artifact("rolled out new offering", ArtifactType.SERVICE_PROGRAM),
        ]

        for artifact in timing_artifacts:
            result = validator.validate_artifact(artifact)
            assert not result.is_valid
            assert any("timing" in e.lower() for e in result.errors)

    def test_banned_hype_adjectives_rejected(self, validator):
        """Artifacts with hype adjectives should be rejected."""
        hype_artifacts = [
            make_artifact("impressive HVAC solutions", ArtifactType.SERVICE_PROGRAM),
            make_artifact("amazing customer service", ArtifactType.SERVICE_PROGRAM),
            make_artifact("innovative approach", ArtifactType.SERVICE_PROGRAM),
        ]

        for artifact in hype_artifacts:
            result = validator.validate_artifact(artifact)
            assert not result.is_valid
            assert any("hype" in e.lower() for e in result.errors)

    def test_generic_phrases_rejected(self, validator):
        """Generic phrases should be rejected."""
        generic_artifacts = [
            make_artifact("quality service", ArtifactType.SERVICE_PROGRAM),
            make_artifact("customer satisfaction guaranteed", ArtifactType.EXACT_PHRASE),
            make_artifact("your trusted local provider", ArtifactType.COMPANY_DESCRIPTION),
            make_artifact("we offer professional service", ArtifactType.SERVICE_PROGRAM),
            make_artifact("family owned business", ArtifactType.COMPANY_DESCRIPTION),
        ]

        for artifact in generic_artifacts:
            result = validator.validate_artifact(artifact)
            assert not result.is_valid, f"Should reject: {artifact.text}"
            assert any("generic" in e.lower() for e in result.errors)

    def test_multiple_artifacts_rejected(self, validator):
        """Lines with multiple artifacts (stacking) should be rejected."""
        all_artifacts = [
            make_artifact("ServiceTitan", ArtifactType.TOOL_PLATFORM),
            make_artifact("Phoenix, AZ", ArtifactType.LOCATION),
        ]

        # Line that contains both artifacts
        stacked_line = "Saw ServiceTitan and Phoenix, AZ on your site—quick question."
        main_artifact = all_artifacts[0]

        result = validator.validate(stacked_line, main_artifact, all_artifacts)
        assert not result.is_valid
        assert any("multiple" in e.lower() or "stacking" in e.lower() for e in result.errors)

    def test_single_artifact_allowed(self, validator):
        """Lines with single artifact should be allowed."""
        all_artifacts = [
            make_artifact("ServiceTitan", ArtifactType.TOOL_PLATFORM),
            make_artifact("Phoenix, AZ", ArtifactType.LOCATION),
        ]

        # Line that contains only one artifact
        single_line = "Noticed ServiceTitan in your setup—quick question."
        main_artifact = all_artifacts[0]

        result = validator.validate(single_line, main_artifact, all_artifacts)
        # Should not fail due to stacking (may pass or fail for other reasons)
        assert not any("stacking" in e.lower() for e in result.errors)

    def test_timing_words_in_line_rejected(self, validator):
        """Lines containing timing words should be rejected."""
        artifact = make_artifact("ServiceTitan", ArtifactType.TOOL_PLATFORM)

        # Line with timing word
        bad_line = "Noticed you recently added ServiceTitan—quick question."
        result = validator.validate(bad_line, artifact)
        assert not result.is_valid
        assert any("timing" in e.lower() for e in result.errors)

    def test_word_count_limit(self, validator):
        """Lines exceeding word limit should be rejected."""
        artifact = make_artifact("ServiceTitan", ArtifactType.TOOL_PLATFORM)

        # Very long line
        long_line = "Saw that you are using ServiceTitan " + "word " * 20 + "question."
        result = validator.validate(long_line, artifact)
        assert not result.is_valid
        assert any("words" in e.lower() for e in result.errors)


# =============================================================================
# Valid Artifact Tests
# =============================================================================

class TestValidArtifacts:
    """Test that good artifacts pass validation."""

    def test_tier_s_client_project_valid(self, validator):
        """Valid client/project names should pass."""
        valid_artifacts = [
            make_artifact("Marriott Hotel Renovation", ArtifactType.CLIENT_OR_PROJECT),
            make_artifact("Downtown Phoenix Office", ArtifactType.CLIENT_OR_PROJECT),
            make_artifact("Smith Residence HVAC", ArtifactType.CLIENT_OR_PROJECT),
        ]

        for artifact in valid_artifacts:
            result = validator.validate_artifact(artifact)
            assert result.is_valid, f"Should accept: {artifact.text}, errors: {result.errors}"

    def test_tier_s_tool_platform_valid(self, validator):
        """Valid tool/platform names should pass."""
        valid_artifacts = [
            make_artifact("ServiceTitan", ArtifactType.TOOL_PLATFORM),
            make_artifact("Housecall Pro", ArtifactType.TOOL_PLATFORM),
            make_artifact("Jobber CRM", ArtifactType.TOOL_PLATFORM),
        ]

        for artifact in valid_artifacts:
            result = validator.validate_artifact(artifact)
            assert result.is_valid, f"Should accept: {artifact.text}, errors: {result.errors}"

    def test_tier_s_exact_phrase_valid(self, validator):
        """Valid exact phrases should pass."""
        valid_artifacts = [
            make_artifact("Your Comfort Is Our Priority", ArtifactType.EXACT_PHRASE),
            make_artifact("Cool Today Warm Tomorrow", ArtifactType.EXACT_PHRASE),
            make_artifact("We Fix It Right", ArtifactType.EXACT_PHRASE),
        ]

        for artifact in valid_artifacts:
            result = validator.validate_artifact(artifact)
            assert result.is_valid, f"Should accept: {artifact.text}, errors: {result.errors}"

    def test_tier_a_competitor_valid(self, validator):
        """Valid competitor names should pass."""
        valid_artifacts = [
            make_artifact("Roto-Rooter", ArtifactType.COMPETITOR),
            make_artifact("Mr. Rooter", ArtifactType.COMPETITOR),
            make_artifact("One Hour Heating", ArtifactType.COMPETITOR),
        ]

        for artifact in valid_artifacts:
            result = validator.validate_artifact(artifact)
            assert result.is_valid, f"Should accept: {artifact.text}, errors: {result.errors}"

    def test_tier_a_service_program_valid(self, validator):
        """Valid service/program names should pass."""
        valid_artifacts = [
            make_artifact("24/7 Emergency Service", ArtifactType.SERVICE_PROGRAM),
            make_artifact("Comfort Club Membership", ArtifactType.SERVICE_PROGRAM),
            make_artifact("Same Day Repair", ArtifactType.SERVICE_PROGRAM),
        ]

        for artifact in valid_artifacts:
            result = validator.validate_artifact(artifact)
            assert result.is_valid, f"Should accept: {artifact.text}, errors: {result.errors}"

    def test_tier_a_hiring_signal_valid(self, validator):
        """Valid hiring signals should pass."""
        valid_artifacts = [
            make_artifact("HVAC Technician", ArtifactType.HIRING_SIGNAL),
            make_artifact("Service Manager", ArtifactType.HIRING_SIGNAL),
            make_artifact("Sales Representative", ArtifactType.HIRING_SIGNAL),
        ]

        for artifact in valid_artifacts:
            result = validator.validate_artifact(artifact)
            assert result.is_valid, f"Should accept: {artifact.text}, errors: {result.errors}"

    def test_tier_b_location_valid(self, validator):
        """Valid locations should pass."""
        valid_artifacts = [
            make_artifact("Phoenix, AZ", ArtifactType.LOCATION),
            make_artifact("Greater Denver Area", ArtifactType.LOCATION),
            make_artifact("North Dallas", ArtifactType.LOCATION),
        ]

        for artifact in valid_artifacts:
            result = validator.validate_artifact(artifact)
            assert result.is_valid, f"Should accept: {artifact.text}, errors: {result.errors}"


# =============================================================================
# Ranker Integration Tests
# =============================================================================

class TestRankerIntegration:
    """Test artifact ranker with the hierarchy."""

    def test_ranker_respects_priority(self, ranker):
        """Ranker should respect artifact type priority."""
        artifacts = [
            make_artifact("Phoenix, AZ", ArtifactType.LOCATION, score=10.0),
            make_artifact("ServiceTitan", ArtifactType.TOOL_PLATFORM, score=1.0),
        ]

        best = ranker.select_best(artifacts)
        # TOOL_PLATFORM (Tier S) should win even with lower score
        assert best.artifact_type == ArtifactType.TOOL_PLATFORM

    def test_ranker_confidence_tier(self, ranker):
        """Ranker should return correct confidence tier."""
        tier_s = make_artifact("ServiceTitan", ArtifactType.TOOL_PLATFORM)
        tier_a = make_artifact("Plumbing Services", ArtifactType.SERVICE_PROGRAM)
        tier_b = make_artifact("Phoenix, AZ", ArtifactType.LOCATION)

        assert ranker.get_confidence_tier(tier_s) == ConfidenceTier.S
        assert ranker.get_confidence_tier(tier_a) == ConfidenceTier.A
        assert ranker.get_confidence_tier(tier_b) == ConfidenceTier.B

    def test_ranker_fallback(self, ranker):
        """Ranker should create fallback when no artifacts."""
        fallback = ranker.get_fallback_artifact()

        assert fallback.artifact_type == ArtifactType.FALLBACK
        assert fallback.text == ""
        assert ranker.get_confidence_tier(fallback) == ConfidenceTier.B

    def test_select_with_fallback_empty(self, ranker):
        """Select with fallback should return fallback when empty."""
        result = ranker.select_with_fallback([])
        assert result.artifact_type == ArtifactType.FALLBACK


# =============================================================================
# End-to-End Tests
# =============================================================================

class TestEndToEnd:
    """End-to-end tests for the full pipeline."""

    def test_full_pipeline_tier_s(self, generator, validator, ranker):
        """Full pipeline with Tier S artifact."""
        artifacts = [
            make_artifact("ServiceTitan", ArtifactType.TOOL_PLATFORM),
            make_artifact("Phoenix, AZ", ArtifactType.LOCATION),
        ]

        # Filter valid artifacts
        valid = [a for a in artifacts if validator.validate_artifact(a).is_valid]

        # Select best
        best = ranker.select_best(valid)
        assert best.artifact_type == ArtifactType.TOOL_PLATFORM

        # Generate line
        result = generator.generate_with_metadata(best)
        assert result.confidence == ConfidenceTier.S
        assert "ServiceTitan" in result.line

        # Validate line
        validation = validator.validate(result.line, best)
        assert validation.is_valid

    def test_full_pipeline_fallback_on_all_invalid(self, generator, validator, ranker):
        """Pipeline should fallback when all artifacts invalid."""
        artifacts = [
            make_artifact("quality service guaranteed", ArtifactType.SERVICE_PROGRAM),
            make_artifact("recently expanded", ArtifactType.SERVICE_PROGRAM),
        ]

        # All should be invalid
        valid = [a for a in artifacts if validator.validate_artifact(a).is_valid]
        assert len(valid) == 0

        # Should use fallback
        best = ranker.select_with_fallback(valid)
        assert best.artifact_type == ArtifactType.FALLBACK

        # Generate fallback line
        result = generator.generate_with_metadata(best)
        assert result.confidence == ConfidenceTier.B

    def test_confidence_b_tagged_for_tier_b(self, generator, ranker):
        """Tier B artifacts should be tagged with confidence B."""
        artifacts = [
            make_artifact("Phoenix, AZ", ArtifactType.LOCATION),
        ]

        best = ranker.select_with_fallback(artifacts)
        result = generator.generate_with_metadata(best)

        assert result.confidence == ConfidenceTier.B


# =============================================================================
# Run Tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
