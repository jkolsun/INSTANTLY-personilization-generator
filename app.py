#!/usr/bin/env python3
"""
Bright Automations - Lead Personalization Platform

Professional lead personalization and cold email automation.
https://brightautomations.org

Run with: streamlit run app.py
"""
import io
import json
import logging
import os
from datetime import datetime
from typing import List, Optional, Dict, Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# Core modules
from column_normalizer import normalize_columns
from instantly_client import InstantlyClient
from serper_client import SerperClient, extract_artifacts_from_serper
from ai_line_generator import AILineGenerator, test_api_key as test_anthropic_key
import database as db

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ========== Page Configuration ==========

st.set_page_config(
    page_title="Bright Automations",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ========== Custom CSS - Bright Automations Branding ==========

st.markdown("""
<style>
    /* Main branding colors */
    :root {
        --primary: #6366f1;
        --primary-dark: #4f46e5;
        --secondary: #10b981;
        --accent: #f59e0b;
        --background: #0f172a;
        --surface: #1e293b;
        --text: #f8fafc;
        --text-muted: #94a3b8;
    }

    /* Hide default Streamlit branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}

    /* Sidebar styling */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #1e293b 0%, #0f172a 100%);
    }

    [data-testid="stSidebar"] .stMarkdown h1,
    [data-testid="stSidebar"] .stMarkdown h2,
    [data-testid="stSidebar"] .stMarkdown h3 {
        color: #f8fafc;
    }

    /* Progress bar */
    .stProgress > div > div > div > div {
        background: linear-gradient(90deg, #6366f1 0%, #10b981 100%);
    }

    /* Metric cards */
    [data-testid="stMetricValue"] {
        font-size: 2rem;
        font-weight: 700;
    }

    /* Tier colors */
    .tier-s { color: #10b981; font-weight: bold; }
    .tier-a { color: #6366f1; font-weight: bold; }
    .tier-b { color: #94a3b8; font-weight: bold; }

    /* Custom cards */
    .feature-card {
        background: linear-gradient(135deg, #1e293b 0%, #334155 100%);
        border-radius: 12px;
        padding: 24px;
        border: 1px solid #334155;
        margin: 8px 0;
    }

    .stat-card {
        background: #1e293b;
        border-radius: 8px;
        padding: 16px;
        text-align: center;
        border: 1px solid #334155;
    }

    /* Button styling */
    .stButton > button {
        border-radius: 8px;
        font-weight: 600;
    }

    .stButton > button[kind="primary"] {
        background: linear-gradient(90deg, #6366f1 0%, #4f46e5 100%);
    }

    /* Tab styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }

    .stTabs [data-baseweb="tab"] {
        border-radius: 8px 8px 0 0;
    }

    /* Header styling */
    .main-header {
        font-size: 2.5rem;
        font-weight: 800;
        background: linear-gradient(90deg, #6366f1 0%, #10b981 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0;
    }

    .sub-header {
        color: #94a3b8;
        font-size: 1.1rem;
        margin-top: 0;
    }

    /* Status indicators */
    .status-pending { color: #f59e0b; }
    .status-processed { color: #10b981; }
    .status-pushed { color: #6366f1; }
    .status-error { color: #ef4444; }
</style>
""", unsafe_allow_html=True)


# ========== Session State ==========

def init_session_state():
    """Initialize session state variables."""
    defaults = {
        # Navigation
        "current_page": "Dashboard",

        # API Keys (from environment)
        "instantly_api_key": os.environ.get("INSTANTLY_API_KEY", ""),
        "serper_api_key": os.environ.get("SERPER_API_KEY", ""),
        "anthropic_api_key": os.environ.get("ANTHROPIC_API_KEY", ""),

        # Connection states
        "instantly_connected": bool(os.environ.get("INSTANTLY_API_KEY")),
        "anthropic_connected": bool(os.environ.get("ANTHROPIC_API_KEY")),

        # Instantly data
        "instantly_campaigns": [],

        # Processing state
        "processing_active": False,
        "processing_cancelled": False,

        # Quick personalize
        "df_input": None,
        "df_processed": None,
        "processing_complete": False,
        "processing_stats": {},

        # Selected campaign for database
        "selected_campaign_id": None,
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

    # Auto-fetch Instantly campaigns if connected
    if st.session_state.instantly_connected and not st.session_state.instantly_campaigns:
        try:
            client = InstantlyClient(st.session_state.instantly_api_key)
            st.session_state.instantly_campaigns = client.list_campaigns()
        except Exception:
            pass


# ========== Sidebar Navigation ==========

def render_sidebar():
    """Render the sidebar with navigation and status."""
    with st.sidebar:
        # Logo/Brand
        st.markdown("## Bright Automations")
        st.caption("Lead Personalization Platform")

        st.markdown("---")

        # Main Navigation
        st.markdown("### Navigation")

        pages = {
            "Dashboard": "",
            "Lead Manager": "",
            "Quick Personalize": "",
            "Instantly Sync": "",
            "Settings": "",
        }

        for page_name, icon in pages.items():
            if st.button(
                f"{icon} {page_name}",
                key=f"nav_{page_name}",
                use_container_width=True,
                type="primary" if st.session_state.current_page == page_name else "secondary"
            ):
                st.session_state.current_page = page_name
                st.rerun()

        st.markdown("---")

        # Quick Stats
        st.markdown("### Quick Stats")
        stats = db.get_lead_stats()

        col1, col2 = st.columns(2)
        with col1:
            st.metric("Total Leads", stats["total"])
        with col2:
            st.metric("Processed", stats["processed"])

        # Database indicator
        db_type = db.get_database_type()
        if db_type == "supabase":
            st.success(" Cloud Database")
        else:
            st.info(" Local Database")

        st.markdown("---")

        # Connection Status
        st.markdown("### Connections")

        if st.session_state.anthropic_connected:
            st.success(" Claude AI")
        else:
            st.error(" Claude AI")

        if st.session_state.instantly_connected:
            st.success(" Instantly")
        else:
            st.warning(" Instantly")

        # Footer
        st.markdown("---")
        st.caption("v2.0 | [brightautomations.org](https://brightautomations.org)")


# ========== Dashboard Page ==========

def render_dashboard():
    """Render the main dashboard overview."""
    st.markdown('<h1 class="main-header">Dashboard</h1>', unsafe_allow_html=True)
    st.markdown('<p class="sub-header">Overview of your lead personalization pipeline</p>', unsafe_allow_html=True)

    # Top metrics
    stats = db.get_lead_stats()
    campaigns = db.get_campaigns()

    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        st.metric("Total Leads", stats["total"], help="All leads across campaigns")
    with col2:
        st.metric("Pending", stats["pending"], help="Awaiting personalization")
    with col3:
        st.metric("Processed", stats["processed"], help="Personalized and ready")
    with col4:
        st.metric("Pushed", stats["pushed"], help="Sent to Instantly")
    with col5:
        st.metric("Campaigns", len(campaigns), help="Active campaigns")

    st.markdown("---")

    # Two column layout
    col_left, col_right = st.columns([2, 1])

    with col_left:
        st.markdown("### Recent Campaigns")

        if campaigns:
            for campaign in campaigns[:5]:
                with st.container():
                    c1, c2, c3, c4 = st.columns([3, 1, 1, 1])
                    with c1:
                        st.markdown(f"**{campaign['name']}**")
                        st.caption(f"ID: {campaign['id']}")
                    with c2:
                        st.metric("Pending", campaign.get('pending_count', 0), label_visibility="collapsed")
                    with c3:
                        st.metric("Done", campaign.get('actual_processed', 0), label_visibility="collapsed")
                    with c4:
                        if st.button("Open", key=f"open_{campaign['id']}"):
                            st.session_state.selected_campaign_id = campaign['id']
                            st.session_state.current_page = "Lead Manager"
                            st.rerun()
                    st.markdown("---")
        else:
            st.info("No campaigns yet. Create one in Lead Manager to get started.")
            if st.button("Go to Lead Manager", type="primary"):
                st.session_state.current_page = "Lead Manager"
                st.rerun()

    with col_right:
        st.markdown("### Quality Distribution")

        tiers = stats.get("tiers", {})
        if tiers:
            fig = go.Figure(data=[go.Pie(
                labels=list(tiers.keys()),
                values=list(tiers.values()),
                hole=0.6,
                marker_colors=['#10b981', '#6366f1', '#94a3b8'],
            )])
            fig.update_layout(
                showlegend=True,
                height=250,
                margin=dict(t=20, b=20, l=20, r=20),
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Process leads to see quality distribution")

        st.markdown("### Quick Actions")

        if st.button(" Import Leads", use_container_width=True):
            st.session_state.current_page = "Lead Manager"
            st.rerun()

        if st.button(" Process Pending", use_container_width=True):
            st.session_state.current_page = "Lead Manager"
            st.rerun()

        if st.button(" Sync to Instantly", use_container_width=True):
            st.session_state.current_page = "Instantly Sync"
            st.rerun()


# ========== Lead Manager Page ==========

def render_lead_manager():
    """Render the lead management page."""
    st.markdown('<h1 class="main-header">Lead Manager</h1>', unsafe_allow_html=True)
    st.markdown('<p class="sub-header">Manage campaigns and process leads at scale</p>', unsafe_allow_html=True)

    # Tabs for different functions
    tab1, tab2, tab3, tab4 = st.tabs([" Campaigns", " Import", " Process", " Export"])

    campaigns = db.get_campaigns()

    # ===== Campaigns Tab =====
    with tab1:
        col_left, col_right = st.columns([2, 1])

        with col_right:
            st.markdown("### Create Campaign")
            with st.form("create_campaign"):
                name = st.text_input("Campaign Name", placeholder="Q1 HVAC Outreach")
                desc = st.text_input("Description", placeholder="Optional notes...")

                if st.form_submit_button("Create", type="primary", use_container_width=True):
                    if name:
                        campaign_id = db.create_campaign(name, desc)
                        st.success(f"Created: {name} (ID: {campaign_id})")
                        st.rerun()
                    else:
                        st.error("Name is required")

        with col_left:
            st.markdown("### Your Campaigns")

            if campaigns:
                for campaign in campaigns:
                    with st.expander(f"**{campaign['name']}** — {campaign.get('actual_total', 0)} leads", expanded=False):
                        c1, c2, c3, c4 = st.columns(4)
                        with c1:
                            st.metric("Pending", campaign.get('pending_count', 0))
                        with c2:
                            st.metric("Processed", campaign.get('actual_processed', 0))
                        with c3:
                            st.metric("Pushed", campaign.get('actual_pushed', 0))
                        with c4:
                            st.metric("Errors", campaign.get('error_count', 0))

                        st.caption(f"ID: {campaign['id']} | Created: {str(campaign.get('created_at', ''))[:10]}")

                        col_a, col_b = st.columns(2)
                        with col_a:
                            if st.button("Select", key=f"sel_{campaign['id']}", use_container_width=True):
                                st.session_state.selected_campaign_id = campaign['id']
                                st.rerun()
                        with col_b:
                            if st.button("Delete", key=f"del_{campaign['id']}", use_container_width=True):
                                db.delete_campaign(campaign['id'])
                                st.rerun()
            else:
                st.info("No campaigns yet. Create one to get started.")

    # ===== Import Tab =====
    with tab2:
        st.markdown("### Import Leads from CSV")

        if not campaigns:
            st.warning("Create a campaign first before importing leads.")
        else:
            # Campaign selector
            campaign_names = {c['name']: c['id'] for c in campaigns}
            selected_name = st.selectbox("Select Campaign", list(campaign_names.keys()))
            selected_id = campaign_names.get(selected_name)

            # File uploader
            uploaded = st.file_uploader(
                "Upload CSV",
                type=["csv"],
                help="Required: email, company_name. Optional: first_name, last_name, site_url, city, state"
            )

            if uploaded:
                try:
                    df = pd.read_csv(uploaded)
                    st.success(f"Found **{len(df)}** leads in CSV")

                    # Preview
                    with st.expander("Preview Data", expanded=True):
                        st.dataframe(df.head(10), use_container_width=True)

                    # Import button
                    if st.button(" Import to Database", type="primary"):
                        with st.spinner("Importing..."):
                            result = db.import_leads_from_csv(df.to_dict('records'), selected_id)

                        st.success(f"""
                        **Import Complete**
                        - Imported: {result['imported']}
                        - Skipped: {result['skipped']}
                        - Errors: {result['errors']}
                        """)
                        st.rerun()

                except Exception as e:
                    st.error(f"Error reading CSV: {e}")

    # ===== Process Tab =====
    with tab3:
        st.markdown("### Process Pending Leads")

        if not campaigns:
            st.warning("No campaigns available.")
        else:
            # Campaign selector with pending counts
            campaign_opts = {f"{c['name']} ({c.get('pending_count', 0)} pending)": c['id'] for c in campaigns}
            selected_name = st.selectbox("Campaign", list(campaign_opts.keys()), key="process_campaign")
            selected_id = campaign_opts.get(selected_name)

            pending = db.get_lead_count(campaign_id=selected_id, status="pending")

            if pending == 0:
                st.info("No pending leads in this campaign.")
            else:
                st.info(f"**{pending}** leads ready to process")

                # Settings
                col1, col2 = st.columns(2)
                with col1:
                    batch_size = st.slider("Batch Size", 1, min(500, pending), min(50, pending))
                with col2:
                    st.markdown("**API Status**")
                    if st.session_state.anthropic_connected:
                        st.success(" Claude Ready")
                    else:
                        st.error(" Claude Not Connected")

                # Process button
                if st.button(" Start Processing", type="primary", disabled=not st.session_state.anthropic_connected):
                    run_lead_processing(selected_id, batch_size)

            # Error leads
            errors = db.get_lead_count(campaign_id=selected_id, status="error")
            if errors > 0:
                st.markdown("---")
                st.warning(f"**{errors}** leads with errors")
                if st.button(" Reset Errors to Pending"):
                    db.reset_error_leads(selected_id)
                    st.success("Reset complete")
                    st.rerun()

    # ===== Export Tab =====
    with tab4:
        st.markdown("### Export Leads")

        if not campaigns:
            st.warning("No campaigns available.")
        else:
            campaign_opts = {f"{c['name']}": c['id'] for c in campaigns}
            selected_name = st.selectbox("Campaign", list(campaign_opts.keys()), key="export_campaign")
            selected_id = campaign_opts.get(selected_name)

            status_filter = st.radio("Status", ["processed", "pushed", "all"], horizontal=True)

            count = db.get_lead_count(
                campaign_id=selected_id,
                status=None if status_filter == "all" else status_filter
            )

            st.info(f"**{count}** leads to export")

            if count > 0 and st.button(" Generate CSV"):
                status = None if status_filter == "all" else status_filter
                data = db.export_leads_to_csv(selected_id, status)

                if data:
                    df = pd.DataFrame(data)
                    csv = df.to_csv(index=False)

                    st.download_button(
                        " Download CSV",
                        csv,
                        f"leads_{selected_id}_{datetime.now().strftime('%Y%m%d')}.csv",
                        "text/csv",
                        use_container_width=True
                    )

                    st.dataframe(df.head(10), use_container_width=True)


def run_lead_processing(campaign_id: str, batch_size: int):
    """Process pending leads from database."""
    leads = db.get_pending_leads(campaign_id, limit=batch_size)

    if not leads:
        st.warning("No leads to process")
        return

    # Initialize
    serper = SerperClient(st.session_state.serper_api_key)
    ai_gen = AILineGenerator(st.session_state.anthropic_api_key)

    progress = st.progress(0)
    status = st.empty()
    stats = {"S": 0, "A": 0, "B": 0, "errors": 0}

    for i, lead in enumerate(leads):
        company = lead["company_name"]
        status.text(f"Processing {i+1}/{len(leads)}: {company}")

        try:
            # Build location
            location = ""
            if lead.get("city") and lead.get("state"):
                location = f"{lead['city']}, {lead['state']}"
            elif lead.get("city"):
                location = lead["city"]
            elif lead.get("state"):
                location = lead["state"]

            # Serper research
            serper_data = ""
            try:
                info = serper.get_company_info(company, lead.get("site_url", ""), location)
                serper_data = extract_artifacts_from_serper(info)
            except Exception as e:
                logger.warning(f"Serper failed for {company}: {e}")

            # Generate line
            lead_data = {
                "location": location,
                "technologies": lead.get("technologies"),
                "keywords": lead.get("keywords"),
                "person_title": lead.get("job_title"),
            }

            result = ai_gen.generate_line(company, serper_data, lead_data)

            # Update database
            db.update_lead_status(
                lead["id"],
                "processed",
                result.line,
                result.artifact_type,
                result.confidence_tier,
                result.artifact_used,
                result.reasoning
            )

            if result.confidence_tier in stats:
                stats[result.confidence_tier] += 1

        except Exception as e:
            logger.error(f"Error processing {company}: {e}")
            db.update_lead_status(lead["id"], "error", error_message=str(e)[:200])
            stats["errors"] += 1

        progress.progress((i + 1) / len(leads))

    # Complete
    status.empty()
    progress.progress(100)

    total = stats["S"] + stats["A"] + stats["B"]
    st.success(f"""
    **Processing Complete**
    - Total: {total}
    - S-Tier: {stats['S']}
    - A-Tier: {stats['A']}
    - B-Tier: {stats['B']}
    - Errors: {stats['errors']}
    """)
    st.rerun()


# ========== Quick Personalize Page ==========

def render_quick_personalize():
    """Render the quick CSV personalization page."""
    st.markdown('<h1 class="main-header">Quick Personalize</h1>', unsafe_allow_html=True)
    st.markdown('<p class="sub-header">Upload a CSV and get personalized lines instantly</p>', unsafe_allow_html=True)

    # Check API connection
    if not st.session_state.anthropic_connected:
        st.error("Claude AI not connected. Add ANTHROPIC_API_KEY to settings.")
        return

    col1, col2 = st.columns([2, 1])

    with col1:
        uploaded = st.file_uploader("Upload CSV", type=["csv"])

        if uploaded:
            df = pd.read_csv(uploaded)
            df = normalize_columns(df)
            st.session_state.df_input = df

            st.success(f"Loaded **{len(df)}** leads")
            st.dataframe(df.head(10), use_container_width=True)

    with col2:
        st.markdown("### Settings")

        if st.session_state.df_input is not None:
            total = len(st.session_state.df_input)
            limit = st.slider("Process limit", 1, total, min(50, total))

            if st.button(" Process Leads", type="primary", use_container_width=True):
                process_quick_leads(limit)

    # Results
    if st.session_state.df_processed is not None:
        st.markdown("---")
        st.markdown("### Results")

        df = st.session_state.df_processed
        stats = st.session_state.processing_stats

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("S-Tier", stats.get("S", 0))
        with col2:
            st.metric("A-Tier", stats.get("A", 0))
        with col3:
            st.metric("B-Tier", stats.get("B", 0))
        with col4:
            st.metric("Errors", stats.get("errors", 0))

        st.dataframe(df, use_container_width=True)

        # Download
        csv = df.to_csv(index=False)
        st.download_button(
            " Download Results",
            csv,
            f"personalized_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            "text/csv",
            use_container_width=True
        )


def process_quick_leads(limit: int):
    """Process leads from uploaded CSV."""
    df = st.session_state.df_input.head(limit).copy()

    serper = SerperClient(st.session_state.serper_api_key)
    ai_gen = AILineGenerator(st.session_state.anthropic_api_key)

    results = []
    stats = {"S": 0, "A": 0, "B": 0, "errors": 0}

    progress = st.progress(0)
    status = st.empty()

    for i, row in df.iterrows():
        company = row.get("company_name", "Unknown")
        status.text(f"Processing {i+1}/{len(df)}: {company}")

        try:
            location = row.get("location", "")
            domain = row.get("site_url", "")

            # Research
            serper_data = ""
            try:
                info = serper.get_company_info(company, domain, location)
                serper_data = extract_artifacts_from_serper(info)
            except:
                pass

            # Generate
            lead_data = {"location": location}
            result = ai_gen.generate_line(company, serper_data, lead_data)

            results.append({
                **row.to_dict(),
                "personalization_line": result.line,
                "confidence_tier": result.confidence_tier,
                "artifact_type": result.artifact_type,
            })

            if result.confidence_tier in stats:
                stats[result.confidence_tier] += 1

        except Exception as e:
            results.append({
                **row.to_dict(),
                "personalization_line": "Came across your company online.",
                "confidence_tier": "B",
                "artifact_type": "ERROR",
            })
            stats["errors"] += 1

        progress.progress((i + 1) / len(df))

    status.empty()
    st.session_state.df_processed = pd.DataFrame(results)
    st.session_state.processing_stats = stats
    st.session_state.processing_complete = True
    st.rerun()


# ========== Instantly Sync Page ==========

def render_instantly_sync():
    """Render the Instantly integration page."""
    st.markdown('<h1 class="main-header">Instantly Sync</h1>', unsafe_allow_html=True)
    st.markdown('<p class="sub-header">Push personalized leads to your Instantly campaigns</p>', unsafe_allow_html=True)

    if not st.session_state.instantly_connected:
        st.warning("Instantly not connected. Add your API key in Settings.")

        with st.expander("Connect Instantly"):
            api_key = st.text_input("Instantly API Key", type="password")
            if st.button("Connect"):
                try:
                    client = InstantlyClient(api_key)
                    campaigns = client.list_campaigns()
                    st.session_state.instantly_api_key = api_key
                    st.session_state.instantly_connected = True
                    st.session_state.instantly_campaigns = campaigns
                    st.success("Connected!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Connection failed: {e}")
        return

    # Connected - show sync interface
    col1, col2 = st.columns([2, 1])

    with col1:
        st.markdown("### Select Leads to Push")

        campaigns = db.get_campaigns()
        if campaigns:
            campaign_opts = {c['name']: c['id'] for c in campaigns}
            selected = st.selectbox("From Campaign", list(campaign_opts.keys()))
            campaign_id = campaign_opts.get(selected)

            # Get processed leads
            processed = db.get_leads(campaign_id=campaign_id, status="processed", limit=500)

            if processed:
                st.success(f"**{len(processed)}** leads ready to push")

                # Preview
                preview_df = pd.DataFrame([{
                    "email": l["email"],
                    "company": l["company_name"],
                    "line": l.get("personalization_line", "")[:50] + "...",
                    "tier": l.get("confidence_tier", ""),
                } for l in processed[:10]])

                st.dataframe(preview_df, use_container_width=True)
            else:
                st.info("No processed leads to push. Process some leads first.")
        else:
            st.info("No campaigns. Create one in Lead Manager.")

    with col2:
        st.markdown("### Instantly Campaign")

        instantly_campaigns = st.session_state.instantly_campaigns
        if instantly_campaigns:
            campaign_names = {c["name"]: c["id"] for c in instantly_campaigns}
            target = st.selectbox("Target Campaign", list(campaign_names.keys()))
            target_id = campaign_names.get(target)

            st.markdown("---")

            if st.button(" Push to Instantly", type="primary", use_container_width=True):
                if 'processed' in dir() and processed:
                    push_to_instantly(processed, target_id, campaign_id)
        else:
            st.warning("No Instantly campaigns found")
            if st.button("Refresh Campaigns"):
                try:
                    client = InstantlyClient(st.session_state.instantly_api_key)
                    st.session_state.instantly_campaigns = client.list_campaigns()
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")


def push_to_instantly(leads: List[Dict], instantly_campaign_id: str, db_campaign_id: str):
    """Push leads to Instantly campaign."""
    client = InstantlyClient(st.session_state.instantly_api_key)

    # Format for Instantly
    instantly_leads = []
    lead_ids = []

    for lead in leads:
        instantly_leads.append({
            "email": lead["email"],
            "first_name": lead.get("first_name", ""),
            "last_name": lead.get("last_name", ""),
            "company_name": lead.get("company_name", ""),
            "personalization": lead.get("personalization_line", ""),
            "website": lead.get("site_url", ""),
        })
        lead_ids.append(lead["id"])

    progress = st.progress(0)
    status = st.empty()

    try:
        status.text("Pushing to Instantly...")

        # Push in batches
        batch_size = 100
        for i in range(0, len(instantly_leads), batch_size):
            batch = instantly_leads[i:i+batch_size]
            client.add_leads_to_campaign(instantly_campaign_id, batch)
            progress.progress(min((i + batch_size) / len(instantly_leads), 1.0))

        # Update database status
        db.bulk_update_status(lead_ids, "pushed")

        status.empty()
        st.success(f"Pushed **{len(leads)}** leads to Instantly!")
        st.rerun()

    except Exception as e:
        st.error(f"Push failed: {e}")


# ========== Settings Page ==========

def render_settings():
    """Render the settings page."""
    st.markdown('<h1 class="main-header">Settings</h1>', unsafe_allow_html=True)
    st.markdown('<p class="sub-header">Configure your integrations and API connections</p>', unsafe_allow_html=True)

    # Connection Status Overview
    st.markdown("### Connection Status")
    status_cols = st.columns(4)

    with status_cols[0]:
        if st.session_state.anthropic_connected:
            st.success("Claude AI")
        else:
            st.error("Claude AI")

    with status_cols[1]:
        if st.session_state.serper_api_key:
            st.success("Serper")
        else:
            st.warning("Serper")

    with status_cols[2]:
        if st.session_state.instantly_connected:
            st.success("Instantly")
        else:
            st.warning("Instantly")

    with status_cols[3]:
        if db.get_database_type() == "supabase":
            st.success("Supabase")
        else:
            st.info("SQLite")

    st.markdown("---")

    # Tabs for different settings categories
    tab1, tab2, tab3 = st.tabs(["API Keys", "Database", "Getting Started"])

    # ===== API Keys Tab =====
    with tab1:
        st.markdown("### Configure Your API Integrations")
        st.caption("Add your API keys below. Keys are stored in your session and can also be set via environment variables.")

        # Two column layout for APIs
        col1, col2 = st.columns(2)

        with col1:
            # Claude AI (Required)
            st.markdown("#### Claude AI (Anthropic)")
            st.markdown("""
            <div style="background: #1e293b; padding: 16px; border-radius: 8px; margin-bottom: 16px;">
                <span style="color: #10b981; font-weight: bold;">REQUIRED</span> - Powers AI personalization
            </div>
            """, unsafe_allow_html=True)

            current = st.session_state.anthropic_api_key
            if current:
                masked = f"`{current[:8]}...{current[-4:]}`"
                st.markdown(f"**Current:** {masked}")
            else:
                st.markdown("**Current:** Not configured")

            with st.form("anthropic_form"):
                new_key = st.text_input(
                    "API Key",
                    type="password",
                    placeholder="sk-ant-api03-...",
                    help="Your Anthropic API key starting with 'sk-ant-'"
                )
                submitted = st.form_submit_button("Save & Test", type="primary", use_container_width=True)

                if submitted and new_key:
                    with st.spinner("Testing connection..."):
                        if test_anthropic_key(new_key):
                            st.session_state.anthropic_api_key = new_key
                            st.session_state.anthropic_connected = True
                            st.success("Connected successfully!")
                            st.rerun()
                        else:
                            st.error("Invalid API key. Please check and try again.")

            with st.expander("How to get your API key"):
                st.markdown("""
                1. Go to [console.anthropic.com](https://console.anthropic.com)
                2. Sign up or log in to your account
                3. Navigate to **API Keys** in the sidebar
                4. Click **Create Key** and copy it
                5. Paste it above

                **Cost:** ~$0.25 per 1,000 leads (using Claude Haiku)
                """)

            st.markdown("---")

            # Serper (Required)
            st.markdown("#### Serper (Google Search)")
            st.markdown("""
            <div style="background: #1e293b; padding: 16px; border-radius: 8px; margin-bottom: 16px;">
                <span style="color: #10b981; font-weight: bold;">REQUIRED</span> - Powers company research
            </div>
            """, unsafe_allow_html=True)

            current = st.session_state.serper_api_key
            if current:
                masked = f"`{current[:8]}...{current[-4:]}`"
                st.markdown(f"**Current:** {masked}")
            else:
                st.markdown("**Current:** Not configured")

            with st.form("serper_form"):
                new_key = st.text_input(
                    "API Key",
                    type="password",
                    placeholder="your-serper-api-key",
                    help="Your Serper.dev API key"
                )
                submitted = st.form_submit_button("Save", type="primary", use_container_width=True)

                if submitted and new_key:
                    st.session_state.serper_api_key = new_key
                    st.success("Saved!")
                    st.rerun()

            with st.expander("How to get your API key"):
                st.markdown("""
                1. Go to [serper.dev](https://serper.dev)
                2. Sign up for a free account
                3. You'll get **2,500 free searches** to start
                4. Copy your API key from the dashboard
                5. Paste it above

                **Cost:** $50 for 50,000 searches (after free tier)
                """)

        with col2:
            # Instantly (Optional)
            st.markdown("#### Instantly")
            st.markdown("""
            <div style="background: #1e293b; padding: 16px; border-radius: 8px; margin-bottom: 16px;">
                <span style="color: #6366f1; font-weight: bold;">OPTIONAL</span> - Push leads to campaigns
            </div>
            """, unsafe_allow_html=True)

            current = st.session_state.instantly_api_key
            if current:
                masked = f"`{current[:8]}...{current[-4:]}`"
                st.markdown(f"**Current:** {masked}")
            else:
                st.markdown("**Current:** Not configured")

            with st.form("instantly_form"):
                new_key = st.text_input(
                    "API Key",
                    type="password",
                    placeholder="your-instantly-api-key",
                    help="Your Instantly API key"
                )
                submitted = st.form_submit_button("Save & Test", type="primary", use_container_width=True)

                if submitted and new_key:
                    with st.spinner("Testing connection..."):
                        try:
                            client = InstantlyClient(new_key)
                            campaigns = client.list_campaigns()
                            st.session_state.instantly_api_key = new_key
                            st.session_state.instantly_connected = True
                            st.session_state.instantly_campaigns = campaigns
                            st.success(f"Connected! Found {len(campaigns)} campaigns.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Connection failed: {str(e)[:100]}")

            with st.expander("How to get your API key"):
                st.markdown("""
                1. Log in to [instantly.ai](https://instantly.ai)
                2. Go to **Settings** → **Integrations**
                3. Find **API** section
                4. Copy your API key
                5. Paste it above

                **Note:** Requires an Instantly subscription
                """)

            st.markdown("---")

            # Environment Variables Info
            st.markdown("#### Environment Variables")
            st.markdown("""
            <div style="background: #1e293b; padding: 16px; border-radius: 8px; margin-bottom: 16px;">
                <span style="color: #94a3b8; font-weight: bold;">RECOMMENDED</span> - For production deployment
            </div>
            """, unsafe_allow_html=True)

            st.markdown("Set these in Railway/Heroku/your hosting platform:")

            st.code("""
# Required
ANTHROPIC_API_KEY=sk-ant-api03-...
SERPER_API_KEY=your-serper-key

# Optional
INSTANTLY_API_KEY=your-instantly-key

# Database (for persistence)
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=your-anon-key
            """, language="bash")

    # ===== Database Tab =====
    with tab2:
        st.markdown("### Database Configuration")

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("#### Current Status")

            db_type = db.get_database_type()

            if db_type == "supabase":
                st.success("Using Supabase (Cloud Database)")
                st.markdown("""
                - Data persists across deployments
                - Accessible from anywhere
                - Ready for production
                """)
            else:
                st.warning("Using SQLite (Local Database)")
                st.markdown("""
                - Data stored locally only
                - Resets on deployment (Railway/Heroku)
                - Good for development/testing
                """)

            st.markdown("---")

            st.markdown("#### Why Supabase?")
            st.markdown("""
            - **Free tier:** 500MB storage, unlimited API requests
            - **Persistent:** Data survives deployments
            - **Fast:** PostgreSQL with global CDN
            - **Dashboard:** View/edit data in browser
            """)

        with col2:
            st.markdown("#### Supabase Setup")

            st.markdown("**Step 1:** Create a free project")
            st.markdown("Go to [supabase.com](https://supabase.com) and create a new project")

            st.markdown("**Step 2:** Run this SQL in the SQL Editor")

            st.code("""
-- Create tables for Bright Automations

CREATE TABLE campaigns (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE leads (
    id BIGSERIAL PRIMARY KEY,
    email TEXT NOT NULL,
    company_name TEXT NOT NULL,
    first_name TEXT,
    last_name TEXT,
    job_title TEXT,
    site_url TEXT,
    linkedin_url TEXT,
    city TEXT,
    state TEXT,
    technologies TEXT,
    keywords TEXT,
    annual_revenue NUMERIC,
    num_locations INTEGER,
    subsidiary_of TEXT,
    status TEXT DEFAULT 'pending',
    personalization_line TEXT,
    artifact_type TEXT,
    confidence_tier TEXT,
    artifact_used TEXT,
    reasoning TEXT,
    campaign_id TEXT REFERENCES campaigns(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    processed_at TIMESTAMPTZ,
    pushed_at TIMESTAMPTZ,
    error_message TEXT,
    UNIQUE(email, campaign_id)
);

CREATE INDEX idx_leads_status ON leads(status);
CREATE INDEX idx_leads_campaign ON leads(campaign_id);
            """, language="sql")

            st.markdown("**Step 3:** Add environment variables")
            st.markdown("""
            In your hosting platform (Railway, etc.):
            - `SUPABASE_URL` - Project URL from Settings → API
            - `SUPABASE_KEY` - `anon` `public` key from Settings → API
            """)

    # ===== Getting Started Tab =====
    with tab3:
        st.markdown("### Quick Start Guide")

        st.markdown("""
        Follow these steps to get up and running in under 5 minutes.
        """)

        # Step 1
        st.markdown("#### Step 1: Get Your API Keys")
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("""
            **Claude AI (Required)**
            1. Visit [console.anthropic.com](https://console.anthropic.com)
            2. Create account → Get API key
            3. Cost: ~$0.25 per 1,000 leads
            """)

        with col2:
            st.markdown("""
            **Serper (Required)**
            1. Visit [serper.dev](https://serper.dev)
            2. Sign up → Get 2,500 free searches
            3. Copy API key from dashboard
            """)

        st.markdown("---")

        # Step 2
        st.markdown("#### Step 2: Add Keys to Settings")
        st.markdown("""
        Paste your API keys in the **API Keys** tab above. Click "Save & Test" to verify they work.
        """)

        st.markdown("---")

        # Step 3
        st.markdown("#### Step 3: Create Your First Campaign")
        st.markdown("""
        1. Go to **Lead Manager** → **Campaigns** tab
        2. Enter a campaign name (e.g., "Q1 HVAC Outreach")
        3. Click **Create**
        """)

        st.markdown("---")

        # Step 4
        st.markdown("#### Step 4: Import Leads")
        st.markdown("""
        1. Go to **Lead Manager** → **Import** tab
        2. Select your campaign
        3. Upload a CSV with columns:
           - `email` (required)
           - `company_name` (required)
           - `first_name`, `last_name`, `site_url`, `city`, `state` (optional)
        4. Click **Import to Database**
        """)

        st.markdown("---")

        # Step 5
        st.markdown("#### Step 5: Process Leads")
        st.markdown("""
        1. Go to **Lead Manager** → **Process** tab
        2. Select campaign and batch size
        3. Click **Start Processing**
        4. Watch as AI generates personalized lines!
        """)

        st.markdown("---")

        # Step 6
        st.markdown("#### Step 6: Export or Push to Instantly")
        st.markdown("""
        **Option A: Export CSV**
        - Go to **Lead Manager** → **Export** tab
        - Download CSV with personalized lines
        - Upload manually to your email tool

        **Option B: Push to Instantly**
        - Go to **Instantly Sync**
        - Select leads and target campaign
        - Click **Push to Instantly**
        """)

        st.markdown("---")

        st.markdown("### Need Help?")
        st.markdown("""
        - **Documentation:** [brightautomations.org/docs](https://brightautomations.org)
        - **Support:** support@brightautomations.org
        """)

        st.markdown("---")

        # About section
        col1, col2 = st.columns([2, 1])
        with col1:
            st.markdown("### About Bright Automations")
            st.markdown("""
            Bright Automations helps agencies and sales teams personalize cold outreach at scale.

            Our AI researches each company, finds impressive facts (awards, reviews, years in business),
            and writes custom opening lines that get replies.

            **v2.0** | Built with Claude AI
            """)

        with col2:
            st.markdown("### Links")
            st.markdown("""
            - [Website](https://brightautomations.org)
            - [Documentation](https://brightautomations.org/docs)
            - [Support](mailto:support@brightautomations.org)
            """)


# ========== Main Entry Point ==========

def main():
    """Main application entry point."""
    init_session_state()
    render_sidebar()

    # Route to current page
    page = st.session_state.current_page

    if page == "Dashboard":
        render_dashboard()
    elif page == "Lead Manager":
        render_lead_manager()
    elif page == "Quick Personalize":
        render_quick_personalize()
    elif page == "Instantly Sync":
        render_instantly_sync()
    elif page == "Settings":
        render_settings()
    else:
        render_dashboard()


if __name__ == "__main__":
    main()
