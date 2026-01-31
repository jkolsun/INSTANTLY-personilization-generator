#!/usr/bin/env python3
"""
Streamlit Dashboard for the Personalization Line Engine

Run with: streamlit run app.py
"""
import io
import json
import logging
import os
import time
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
        # Auto-connect if env var is set
        st.session_state.anthropic_connected = bool(os.environ.get("ANTHROPIC_API_KEY"))
    if "use_ai_generation" not in st.session_state:
        st.session_state.use_ai_generation = True  # Default to AI generation

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
        st.title("Personalization Engine")
        st.markdown("---")

        page = st.radio(
            "Navigation",
            ["Upload & Preview", "Process Leads", "Results & Stats", "Artifact Inspector", "Instantly Sync"],
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

        if st.button("Clear All Data", width="stretch"):
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


def render_instantly_page():
    """Render the Instantly sync page."""
    st.header("Instantly Sync")

    st.markdown("""
    Connect to your Instantly account to pull leads directly and push personalization lines back.

    **How it works:**
    1. Enter your Instantly API key
    2. Select a campaign
    3. Process leads (generates personalization lines)
    4. Push results back to Instantly as custom variables
    """)

    st.markdown("---")

    # API Key input
    col1, col2 = st.columns([3, 1])

    with col1:
        api_key = st.text_input(
            "Instantly API Key",
            value=st.session_state.instantly_api_key,
            type="password",
            help="Your Instantly API V2 key. Find it in Instantly Settings > Integrations > API",
        )

    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Connect", type="primary", width="stretch"):
            if api_key:
                with st.spinner("Testing connection..."):
                    try:
                        client = InstantlyClient(api_key)
                        if client.test_connection():
                            st.session_state.instantly_api_key = api_key
                            st.session_state.instantly_connected = True
                            # Fetch campaigns
                            campaigns = client.list_campaigns()
                            st.session_state.instantly_campaigns = campaigns
                            st.success(f"Connected! Found {len(campaigns)} campaigns.")
                            st.rerun()
                        else:
                            st.error("Connection failed. Check your API key.")
                    except Exception as e:
                        st.error(f"Connection error: {e}")
            else:
                st.warning("Please enter your API key.")

    # Show connection status
    if st.session_state.instantly_connected:
        st.success("Connected to Instantly")

        st.markdown("---")

        # Anthropic API Key section
        st.subheader("AI Line Generation (Claude)")
        st.markdown("""
        Use Claude AI to generate intelligent, context-aware personalization lines instead of templates.
        This produces much higher quality, natural-sounding lines.
        """)

        col1, col2 = st.columns([3, 1])

        with col1:
            anthropic_key = st.text_input(
                "Anthropic API Key",
                value=st.session_state.anthropic_api_key,
                type="password",
                help="Your Anthropic API key from console.anthropic.com",
            )

        with col2:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("Connect", key="anthropic_connect", width="stretch"):
                if anthropic_key:
                    with st.spinner("Testing connection..."):
                        if test_anthropic_key(anthropic_key):
                            st.session_state.anthropic_api_key = anthropic_key
                            st.session_state.anthropic_connected = True
                            st.success("Claude API connected!")
                            st.rerun()
                        else:
                            st.error("Invalid API key. Check console.anthropic.com")
                else:
                    st.warning("Please enter your Anthropic API key.")

        if st.session_state.anthropic_connected:
            st.success("Claude AI Ready")
            st.session_state.use_ai_generation = st.checkbox(
                "Use AI-generated lines (recommended)",
                value=st.session_state.use_ai_generation,
                help="When enabled, Claude writes personalization lines. When disabled, uses templates.",
            )
        else:
            st.warning("Add your Anthropic API key to enable AI-generated lines. Without it, template-based lines will be used.")
            st.session_state.use_ai_generation = False

        st.markdown("---")
        st.subheader("Select Campaign")

        campaigns = st.session_state.instantly_campaigns
        if campaigns:
            campaign_options = {f"{c.name} ({c.status})": c.id for c in campaigns}
            selected_campaign_name = st.selectbox(
                "Campaign",
                options=list(campaign_options.keys()),
                help="Select a campaign to process",
            )
            selected_campaign_id = campaign_options[selected_campaign_name]

            limit = st.number_input(
                "Limit leads (0 = all)",
                min_value=0,
                value=100,
                help="Maximum number of leads to process",
            )

            skip_existing = st.checkbox(
                "Skip leads with existing personalization",
                value=True,
                help="Skip leads that already have a personalization_line set",
            )

            preview_only = st.checkbox(
                "Preview only (don't push to Instantly)",
                value=False,
                help="Generate lines but don't update Instantly - for testing",
            )

            st.info("Using Serper API for fast, high-quality company research (~1 sec per lead)")

            st.markdown("---")

            # Fetch leads button
            if st.button("Fetch Leads", width="stretch"):
                with st.spinner("Fetching leads from Instantly..."):
                    try:
                        client = InstantlyClient(st.session_state.instantly_api_key)
                        leads = client.list_leads(
                            campaign_id=selected_campaign_id,
                            limit=limit if limit > 0 else 10000,
                        )
                        st.session_state.instantly_leads = leads
                        st.success(f"Fetched {len(leads)} leads")
                    except Exception as e:
                        st.error(f"Error fetching leads: {e}")

            # Show fetched leads
            if st.session_state.instantly_leads:
                leads = st.session_state.instantly_leads

                # Count leads with existing personalization
                leads_with_personalization = sum(
                    1 for lead in leads
                    if lead.custom_variables.get("personalization_line")
                    and str(lead.custom_variables.get("personalization_line")).strip()
                )

                st.markdown(f"### Leads Preview ({len(leads)} total)")

                # Show warning if many leads have personalization
                if leads_with_personalization > 0:
                    st.warning(f"**{leads_with_personalization} of {len(leads)} leads already have personalization.** "
                              f"{'These will be skipped.' if skip_existing else 'These will be overwritten.'}")

                # Create preview dataframe
                preview_data = []
                for lead in leads[:20]:  # Show first 20
                    personalization_value = lead.custom_variables.get("personalization_line", "")
                    has_personalization = bool(personalization_value and str(personalization_value).strip())
                    preview_data.append({
                        "Email": lead.email,
                        "Company": lead.company_name or "-",
                        "Has Personalization": "Yes" if has_personalization else "No",
                        "Existing Line": str(personalization_value)[:50] + "..." if personalization_value and len(str(personalization_value)) > 50 else (personalization_value or "-"),
                    })

                st.dataframe(pd.DataFrame(preview_data), width="stretch", hide_index=True)

                if len(leads) > 20:
                    st.caption(f"Showing 20 of {len(leads)} leads")

                st.markdown("---")

                # Process button
                if st.button("Process & Sync to Instantly", type="primary", width="stretch"):
                    # Initialize components
                    serper = SerperClient(st.session_state.serper_api_key)
                    instantly_client = InstantlyClient(st.session_state.instantly_api_key)
                    use_ai = st.session_state.use_ai_generation and st.session_state.anthropic_connected

                    # AI generator or template-based fallback
                    ai_generator = None
                    if use_ai:
                        ai_generator = AILineGenerator(st.session_state.anthropic_api_key)
                        st.info("Using Claude AI for line generation")
                    else:
                        st.info("Using template-based line generation")
                        extractor = ArtifactExtractor()
                        ranker = ArtifactRanker()
                        generator = LineGenerator(seed=42)
                        validator = Validator()

                    if preview_only:
                        st.warning("PREVIEW MODE: Lines will NOT be pushed to Instantly")

                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    stats_display = st.empty()
                    results_container = st.container()

                    stats = {"S": 0, "A": 0, "B": 0, "errors": 0, "skipped": 0}
                    results_log = []

                    for idx, lead in enumerate(leads):
                        try:
                            # Skip if already has personalization and skip_existing is True
                            existing_line = lead.custom_variables.get("personalization_line", "")
                            has_existing = bool(existing_line and str(existing_line).strip())

                            if skip_existing and has_existing:
                                stats["skipped"] += 1
                                results_log.append({
                                    "email": lead.email,
                                    "company": lead.company_name,
                                    "line": f"[SKIPPED] {str(existing_line)[:50]}...",
                                    "tier": "SKIPPED",
                                    "artifact": "",
                                    "synced": "Skipped",
                                    "error": "",
                                })
                                # Update progress even for skipped leads
                                progress = (idx + 1) / len(leads)
                                progress_bar.progress(progress)
                                status_text.markdown(f"**Skipping:** {lead.company_name or lead.email} (already has personalization)")
                                continue

                            company_name = lead.company_name or "Unknown"
                            domain = lead.company_domain or ""
                            status_text.markdown(f"**Processing:** {company_name} ({idx + 1}/{len(leads)})")

                            # Use Serper to get rich company info
                            serper_description = ""
                            try:
                                company_info = serper.get_company_info(company_name, domain)
                                serper_description = extract_artifacts_from_serper(company_info)
                            except Exception as e:
                                # Log but continue - AI can still work with lead data
                                logging.warning(f"Serper lookup failed for {company_name}: {e}")

                            # Build lead data dict for AI generator
                            lead_data = {
                                "company_description": lead.raw_data.get("company_description", ""),
                                "summary": lead.raw_data.get("summary", ""),
                                "headline": lead.raw_data.get("headline", ""),
                                "industry": lead.raw_data.get("industry", ""),
                                "location": lead.raw_data.get("location", ""),
                            }

                            if use_ai and ai_generator:
                                # Use Claude AI to generate the line
                                ai_result = ai_generator.generate_line(
                                    company_name=company_name,
                                    serper_data=serper_description,
                                    lead_data=lead_data,
                                )

                                variables = {
                                    "personalization_line": ai_result.line,
                                    "artifact_type": ai_result.artifact_type,
                                    "artifact_text": ai_result.artifact_used,
                                    "confidence_tier": ai_result.confidence_tier,
                                    "evidence_source": "claude_ai",
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

                                # Validate line, try alternatives if needed
                                validation = validator.validate(line, selected)
                                if not validation.is_valid and len(valid_artifacts) > 1:
                                    ranked = ranker.rank_artifacts(valid_artifacts)
                                    for alt in ranked[1:]:
                                        alt_line = generator.generate(alt)
                                        if validator.validate(alt_line, alt).is_valid:
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
                                update_success = True
                                error_msg = None
                                sync_status = "Preview"
                            else:
                                update_success, error_msg = instantly_client.update_lead_variables(
                                    lead_id=lead.id,
                                    variables=variables,
                                    email=lead.email,
                                    campaign_id=selected_campaign_id,
                                )
                                sync_status = "Yes" if update_success else "FAILED"

                            results_log.append({
                                "email": lead.email,
                                "company": lead.company_name,
                                "line": variables["personalization_line"],
                                "tier": tier,
                                "artifact": variables["artifact_text"],
                                "synced": sync_status,
                                "error": error_msg[:100] if error_msg else "",
                            })

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

                        # Update progress
                        progress = (idx + 1) / len(leads)
                        progress_bar.progress(progress)

                        # Update stats display
                        total_processed = stats["S"] + stats["A"] + stats["B"]
                        high_conf = stats["S"] + stats["A"]
                        high_conf_pct = high_conf / total_processed * 100 if total_processed > 0 else 0

                        stats_display.markdown(f"""
                        | Metric | Value |
                        |--------|-------|
                        | Processed | {idx + 1}/{len(leads)} |
                        | Tier S | {stats['S']} |
                        | Tier A | {stats['A']} |
                        | Tier B | {stats['B']} |
                        | Skipped | {stats['skipped']} |
                        | High Confidence | {high_conf_pct:.1f}% |
                        | Errors | {stats['errors']} |
                        """)

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

                    # Show results
                    with results_container:
                        st.markdown("### Results")
                        results_df = pd.DataFrame(results_log)
                        st.dataframe(results_df, width="stretch", hide_index=True)

                        # Download results
                        csv = results_df.to_csv(index=False)
                        st.download_button(
                            "Download Results CSV",
                            data=csv,
                            file_name="instantly_sync_results.csv",
                            mime="text/csv",
                        )

                    st.balloons()

            # Show previous results if they exist (persist across navigation AND page refresh)
            elif st.session_state.instantly_sync_complete and st.session_state.instantly_results_log:
                st.markdown("---")

                # Show campaign name if available
                campaign_label = st.session_state.get("saved_campaign_name", "")
                if campaign_label:
                    st.subheader(f"Saved Results: {campaign_label}")
                else:
                    st.subheader("Saved Results")

                st.info(f"Results are auto-saved and will persist across page refreshes. {len(st.session_state.instantly_results_log)} leads loaded.")

                stats = st.session_state.instantly_sync_stats
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Tier S", stats.get("S", 0))
                with col2:
                    st.metric("Tier A", stats.get("A", 0))
                with col3:
                    st.metric("Tier B", stats.get("B", 0))
                with col4:
                    st.metric("Errors", stats.get("errors", 0))

                results_df = pd.DataFrame(st.session_state.instantly_results_log)
                st.dataframe(results_df, width="stretch", hide_index=True)

                col1, col2 = st.columns(2)
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
                    if st.button("Clear Saved Results & Start New", width="stretch"):
                        st.session_state.instantly_results_log = []
                        st.session_state.instantly_sync_complete = False
                        st.session_state.instantly_sync_stats = {}
                        st.session_state.saved_campaign_name = ""
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
    elif page == "Instantly Sync":
        render_instantly_page()


if __name__ == "__main__":
    main()
