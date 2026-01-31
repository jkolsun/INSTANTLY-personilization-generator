#!/usr/bin/env python3
"""
Streamlit Dashboard for the Personalization Line Engine

Run with: streamlit run app.py
"""
import io
import time
from typing import List, Optional, Tuple

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from artifact_extractor import Artifact, ArtifactExtractor
from artifact_ranker import ArtifactRanker
from column_normalizer import (
    get_company_description,
    get_company_name,
    get_location,
    get_site_url,
    normalize_columns,
)
from config import ArtifactType, ConfidenceTier, ARTIFACT_CONFIDENCE
from line_generator import LineGenerator
from validator import Validator
from website_scraper import WebsiteScraper


# Page configuration
st.set_page_config(
    page_title="Personalization Engine",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded",
)


# Custom CSS for better styling
st.markdown("""
<style>
    .stProgress > div > div > div > div {
        background-color: #00d4aa;
    }
    .metric-card {
        background-color: #f0f2f6;
        border-radius: 10px;
        padding: 20px;
        margin: 10px 0;
    }
    .tier-s { color: #00d4aa; font-weight: bold; }
    .tier-a { color: #ffa500; font-weight: bold; }
    .tier-b { color: #6c757d; font-weight: bold; }
    div[data-testid="stMetricValue"] {
        font-size: 2rem;
    }
</style>
""", unsafe_allow_html=True)


def init_session_state():
    """Initialize session state variables."""
    if "df_input" not in st.session_state:
        st.session_state.df_input = None
    if "df_processed" not in st.session_state:
        st.session_state.df_processed = None
    if "processing_complete" not in st.session_state:
        st.session_state.processing_complete = False
    if "processing_stats" not in st.session_state:
        st.session_state.processing_stats = {}
    if "artifacts_log" not in st.session_state:
        st.session_state.artifacts_log = []


def process_single_row(
    row: pd.Series,
    scraper: WebsiteScraper,
    extractor: ArtifactExtractor,
    ranker: ArtifactRanker,
    generator: LineGenerator,
    validator: Validator,
) -> Tuple[dict, List[Artifact]]:
    """Process a single row and return results with artifacts for inspection."""
    site_url = get_site_url(row)
    description = get_company_description(row)
    location = get_location(row)

    website_elements = None
    if site_url:
        try:
            website_elements = scraper.scrape_website(site_url)
        except Exception:
            pass

    artifacts = extractor.extract_all(website_elements, description)

    if location and not any(a.artifact_type == ArtifactType.LOCATION for a in artifacts):
        artifacts.append(Artifact(
            text=location,
            artifact_type=ArtifactType.LOCATION,
            evidence_source="csv_field",
            evidence_url="",
            score=1.0,
        ))

    valid_artifacts = []
    for artifact in artifacts:
        result = validator.validate_artifact(artifact)
        if result.is_valid:
            valid_artifacts.append(artifact)

    selected = ranker.select_with_fallback(valid_artifacts)
    line = generator.generate(selected)
    validation = validator.validate(line, selected)

    if not validation.is_valid and len(valid_artifacts) > 1:
        ranked = ranker.rank_artifacts(valid_artifacts)
        for alt_artifact in ranked[1:]:
            alt_line = generator.generate(alt_artifact)
            alt_validation = validator.validate(alt_line, alt_artifact)
            if alt_validation.is_valid:
                selected = alt_artifact
                line = alt_line
                break
        else:
            selected = ranker.get_fallback_artifact()
            line = generator.generate(selected)

    confidence = ranker.get_confidence_tier(selected)

    result = {
        "personalization_line": line,
        "artifact_type": selected.artifact_type.value,
        "artifact_text": selected.text if selected.artifact_type != ArtifactType.FALLBACK else "",
        "evidence_source": selected.evidence_source,
        "evidence_url": selected.evidence_url,
        "confidence_tier": confidence.value,
    }

    return result, artifacts


def render_sidebar():
    """Render the sidebar navigation."""
    with st.sidebar:
        st.title("Personalization Engine")
        st.markdown("---")

        page = st.radio(
            "Navigation",
            ["Upload & Preview", "Process Leads", "Results & Stats", "Artifact Inspector"],
            label_visibility="collapsed",
        )

        st.markdown("---")

        # Show quick stats if data is loaded
        if st.session_state.df_input is not None:
            st.markdown("### Data Status")
            st.metric("Leads Loaded", len(st.session_state.df_input))

            if st.session_state.df_processed is not None:
                st.metric("Processed", len(st.session_state.df_processed))
                if st.session_state.processing_stats:
                    stats = st.session_state.processing_stats
                    high_conf = stats.get("S", 0) + stats.get("A", 0)
                    total = sum(stats.get(t, 0) for t in ["S", "A", "B"])
                    if total > 0:
                        st.metric("High Confidence", f"{high_conf/total*100:.0f}%")

        st.markdown("---")
        st.markdown("**Quick Actions**")

        if st.button("Clear All Data", use_container_width=True):
            st.session_state.df_input = None
            st.session_state.df_processed = None
            st.session_state.processing_complete = False
            st.session_state.processing_stats = {}
            st.session_state.artifacts_log = []
            st.rerun()

    return page


def render_upload_page():
    """Render the upload and preview page."""
    st.header("Upload & Preview Leads")

    col1, col2 = st.columns([2, 1])

    with col1:
        uploaded_file = st.file_uploader(
            "Upload your CSV file",
            type=["csv"],
            help="Upload a CSV with lead data. Required columns: site_url/website, company_description (optional), location (optional)",
        )

        if uploaded_file is not None:
            try:
                df = pd.read_csv(uploaded_file, low_memory=False)
                df = normalize_columns(df)
                st.session_state.df_input = df
                st.session_state.processing_complete = False
                st.session_state.df_processed = None
                st.success(f"Loaded {len(df)} leads successfully!")
            except Exception as e:
                st.error(f"Error reading file: {e}")

    with col2:
        st.markdown("### Expected Columns")
        st.markdown("""
        - `site_url` / `website` / `domain`
        - `company_name`
        - `company_description`
        - `location` / `city` / `state`
        - `email` / `first_name` / `last_name`
        """)

    # Preview loaded data
    if st.session_state.df_input is not None:
        st.markdown("---")
        st.subheader("Data Preview")

        df = st.session_state.df_input

        # Column detection status
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            has_url = any(col for col in df.columns if "url" in col.lower() or "website" in col.lower() or "domain" in col.lower())
            st.metric("Website URLs", "Detected" if has_url else "Missing", delta=None)
        with col2:
            has_desc = any(col for col in df.columns if "description" in col.lower())
            st.metric("Descriptions", "Detected" if has_desc else "Missing", delta=None)
        with col3:
            has_loc = any(col for col in df.columns if "location" in col.lower() or "city" in col.lower() or "state" in col.lower())
            st.metric("Locations", "Detected" if has_loc else "Missing", delta=None)
        with col4:
            st.metric("Total Rows", len(df))

        st.markdown("---")

        # Show sample data
        st.markdown("### Sample Data (first 10 rows)")
        display_cols = [col for col in df.columns if col.lower() in [
            "company_name", "site_url", "website", "domain", "email",
            "first_name", "last_name", "company_description", "location", "city", "state"
        ]]
        if not display_cols:
            display_cols = df.columns[:8].tolist()

        st.dataframe(df[display_cols].head(10), use_container_width=True)

        # All columns
        with st.expander("View All Columns"):
            st.write(df.columns.tolist())


def render_process_page():
    """Render the processing page."""
    st.header("Process Leads")

    if st.session_state.df_input is None:
        st.warning("Please upload a CSV file first.")
        return

    df = st.session_state.df_input

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### Processing Options")

        limit = st.number_input(
            "Limit rows (0 = all)",
            min_value=0,
            max_value=len(df),
            value=0,
            help="Process only first N rows for testing. Set to 0 to process all.",
        )

        seed = st.number_input(
            "Random seed (optional)",
            min_value=0,
            value=42,
            help="Set a seed for reproducible template selection",
        )

        use_seed = st.checkbox("Use random seed", value=True)

    with col2:
        st.markdown("### Status")
        if st.session_state.processing_complete:
            st.success("Processing complete!")
            stats = st.session_state.processing_stats
            st.markdown(f"""
            - **Tier S:** {stats.get('S', 0)} leads
            - **Tier A:** {stats.get('A', 0)} leads
            - **Tier B:** {stats.get('B', 0)} leads
            - **Errors:** {stats.get('errors', 0)}
            """)
        else:
            st.info("Ready to process")

    st.markdown("---")

    # Process button
    if st.button("Start Processing", type="primary", use_container_width=True):
        rows_to_process = df.head(limit) if limit > 0 else df
        total = len(rows_to_process)

        # Initialize components
        scraper = WebsiteScraper()
        extractor = ArtifactExtractor()
        ranker = ArtifactRanker()
        generator = LineGenerator(seed=seed if use_seed else None)
        validator = Validator()

        # Progress tracking
        progress_bar = st.progress(0)
        status_text = st.empty()
        stats_display = st.empty()

        results = []
        artifacts_log = []
        stats = {"S": 0, "A": 0, "B": 0, "errors": 0}

        for idx, (row_idx, row) in enumerate(rows_to_process.iterrows()):
            try:
                company = get_company_name(row) or f"Row {row_idx}"
                status_text.markdown(f"**Processing:** {company} ({idx + 1}/{total})")

                result, row_artifacts = process_single_row(
                    row, scraper, extractor, ranker, generator, validator
                )
                results.append(result)

                # Log artifacts for inspection
                artifacts_log.append({
                    "row_idx": row_idx,
                    "company": company,
                    "artifacts": row_artifacts,
                    "selected": result,
                })

                # Update stats
                tier = result["confidence_tier"]
                stats[tier] = stats.get(tier, 0) + 1

            except Exception as e:
                results.append({
                    "personalization_line": "Came across your site-quick question.",
                    "artifact_type": "FALLBACK",
                    "artifact_text": "",
                    "evidence_source": "error",
                    "evidence_url": "",
                    "confidence_tier": "B",
                })
                stats["errors"] = stats.get("errors", 0) + 1
                artifacts_log.append({
                    "row_idx": row_idx,
                    "company": get_company_name(row) or f"Row {row_idx}",
                    "artifacts": [],
                    "selected": None,
                    "error": str(e),
                })

            # Update progress
            progress = (idx + 1) / total
            progress_bar.progress(progress)

            # Update stats display
            processed = idx + 1
            high_conf = stats["S"] + stats["A"]
            high_conf_pct = high_conf / processed * 100 if processed > 0 else 0

            stats_display.markdown(f"""
            | Metric | Value |
            |--------|-------|
            | Processed | {processed}/{total} |
            | Tier S | {stats['S']} |
            | Tier A | {stats['A']} |
            | Tier B | {stats['B']} |
            | High Confidence | {high_conf_pct:.1f}% |
            | Errors | {stats['errors']} |
            """)

        # Create processed DataFrame
        results_df = pd.DataFrame(results)
        processed_df = rows_to_process.copy()
        for col in results_df.columns:
            processed_df[col] = results_df[col].values

        # Save to session state
        st.session_state.df_processed = processed_df
        st.session_state.processing_complete = True
        st.session_state.processing_stats = stats
        st.session_state.artifacts_log = artifacts_log

        status_text.markdown("**Processing complete!**")
        st.balloons()


def render_results_page():
    """Render the results and statistics page."""
    st.header("Results & Statistics")

    if st.session_state.df_processed is None:
        st.warning("No processed data available. Please process leads first.")
        return

    df = st.session_state.df_processed
    stats = st.session_state.processing_stats

    # Summary metrics
    st.subheader("Summary")
    col1, col2, col3, col4, col5 = st.columns(5)

    total = len(df)
    tier_s = stats.get("S", 0)
    tier_a = stats.get("A", 0)
    tier_b = stats.get("B", 0)
    high_conf = tier_s + tier_a

    with col1:
        st.metric("Total Processed", total)
    with col2:
        st.metric("Tier S", tier_s, delta=f"{tier_s/total*100:.1f}%" if total > 0 else None)
    with col3:
        st.metric("Tier A", tier_a, delta=f"{tier_a/total*100:.1f}%" if total > 0 else None)
    with col4:
        st.metric("Tier B", tier_b, delta=f"{tier_b/total*100:.1f}%" if total > 0 else None)
    with col5:
        st.metric("High Confidence (S+A)", f"{high_conf/total*100:.0f}%" if total > 0 else "0%")

    st.markdown("---")

    # Charts
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Confidence Tier Distribution")
        tier_data = pd.DataFrame({
            "Tier": ["S", "A", "B"],
            "Count": [tier_s, tier_a, tier_b],
            "Color": ["#00d4aa", "#ffa500", "#6c757d"],
        })
        fig = px.pie(
            tier_data,
            values="Count",
            names="Tier",
            color="Tier",
            color_discrete_map={"S": "#00d4aa", "A": "#ffa500", "B": "#6c757d"},
            hole=0.4,
        )
        fig.update_traces(textposition="inside", textinfo="percent+label")
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("Artifact Type Breakdown")
        if "artifact_type" in df.columns:
            type_counts = df["artifact_type"].value_counts()
            fig = px.bar(
                x=type_counts.index,
                y=type_counts.values,
                labels={"x": "Artifact Type", "y": "Count"},
                color=type_counts.values,
                color_continuous_scale="Viridis",
            )
            fig.update_layout(showlegend=False)
            st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    # Results table
    st.subheader("Processed Leads")

    # Filter options
    col1, col2 = st.columns(2)
    with col1:
        tier_filter = st.multiselect(
            "Filter by Tier",
            options=["S", "A", "B"],
            default=["S", "A", "B"],
        )
    with col2:
        search = st.text_input("Search company/line", "")

    # Apply filters
    display_df = df.copy()
    if tier_filter:
        display_df = display_df[display_df["confidence_tier"].isin(tier_filter)]
    if search:
        mask = (
            display_df.apply(lambda row: search.lower() in str(row).lower(), axis=1)
        )
        display_df = display_df[mask]

    # Select columns to display
    display_cols = ["company_name", "personalization_line", "artifact_type", "artifact_text", "confidence_tier", "evidence_source"]
    display_cols = [c for c in display_cols if c in display_df.columns]

    st.dataframe(
        display_df[display_cols],
        use_container_width=True,
        height=400,
    )

    st.markdown(f"Showing {len(display_df)} of {len(df)} leads")

    st.markdown("---")

    # Download section
    st.subheader("Export Results")

    col1, col2 = st.columns(2)

    with col1:
        csv = df.to_csv(index=False)
        st.download_button(
            label="Download Full CSV",
            data=csv,
            file_name="personalized_leads.csv",
            mime="text/csv",
            use_container_width=True,
        )

    with col2:
        # High confidence only
        high_conf_df = df[df["confidence_tier"].isin(["S", "A"])]
        csv_high = high_conf_df.to_csv(index=False)
        st.download_button(
            label="Download High Confidence Only (S+A)",
            data=csv_high,
            file_name="high_confidence_leads.csv",
            mime="text/csv",
            use_container_width=True,
        )


def render_inspector_page():
    """Render the artifact inspector page."""
    st.header("Artifact Inspector")

    if not st.session_state.artifacts_log:
        st.warning("No processing data available. Please process leads first.")
        return

    st.markdown("Inspect the artifacts extracted for each lead and understand why specific lines were chosen.")

    # Lead selector
    log = st.session_state.artifacts_log
    companies = [item["company"] for item in log]

    selected_idx = st.selectbox(
        "Select a lead to inspect",
        range(len(companies)),
        format_func=lambda x: f"{x + 1}. {companies[x]}",
    )

    if selected_idx is not None:
        item = log[selected_idx]

        st.markdown("---")

        # Lead info
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("### Lead Info")
            st.markdown(f"**Company:** {item['company']}")

            if item.get("error"):
                st.error(f"**Error:** {item['error']}")
            elif item.get("selected"):
                sel = item["selected"]
                st.markdown(f"**Generated Line:** {sel['personalization_line']}")

                tier_color = {"S": "green", "A": "orange", "B": "gray"}[sel["confidence_tier"]]
                st.markdown(f"**Confidence Tier:** :{tier_color}[{sel['confidence_tier']}]")
                st.markdown(f"**Artifact Type:** {sel['artifact_type']}")
                st.markdown(f"**Artifact Text:** {sel['artifact_text']}")
                st.markdown(f"**Evidence Source:** {sel['evidence_source']}")
                if sel["evidence_url"]:
                    st.markdown(f"**Evidence URL:** {sel['evidence_url']}")

        with col2:
            st.markdown("### All Extracted Artifacts")
            artifacts = item.get("artifacts", [])

            if artifacts:
                # Group by tier
                tier_mapping = ARTIFACT_CONFIDENCE

                artifacts_data = []
                for a in artifacts:
                    tier = tier_mapping.get(a.artifact_type, ConfidenceTier.B).value
                    artifacts_data.append({
                        "Tier": tier,
                        "Type": a.artifact_type.value,
                        "Text": a.text[:50] + "..." if len(a.text) > 50 else a.text,
                        "Score": f"{a.score:.1f}",
                        "Source": a.evidence_source,
                    })

                artifacts_df = pd.DataFrame(artifacts_data)

                # Sort by tier then score
                tier_order = {"S": 0, "A": 1, "B": 2}
                artifacts_df["tier_order"] = artifacts_df["Tier"].map(tier_order)
                artifacts_df = artifacts_df.sort_values(["tier_order", "Score"], ascending=[True, False])
                artifacts_df = artifacts_df.drop("tier_order", axis=1)

                st.dataframe(artifacts_df, use_container_width=True, hide_index=True)
                st.markdown(f"**Total artifacts:** {len(artifacts)}")
            else:
                st.info("No artifacts extracted for this lead.")

        # Detailed artifact view
        if artifacts:
            st.markdown("---")
            st.markdown("### Artifact Details")

            for i, a in enumerate(sorted(artifacts, key=lambda x: -x.score)):
                tier = ARTIFACT_CONFIDENCE.get(a.artifact_type, ConfidenceTier.B).value
                tier_emoji = {"S": "", "A": "", "B": ""}[tier]

                with st.expander(f"{tier_emoji} {a.artifact_type.value}: {a.text[:40]}..."):
                    st.markdown(f"**Full Text:** {a.text}")
                    st.markdown(f"**Type:** {a.artifact_type.value}")
                    st.markdown(f"**Tier:** {tier}")
                    st.markdown(f"**Score:** {a.score:.2f}")
                    st.markdown(f"**Source:** {a.evidence_source}")
                    if a.evidence_url:
                        st.markdown(f"**URL:** {a.evidence_url}")


def main():
    """Main application entry point."""
    init_session_state()

    page = render_sidebar()

    if page == "Upload & Preview":
        render_upload_page()
    elif page == "Process Leads":
        render_process_page()
    elif page == "Results & Stats":
        render_results_page()
    elif page == "Artifact Inspector":
        render_inspector_page()


if __name__ == "__main__":
    main()
