#!/usr/bin/env python3
"""
Streamlit Dashboard for the Personalization Line Engine

Run with: streamlit run app.py
"""
import io
import json
import logging
import os
from datetime import datetime
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
from instantly_client import InstantlyClient
from serper_client import SerperClient, extract_artifacts_from_serper
from ai_line_generator import AILineGenerator, test_api_key as test_anthropic_key


# Data persistence directory
DATA_DIR = "saved_results"
RESULTS_FILE = os.path.join(DATA_DIR, "instantly_results.json")


def ensure_data_dir():
    """Create data directory if it doesn't exist."""
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)


def save_results(results_log: List[dict], stats: dict, campaign_name: str = ""):
    """Save results to a JSON file for persistence."""
    ensure_data_dir()
    data = {
        "saved_at": datetime.now().isoformat(),
        "campaign_name": campaign_name,
        "stats": stats,
        "results": results_log,
    }
    with open(RESULTS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def load_saved_results() -> Optional[dict]:
    """Load previously saved results if they exist."""
    if os.path.exists(RESULTS_FILE):
        try:
            with open(RESULTS_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None
    return None


def delete_saved_results():
    """Delete saved results file."""
    if os.path.exists(RESULTS_FILE):
        os.remove(RESULTS_FILE)


# Page configuration
st.set_page_config(
    page_title="Instantly Tools",
    page_icon="⚡",
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
    # Instantly integration - from env var
    if "instantly_api_key" not in st.session_state:
        st.session_state.instantly_api_key = os.environ.get("INSTANTLY_API_KEY", "")
    if "instantly_connected" not in st.session_state:
        # Auto-connect if env var is set
        st.session_state.instantly_connected = bool(os.environ.get("INSTANTLY_API_KEY"))
    if "instantly_campaigns" not in st.session_state:
        st.session_state.instantly_campaigns = []
        # Auto-fetch campaigns if connected via env var
        if st.session_state.instantly_connected and st.session_state.instantly_api_key:
            try:
                client = InstantlyClient(st.session_state.instantly_api_key)
                st.session_state.instantly_campaigns = client.list_campaigns()
            except Exception:
                pass
    if "instantly_leads" not in st.session_state:
        st.session_state.instantly_leads = []
    if "instantly_sync_stats" not in st.session_state:
        st.session_state.instantly_sync_stats = {}
    if "instantly_results_log" not in st.session_state:
        st.session_state.instantly_results_log = []
    if "instantly_sync_complete" not in st.session_state:
        st.session_state.instantly_sync_complete = False
    if "saved_campaign_name" not in st.session_state:
        st.session_state.saved_campaign_name = ""
    # Serper API key - from env var or hardcoded fallback
    if "serper_api_key" not in st.session_state:
        st.session_state.serper_api_key = os.environ.get("SERPER_API_KEY", "2e396f4a9a63bd80b9c15e4857addd053b3747ec")
    # Anthropic API for AI-generated lines - from env var
    if "anthropic_api_key" not in st.session_state:
        st.session_state.anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if "anthropic_connected" not in st.session_state:
        # Auto-connect if env var is set and non-empty
        env_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        st.session_state.anthropic_connected = bool(env_key)
    if "use_ai_generation" not in st.session_state:
        # Default to AI generation if Anthropic is connected
        st.session_state.use_ai_generation = st.session_state.anthropic_connected

    # Processing state for cancel functionality
    if "processing_cancelled" not in st.session_state:
        st.session_state.processing_cancelled = False

    # Auto-load saved results on first run
    if "results_loaded" not in st.session_state:
        st.session_state.results_loaded = True
        saved = load_saved_results()
        if saved:
            st.session_state.instantly_results_log = saved.get("results", [])
            st.session_state.instantly_sync_stats = saved.get("stats", {})
            st.session_state.instantly_sync_complete = bool(saved.get("results"))
            st.session_state.saved_campaign_name = saved.get("campaign_name", "")


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
        st.title("Instantly Tools")
        st.caption("Lead personalization & automation")
        st.markdown("---")

        # Main Instantly Tools Section
        st.markdown("### Instantly")
        page = st.radio(
            "Instantly Tools",
            ["CSV Personalization", "Campaign Sync", "Unibox Automation"],
            label_visibility="collapsed",
            key="instantly_nav",
        )

        # Show Instantly stats if available
        if st.session_state.instantly_sync_complete and st.session_state.instantly_sync_stats:
            stats = st.session_state.instantly_sync_stats
            total = stats.get("S", 0) + stats.get("A", 0) + stats.get("B", 0)
            if total > 0:
                st.markdown("---")
                st.markdown("##### Last Run")
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Processed", total)
                with col2:
                    high_conf = stats.get("S", 0) + stats.get("A", 0)
                    st.metric("Quality", f"{high_conf/total*100:.0f}%")

        st.markdown("---")

        # CSV Tools in collapsible section
        with st.expander("CSV Tools (Advanced)", expanded=False):
            st.caption("Process leads from CSV files")

            # Use a button to enter CSV mode
            if st.button("Open CSV Tools", use_container_width=True, type="secondary"):
                st.session_state.use_csv_tools = True
                st.rerun()

            if st.session_state.get("use_csv_tools"):
                csv_page = st.radio(
                    "CSV Tools",
                    ["Upload & Preview", "Process Leads", "Results & Stats", "Artifact Inspector"],
                    label_visibility="collapsed",
                    key="csv_nav",
                )
                page = f"CSV:{csv_page}"

                # Show CSV stats if data is loaded
                if st.session_state.df_input is not None:
                    st.markdown("---")
                    st.metric("CSV Leads", len(st.session_state.df_input))

                if st.button("Back to Instantly Tools", use_container_width=True):
                    st.session_state.use_csv_tools = False
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

        st.dataframe(df[display_cols].head(10), width="stretch")

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
    if st.button("Start Processing", type="primary", width="stretch"):
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
        st.plotly_chart(fig, width="stretch")

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
            st.plotly_chart(fig, width="stretch")

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
        width="stretch",
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
            width="stretch",
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
            width="stretch",
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

                st.dataframe(artifacts_df, width="stretch", hide_index=True)
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


def render_csv_personalization_page():
    """Render the CSV Personalization page - Upload CSV, process, download, optionally push to Instantly."""
    st.header("CSV Personalization")
    st.caption("Upload CSV → Build personalization → Download CSV → Optional push to Instantly")

    # Initialize session state for CSV workflow
    if "csv_upload_df" not in st.session_state:
        st.session_state.csv_upload_df = None
    if "csv_processed_df" not in st.session_state:
        st.session_state.csv_processed_df = None
    if "csv_results_log" not in st.session_state:
        st.session_state.csv_results_log = []
    if "csv_processing_complete" not in st.session_state:
        st.session_state.csv_processing_complete = False
    if "csv_processing_stats" not in st.session_state:
        st.session_state.csv_processing_stats = {}

    # ========== STEP 1: API CONFIGURATION ==========
    with st.expander("API Configuration", expanded=not st.session_state.anthropic_connected):
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("#### Claude AI (Required)")
            anthropic_key = st.text_input(
                "Anthropic API Key",
                value=st.session_state.anthropic_api_key,
                type="password",
                help="From console.anthropic.com",
                key="csv_anthropic_input",
            )
            if st.session_state.anthropic_connected:
                st.success("Connected")
            elif st.button("Connect Claude", type="primary", key="csv_anthropic_connect"):
                if anthropic_key:
                    with st.spinner("Testing..."):
                        if test_anthropic_key(anthropic_key):
                            st.session_state.anthropic_api_key = anthropic_key
                            st.session_state.anthropic_connected = True
                            st.session_state.use_ai_generation = True
                            st.rerun()
                        else:
                            st.error("Invalid key.")

        with col2:
            st.markdown("#### Instantly (Optional - for pushing)")
            instantly_key = st.text_input(
                "Instantly API Key",
                value=st.session_state.instantly_api_key,
                type="password",
                help="Only needed if you want to push to Instantly",
                key="csv_instantly_input",
            )
            if st.session_state.instantly_connected:
                st.success("Connected")
            elif st.button("Connect Instantly", key="csv_instantly_connect"):
                if instantly_key:
                    with st.spinner("Testing..."):
                        try:
                            client = InstantlyClient(instantly_key)
                            if client.test_connection():
                                st.session_state.instantly_api_key = instantly_key
                                st.session_state.instantly_connected = True
                                st.session_state.instantly_campaigns = client.list_campaigns()
                                st.rerun()
                        except Exception as e:
                            st.error(f"Error: {e}")

    st.markdown("---")

    # ========== STEP 2: UPLOAD CSV ==========
    st.markdown("### Step 1: Upload CSV")

    uploaded_file = st.file_uploader(
        "Upload your leads CSV",
        type=["csv"],
        help="CSV with company_name, website/domain, and email columns",
        key="csv_uploader",
    )

    if uploaded_file is not None:
        try:
            df = pd.read_csv(uploaded_file, low_memory=False)
            # Debug: Show original column names before normalization
            original_cols = list(df.columns)
            df = normalize_columns(df)
            st.session_state.csv_upload_df = df
            # Reset processing state when new file uploaded
            st.session_state.csv_processing_complete = False
            st.session_state.csv_processed_df = None
            st.session_state.csv_results_log = []
            st.success(f"Loaded {len(df)} leads")
            # Debug: Show column mapping info
            with st.expander("Debug: Column Mapping", expanded=False):
                st.write("**Original columns:**", original_cols[:15])
                st.write("**Normalized columns:**", list(df.columns)[:15])
                # Check if company_name exists
                if "company_name" in df.columns:
                    sample = df["company_name"].dropna().head(3).tolist()
                    st.success(f"company_name column found! Samples: {sample}")
                else:
                    st.error("company_name column NOT found after normalization!")
        except Exception as e:
            st.error(f"Error reading file: {e}")

    # Show preview if data loaded
    if st.session_state.csv_upload_df is not None:
        df = st.session_state.csv_upload_df

        with st.expander(f"Preview {len(df)} leads", expanded=True):
            preview_cols = [c for c in df.columns if c.lower() in [
                "company_name", "email", "first_name", "last_name",
                "website", "site_url", "domain", "location", "city", "state"
            ]]
            if not preview_cols:
                preview_cols = df.columns[:6].tolist()
            st.dataframe(df[preview_cols].head(20), use_container_width=True, hide_index=True)
            if len(df) > 20:
                st.caption(f"Showing 20 of {len(df)} leads")

        st.markdown("---")

        # ========== STEP 3: PROCESS ==========
        st.markdown("### Step 2: Build Personalization")

        if not st.session_state.anthropic_connected:
            st.warning("Connect Claude AI above to enable processing")
        else:
            col1, col2 = st.columns([2, 1])
            with col1:
                limit = st.number_input(
                    "Limit (0 = all)",
                    min_value=0,
                    max_value=len(df),
                    value=0,
                    help="Process only first N leads for testing",
                    key="csv_limit",
                )
            with col2:
                actual_count = limit if limit > 0 else len(df)
                st.metric("Will Process", actual_count)

            # Confirmation
            confirm = st.checkbox(
                f"I confirm I want to process {actual_count} leads",
                key="csv_confirm_process",
            )

            if st.button("Build Personalization", type="primary", disabled=not confirm, use_container_width=True):
                # Initialize components
                serper = SerperClient(st.session_state.serper_api_key)
                ai_generator = AILineGenerator(st.session_state.anthropic_api_key)
                validator = Validator()

                # Test Claude API first
                st.info("Testing Claude API...")
                test_result = ai_generator.generate_line("Test", "Test company", {})
                if test_result.artifact_type in ["API_ERROR", "UNEXPECTED_ERROR", "CONNECTION_ERROR"]:
                    st.error(f"Claude API failed: {test_result.reasoning}")
                    st.stop()
                st.success("Claude API ready!")

                progress_bar = st.progress(0)
                status_text = st.empty()
                stats_display = st.empty()

                rows_to_process = df.head(limit) if limit > 0 else df
                total = len(rows_to_process)

                stats = {"S": 0, "A": 0, "B": 0, "errors": 0}
                results_log = []
                results_data = []

                # Debug: show first row columns
                first_row = rows_to_process.iloc[0]
                st.write("**DEBUG - First row columns:**", list(first_row.index)[:10])
                st.write("**DEBUG - Looking for company in:**", [c for c in first_row.index if "company" in c.lower()])

                for idx, (row_idx, row) in enumerate(rows_to_process.iterrows()):
                    try:
                        company_name = get_company_name(row) or "Unknown"
                        domain = get_site_url(row) or ""
                        location = get_location(row) or ""
                        email = row.get("email", "") or ""

                        # Debug first 3 rows
                        if idx < 3:
                            st.write(f"**DEBUG Row {idx}:** company={company_name}, domain={domain[:30] if domain else 'None'}")

                        status_text.markdown(f"**Processing:** {company_name} ({idx + 1}/{total})")

                        # Serper lookup
                        serper_description = ""
                        try:
                            company_info = serper.get_company_info(company_name, domain, location)
                            serper_description = extract_artifacts_from_serper(company_info)

                            # Check confidence
                            if company_info.is_low_confidence or company_info.industry_mismatch_detected:
                                serper_description = ""
                        except Exception:
                            pass

                        # Build lead data
                        lead_data = {
                            "company_description": row.get("company_description", "") or "",
                            "industry": row.get("industry", "") or "",
                            "location": location,
                        }

                        # Generate line with Claude
                        ai_result = ai_generator.generate_line(
                            company_name=company_name,
                            serper_data=serper_description,
                            lead_data=lead_data,
                        )

                        # Use AI result directly - Claude validates internally
                        final_line = ai_result.line
                        final_tier = ai_result.confidence_tier
                        final_type = ai_result.artifact_type

                        # Fix type if Claude returned generic fallback with wrong type
                        if final_line.lower().strip().rstrip('.') == "came across your company online":
                            final_tier = "B"
                            final_type = "FALLBACK"

                        stats[final_tier] = stats.get(final_tier, 0) + 1

                        results_log.append({
                            "email": email,
                            "company": company_name,
                            "line": final_line,
                            "tier": final_tier,
                            "type": final_type,
                            "artifact": ai_result.artifact_used or "",
                            "source": "Serper+Claude" if serper_description else "Claude",
                        })

                        results_data.append({
                            "personalization_line": final_line,
                            "artifact_type": final_type,
                            "confidence_tier": final_tier,
                        })

                    except Exception as e:
                        stats["errors"] += 1
                        results_log.append({
                            "email": row.get("email", ""),
                            "company": get_company_name(row) or "",
                            "line": f"Error: {str(e)[:50]}",
                            "tier": "ERROR",
                            "type": "ERROR",
                            "artifact": "",
                            "source": "",
                        })
                        results_data.append({
                            "personalization_line": "Came across your company online.",
                            "artifact_type": "FALLBACK",
                            "confidence_tier": "B",
                        })

                    progress_bar.progress((idx + 1) / total)

                    # Update stats
                    processed = stats["S"] + stats["A"] + stats["B"]
                    if processed > 0:
                        stats_display.markdown(f"""
                        **Progress:** {idx + 1}/{total} | S: {stats['S']} | A: {stats['A']} | B: {stats['B']} | Errors: {stats['errors']}
                        """)

                # Create processed DataFrame
                results_df = pd.DataFrame(results_data)
                processed_df = rows_to_process.copy()
                for col in results_df.columns:
                    processed_df[col] = results_df[col].values

                # Save to session state
                st.session_state.csv_processed_df = processed_df
                st.session_state.csv_results_log = results_log
                st.session_state.csv_processing_complete = True
                st.session_state.csv_processing_stats = stats

                status_text.markdown("**Processing complete!**")
                st.balloons()

    # ========== STEP 4: RESULTS - DOWNLOAD & PUSH ==========
    if st.session_state.csv_processing_complete and st.session_state.csv_processed_df is not None:
        st.markdown("---")
        st.markdown("### Step 3: Review & Export")

        stats = st.session_state.csv_processing_stats
        results_log = st.session_state.csv_results_log
        processed_df = st.session_state.csv_processed_df

        # Stats summary
        col1, col2, col3, col4 = st.columns(4)
        total = stats.get("S", 0) + stats.get("A", 0) + stats.get("B", 0)
        with col1:
            st.metric("Total", total)
        with col2:
            st.metric("Tier S", stats.get("S", 0))
        with col3:
            st.metric("Tier A", stats.get("A", 0))
        with col4:
            high_conf = stats.get("S", 0) + stats.get("A", 0)
            st.metric("High Quality", f"{high_conf/total*100:.0f}%" if total > 0 else "0%")

        # Results table
        results_df = pd.DataFrame(results_log)
        with st.expander("View Results", expanded=True):
            st.dataframe(results_df, use_container_width=True, hide_index=True)

        st.markdown("---")

        # ========== DOWNLOAD CSV ==========
        st.markdown("### Step 4: Download CSV")
        col1, col2 = st.columns(2)

        with col1:
            csv_all = processed_df.to_csv(index=False)
            st.download_button(
                "Download Full CSV",
                data=csv_all,
                file_name="personalized_leads.csv",
                mime="text/csv",
                use_container_width=True,
                type="primary",
            )

        with col2:
            high_conf_df = processed_df[processed_df["confidence_tier"].isin(["S", "A"])]
            csv_high = high_conf_df.to_csv(index=False)
            st.download_button(
                f"Download High Quality Only ({len(high_conf_df)})",
                data=csv_high,
                file_name="high_quality_leads.csv",
                mime="text/csv",
                use_container_width=True,
            )

        st.markdown("---")

        # ========== OPTIONAL: PUSH TO INSTANTLY ==========
        st.markdown("### Step 5: Push to Instantly (Optional)")

        if not st.session_state.instantly_connected:
            st.info("Connect Instantly API above to enable pushing to campaigns")
        else:
            campaigns = st.session_state.instantly_campaigns
            if campaigns:
                col1, col2 = st.columns([2, 1])

                with col1:
                    campaign_options = {f"{c.name} ({c.status})": c.id for c in campaigns}
                    selected_campaign = st.selectbox(
                        "Select Campaign",
                        options=list(campaign_options.keys()),
                        key="csv_campaign_select",
                    )
                    selected_campaign_id = campaign_options[selected_campaign]

                with col2:
                    if st.button("Refresh Campaigns", key="csv_refresh_campaigns"):
                        client = InstantlyClient(st.session_state.instantly_api_key)
                        st.session_state.instantly_campaigns = client.list_campaigns()
                        st.rerun()

                st.warning("This will update leads in the selected Instantly campaign. Make sure the emails match!")

                confirm_push = st.checkbox(
                    f"I confirm I want to push {len(results_log)} leads to Instantly",
                    key="csv_confirm_push",
                )

                if st.button("Push to Instantly", type="primary", disabled=not confirm_push, use_container_width=True):
                    instantly_client = InstantlyClient(st.session_state.instantly_api_key)

                    push_progress = st.progress(0)
                    push_status = st.empty()

                    success_count = 0
                    fail_count = 0

                    for idx, result in enumerate(results_log):
                        if result.get("tier") not in ["ERROR", "SKIPPED"]:
                            variables = {
                                "personalization_line": result.get("line", ""),
                                "artifact_type": result.get("type", ""),
                                "artifact_text": result.get("artifact", ""),
                                "confidence_tier": result.get("tier", ""),
                            }

                            update_success, _ = instantly_client.update_lead_variables(
                                lead_id=None,
                                variables=variables,
                                email=result.get("email"),
                                campaign_id=selected_campaign_id,
                            )

                            if update_success:
                                success_count += 1
                            else:
                                fail_count += 1

                        push_progress.progress((idx + 1) / len(results_log))
                        push_status.markdown(f"**Pushing:** {idx + 1}/{len(results_log)} | Success: {success_count} | Failed: {fail_count}")

                    if fail_count == 0:
                        st.success(f"Successfully pushed {success_count} leads to Instantly!")
                    else:
                        st.warning(f"Pushed {success_count} leads, {fail_count} failed (email may not exist in campaign)")
            else:
                st.warning("No campaigns found in Instantly")

        # Clear button
        st.markdown("---")
        if st.button("Clear & Start Over", key="csv_clear"):
            st.session_state.csv_upload_df = None
            st.session_state.csv_processed_df = None
            st.session_state.csv_results_log = []
            st.session_state.csv_processing_complete = False
            st.session_state.csv_processing_stats = {}
            st.rerun()


def render_instantly_page():
    """Render the Campaign Sync page - fetch from Instantly, process, sync back."""
    st.header("Campaign Sync")
    st.caption("Fetch leads from Instantly campaign, process, and sync back automatically")

    # ========== WORKFLOW STATUS BAR ==========
    # Determine current workflow state
    step1_done = st.session_state.instantly_connected
    step2_done = st.session_state.anthropic_connected
    step3_done = bool(st.session_state.instantly_leads)
    step4_done = st.session_state.instantly_sync_complete

    # Show workflow progress
    st.markdown("### Workflow Progress")
    cols = st.columns(4)
    with cols[0]:
        if step1_done:
            st.success("1. Instantly Connected")
        else:
            st.warning("1. Connect Instantly")
    with cols[1]:
        if step2_done:
            st.success("2. Claude AI Ready")
        else:
            st.info("2. Connect Claude (optional)")
    with cols[2]:
        if step3_done:
            leads = st.session_state.instantly_leads
            leads_with = sum(1 for l in leads if l.custom_variables.get("personalization_line") and str(l.custom_variables.get("personalization_line")).strip())
            leads_without = len(leads) - leads_with
            st.success(f"3. {len(leads)} Leads Fetched")
            st.caption(f"{leads_without} new, {leads_with} existing")
        else:
            st.warning("3. Fetch Leads")
    with cols[3]:
        if step4_done:
            stats = st.session_state.instantly_sync_stats
            processed = stats.get("S", 0) + stats.get("A", 0) + stats.get("B", 0)
            st.success(f"4. {processed} Processed")
        else:
            st.info("4. Process & Sync")

    st.markdown("---")

    # ========== SETUP SECTION (Collapsible when done) ==========
    setup_expanded = not (step1_done and step2_done)
    with st.expander("API Configuration", expanded=setup_expanded):
        # Instantly API
        st.markdown("#### Instantly API")
        col1, col2 = st.columns([3, 1])
        with col1:
            api_key = st.text_input(
                "API Key",
                value=st.session_state.instantly_api_key,
                type="password",
                help="Your Instantly API V2 key",
                key="instantly_api_input",
            )
        with col2:
            st.markdown("<br>", unsafe_allow_html=True)
            if step1_done:
                st.button("Connected", disabled=True, key="instantly_connected_btn")
            elif st.button("Connect", type="primary", key="instantly_connect_btn"):
                if api_key:
                    with st.spinner("Testing connection..."):
                        try:
                            client = InstantlyClient(api_key)
                            if client.test_connection():
                                st.session_state.instantly_api_key = api_key
                                st.session_state.instantly_connected = True
                                campaigns = client.list_campaigns()
                                st.session_state.instantly_campaigns = campaigns
                                st.rerun()
                            else:
                                st.error("Connection failed.")
                        except Exception as e:
                            st.error(f"Error: {e}")
                else:
                    st.warning("Enter API key first.")

        st.markdown("---")

        # Claude API
        st.markdown("#### Claude AI (Recommended)")
        st.caption("Generates intelligent, context-aware personalization lines")
        col1, col2 = st.columns([3, 1])
        with col1:
            anthropic_key = st.text_input(
                "Anthropic API Key",
                value=st.session_state.anthropic_api_key,
                type="password",
                help="From console.anthropic.com",
                key="anthropic_api_input",
            )
        with col2:
            st.markdown("<br>", unsafe_allow_html=True)
            if step2_done:
                st.button("Connected", disabled=True, key="anthropic_connected_btn")
            elif st.button("Connect", type="primary", key="anthropic_connect_btn"):
                if anthropic_key:
                    with st.spinner("Testing..."):
                        if test_anthropic_key(anthropic_key):
                            st.session_state.anthropic_api_key = anthropic_key
                            st.session_state.anthropic_connected = True
                            st.session_state.use_ai_generation = True
                            st.rerun()
                        else:
                            st.error("Invalid key.")
                else:
                    st.warning("Enter API key first.")

        if step2_done:
            st.session_state.use_ai_generation = st.checkbox(
                "Use AI-generated lines (recommended)",
                value=st.session_state.use_ai_generation,
                key="use_ai_checkbox",
            )

    # ========== MAIN CAMPAIGN SECTION ==========
    if st.session_state.instantly_connected:
        campaigns = st.session_state.instantly_campaigns
        if campaigns:
            # Campaign selection in a prominent box
            st.markdown("### Select Campaign")
            col1, col2 = st.columns([2, 1])

            with col1:
                campaign_options = {f"{c.name} ({c.status})": c.id for c in campaigns}
                selected_campaign_name = st.selectbox(
                    "Campaign",
                    options=list(campaign_options.keys()),
                    label_visibility="collapsed",
                )
                selected_campaign_id = campaign_options[selected_campaign_name]

            with col2:
                if st.button("Refresh Campaigns", key="refresh_campaigns"):
                    with st.spinner("Refreshing..."):
                        client = InstantlyClient(st.session_state.instantly_api_key)
                        st.session_state.instantly_campaigns = client.list_campaigns()
                        st.rerun()

            st.markdown("---")

            # ========== CAMPAIGN DASHBOARD ==========
            st.markdown("### Campaign Dashboard")

            # Quick action buttons row
            col1, col2, col3 = st.columns(3)

            with col1:
                fetch_btn = st.button(
                    "Fetch Leads from Instantly",
                    type="primary" if not step3_done else "secondary",
                    key="fetch_leads_btn",
                    use_container_width=True,
                )

            with col2:
                # Processing options
                skip_existing = st.checkbox(
                    "Skip existing personalizations",
                    value=True,
                    key="skip_existing_check",
                    help="Only process leads that don't have personalization yet",
                )

            with col3:
                preview_only = st.checkbox(
                    "Preview mode (don't push)",
                    value=False,
                    key="preview_only_check",
                    help="Generate lines but don't update Instantly",
                )

            # Handle fetch button
            if fetch_btn:
                with st.spinner("Fetching leads from Instantly..."):
                    try:
                        client = InstantlyClient(st.session_state.instantly_api_key)
                        leads = client.list_leads(
                            campaign_id=selected_campaign_id,
                            limit=10000,  # Always fetch all
                        )

                        st.session_state.instantly_leads = leads
                        st.session_state.instantly_sync_complete = False  # Reset for new fetch
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error fetching leads: {e}")

            # ========== LEADS OVERVIEW ==========
            if st.session_state.instantly_leads:
                leads = st.session_state.instantly_leads

                # Separate leads into new vs existing
                new_leads = [lead for lead in leads
                            if not (lead.custom_variables.get("personalization_line")
                                   and str(lead.custom_variables.get("personalization_line")).strip())]
                existing_leads = [lead for lead in leads
                                 if lead.custom_variables.get("personalization_line")
                                 and str(lead.custom_variables.get("personalization_line")).strip()]

                leads_without_personalization = len(new_leads)
                leads_with_personalization = len(existing_leads)

                # Determine what to show based on skip_existing
                if skip_existing:
                    # ONLY show new leads - this is what will be processed
                    display_leads = new_leads
                    st.markdown("---")

                    if leads_without_personalization > 0:
                        st.success(f"### {leads_without_personalization} New Leads Ready to Process")
                        st.caption(f"({leads_with_personalization} existing leads will be skipped)")
                    else:
                        st.info("### No New Leads to Process")
                        st.markdown(f"All {leads_with_personalization} leads already have personalization. Add more leads to your campaign in Instantly and click 'Fetch Leads' again.")
                else:
                    # Show all leads when overwriting
                    display_leads = leads
                    st.markdown("---")
                    st.warning(f"### {len(leads)} Leads (Will Overwrite All)")
                    st.caption("Uncheck 'Skip existing' is OFF - all existing personalizations will be replaced")

                # Preview table showing ONLY what will be processed
                if display_leads:
                    with st.expander(f"Preview {len(display_leads)} Leads to Process", expanded=True):
                        preview_data = []
                        for lead in display_leads[:30]:  # Show first 30 of what will be processed
                            preview_data.append({
                                "Email": lead.email,
                                "Company": lead.company_name or "-",
                            })

                        preview_df = pd.DataFrame(preview_data)
                        st.dataframe(preview_df, use_container_width=True, hide_index=True)
                        if len(display_leads) > 30:
                            st.caption(f"Showing 30 of {len(display_leads)} leads that will be processed")

                st.markdown("---")

                # ========== PROCESS SECTION WITH CONFIRMATION ==========
                process_count = leads_without_personalization if skip_existing else len(leads)

                if process_count > 0:
                    # Limit input
                    col1, col2 = st.columns([2, 1])
                    with col1:
                        st.markdown(f"**Ready to process {process_count} leads**")
                    with col2:
                        limit = st.number_input(
                            "Limit (0 = all)",
                            min_value=0,
                            max_value=process_count,
                            value=0,
                            help="Process only first N leads",
                            key="limit_input",
                        )

                    actual_count = limit if limit > 0 else process_count

                    # Confirmation checkbox before processing
                    st.markdown("---")
                    confirm = st.checkbox(
                        f"I confirm I want to process {actual_count} leads and use API credits",
                        key="confirm_process",
                        help="Check this box to enable the process button"
                    )

                    col1, col2 = st.columns(2)
                    with col1:
                        process_btn = st.button(
                            f"Process {actual_count} Leads & Sync to Instantly",
                            type="primary",
                            key="process_sync_btn",
                            use_container_width=True,
                            disabled=not confirm,  # Disabled until confirmed
                        )
                    with col2:
                        if st.button("Clear & Start Over", key="clear_leads_btn", use_container_width=True):
                            st.session_state.instantly_leads = []
                            st.session_state.instantly_sync_complete = False
                            st.rerun()

                    if not confirm:
                        st.caption("Check the confirmation box above to enable processing")
                else:
                    process_btn = False
                    limit = 0
                    actual_count = 0

                # Process when button is clicked
                if process_btn:
                    # Initialize components
                    serper = SerperClient(st.session_state.serper_api_key)
                    instantly_client = InstantlyClient(st.session_state.instantly_api_key)
                    use_ai = st.session_state.use_ai_generation and st.session_state.anthropic_connected

                    # Show Serper status
                    serper_key = st.session_state.serper_api_key
                    if serper_key and len(serper_key) > 10:
                        st.info(f"✓ Serper API: Ready for company research")
                    else:
                        st.warning(f"✗ Serper API key missing or invalid - company research will be limited")

                    # AI generator or template-based fallback
                    ai_generator = None

                    # Show clear status about AI mode
                    if use_ai:
                        st.info(f"✓ AI Mode: Claude will generate personalization lines")
                    else:
                        st.error(f"✗ AI Mode DISABLED - Using template fallback. Check: use_ai_generation={st.session_state.use_ai_generation}, anthropic_connected={st.session_state.anthropic_connected}")

                    if use_ai:
                        ai_generator = AILineGenerator(st.session_state.anthropic_api_key)

                        # TEST Claude API before processing to avoid wasting Serper credits
                        st.info("Testing Claude API connection...")
                        test_result = ai_generator.generate_line(
                            company_name="Test Company",
                            serper_data="Test company provides software services.",
                            lead_data={}
                        )
                        if test_result.artifact_type in ["API_ERROR", "UNEXPECTED_ERROR", "CONNECTION_ERROR"]:
                            st.error(f"❌ Claude API TEST FAILED: {test_result.reasoning}")
                            st.error("Fix your Anthropic API key before proceeding. Processing stopped to save Serper credits.")
                            st.stop()
                        else:
                            st.success(f"✓ Claude API working! Test line: '{test_result.line[:50]}...'")
                    else:
                        st.error("NOT using Claude AI - falling back to templates (THIS IS THE PROBLEM)")
                        extractor = ArtifactExtractor()
                        ranker = ArtifactRanker()
                        generator = LineGenerator(seed=42)
                        validator = Validator()

                    if preview_only:
                        st.warning("PREVIEW MODE: Lines will NOT be pushed to Instantly")

                    # Cancel instructions
                    cancel_info = st.info("**To cancel:** Refresh the page. Partial results are saved every 10 leads.")

                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    stats_display = st.empty()
                    results_container = st.container()

                    stats = {"S": 0, "A": 0, "B": 0, "errors": 0, "skipped": 0, "serper_success": 0, "serper_fail": 0, "claude_success": 0, "claude_fail": 0}
                    results_log = []

                    # Use actual_count (respects limit) instead of process_count
                    target_count = actual_count
                    total_leads = len(leads)  # Total to scan through
                    processed_count = 0  # Track non-skipped leads processed

                    for idx, lead in enumerate(leads):
                        # Check if we've hit the target (limit or all new leads)
                        if processed_count >= target_count:
                            status_text.markdown(f"**Complete:** Processed {processed_count} leads")
                            break

                        try:
                            # Skip if already has personalization and skip_existing is True
                            existing_line = lead.custom_variables.get("personalization_line", "")
                            has_existing = bool(existing_line and str(existing_line).strip())

                            if skip_existing and has_existing:
                                stats["skipped"] += 1
                                # Don't add skipped to results_log to keep it clean for large datasets
                                # Update progress even for skipped leads
                                progress = (idx + 1) / total_leads
                                progress_bar.progress(progress)
                                # Only show skip status every 10 leads to reduce UI updates for large datasets
                                if idx % 10 == 0:
                                    status_text.markdown(f"**Scanning:** {idx + 1}/{total_leads} (skipping existing...)")
                                continue

                            company_name = lead.company_name or "Unknown"
                            domain = lead.company_domain or ""
                            # Extract location BEFORE Serper call for query disambiguation
                            location = lead.raw_data.get("location", "") or lead.raw_data.get("city", "")
                            status_text.markdown(f"**Processing:** {company_name} ({processed_count + 1} of {process_count} to process)")

                            # Use Serper to get rich company info with disambiguated query
                            serper_description = ""
                            try:
                                company_info = serper.get_company_info(company_name, domain, location)
                                serper_description = extract_artifacts_from_serper(company_info)
                                if serper_description and len(serper_description) > 20:
                                    stats["serper_success"] += 1
                                    logging.info(f"Serper found data for {company_name}: {len(serper_description)} chars")
                                else:
                                    stats["serper_fail"] += 1
                                    logging.warning(f"Serper returned no useful data for {company_name}")
                            except Exception as e:
                                stats["serper_fail"] += 1
                                logging.warning(f"Serper lookup failed for {company_name}: {e}")

                            # Build lead data dict for AI generator
                            lead_data = {
                                "company_description": lead.raw_data.get("company_description", ""),
                                "summary": lead.raw_data.get("summary", ""),
                                "headline": lead.raw_data.get("headline", ""),
                                "industry": lead.raw_data.get("industry", ""),
                                "location": lead.raw_data.get("location", ""),
                            }

                            # Track data source
                            has_serper_data = bool(serper_description and len(serper_description) > 20)

                            # SD-04/SD-05/SD-06: Check Serper confidence - use safe fallback if low confidence or industry mismatch
                            serper_is_reliable = True
                            if has_serper_data and 'company_info' in dir():
                                if company_info.is_low_confidence:
                                    logging.warning(f"Low confidence Serper data for {company_name} - using safe fallback")
                                    serper_description = ""  # Clear unreliable data
                                    serper_is_reliable = False
                                    stats["serper_fail"] += 1
                                    stats["serper_success"] -= 1
                                elif company_info.industry_mismatch_detected:
                                    logging.warning(f"Industry mismatch for {company_name} ({company_info.mismatched_industry}) - using safe fallback")
                                    serper_description = ""  # Clear wrong-industry data
                                    serper_is_reliable = False
                                    stats["serper_fail"] += 1
                                    stats["serper_success"] -= 1

                            if use_ai and ai_generator:
                                # Use Claude AI to generate the line
                                ai_result = ai_generator.generate_line(
                                    company_name=company_name,
                                    serper_data=serper_description,
                                    lead_data=lead_data,
                                )

                                # Track Claude success/failure
                                if ai_result.artifact_type in ["API_ERROR", "UNEXPECTED_ERROR", "FALLBACK"]:
                                    stats["claude_fail"] += 1
                                    logging.error(f"Claude FAILED for {company_name}: {ai_result.reasoning}")
                                else:
                                    stats["claude_success"] += 1
                                    logging.info(f"Claude SUCCESS for {company_name}: {ai_result.line[:50]}")

                                # Validate AI-generated line with company_name for VU-08/VU-09 checks
                                ai_artifact = Artifact(
                                    text=ai_result.artifact_used or "",
                                    artifact_type=ArtifactType.FALLBACK if ai_result.artifact_type == "FALLBACK" else ArtifactType.EXACT_PHRASE,
                                    evidence_source="claude_ai",
                                    evidence_url="",
                                    score=1.0,
                                )
                                ai_validation = validator.validate(ai_result.line, ai_artifact, company_name=company_name)

                                final_line = ai_result.line
                                final_tier = ai_result.confidence_tier
                                final_type = ai_result.artifact_type
                                final_artifact = ai_result.artifact_used
                                final_reasoning = ai_result.reasoning

                                if not ai_validation.is_valid:
                                    # AI line failed validation - use safe fallback
                                    logging.warning(f"AI line failed validation for {company_name}: {ai_validation.errors}")
                                    final_line = "Came across your company online."
                                    final_tier = "B"
                                    final_type = "FALLBACK"
                                    final_artifact = ""
                                    final_reasoning = f"Original failed validation: {'; '.join(ai_validation.errors)}"
                                    stats["claude_fail"] += 1
                                    if ai_result.artifact_type not in ["API_ERROR", "UNEXPECTED_ERROR", "FALLBACK"]:
                                        stats["claude_success"] -= 1

                                variables = {
                                    "personalization_line": final_line,
                                    "artifact_type": final_type,
                                    "artifact_text": final_artifact,
                                    "confidence_tier": final_tier,
                                    "evidence_source": "claude_ai" + ("+serper" if has_serper_data else ""),
                                    "ai_reasoning": final_reasoning,
                                }
                            else:
                                # Fallback to template-based generation
                                description_parts = []
                                if serper_description:
                                    description_parts.append(serper_description)
                                if lead.raw_data.get("company_description"):
                                    description_parts.append(lead.raw_data["company_description"])
                                if lead.raw_data.get("summary"):
                                    description_parts.append(lead.raw_data["summary"])
                                if lead.raw_data.get("headline"):
                                    description_parts.append(lead.raw_data["headline"])
                                if lead.raw_data.get("industry"):
                                    description_parts.append(f"Industry: {lead.raw_data['industry']}")
                                description = " ".join(description_parts)

                                # Extract artifacts from combined description
                                artifacts = extractor.extract_from_description(description)

                                # Add location if available
                                location = lead.raw_data.get("location")
                                if location and location.lower() not in ["no data found", "n/a", "skipped"]:
                                    for suffix in [", United States", ", USA", ", US"]:
                                        if location.endswith(suffix):
                                            location = location[:-len(suffix)]
                                    if location.lower() not in ["united states", "usa", "us"]:
                                        artifacts.append(Artifact(
                                            text=location,
                                            artifact_type=ArtifactType.LOCATION,
                                            evidence_source="instantly_lead",
                                            evidence_url="",
                                            score=1.0,
                                        ))

                                # Validate artifacts
                                valid_artifacts = [a for a in artifacts if validator.validate_artifact(a).is_valid]

                                # Select best artifact
                                selected = ranker.select_with_fallback(valid_artifacts)

                                # Generate line
                                line = generator.generate(selected)

                                # Validate line, try alternatives if needed (pass company_name for VU-08/VU-09)
                                validation = validator.validate(line, selected, company_name=company_name)
                                if not validation.is_valid and len(valid_artifacts) > 1:
                                    ranked = ranker.rank_artifacts(valid_artifacts)
                                    for alt in ranked[1:]:
                                        alt_line = generator.generate(alt)
                                        if validator.validate(alt_line, alt, company_name=company_name).is_valid:
                                            selected = alt
                                            line = alt_line
                                            break
                                    else:
                                        selected = ranker.get_fallback_artifact()
                                        line = generator.generate(selected)

                                confidence = ranker.get_confidence_tier(selected)

                                variables = {
                                    "personalization_line": line,
                                    "artifact_type": selected.artifact_type.value,
                                    "artifact_text": selected.text if selected.artifact_type != ArtifactType.FALLBACK else "",
                                    "confidence_tier": confidence.value,
                                    "evidence_source": selected.evidence_source,
                                }

                            # Update stats
                            tier = variables["confidence_tier"]
                            stats[tier] = stats.get(tier, 0) + 1

                            # Update lead in Instantly (unless preview only)
                            if preview_only:
                                sync_status = "Preview"
                            else:
                                update_success, _ = instantly_client.update_lead_variables(
                                    lead_id=lead.id,
                                    variables=variables,
                                    email=lead.email,
                                    campaign_id=selected_campaign_id,
                                )
                                sync_status = "Yes" if update_success else "FAILED"

                            # Get AI reasoning if available (for debugging)
                            ai_reason = variables.get("ai_reasoning", "")

                            results_log.append({
                                "email": lead.email,
                                "company": lead.company_name,
                                "line": variables["personalization_line"],
                                "tier": tier,
                                "type": variables.get("artifact_type", ""),
                                "artifact": variables["artifact_text"][:50] if variables["artifact_text"] else "",
                                "source": "Serper" if has_serper_data else "Lead data",
                                "synced": sync_status,
                            })

                            # Increment processed count
                            processed_count += 1

                        except Exception as e:
                            stats["errors"] += 1
                            results_log.append({
                                "email": lead.email,
                                "company": lead.company_name,
                                "line": f"Error: {str(e)[:80]}",
                                "tier": "ERROR",
                                "artifact": "",
                                "synced": "FAILED",
                                "error": str(e)[:100],
                            })
                            processed_count += 1  # Count errors too

                        # Update progress (based on processed count vs target)
                        progress = min(1.0, processed_count / target_count) if target_count > 0 else 1.0
                        progress_bar.progress(progress)

                        # Update stats display (compact for large datasets)
                        actual_processed = stats["S"] + stats["A"] + stats["B"]
                        high_conf = stats["S"] + stats["A"]
                        high_conf_pct = high_conf / actual_processed * 100 if actual_processed > 0 else 0

                        stats_display.markdown(f"""
                        **Progress:** {processed_count}/{target_count} processed | {stats['skipped']} skipped | {stats['errors']} errors

                        | Tier | Count | % |
                        |------|-------|---|
                        | S (Best) | {stats['S']} | {stats['S']/actual_processed*100:.0f}% |
                        | A (Good) | {stats['A']} | {stats['A']/actual_processed*100:.0f}% |
                        | B (Basic) | {stats['B']} | {stats['B']/actual_processed*100:.0f}% |

                        **High Confidence (S+A): {high_conf_pct:.0f}%** | Serper: {stats['serper_success']}/{stats['serper_success']+stats['serper_fail']} | Claude: {stats['claude_success']}/{stats['claude_success']+stats['claude_fail']}
                        """ if actual_processed > 0 else f"**Starting...** Scanning for new leads...")

                        # Save partial results every 10 leads (for cancel safety)
                        if processed_count > 0 and processed_count % 10 == 0:
                            st.session_state.instantly_sync_stats = stats.copy()
                            st.session_state.instantly_results_log = results_log.copy()
                            save_results(results_log, stats, selected_campaign_name)

                    # Save results to session state so they persist
                    st.session_state.instantly_sync_stats = stats
                    st.session_state.instantly_results_log = results_log
                    st.session_state.instantly_sync_complete = True
                    st.session_state.saved_campaign_name = selected_campaign_name

                    # Auto-save to file for persistence across refreshes
                    save_results(results_log, stats, selected_campaign_name)

                    status_text.markdown("**Processing complete! Results saved.**")

                    # Count sync failures
                    failed_syncs = sum(1 for r in results_log if r.get("synced") == "FAILED")
                    if failed_syncs > 0:
                        st.warning(f"Completed with {failed_syncs} sync failures. Check the 'synced' column below.")
                    else:
                        st.success("All personalizations synced to Instantly!")

                    # Show results summary
                    with results_container:
                        st.markdown("### Processing Complete!")

                        # Summary stats
                        total_done = stats["S"] + stats["A"] + stats["B"]
                        col1, col2, col3, col4 = st.columns(4)
                        with col1:
                            st.metric("Processed", total_done)
                        with col2:
                            high_conf = stats["S"] + stats["A"]
                            st.metric("High Quality (S+A)", high_conf, delta=f"{high_conf/total_done*100:.0f}%" if total_done else None)
                        with col3:
                            st.metric("Skipped", stats["skipped"])
                        with col4:
                            synced = sum(1 for r in results_log if r.get("synced") == "Yes")
                            st.metric("Synced to Instantly", synced)

                        # Quick preview of results (first 20)
                        results_df = pd.DataFrame(results_log)
                        with st.expander(f"Preview Results ({len(results_log)} total)", expanded=True):
                            st.dataframe(results_df.head(50), use_container_width=True, hide_index=True)
                            if len(results_log) > 50:
                                st.caption("Showing first 50 results. See 'Previous Results' section below for full list with search/filter.")

                        # Action buttons row
                        st.markdown("---")
                        col1, col2 = st.columns(2)

                        with col1:
                            csv = results_df.to_csv(index=False)
                            st.download_button(
                                "Download All Results CSV",
                                data=csv,
                                file_name="instantly_sync_results.csv",
                                mime="text/csv",
                                use_container_width=True,
                            )

                        with col2:
                            # Check for unsynced results (preview mode or failures)
                            unsynced_count = sum(1 for r in results_log if r.get("synced") in ["Preview", "FAILED"])
                            if unsynced_count > 0:
                                if st.button(f"🚀 Push {unsynced_count} to Instantly", type="primary", use_container_width=True, key="push_after_process"):
                                    with st.spinner(f"Pushing {unsynced_count} leads to Instantly..."):
                                        push_success = 0
                                        push_fail = 0
                                        for result in results_log:
                                            if result.get("synced") in ["Preview", "FAILED"]:
                                                variables = {
                                                    "personalization_line": result.get("line", ""),
                                                    "artifact_type": result.get("type", ""),
                                                    "artifact_text": result.get("artifact", ""),
                                                    "confidence_tier": result.get("tier", ""),
                                                }
                                                success, _ = instantly_client.update_lead_variables(
                                                    lead_id=None,
                                                    variables=variables,
                                                    email=result.get("email"),
                                                    campaign_id=selected_campaign_id,
                                                )
                                                if success:
                                                    result["synced"] = "Yes"
                                                    push_success += 1
                                                else:
                                                    push_fail += 1

                                        # Update saved results
                                        st.session_state.instantly_results_log = results_log
                                        save_results(results_log, stats, selected_campaign_name)

                                        if push_fail == 0:
                                            st.success(f"✅ Successfully pushed {push_success} leads to Instantly!")
                                        else:
                                            st.warning(f"Pushed {push_success}, {push_fail} failed")
                                        st.rerun()
                            else:
                                st.success("✅ All synced to Instantly!")

                    st.balloons()

            # Show previous results if they exist (persist across navigation AND page refresh)
            # IMPORTANT: Changed from elif to if - so users can always fetch new leads even with saved results
            if st.session_state.instantly_sync_complete and st.session_state.instantly_results_log:
                st.markdown("---")

                # Show campaign name if available
                campaign_label = st.session_state.get("saved_campaign_name", "")
                if campaign_label:
                    st.subheader(f"Previous Results: {campaign_label}")
                else:
                    st.subheader("Previous Results")

                st.info(f"These are saved results from a previous run. To process NEW leads added to the campaign, click 'Fetch Leads' above first, then 'Process & Sync'.")

                stats = st.session_state.instantly_sync_stats
                col1, col2, col3, col4, col5 = st.columns(5)
                with col1:
                    st.metric("Tier S", stats.get("S", 0))
                with col2:
                    st.metric("Tier A", stats.get("A", 0))
                with col3:
                    st.metric("Tier B", stats.get("B", 0))
                with col4:
                    st.metric("Skipped", stats.get("skipped", 0))
                with col5:
                    st.metric("Errors", stats.get("errors", 0))

                results_df = pd.DataFrame(st.session_state.instantly_results_log)

                # Filter and search row
                col1, col2, col3 = st.columns([1, 1, 2])
                with col1:
                    show_filter = st.selectbox(
                        "Filter",
                        ["Processed only", "All", "Errors only"],
                        key="results_filter",
                        label_visibility="collapsed",
                    )
                with col2:
                    tier_filter = st.selectbox(
                        "Tier",
                        ["All Tiers", "S only", "A only", "B only"],
                        key="tier_filter",
                        label_visibility="collapsed",
                    )
                with col3:
                    search_term = st.text_input(
                        "Search",
                        placeholder="Search by company or email...",
                        key="results_search",
                        label_visibility="collapsed",
                    )

                # Apply filters
                filtered_df = results_df.copy()
                if show_filter == "Processed only":
                    filtered_df = filtered_df[~filtered_df["tier"].isin(["SKIPPED", "ERROR"])]
                elif show_filter == "Errors only":
                    filtered_df = filtered_df[filtered_df["tier"] == "ERROR"]

                if tier_filter != "All Tiers":
                    tier_val = tier_filter.split()[0]  # "S only" -> "S"
                    filtered_df = filtered_df[filtered_df["tier"] == tier_val]

                if search_term:
                    search_lower = search_term.lower()
                    filtered_df = filtered_df[
                        filtered_df["email"].str.lower().str.contains(search_lower, na=False) |
                        filtered_df["company"].str.lower().str.contains(search_lower, na=False)
                    ]

                # Pagination for large datasets
                ROWS_PER_PAGE = 100
                total_rows = len(filtered_df)
                total_pages = max(1, (total_rows + ROWS_PER_PAGE - 1) // ROWS_PER_PAGE)

                if total_rows > ROWS_PER_PAGE:
                    col1, col2, col3 = st.columns([1, 2, 1])
                    with col2:
                        page = st.number_input(
                            f"Page (1-{total_pages})",
                            min_value=1,
                            max_value=total_pages,
                            value=1,
                            key="results_page",
                        )
                    start_idx = (page - 1) * ROWS_PER_PAGE
                    end_idx = min(start_idx + ROWS_PER_PAGE, total_rows)
                    display_df = filtered_df.iloc[start_idx:end_idx]
                    st.dataframe(display_df, use_container_width=True, hide_index=True)
                    st.caption(f"Showing {start_idx + 1}-{end_idx} of {total_rows} results (Page {page}/{total_pages})")
                else:
                    st.dataframe(filtered_df, use_container_width=True, hide_index=True)
                    st.caption(f"Showing {total_rows} results")

                # Check if any results weren't synced (preview mode or failures)
                unsynced_results = [r for r in st.session_state.instantly_results_log
                                   if r.get("synced") in ["Preview", "FAILED"] and r.get("tier") not in ["SKIPPED", "ERROR"]]

                st.markdown("---")
                col1, col2, col3 = st.columns(3)

                with col1:
                    csv = results_df.to_csv(index=False)
                    st.download_button(
                        "Download Results CSV",
                        data=csv,
                        file_name="instantly_sync_results.csv",
                        mime="text/csv",
                        width="stretch",
                    )

                with col2:
                    # Push to Instantly button - for preview results or retrying failed syncs
                    if unsynced_results:
                        if st.button(f"Push {len(unsynced_results)} to Instantly", type="primary", width="stretch"):
                            with st.spinner(f"Pushing {len(unsynced_results)} leads to Instantly..."):
                                try:
                                    instantly_client = InstantlyClient(st.session_state.instantly_api_key)

                                    # Need to get campaign ID - use the currently selected one
                                    push_campaign_id = campaign_options.get(selected_campaign_name) if 'campaign_options' in dir() else None

                                    if not push_campaign_id:
                                        # Try to find the campaign by name
                                        for c in st.session_state.instantly_campaigns:
                                            if c.name in campaign_label:
                                                push_campaign_id = c.id
                                                break

                                    if not push_campaign_id:
                                        st.error("Could not determine campaign ID. Please select a campaign above and fetch leads first.")
                                    else:
                                        success_count = 0
                                        fail_count = 0
                                        push_progress = st.progress(0)

                                        for idx, result in enumerate(st.session_state.instantly_results_log):
                                            if result.get("synced") in ["Preview", "FAILED"] and result.get("tier") not in ["SKIPPED", "ERROR"]:
                                                variables = {
                                                    "personalization_line": result.get("line", ""),
                                                    "artifact_type": result.get("type", ""),
                                                    "artifact_text": result.get("artifact", ""),
                                                    "confidence_tier": result.get("tier", ""),
                                                }

                                                update_success, _ = instantly_client.update_lead_variables(
                                                    lead_id=None,  # Will use email lookup
                                                    variables=variables,
                                                    email=result.get("email"),
                                                    campaign_id=push_campaign_id,
                                                )

                                                if update_success:
                                                    result["synced"] = "Yes"
                                                    success_count += 1
                                                else:
                                                    result["synced"] = "FAILED"
                                                    fail_count += 1

                                            push_progress.progress((idx + 1) / len(st.session_state.instantly_results_log))

                                        # Update saved file
                                        save_results(st.session_state.instantly_results_log, stats, campaign_label)

                                        if fail_count == 0:
                                            st.success(f"Successfully pushed {success_count} leads to Instantly!")
                                        else:
                                            st.warning(f"Pushed {success_count} leads, {fail_count} failed.")

                                        st.rerun()

                                except Exception as e:
                                    st.error(f"Error pushing to Instantly: {e}")
                    else:
                        st.button("All synced to Instantly", disabled=True, width="stretch")

                with col3:
                    if st.button("Clear Results & Start Fresh", width="stretch"):
                        st.session_state.instantly_results_log = []
                        st.session_state.instantly_sync_complete = False
                        st.session_state.instantly_sync_stats = {}
                        st.session_state.saved_campaign_name = ""
                        st.session_state.instantly_leads = []  # Also clear fetched leads
                        delete_saved_results()  # Delete the file too
                        st.rerun()

        else:
            st.warning("No campaigns found in your Instantly account.")

    # Instructions
    with st.expander("How to get your Instantly API Key"):
        st.markdown("""
        1. Log in to [Instantly.ai](https://instantly.ai)
        2. Go to **Settings** (gear icon)
        3. Click **Integrations**
        4. Find **API** section
        5. Copy your **API V2 Key**

        **Note:** The personalization will be stored in these custom variables:
        - `personalization_line` - The generated opening line
        - `artifact_type` - Type of content used (EXACT_PHRASE, TOOL_PLATFORM, etc.)
        - `artifact_text` - The actual text extracted
        - `confidence_tier` - S, A, or B quality rating

        Use `{{personalization_line}}` in your email templates to include the personalization.
        """)


def render_unibox_page():
    """Render the Unibox Automation page (placeholder)."""
    st.header("Unibox Automation")
    st.info("Coming Soon: Automated follow-up sequences through Instantly Unibox")

    st.markdown("---")
    st.markdown("""
    ### Planned Features
    - Automated reply detection and categorization
    - Smart follow-up sequences based on reply sentiment
    - Lead status tracking and updates
    - Integration with Campaign Personalization
    """)

    st.markdown("---")
    st.caption("This feature is under development. Stay tuned!")


def main():
    """Main application entry point."""
    init_session_state()

    page = render_sidebar()

    # Instantly Tools (primary)
    if page == "CSV Personalization":
        render_csv_personalization_page()
    elif page == "Campaign Sync":
        render_instantly_page()
    elif page == "Unibox Automation":
        render_unibox_page()
    # CSV Tools (secondary/advanced)
    elif page == "CSV:Upload & Preview":
        render_upload_page()
    elif page == "CSV:Process Leads":
        render_process_page()
    elif page == "CSV:Results & Stats":
        render_results_page()
    elif page == "CSV:Artifact Inspector":
        render_inspector_page()


if __name__ == "__main__":
    main()
