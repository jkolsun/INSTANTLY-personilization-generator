#!/usr/bin/env python3
"""
Bright Automations Personalization Line Engine

Generates personalized email opening lines from Instantly SuperSearch CSV exports.

Usage:
    python main.py --input leads.csv --output personalized_leads.csv [--seed 42] [--limit 10]
"""
import argparse
import sys
from typing import List, Optional

import pandas as pd
from tqdm import tqdm

from artifact_extractor import Artifact, ArtifactExtractor
from artifact_ranker import ArtifactRanker
from column_normalizer import (
    get_company_description,
    get_company_name,
    get_location,
    get_site_url,
    normalize_columns,
)
from config import ArtifactType, ConfidenceTier
from line_generator import LineGenerator
from validator import Validator
from website_scraper import WebsiteScraper


def process_row(
    row: pd.Series,
    scraper: WebsiteScraper,
    extractor: ArtifactExtractor,
    ranker: ArtifactRanker,
    generator: LineGenerator,
    validator: Validator,
) -> dict:
    """
    Process a single row and generate personalization data.

    Args:
        row: DataFrame row
        scraper: Website scraper instance
        extractor: Artifact extractor instance
        ranker: Artifact ranker instance
        generator: Line generator instance
        validator: Validator instance

    Returns:
        Dict with personalization fields
    """
    # Get data from row
    site_url = get_site_url(row)
    description = get_company_description(row)
    location = get_location(row)
    company_name = get_company_name(row)

    # Scrape website if URL available
    website_elements = None
    if site_url:
        try:
            website_elements = scraper.scrape_website(site_url)
        except Exception:
            pass  # Graceful failure, will use description fallback

    # Extract artifacts
    artifacts = extractor.extract_all(website_elements, description)

    # Add location as artifact if available
    if location and not any(a.artifact_type == ArtifactType.LOCATION for a in artifacts):
        artifacts.append(Artifact(
            text=location,
            artifact_type=ArtifactType.LOCATION,
            evidence_source="csv_field",
            evidence_url="",
            score=1.0,
        ))

    # Filter out artifacts that fail validation
    valid_artifacts = []
    for artifact in artifacts:
        result = validator.validate_artifact(artifact)
        if result.is_valid:
            valid_artifacts.append(artifact)

    # Select best artifact (with fallback)
    selected = ranker.select_with_fallback(valid_artifacts)

    # Generate personalization line
    line = generator.generate(selected)

    # Validate line (pass company_name for VU-08/VU-09 checks)
    validation = validator.validate(line, selected, company_name=company_name)

    # If validation fails, try other artifacts
    if not validation.is_valid and len(valid_artifacts) > 1:
        # Try next best artifacts
        ranked = ranker.rank_artifacts(valid_artifacts)
        for alt_artifact in ranked[1:]:  # Skip first (already tried)
            alt_line = generator.generate(alt_artifact)
            alt_validation = validator.validate(alt_line, alt_artifact, company_name=company_name)
            if alt_validation.is_valid:
                selected = alt_artifact
                line = alt_line
                break
        else:
            # All failed, use fallback
            selected = ranker.get_fallback_artifact()
            line = generator.generate(selected)

    # Get confidence tier
    confidence = ranker.get_confidence_tier(selected)

    return {
        "personalization_line": line,
        "artifact_type": selected.artifact_type.value,
        "artifact_text": selected.text if selected.artifact_type != ArtifactType.FALLBACK else "",
        "evidence_source": selected.evidence_source,
        "evidence_url": selected.evidence_url,
        "confidence_tier": confidence.value,
    }


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate personalization lines for email outreach"
    )
    parser.add_argument(
        "--input", "-i",
        required=True,
        help="Input CSV file (Instantly SuperSearch export)"
    )
    parser.add_argument(
        "--output", "-o",
        required=True,
        help="Output CSV file with personalization columns"
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed for reproducible template selection"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of rows to process (for testing)"
    )

    args = parser.parse_args()

    # Read input CSV
    print(f"Reading input file: {args.input}")
    try:
        df = pd.read_csv(args.input, low_memory=False)
    except Exception as e:
        print(f"Error reading input file: {e}")
        sys.exit(1)

    # Normalize column names
    df = normalize_columns(df)

    # Apply limit if specified
    if args.limit:
        df = df.head(args.limit)

    print(f"Processing {len(df)} leads...")

    # Initialize components
    scraper = WebsiteScraper()
    extractor = ArtifactExtractor()
    ranker = ArtifactRanker()
    generator = LineGenerator(seed=args.seed)
    validator = Validator()

    # Process each row
    results = []
    for idx, row in tqdm(df.iterrows(), total=len(df), desc="Generating lines"):
        try:
            result = process_row(
                row, scraper, extractor, ranker, generator, validator
            )
            results.append(result)
        except Exception as e:
            # Fallback on any error
            results.append({
                "personalization_line": "Came across your site—quick question.",
                "artifact_type": "FALLBACK",
                "artifact_text": "",
                "evidence_source": "error",
                "evidence_url": "",
                "confidence_tier": "B",
            })
            print(f"Warning: Error processing row {idx}: {e}")

    # Create results DataFrame
    results_df = pd.DataFrame(results)

    # Append new columns to original DataFrame
    for col in results_df.columns:
        df[col] = results_df[col].values

    # Write output
    print(f"\nWriting output file: {args.output}")
    df.to_csv(args.output, index=False)

    # Print summary
    tier_counts = results_df["confidence_tier"].value_counts()
    total = len(results_df)

    print("\n" + "=" * 50)
    print("SUMMARY")
    print("=" * 50)
    print(f"Total leads processed: {total}")
    print(f"\nConfidence tier breakdown:")
    for tier in ["S", "A", "B"]:
        count = tier_counts.get(tier, 0)
        pct = count / total * 100 if total > 0 else 0
        print(f"  Tier {tier}: {count} ({pct:.1f}%)")

    s_count = tier_counts.get("S", 0)
    a_count = tier_counts.get("A", 0)
    high_confidence_pct = (s_count + a_count) / total * 100 if total > 0 else 0
    print(f"\nHigh confidence (S+A): {s_count + a_count} ({high_confidence_pct:.1f}%)")

    # Artifact type breakdown
    type_counts = results_df["artifact_type"].value_counts()
    print(f"\nArtifact type breakdown:")
    for atype, count in type_counts.items():
        pct = count / total * 100 if total > 0 else 0
        print(f"  {atype}: {count} ({pct:.1f}%)")

    print("=" * 50)
    print(f"\nDone! Output saved to: {args.output}")


if __name__ == "__main__":
    main()
