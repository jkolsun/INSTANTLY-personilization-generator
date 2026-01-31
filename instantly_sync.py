#!/usr/bin/env python3
"""
Instantly Personalization Sync

Fetches leads from Instantly, generates personalization lines,
and updates them back in Instantly.

Usage:
    python instantly_sync.py --api-key YOUR_API_KEY [--campaign CAMPAIGN_ID] [--limit 100]

Environment Variables:
    INSTANTLY_API_KEY: Your Instantly API V2 key (alternative to --api-key)
"""
import argparse
import os
import sys
from typing import Dict, List, Optional

from tqdm import tqdm

from artifact_extractor import Artifact, ArtifactExtractor
from artifact_ranker import ArtifactRanker
from config import ArtifactType
from instantly_client import InstantlyClient, Lead
from line_generator import LineGenerator
from validator import Validator


class InstantlyPersonalizer:
    """
    Syncs personalization data with Instantly.

    Workflow:
    1. Fetch leads from Instantly campaign(s)
    2. For each lead, extract artifacts from available data
    3. Generate personalization line following the hierarchy
    4. Update lead in Instantly with personalization data
    """

    # Custom variable names to use in Instantly
    VAR_PERSONALIZATION_LINE = "personalization_line"
    VAR_ARTIFACT_TYPE = "artifact_type"
    VAR_ARTIFACT_TEXT = "artifact_text"
    VAR_CONFIDENCE_TIER = "confidence_tier"
    VAR_EVIDENCE_SOURCE = "evidence_source"

    def __init__(self, api_key: str, seed: Optional[int] = None):
        """
        Initialize the personalizer.

        Args:
            api_key: Instantly API V2 key
            seed: Random seed for reproducible template selection
        """
        self.client = InstantlyClient(api_key)
        self.extractor = ArtifactExtractor()
        self.ranker = ArtifactRanker()
        self.generator = LineGenerator(seed=seed)
        self.validator = Validator()

    def _build_description(self, lead: Lead) -> str:
        """
        Build a description string from lead data for artifact extraction.

        Args:
            lead: Lead object from Instantly

        Returns:
            Combined description text
        """
        parts = []

        # Get company-related data from raw response
        raw = lead.raw_data

        # Company description (most valuable)
        if raw.get("company_description"):
            parts.append(raw["company_description"])

        # LinkedIn summary/headline
        if raw.get("summary"):
            parts.append(raw["summary"])
        if raw.get("headline"):
            parts.append(raw["headline"])

        # Industry info
        if raw.get("industry"):
            parts.append(f"Industry: {raw['industry']}")

        return " ".join(parts)

    def _get_location(self, lead: Lead) -> Optional[str]:
        """Extract location from lead data."""
        raw = lead.raw_data

        location = raw.get("location")
        if location and location.lower() not in ["no data found", "n/a", "skipped"]:
            # Clean up location (remove country suffix)
            for suffix in [", United States", ", USA", ", US"]:
                if location.endswith(suffix):
                    location = location[:-len(suffix)]
            if location.lower() not in ["united states", "usa", "us"]:
                return location

        return None

    def personalize_lead(self, lead: Lead) -> Dict[str, str]:
        """
        Generate personalization data for a lead.

        Args:
            lead: Lead object from Instantly

        Returns:
            Dict with personalization variables
        """
        # Build description from available data
        description = self._build_description(lead)

        # Extract artifacts from description
        artifacts = self.extractor.extract_from_description(description)

        # Add location as artifact if available
        location = self._get_location(lead)
        if location and not any(a.artifact_type == ArtifactType.LOCATION for a in artifacts):
            artifacts.append(Artifact(
                text=location,
                artifact_type=ArtifactType.LOCATION,
                evidence_source="instantly_lead",
                evidence_url="",
                score=1.0,
            ))

        # Filter out invalid artifacts
        valid_artifacts = []
        for artifact in artifacts:
            result = self.validator.validate_artifact(artifact)
            if result.is_valid:
                valid_artifacts.append(artifact)

        # Select best artifact (with fallback)
        selected = self.ranker.select_with_fallback(valid_artifacts)

        # Generate personalization line
        line = self.generator.generate(selected)

        # Validate line
        validation = self.validator.validate(line, selected)

        # If validation fails, try other artifacts
        if not validation.is_valid and len(valid_artifacts) > 1:
            ranked = self.ranker.rank_artifacts(valid_artifacts)
            for alt_artifact in ranked[1:]:
                alt_line = self.generator.generate(alt_artifact)
                alt_validation = self.validator.validate(alt_line, alt_artifact)
                if alt_validation.is_valid:
                    selected = alt_artifact
                    line = alt_line
                    break
            else:
                # All failed, use fallback
                selected = self.ranker.get_fallback_artifact()
                line = self.generator.generate(selected)

        # Get confidence tier
        confidence = self.ranker.get_confidence_tier(selected)

        return {
            self.VAR_PERSONALIZATION_LINE: line,
            self.VAR_ARTIFACT_TYPE: selected.artifact_type.value,
            self.VAR_ARTIFACT_TEXT: selected.text if selected.artifact_type != ArtifactType.FALLBACK else "",
            self.VAR_CONFIDENCE_TIER: confidence.value,
            self.VAR_EVIDENCE_SOURCE: selected.evidence_source,
        }

    def sync_campaign(
        self,
        campaign_id: str,
        limit: Optional[int] = None,
        dry_run: bool = False,
    ) -> Dict[str, int]:
        """
        Sync personalization for all leads in a campaign.

        Args:
            campaign_id: Campaign ID to process
            limit: Maximum number of leads to process
            dry_run: If True, don't update leads (just show what would happen)

        Returns:
            Stats dict with counts by confidence tier
        """
        print(f"Fetching leads from campaign {campaign_id}...")
        leads = self.client.list_leads(campaign_id=campaign_id, limit=limit or 10000)
        print(f"Found {len(leads)} leads")

        if limit:
            leads = leads[:limit]

        stats = {"S": 0, "A": 0, "B": 0, "errors": 0, "skipped": 0}

        for lead in tqdm(leads, desc="Personalizing leads"):
            try:
                # Skip if already has personalization
                if lead.custom_variables.get(self.VAR_PERSONALIZATION_LINE):
                    stats["skipped"] += 1
                    continue

                # Generate personalization
                variables = self.personalize_lead(lead)

                # Update stats
                tier = variables[self.VAR_CONFIDENCE_TIER]
                stats[tier] = stats.get(tier, 0) + 1

                if dry_run:
                    print(f"\n[DRY RUN] {lead.email}")
                    print(f"  Line: {variables[self.VAR_PERSONALIZATION_LINE]}")
                    print(f"  Artifact: {variables[self.VAR_ARTIFACT_TEXT]} ({variables[self.VAR_ARTIFACT_TYPE]})")
                    print(f"  Confidence: {tier}")
                else:
                    # Update lead in Instantly
                    self.client.update_lead_variables(lead.id, variables)

            except Exception as e:
                stats["errors"] += 1
                print(f"\nError processing {lead.email}: {e}")

        return stats

    def sync_all_campaigns(
        self,
        limit_per_campaign: Optional[int] = None,
        dry_run: bool = False,
    ) -> Dict[str, Dict[str, int]]:
        """
        Sync personalization for all campaigns.

        Args:
            limit_per_campaign: Maximum leads per campaign
            dry_run: If True, don't update leads

        Returns:
            Dict mapping campaign ID -> stats
        """
        print("Fetching campaigns...")
        campaigns = self.client.list_campaigns()
        print(f"Found {len(campaigns)} campaigns")

        all_stats = {}

        for campaign in campaigns:
            print(f"\n{'='*50}")
            print(f"Campaign: {campaign.name} ({campaign.id})")
            print(f"{'='*50}")

            stats = self.sync_campaign(
                campaign_id=campaign.id,
                limit=limit_per_campaign,
                dry_run=dry_run,
            )
            all_stats[campaign.id] = stats

            self._print_stats(stats)

        return all_stats

    def _print_stats(self, stats: Dict[str, int]):
        """Print stats summary."""
        total = stats.get("S", 0) + stats.get("A", 0) + stats.get("B", 0)

        print(f"\nResults:")
        print(f"  Tier S: {stats.get('S', 0)}")
        print(f"  Tier A: {stats.get('A', 0)}")
        print(f"  Tier B: {stats.get('B', 0)}")
        print(f"  Skipped (already personalized): {stats.get('skipped', 0)}")
        print(f"  Errors: {stats.get('errors', 0)}")

        if total > 0:
            high_conf = stats.get("S", 0) + stats.get("A", 0)
            pct = high_conf / total * 100
            print(f"\n  High confidence (S+A): {high_conf} ({pct:.1f}%)")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Sync personalization data with Instantly"
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("INSTANTLY_API_KEY"),
        help="Instantly API V2 key (or set INSTANTLY_API_KEY env var)"
    )
    parser.add_argument(
        "--campaign",
        help="Campaign ID to process (if not specified, processes all campaigns)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of leads to process"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without updating leads"
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed for reproducible template selection"
    )
    parser.add_argument(
        "--test-connection",
        action="store_true",
        help="Just test the API connection and exit"
    )

    args = parser.parse_args()

    if not args.api_key:
        print("Error: API key required. Use --api-key or set INSTANTLY_API_KEY env var")
        sys.exit(1)

    # Initialize personalizer
    personalizer = InstantlyPersonalizer(api_key=args.api_key, seed=args.seed)

    # Test connection
    if args.test_connection:
        if personalizer.client.test_connection():
            print("Connection successful!")
            sys.exit(0)
        else:
            print("Connection failed. Check your API key.")
            sys.exit(1)

    # Verify connection before processing
    print("Testing API connection...")
    if not personalizer.client.test_connection():
        print("Error: Could not connect to Instantly API. Check your API key.")
        sys.exit(1)
    print("Connected!\n")

    # Process leads
    if args.campaign:
        stats = personalizer.sync_campaign(
            campaign_id=args.campaign,
            limit=args.limit,
            dry_run=args.dry_run,
        )
        personalizer._print_stats(stats)
    else:
        personalizer.sync_all_campaigns(
            limit_per_campaign=args.limit,
            dry_run=args.dry_run,
        )

    print("\nDone!")


if __name__ == "__main__":
    main()
