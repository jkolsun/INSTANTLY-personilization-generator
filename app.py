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
    /* Import Space Grotesk font */
    @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600;700&display=swap');

    /* Main branding colors - Bright Automations Teal Theme */
    :root {
        --primary: #2E7D8A;
        --primary-dark: #1e5a63;
        --primary-light: #3a9aa8;
        --secondary: #10b981;
        --accent: #f59e0b;
        --success: #22c55e;
        --warning: #f59e0b;
        --error: #ef4444;
    }

    /* Universal text colors that work in both modes */
    .text-primary { color: #1e293b !important; }
    .text-secondary { color: #475569 !important; }
    .text-muted { color: #64748b !important; }
    .text-brand { color: #2E7D8A !important; }
    .text-success { color: #059669 !important; }
    .text-warning { color: #d97706 !important; }
    .text-error { color: #dc2626 !important; }

    /* Card backgrounds that work in both modes */
    .card-surface {
        background: rgba(241, 245, 249, 0.8) !important;
        border: 1px solid rgba(0, 0, 0, 0.08) !important;
    }
    .card-success { background: rgba(16, 185, 129, 0.1) !important; border: 1px solid rgba(16, 185, 129, 0.2) !important; }
    .card-warning { background: rgba(245, 158, 11, 0.1) !important; border: 1px solid rgba(245, 158, 11, 0.2) !important; }
    .card-error { background: rgba(239, 68, 68, 0.1) !important; border: 1px solid rgba(239, 68, 68, 0.2) !important; }
    .card-brand { background: rgba(46, 125, 138, 0.1) !important; border: 1px solid rgba(46, 125, 138, 0.2) !important; }

    /* Force all text to be readable */
    .stMarkdown, .stMarkdown p, .stMarkdown span, .stMarkdown div,
    [data-testid="stMarkdownContainer"] p,
    [data-testid="stMarkdownContainer"] span,
    [data-testid="stMarkdownContainer"] div {
        color: #1e293b !important;
    }

    /* Fix metric values */
    [data-testid="stMetricValue"] {
        color: #1e293b !important;
    }

    [data-testid="stMetricLabel"] {
        color: #475569 !important;
    }

    /* Fix expander text */
    [data-testid="stExpander"] p,
    [data-testid="stExpander"] span,
    [data-testid="stExpander"] div {
        color: #1e293b !important;
    }

    /* Fix sidebar - keep dark theme */
    [data-testid="stSidebar"] * {
        color: #f8fafc !important;
    }

    [data-testid="stSidebar"] [data-testid="stMetricValue"],
    [data-testid="stSidebar"] [data-testid="stMetricLabel"] {
        color: #f8fafc !important;
    }

    /* Fix form inputs */
    .stTextInput input, .stNumberInput input, .stSelectbox select {
        color: #1e293b !important;
        background: #ffffff !important;
    }

    /* Fix code blocks */
    .stCodeBlock {
        background: #1e293b !important;
    }

    .stCodeBlock code {
        color: #e2e8f0 !important;
    }

    /* Apply Space Grotesk font globally */
    html, body, [class*="css"] {
        font-family: 'Space Grotesk', sans-serif;
    }

    /* Hide default Streamlit branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}

    /* Main container padding adjustment */
    .main .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
        max-width: 1200px;
    }

    /* Sidebar styling */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #1e293b 0%, #0f172a 100%);
        border-right: 1px solid rgba(255, 255, 255, 0.05);
    }

    [data-testid="stSidebar"] .stMarkdown h1,
    [data-testid="stSidebar"] .stMarkdown h2,
    [data-testid="stSidebar"] .stMarkdown h3 {
        color: #f8fafc;
        font-family: 'Space Grotesk', sans-serif;
    }

    /* Progress bar - Teal gradient with animation */
    .stProgress > div > div > div > div {
        background: linear-gradient(90deg, #2E7D8A 0%, #10b981 100%);
        transition: width 0.3s ease;
    }

    /* Metric cards - enhanced */
    [data-testid="stMetricValue"] {
        font-size: 2rem;
        font-weight: 700;
        font-family: 'Space Grotesk', sans-serif;
        color: #f8fafc;
    }

    [data-testid="stMetricLabel"] {
        font-family: 'Space Grotesk', sans-serif;
        color: #94a3b8;
        font-weight: 500;
    }

    [data-testid="stMetricDelta"] {
        font-family: 'Space Grotesk', sans-serif;
    }

    /* Tier colors */
    .tier-s { color: #10b981; font-weight: bold; }
    .tier-a { color: #2E7D8A; font-weight: bold; }
    .tier-b { color: #94a3b8; font-weight: bold; }

    /* Enhanced glassmorphism cards */
    .glass-card {
        background: rgba(30, 41, 59, 0.7);
        backdrop-filter: blur(12px);
        -webkit-backdrop-filter: blur(12px);
        border-radius: 16px;
        padding: 24px;
        border: 1px solid rgba(255, 255, 255, 0.08);
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2), inset 0 1px 0 rgba(255, 255, 255, 0.05);
        margin: 12px 0;
        transition: all 0.3s ease;
    }

    .glass-card:hover {
        border-color: rgba(46, 125, 138, 0.3);
        box-shadow: 0 12px 40px rgba(0, 0, 0, 0.3), inset 0 1px 0 rgba(255, 255, 255, 0.08);
    }

    .feature-card {
        background: linear-gradient(135deg, rgba(30, 41, 59, 0.8) 0%, rgba(51, 65, 85, 0.6) 100%);
        backdrop-filter: blur(12px);
        border-radius: 16px;
        padding: 24px;
        border: 1px solid rgba(255, 255, 255, 0.08);
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
        margin: 8px 0;
        transition: all 0.3s ease;
    }

    .feature-card:hover {
        transform: translateY(-2px);
        border-color: rgba(46, 125, 138, 0.3);
    }

    .stat-card {
        background: rgba(30, 41, 59, 0.6);
        backdrop-filter: blur(8px);
        border-radius: 12px;
        padding: 20px;
        text-align: center;
        border: 1px solid rgba(255, 255, 255, 0.06);
        transition: all 0.3s ease;
    }

    .stat-card:hover {
        background: rgba(30, 41, 59, 0.8);
        border-color: rgba(46, 125, 138, 0.2);
    }

    /* Button styling - Teal theme enhanced */
    .stButton > button {
        border-radius: 10px;
        font-weight: 600;
        font-family: 'Space Grotesk', sans-serif;
        transition: all 0.2s ease;
        border: 1px solid rgba(255, 255, 255, 0.1);
        padding: 0.5rem 1.25rem;
    }

    .stButton > button:hover {
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(46, 125, 138, 0.3);
    }

    .stButton > button:active {
        transform: translateY(0);
    }

    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #2E7D8A 0%, #1e5a63 100%);
        border: none;
        color: white;
    }

    .stButton > button[kind="primary"]:hover {
        background: linear-gradient(135deg, #3a9aa8 0%, #2E7D8A 100%);
    }

    /* Tab styling - refined */
    .stTabs [data-baseweb="tab-list"] {
        gap: 4px;
        background: rgba(30, 41, 59, 0.5);
        padding: 6px;
        border-radius: 12px;
        border: 1px solid rgba(255, 255, 255, 0.05);
    }

    .stTabs [data-baseweb="tab"] {
        border-radius: 8px;
        font-family: 'Space Grotesk', sans-serif;
        font-weight: 500;
        padding: 8px 16px;
        transition: all 0.2s ease;
    }

    .stTabs [data-baseweb="tab"]:hover {
        background: rgba(46, 125, 138, 0.1);
    }

    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #2E7D8A 0%, #1e5a63 100%) !important;
        color: white !important;
    }

    /* Header styling - Teal gradient */
    .main-header {
        font-size: 2.25rem;
        font-weight: 700;
        font-family: 'Space Grotesk', sans-serif;
        background: linear-gradient(135deg, #2E7D8A 0%, #10b981 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        margin-bottom: 0;
        letter-spacing: -0.02em;
    }

    .sub-header {
        color: #94a3b8;
        font-size: 1rem;
        font-family: 'Space Grotesk', sans-serif;
        margin-top: 4px;
        font-weight: 400;
    }

    /* Status indicators */
    .status-pending { color: #f59e0b; }
    .status-processed { color: #10b981; }
    .status-pushed { color: #2E7D8A; }
    .status-error { color: #ef4444; }

    /* Getting Started Banner - Premium Design */
    .getting-started-banner {
        background: linear-gradient(135deg, rgba(46, 125, 138, 0.12) 0%, rgba(16, 185, 129, 0.08) 100%);
        backdrop-filter: blur(12px);
        border-radius: 16px;
        padding: 20px 24px;
        border: 1px solid rgba(46, 125, 138, 0.2);
        margin-bottom: 24px;
        box-shadow: 0 4px 24px rgba(0, 0, 0, 0.1);
    }

    .getting-started-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 16px;
    }

    .getting-started-title-row {
        display: flex;
        align-items: center;
        gap: 12px;
    }

    .getting-started-icon {
        width: 40px;
        height: 40px;
        background: linear-gradient(135deg, #2E7D8A 0%, #10b981 100%);
        border-radius: 10px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1.25rem;
    }

    .getting-started-title {
        font-size: 1.1rem;
        font-weight: 600;
        color: #f8fafc;
        font-family: 'Space Grotesk', sans-serif;
        margin: 0;
    }

    .getting-started-subtitle {
        font-size: 0.85rem;
        color: #94a3b8;
        margin: 2px 0 0 0;
    }

    .progress-badge {
        background: rgba(46, 125, 138, 0.2);
        color: #2E7D8A;
        padding: 6px 12px;
        border-radius: 20px;
        font-size: 0.8rem;
        font-weight: 600;
        font-family: 'Space Grotesk', sans-serif;
    }

    /* Checklist Steps */
    .checklist-steps {
        display: flex;
        gap: 12px;
        flex-wrap: wrap;
    }

    .checklist-step {
        flex: 1;
        min-width: 160px;
        background: rgba(30, 41, 59, 0.5);
        border-radius: 12px;
        padding: 16px;
        border: 1px solid rgba(255, 255, 255, 0.05);
        transition: all 0.2s ease;
        cursor: default;
    }

    .checklist-step:hover {
        background: rgba(30, 41, 59, 0.7);
        border-color: rgba(46, 125, 138, 0.2);
    }

    .checklist-step.completed {
        background: rgba(16, 185, 129, 0.08);
        border-color: rgba(16, 185, 129, 0.2);
    }

    .step-header {
        display: flex;
        align-items: center;
        gap: 10px;
        margin-bottom: 8px;
    }

    .step-number {
        width: 24px;
        height: 24px;
        border-radius: 50%;
        background: rgba(148, 163, 184, 0.2);
        border: 2px solid #64748b;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 0.75rem;
        font-weight: 600;
        color: #94a3b8;
        transition: all 0.2s ease;
    }

    .step-number.completed {
        background: linear-gradient(135deg, #22c55e 0%, #16a34a 100%);
        border-color: #22c55e;
        color: white;
    }

    .step-label {
        font-size: 0.9rem;
        font-weight: 500;
        color: #f8fafc;
        font-family: 'Space Grotesk', sans-serif;
    }

    .step-label.completed {
        color: #94a3b8;
    }

    .step-description {
        font-size: 0.8rem;
        color: #64748b;
        margin-left: 34px;
    }

    /* Expander styling - refined */
    .streamlit-expanderHeader {
        font-family: 'Space Grotesk', sans-serif;
        font-weight: 600;
        background: rgba(30, 41, 59, 0.3);
        border-radius: 10px;
    }

    /* Input styling - enhanced */
    .stTextInput > div > div > input {
        border-radius: 10px;
        font-family: 'Space Grotesk', sans-serif;
        border: 1px solid rgba(255, 255, 255, 0.1);
        transition: all 0.2s ease;
    }

    .stTextInput > div > div > input:focus {
        border-color: #2E7D8A;
        box-shadow: 0 0 0 2px rgba(46, 125, 138, 0.2);
    }

    /* Select box styling */
    .stSelectbox > div > div {
        border-radius: 10px;
    }

    /* Success/Warning/Error/Info boxes - refined */
    .stSuccess {
        background: rgba(34, 197, 94, 0.1);
        border: 1px solid rgba(34, 197, 94, 0.3);
        border-radius: 10px;
    }

    .stWarning {
        background: rgba(245, 158, 11, 0.1);
        border: 1px solid rgba(245, 158, 11, 0.3);
        border-radius: 10px;
    }

    .stError {
        background: rgba(239, 68, 68, 0.1);
        border: 1px solid rgba(239, 68, 68, 0.3);
        border-radius: 10px;
    }

    .stInfo {
        background: rgba(46, 125, 138, 0.1);
        border: 1px solid rgba(46, 125, 138, 0.3);
        border-radius: 10px;
    }

    /* DataFrame styling */
    .stDataFrame {
        border-radius: 12px;
        overflow: hidden;
    }

    /* Form styling */
    [data-testid="stForm"] {
        background: rgba(30, 41, 59, 0.3);
        border-radius: 12px;
        padding: 20px;
        border: 1px solid rgba(255, 255, 255, 0.05);
    }

    /* File uploader styling */
    [data-testid="stFileUploader"] {
        background: rgba(30, 41, 59, 0.3);
        border-radius: 12px;
        padding: 16px;
        border: 2px dashed rgba(46, 125, 138, 0.3);
    }

    [data-testid="stFileUploader"]:hover {
        border-color: rgba(46, 125, 138, 0.5);
        background: rgba(30, 41, 59, 0.5);
    }

    /* Divider styling */
    hr {
        border: none;
        height: 1px;
        background: linear-gradient(90deg, transparent 0%, rgba(255, 255, 255, 0.1) 50%, transparent 100%);
        margin: 24px 0;
    }

    /* Scrollbar styling */
    ::-webkit-scrollbar {
        width: 8px;
        height: 8px;
    }

    ::-webkit-scrollbar-track {
        background: rgba(30, 41, 59, 0.5);
        border-radius: 4px;
    }

    ::-webkit-scrollbar-thumb {
        background: rgba(46, 125, 138, 0.5);
        border-radius: 4px;
    }

    ::-webkit-scrollbar-thumb:hover {
        background: rgba(46, 125, 138, 0.7);
    }

    /* Quick action cards */
    .quick-action-card {
        background: rgba(30, 41, 59, 0.5);
        border-radius: 12px;
        padding: 16px;
        border: 1px solid rgba(255, 255, 255, 0.05);
        transition: all 0.2s ease;
        cursor: pointer;
    }

    .quick-action-card:hover {
        background: rgba(46, 125, 138, 0.1);
        border-color: rgba(46, 125, 138, 0.3);
        transform: translateY(-2px);
    }

    /* Campaign card styling */
    .campaign-card {
        background: rgba(30, 41, 59, 0.4);
        border-radius: 12px;
        padding: 16px 20px;
        border: 1px solid rgba(255, 255, 255, 0.05);
        margin: 8px 0;
        transition: all 0.2s ease;
    }

    .campaign-card:hover {
        background: rgba(30, 41, 59, 0.6);
        border-color: rgba(46, 125, 138, 0.2);
    }

    /* Empty state styling */
    .empty-state {
        text-align: center;
        padding: 40px;
        background: rgba(30, 41, 59, 0.3);
        border-radius: 16px;
        border: 1px dashed rgba(255, 255, 255, 0.1);
    }

    .empty-state-icon {
        font-size: 3rem;
        margin-bottom: 16px;
        opacity: 0.5;
    }

    .empty-state-title {
        font-size: 1.1rem;
        font-weight: 600;
        color: #f8fafc;
        margin-bottom: 8px;
    }

    .empty-state-text {
        color: #94a3b8;
        font-size: 0.9rem;
    }
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
        "supabase_url": os.environ.get("SUPABASE_URL", ""),
        "supabase_key": os.environ.get("SUPABASE_KEY", ""),

        # Connection states
        "instantly_connected": bool(os.environ.get("INSTANTLY_API_KEY")),
        "anthropic_connected": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "supabase_connected": bool(os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_KEY")),

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
        "quick_campaign_id": None,  # Auto-created campaign for persistence

        # Selected campaign for database
        "selected_campaign_id": None,

        # Getting Started checklist
        "checklist_dismissed": False,
        "first_leads_processed": False,
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


def get_checklist_status() -> Dict[str, Any]:
    """Get the current status of the getting started checklist."""
    stats = db.get_lead_stats()
    campaigns = db.get_campaigns()

    checklist = {
        "claude_connected": {
            "label": "Connect Claude AI",
            "description": "Required for AI-powered personalization",
            "completed": st.session_state.anthropic_connected,
            "action": "Settings",
        },
        "serper_connected": {
            "label": "Connect Serper",
            "description": "Required for company research",
            "completed": bool(st.session_state.serper_api_key),
            "action": "Settings",
        },
        "campaign_created": {
            "label": "Create first campaign",
            "description": "Organize your leads by campaign",
            "completed": len(campaigns) > 0,
            "action": "Lead Manager",
        },
        "leads_imported": {
            "label": "Import leads",
            "description": "Upload a CSV with your leads",
            "completed": stats["total"] > 0,
            "action": "Lead Manager",
        },
        "leads_processed": {
            "label": "Process your first lead",
            "description": "Generate personalized opening lines",
            "completed": stats["processed"] > 0 or stats["pushed"] > 0 or st.session_state.first_leads_processed,
            "action": "Lead Manager",
        },
    }

    completed = sum(1 for item in checklist.values() if item["completed"])
    total = len(checklist)

    return {
        "items": checklist,
        "completed": completed,
        "total": total,
        "percentage": int((completed / total) * 100),
        "all_done": completed == total,
    }


def render_getting_started_checklist():
    """Render getting started checklist using native Streamlit components."""
    if st.session_state.checklist_dismissed:
        return

    status = get_checklist_status()

    if status["all_done"]:
        return

    # Simple header using native components
    st.subheader(f"Getting Started ({status['completed']}/{status['total']} Complete)")
    st.progress(status["percentage"] / 100)

    # Step cards using native columns
    cols = st.columns(5)
    items = list(status["items"].items())

    for i, (key, item) in enumerate(items):
        with cols[i]:
            is_complete = item["completed"]
            step_num = i + 1

            # Show status with simple text
            if is_complete:
                st.success(f"Step {step_num} Done")
            else:
                st.info(f"Step {step_num}")

            st.caption(item['label'])

            # Action button only for incomplete items
            if not is_complete:
                if st.button(
                    f"Go to {item['action']}",
                    key=f"checklist_{key}",
                    use_container_width=True,
                ):
                    st.session_state.current_page = item["action"]
                    st.rerun()

    # Dismiss button
    col1, col2, col3 = st.columns([2, 1, 2])
    with col2:
        if st.button("Hide for now", key="dismiss_checklist", use_container_width=True):
            st.session_state.checklist_dismissed = True
            st.rerun()

    st.divider()


# ========== Sidebar Navigation ==========

def render_sidebar():
    """Render the sidebar with navigation and status."""
    with st.sidebar:
        # Logo/Brand with company logo
        st.markdown("""
        <div style="text-align: center; padding: 20px 0 16px 0;">
            <img src="https://www.brightautomations.org/images/Bright_AutoLOGO.png"
                 alt="Bright Automations"
                 style="max-width: 180px; height: auto; margin-bottom: 8px;">
            <div style="color: #94a3b8; font-size: 0.85rem; margin-top: 4px;">Lead Personalization Platform</div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("---")

        # Main Navigation
        st.markdown("### Navigation")

        pages = [
            "Dashboard",
            "Lead Manager",
            "Quick Personalize",
            "Instantly Sync",
            "Settings",
        ]

        # Show warning if processing is active
        if st.session_state.processing_active:
            st.warning("Processing in progress...")

        for page_name in pages:
            is_active = st.session_state.current_page == page_name
            # Disable navigation during processing (except to current page)
            is_disabled = st.session_state.processing_active and not is_active
            if st.button(
                page_name,
                key=f"nav_{page_name}",
                use_container_width=True,
                type="primary" if is_active else "secondary",
                disabled=is_disabled
            ):
                st.session_state.current_page = page_name
                st.rerun()

        st.markdown("---")

        # Quick Stats with glass effect
        st.markdown("### Quick Stats")
        stats = db.get_lead_stats()

        col1, col2 = st.columns(2)
        with col1:
            st.metric("Total", stats["total"])
        with col2:
            st.metric("Done", stats["processed"])

        # Database indicator
        db_type = db.get_database_type()
        if db_type == "supabase":
            st.success("Cloud Database")
        else:
            st.info("Local Database")

        st.markdown("---")

        # Connection Status
        st.markdown("### Connections")

        connections = [
            ("Claude AI", st.session_state.anthropic_connected, True),
            ("Serper", bool(st.session_state.serper_api_key), True),
            ("Instantly", st.session_state.instantly_connected, False),
        ]

        for name, connected, required in connections:
            if connected:
                st.success(f"{name} Connected")
            elif required:
                st.error(f"{name} Not Connected")
            else:
                st.info(f"{name} Optional")

        # Footer
        st.markdown("---")
        st.caption("v2.0 - brightautomations.org")


# ========== Dashboard Page ==========

def render_dashboard():
    """Render the main dashboard overview."""
    st.title("Dashboard")
    st.caption("Overview of your lead personalization pipeline")

    # Top metrics with premium cards
    stats = db.get_lead_stats()
    campaigns = db.get_campaigns()

    # Premium metric cards
    st.markdown("""
    <div style="
        display: grid;
        grid-template-columns: repeat(5, 1fr);
        gap: 16px;
        margin: 24px 0;
    ">
    """ + f"""
        <div style="
            background: linear-gradient(135deg, rgba(46, 125, 138, 0.15) 0%, rgba(46, 125, 138, 0.05) 100%);
            border: 1px solid rgba(46, 125, 138, 0.3);
            border-radius: 16px;
            padding: 20px;
            text-align: center;
        ">
            <div style="color: #94a3b8; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px;">Total Leads</div>
            <div style="color: #2E7D8A; font-size: 2.25rem; font-weight: 700; font-family: 'Space Grotesk', sans-serif;">{stats["total"]}</div>
        </div>
        <div style="
            background: linear-gradient(135deg, rgba(245, 158, 11, 0.15) 0%, rgba(245, 158, 11, 0.05) 100%);
            border: 1px solid rgba(245, 158, 11, 0.3);
            border-radius: 16px;
            padding: 20px;
            text-align: center;
        ">
            <div style="color: #94a3b8; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px;">Pending</div>
            <div style="color: #f59e0b; font-size: 2.25rem; font-weight: 700; font-family: 'Space Grotesk', sans-serif;">{stats["pending"]}</div>
        </div>
        <div style="
            background: linear-gradient(135deg, rgba(34, 197, 94, 0.15) 0%, rgba(34, 197, 94, 0.05) 100%);
            border: 1px solid rgba(34, 197, 94, 0.3);
            border-radius: 16px;
            padding: 20px;
            text-align: center;
        ">
            <div style="color: #94a3b8; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px;">Processed</div>
            <div style="color: #22c55e; font-size: 2.25rem; font-weight: 700; font-family: 'Space Grotesk', sans-serif;">{stats["processed"]}</div>
        </div>
        <div style="
            background: linear-gradient(135deg, rgba(99, 102, 241, 0.15) 0%, rgba(99, 102, 241, 0.05) 100%);
            border: 1px solid rgba(99, 102, 241, 0.3);
            border-radius: 16px;
            padding: 20px;
            text-align: center;
        ">
            <div style="color: #94a3b8; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px;">Pushed</div>
            <div style="color: #6366f1; font-size: 2.25rem; font-weight: 700; font-family: 'Space Grotesk', sans-serif;">{stats["pushed"]}</div>
        </div>
        <div style="
            background: linear-gradient(135deg, rgba(236, 72, 153, 0.15) 0%, rgba(236, 72, 153, 0.05) 100%);
            border: 1px solid rgba(236, 72, 153, 0.3);
            border-radius: 16px;
            padding: 20px;
            text-align: center;
        ">
            <div style="color: #94a3b8; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px;">Campaigns</div>
            <div style="color: #ec4899; font-size: 2.25rem; font-weight: 700; font-family: 'Space Grotesk', sans-serif;">{len(campaigns)}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("")  # Spacer

    # Two column layout
    col_left, col_right = st.columns([2, 1])

    with col_left:
        st.markdown("""
        <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 16px;">
            <div style="
                width: 8px;
                height: 24px;
                background: linear-gradient(180deg, #2E7D8A 0%, #10b981 100%);
                border-radius: 4px;
            "></div>
            <h3 style="margin: 0; color: #f8fafc; font-family: 'Space Grotesk', sans-serif;">Recent Campaigns</h3>
        </div>
        """, unsafe_allow_html=True)

        if campaigns:
            for campaign in campaigns[:5]:
                pending = campaign.get('pending_count', 0)
                processed = campaign.get('actual_processed', 0)
                total = campaign.get('actual_total', 0)
                progress = int((processed / total * 100)) if total > 0 else 0

                st.markdown(f"""
                <div class="campaign-card" style="
                    background: rgba(30, 41, 59, 0.5);
                    border-radius: 12px;
                    padding: 16px 20px;
                    border: 1px solid rgba(255, 255, 255, 0.08);
                    margin-bottom: 12px;
                ">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                        <div>
                            <div style="color: #f8fafc; font-weight: 600; font-size: 1rem; font-family: 'Space Grotesk', sans-serif;">{campaign['name']}</div>
                            <div style="color: #64748b; font-size: 0.75rem; margin-top: 2px;">ID: {campaign['id'][:8]}...</div>
                        </div>
                        <div style="display: flex; gap: 16px; align-items: center;">
                            <div style="text-align: center;">
                                <div style="color: #f59e0b; font-size: 1.1rem; font-weight: 600;">{pending}</div>
                                <div style="color: #64748b; font-size: 0.65rem; text-transform: uppercase;">Pending</div>
                            </div>
                            <div style="text-align: center;">
                                <div style="color: #22c55e; font-size: 1.1rem; font-weight: 600;">{processed}</div>
                                <div style="color: #64748b; font-size: 0.65rem; text-transform: uppercase;">Done</div>
                            </div>
                        </div>
                    </div>
                    <div style="background: rgba(255,255,255,0.1); border-radius: 4px; height: 4px; overflow: hidden;">
                        <div style="background: linear-gradient(90deg, #2E7D8A 0%, #10b981 100%); height: 100%; width: {progress}%; transition: width 0.3s ease;"></div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                if st.button(f"Open Campaign", key=f"open_{campaign['id']}", use_container_width=True):
                    st.session_state.selected_campaign_id = campaign['id']
                    st.session_state.current_page = "Lead Manager"
                    st.rerun()
        else:
            st.markdown("""
            <div class="empty-state">
                <div class="empty-state-icon">📁</div>
                <div class="empty-state-title">No Campaigns Yet</div>
                <div class="empty-state-text">Create your first campaign to start personalizing leads</div>
            </div>
            """, unsafe_allow_html=True)
            if st.button("Create Campaign", type="primary", use_container_width=True):
                st.session_state.current_page = "Lead Manager"
                st.rerun()

    with col_right:
        # Quality Distribution
        st.markdown("""
        <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 16px;">
            <div style="
                width: 8px;
                height: 24px;
                background: linear-gradient(180deg, #22c55e 0%, #16a34a 100%);
                border-radius: 4px;
            "></div>
            <h3 style="margin: 0; color: #f8fafc; font-family: 'Space Grotesk', sans-serif;">Quality Tiers</h3>
        </div>
        """, unsafe_allow_html=True)

        tiers = stats.get("tiers", {})
        if tiers and sum(tiers.values()) > 0:
            fig = go.Figure(data=[go.Pie(
                labels=list(tiers.keys()),
                values=list(tiers.values()),
                hole=0.65,
                marker_colors=['#22c55e', '#2E7D8A', '#64748b'],
                textinfo='label+percent',
                textfont=dict(size=12, family='Space Grotesk'),
            )])
            fig.update_layout(
                showlegend=False,
                height=200,
                margin=dict(t=10, b=10, l=10, r=10),
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
            )
            st.plotly_chart(fig, use_container_width=True)

            # Tier legend
            st.markdown(f"""
            <div style="display: flex; justify-content: center; gap: 16px; margin-top: -10px;">
                <div style="display: flex; align-items: center; gap: 6px;">
                    <div style="width: 10px; height: 10px; background: #22c55e; border-radius: 50%;"></div>
                    <span style="color: #94a3b8; font-size: 0.75rem;">S-Tier</span>
                </div>
                <div style="display: flex; align-items: center; gap: 6px;">
                    <div style="width: 10px; height: 10px; background: #2E7D8A; border-radius: 50%;"></div>
                    <span style="color: #94a3b8; font-size: 0.75rem;">A-Tier</span>
                </div>
                <div style="display: flex; align-items: center; gap: 6px;">
                    <div style="width: 10px; height: 10px; background: #64748b; border-radius: 50%;"></div>
                    <span style="color: #94a3b8; font-size: 0.75rem;">B-Tier</span>
                </div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown("""
            <div style="
                background: rgba(30, 41, 59, 0.5);
                border-radius: 12px;
                padding: 32px;
                text-align: center;
                border: 1px dashed rgba(255, 255, 255, 0.1);
            ">
                <div style="color: #64748b; font-size: 2rem; margin-bottom: 8px;">[Chart]</div>
                <div style="color: #94a3b8; font-size: 0.85rem;">Process leads to see quality breakdown</div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("")  # Spacer

        # Quick Actions
        st.markdown("""
        <div style="display: flex; align-items: center; gap: 12px; margin: 20px 0 16px 0;">
            <div style="
                width: 8px;
                height: 24px;
                background: linear-gradient(180deg, #6366f1 0%, #8b5cf6 100%);
                border-radius: 4px;
            "></div>
            <h3 style="margin: 0; color: #f8fafc; font-family: 'Space Grotesk', sans-serif;">Quick Actions</h3>
        </div>
        """, unsafe_allow_html=True)

        if st.button("Import Leads", use_container_width=True, type="primary"):
            st.session_state.current_page = "Lead Manager"
            st.rerun()

        if st.button("Process Pending", use_container_width=True):
            st.session_state.current_page = "Lead Manager"
            st.rerun()

        if st.button("Sync to Instantly", use_container_width=True):
            st.session_state.current_page = "Instantly Sync"
            st.rerun()


# ========== Lead Manager Page ==========

def render_lead_manager():
    """Render the lead management page."""
    st.title("Lead Manager")
    st.caption("Manage campaigns and process leads at scale")

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
            selected_name = st.selectbox("Select Campaign", list(campaign_names.keys()), key="import_campaign_select")
            selected_id = campaign_names.get(selected_name)

            st.info(f"Importing to: **{selected_name}**")

            # File uploader
            uploaded = st.file_uploader(
                "Upload CSV",
                type=["csv"],
                help="Required: email, company_name. Optional: first_name, last_name, site_url, city, state",
                key="csv_uploader"
            )

            if uploaded:
                try:
                    df = pd.read_csv(uploaded)
                    df = normalize_columns(df)  # Normalize column names
                    st.success(f"Found **{len(df)}** leads in CSV")

                    # Preview
                    with st.expander("Preview Data", expanded=True):
                        st.dataframe(df.head(10), use_container_width=True)

                    # Import button with unique key
                    if st.button("Download Import to Database", type="primary", key="import_btn", use_container_width=True):
                        if not selected_id:
                            st.error("Please select a campaign first!")
                        else:
                            with st.spinner(f"Importing {len(df)} leads to {selected_name}..."):
                                try:
                                    result = db.import_leads_from_csv(df.to_dict('records'), selected_id)
                                    st.success(f"""
                                    **Import Complete!**
                                    - [OK] Imported: {result['imported']}
                                    - ⏭️ Skipped: {result['skipped']}
                                    - ❌ Errors: {result['errors']}
                                    """)
                                    st.balloons()
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Import failed: {e}")

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
                    batch_input = st.number_input(
                        "Number of leads to process (0 = all)",
                        min_value=0,
                        max_value=10000,
                        value=min(50, pending),
                        step=10,
                        help=f"Enter 0 to process all {pending} pending leads"
                    )
                    # Convert 0 to all pending leads
                    batch_size = pending if batch_input == 0 else min(batch_input, pending)
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
    """Process pending leads from database with deep research."""
    leads = db.get_pending_leads(campaign_id, limit=batch_size)

    if not leads:
        st.warning("No leads to process")
        return

    # Set processing active flag to prevent navigation
    st.session_state.processing_active = True

    # Initialize
    serper = SerperClient(st.session_state.serper_api_key)
    ai_gen = AILineGenerator(st.session_state.anthropic_api_key)

    # Enhanced progress display
    progress = st.progress(0)
    status = st.empty()
    research_preview = st.empty()
    stats = {"S": 0, "A": 0, "B": 0, "errors": 0}

    for i, lead in enumerate(leads):
        company = lead["company_name"]

        # Enhanced status display
        status.markdown(f"""
        <div style="background: rgba(46, 125, 138, 0.1); padding: 12px 16px; border-radius: 10px; margin: 8px 0; border: 1px solid rgba(46, 125, 138, 0.2);">
            <div style="color: #2E7D8A; font-weight: 600;">Researching {i+1}/{len(leads)}</div>
            <div style="color: #1e293b; font-size: 1.1rem; margin-top: 4px;">{company}</div>
        </div>
        """, unsafe_allow_html=True)

        try:
            # Build location
            location = ""
            if lead.get("city") and lead.get("state"):
                location = f"{lead['city']}, {lead['state']}"
            elif lead.get("city"):
                location = lead["city"]
            elif lead.get("state"):
                location = lead["state"]

            # Deep Serper research
            serper_data = ""
            try:
                info = serper.get_company_info(company, lead.get("site_url", ""), location)
                serper_data = extract_artifacts_from_serper(info)

                # Show research findings
                highlights = []
                if info.case_verdicts:
                    highlights.append(f"Verdict: {info.case_verdicts[0]}")
                if info.avvo_rating:
                    highlights.append(f"Avvo: {info.avvo_rating}")
                if info.super_lawyers:
                    highlights.append(f"Award: {info.super_lawyers}")
                if info.google_rating:
                    highlights.append(f"Rating: {info.google_rating}")
                if info.iicrc_certs:
                    highlights.append(f"Cert: {info.iicrc_certs[0]}")
                if info.insurance_partners:
                    highlights.append(f"Partner: {info.insurance_partners[0]}")
                if info.years_in_business:
                    highlights.append(f"Est: {info.years_in_business}")

                if highlights:
                    research_preview.markdown(f"""
                    <div style="background: rgba(34, 197, 94, 0.1); padding: 10px 14px; border-radius: 8px; margin: 4px 0; border-left: 3px solid #22c55e;">
                        <div style="color: #475569; font-size: 0.75rem; font-weight: 600;">FOUND:</div>
                        <div style="color: #1e293b; font-size: 0.85rem;">{" | ".join(highlights[:3])}</div>
                    </div>
                    """, unsafe_allow_html=True)

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
    research_preview.empty()
    progress.progress(100)

    total = stats["S"] + stats["A"] + stats["B"]
    s_pct = int((stats["S"] / total * 100)) if total > 0 else 0

    # Mark checklist as complete
    if total > 0:
        st.session_state.first_leads_processed = True

    # Enhanced success display
    st.success(f"Processing Complete - {total} leads personalized")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("S-Tier", stats['S'])
    with col2:
        st.metric("A-Tier", stats['A'])
    with col3:
        st.metric("B-Tier", stats['B'])
    with col4:
        st.metric("Errors", stats['errors'])

    st.info(f"{s_pct}% S-Tier Quality")

    # Clear processing flag
    st.session_state.processing_active = False

    st.rerun()


# ========== Quick Personalize Page ==========

def render_quick_personalize():
    """Render the quick CSV personalization page."""
    st.title("Quick Personalize")
    st.caption("Deep research + AI personalization for legal firms and restoration companies")

    # Check API connection
    if not st.session_state.anthropic_connected:
        st.error("Claude AI not connected. Add ANTHROPIC_API_KEY to settings.")
        return

    # Restore results from database on refresh (if we have a saved campaign)
    if st.session_state.quick_campaign_id and st.session_state.df_processed is None:
        # Load processed leads from database
        processed_leads = db.get_leads(
            campaign_id=st.session_state.quick_campaign_id,
            status="processed",
            limit=2000
        )
        if processed_leads:
            st.session_state.df_processed = pd.DataFrame(processed_leads)
            # Recalculate stats
            stats = {"S": 0, "A": 0, "B": 0, "errors": 0}
            for lead in processed_leads:
                tier = lead.get("confidence_tier", "B")
                if tier in stats:
                    stats[tier] += 1
            st.session_state.processing_stats = stats
            st.session_state.processing_complete = True
            logger.info(f"Restored {len(processed_leads)} leads from campaign {st.session_state.quick_campaign_id}")

    # Industry selection banner
    st.info("**Industry-Specific Deep Research** - Our AI performs 6-8 targeted searches per company to find verdicts, ratings, certifications, and awards.")

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
        st.markdown("### Processing Settings")

        # Industry selector
        industry = st.selectbox(
            "Industry Focus",
            ["Auto-detect", "Legal Firms", "Restoration Companies"],
            help="Choose industry for optimized research queries"
        )

        # Map selection to industry code
        industry_map = {
            "Auto-detect": None,
            "Legal Firms": "legal",
            "Restoration Companies": "restoration"
        }
        selected_industry = industry_map[industry]

        # Store in session state
        if "selected_industry" not in st.session_state:
            st.session_state.selected_industry = None
        st.session_state.selected_industry = selected_industry

        # Industry-specific info
        if industry == "Legal Firms":
            st.caption("Searches: Avvo ratings, Super Lawyers, Martindale, case verdicts, Google reviews")
        elif industry == "Restoration Companies":
            st.caption("Searches: IICRC certs, insurance partnerships, response guarantees, Google reviews")

        if st.session_state.df_input is not None:
            total = len(st.session_state.df_input)
            limit_input = st.number_input(
                "Number of leads to process (0 = all)",
                min_value=0,
                max_value=10000,
                value=min(50, total),
                step=10,
                help=f"Enter 0 to process all {total} leads"
            )
            # Convert 0 to total (all leads)
            limit = total if limit_input == 0 else min(limit_input, total)

            st.markdown("---")

            if st.button("Start Deep Research", type="primary", use_container_width=True):
                process_quick_leads(limit, selected_industry)

    # Results
    if st.session_state.df_processed is not None:
        st.markdown("---")

        df = st.session_state.df_processed
        stats = st.session_state.processing_stats
        total = stats.get("S", 0) + stats.get("A", 0) + stats.get("B", 0)

        # Results header with quality score
        s_pct = int((stats.get("S", 0) / total * 100)) if total > 0 else 0

        st.subheader("Results")
        st.caption(f"Deep research complete for {total} companies")

        # Quality metrics using native Streamlit
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            st.metric("S-Tier", stats.get("S", 0), help="Verdicts, Ratings, Awards")
        with col2:
            st.metric("A-Tier", stats.get("A", 0), help="Years, Growth, Team")
        with col3:
            st.metric("B-Tier", stats.get("B", 0), help="Services, Location")
        with col4:
            st.metric("Errors", stats.get("errors", 0))
        with col5:
            st.metric("S-Tier %", f"{s_pct}%")

        # Sample results preview
        st.markdown("#### Sample Personalization Lines")
        sample_df = df[["company_name", "personalization_line", "confidence_tier", "artifact_type"]].head(5)
        sample_df.columns = ["Company", "Personalization Line", "Tier", "Hook Type"]

        for _, row in sample_df.iterrows():
            with st.container():
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.markdown(f"**{row['Company']}**")
                    st.markdown(f"*\"{row['Personalization Line']}\"*")
                with col2:
                    st.caption(f"{row['Tier']}-Tier | {row['Hook Type']}")

        st.markdown("---")

        # Full data table
        with st.expander("View All Data", expanded=False):
            st.dataframe(df, use_container_width=True)

        # Download button
        csv = df.to_csv(index=False)
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.download_button(
                "Download Download Personalized CSV",
                csv,
                f"personalized_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                "text/csv",
                use_container_width=True,
                type="primary"
            )


def process_quick_leads(limit: int, industry: str = None):
    """Process leads from uploaded CSV with deep research."""
    # Set processing active flag to prevent navigation
    st.session_state.processing_active = True

    df = st.session_state.df_input.head(limit).copy()

    serper = SerperClient(st.session_state.serper_api_key)
    ai_gen = AILineGenerator(st.session_state.anthropic_api_key)

    # Create a campaign for persistence (so results survive refresh)
    campaign_name = f"Quick Test - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    campaign_id = db.create_campaign(campaign_name, f"Auto-created for {limit} leads")
    st.session_state.quick_campaign_id = campaign_id
    logger.info(f"Created campaign {campaign_id} for Quick Personalize persistence")

    # Import leads into the campaign
    leads_data = df.to_dict('records')
    db.import_leads_from_csv(leads_data, campaign_id)

    # Get the imported leads with their database IDs
    db_leads = db.get_leads(campaign_id=campaign_id, status="pending", limit=limit)
    lead_id_map = {l["company_name"]: l["id"] for l in db_leads}

    results = []
    stats = {"S": 0, "A": 0, "B": 0, "errors": 0}
    research_insights = []  # Store research data for display

    # Enhanced progress display
    progress_container = st.container()
    with progress_container:
        progress = st.progress(0)
        status = st.empty()
        research_preview = st.empty()

    for i, row in df.iterrows():
        company = row.get("company_name", "Unknown")
        status.markdown(f"""
        <div style="background: rgba(46, 125, 138, 0.1); padding: 12px 16px; border-radius: 10px; margin: 8px 0; border: 1px solid rgba(46, 125, 138, 0.2);">
            <div style="color: #2E7D8A; font-weight: 600;">Researching {i+1}/{len(df)}</div>
            <div style="color: #1e293b; font-size: 1.1rem; margin-top: 4px;">{company}</div>
        </div>
        """, unsafe_allow_html=True)

        try:
            location = row.get("location", "")
            if not location:
                city = row.get("city", "")
                state = row.get("state", "")
                if city and state:
                    location = f"{city}, {state}"
                elif city:
                    location = city
                elif state:
                    location = state

            domain = row.get("site_url", "")

            # Deep Research with industry hint
            serper_data = ""
            research_summary = ""
            try:
                info = serper.get_company_info(company, domain, location, industry)
                serper_data = extract_artifacts_from_serper(info)

                # Build research summary for display
                highlights = []
                if info.case_verdicts:
                    highlights.append(f"Verdicts: {', '.join(info.case_verdicts[:2])}")
                if info.avvo_rating:
                    highlights.append(f"Avvo: {info.avvo_rating}")
                if info.super_lawyers:
                    highlights.append(f"Award: {info.super_lawyers}")
                if info.google_rating and info.review_count:
                    highlights.append(f"Rating: {info.google_rating} ({info.review_count})")
                if info.iicrc_certs:
                    highlights.append(f"IICRC: {', '.join(info.iicrc_certs[:2])}")
                if info.insurance_partners:
                    highlights.append(f"Partner: {info.insurance_partners[0]}")
                if info.years_in_business:
                    highlights.append(f"Est: {info.years_in_business}")

                if highlights:
                    research_summary = " | ".join(highlights[:3])
                    research_preview.markdown(f"""
                    <div style="background: rgba(34, 197, 94, 0.1); padding: 10px 14px; border-radius: 8px; margin: 4px 0; border-left: 3px solid #22c55e;">
                        <div style="color: #475569; font-size: 0.75rem; font-weight: 600;">FOUND:</div>
                        <div style="color: #1e293b; font-size: 0.85rem;">{research_summary}</div>
                    </div>
                    """, unsafe_allow_html=True)
            except Exception as e:
                logger.warning(f"Serper failed for {company}: {e}")

            # Generate personalized line
            lead_data = {
                "location": location,
                "technologies": row.get("technologies"),
                "keywords": row.get("keywords"),
                "person_title": row.get("job_title"),
            }
            result = ai_gen.generate_line(company, serper_data, lead_data)

            results.append({
                **row.to_dict(),
                "personalization_line": result.line,
                "confidence_tier": result.confidence_tier,
                "artifact_type": result.artifact_type,
                "artifact_used": result.artifact_used,
            })

            # Save to database for persistence
            lead_id = lead_id_map.get(company)
            if lead_id:
                db.update_lead_status(
                    lead_id,
                    "processed",
                    personalization_line=result.line,
                    artifact_type=result.artifact_type,
                    confidence_tier=result.confidence_tier,
                    artifact_used=result.artifact_used,
                )

            research_insights.append({
                "company": company,
                "research": research_summary,
                "line": result.line,
                "tier": result.confidence_tier,
            })

            if result.confidence_tier in stats:
                stats[result.confidence_tier] += 1

        except Exception as e:
            logger.error(f"Error processing {company}: {e}")
            results.append({
                **row.to_dict(),
                "personalization_line": "Came across your company online.",
                "confidence_tier": "B",
                "artifact_type": "ERROR",
                "artifact_used": "",
            })
            # Save error to database
            lead_id = lead_id_map.get(company)
            if lead_id:
                db.update_lead_status(lead_id, "error", error_message=str(e)[:200])
            stats["errors"] += 1

        progress.progress((i + 1) / len(df))

    status.empty()
    research_preview.empty()
    st.session_state.df_processed = pd.DataFrame(results)
    st.session_state.processing_stats = stats
    st.session_state.processing_complete = True

    # Mark checklist as complete
    if len(results) > 0:
        st.session_state.first_leads_processed = True

    # Clear processing flag
    st.session_state.processing_active = False

    st.rerun()


# ========== Instantly Sync Page ==========

def render_instantly_sync():
    """Render the Instantly integration page."""
    st.title("Instantly Sync")
    st.caption("Push personalized leads to your Instantly campaigns")

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
    st.title("Settings")
    st.caption("Configure your integrations and API connections")

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
            <div style="background: rgba(16, 185, 129, 0.1); padding: 16px; border-radius: 12px; margin-bottom: 16px; border: 1px solid rgba(16, 185, 129, 0.2);">
                <span style="color: #10b981; font-weight: bold;">REQUIRED</span> — Powers AI personalization
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
            <div style="background: rgba(16, 185, 129, 0.1); padding: 16px; border-radius: 12px; margin-bottom: 16px; border: 1px solid rgba(16, 185, 129, 0.2);">
                <span style="color: #10b981; font-weight: bold;">REQUIRED</span> — Powers company research
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
            <div style="background: rgba(46, 125, 138, 0.1); padding: 16px; border-radius: 12px; margin-bottom: 16px; border: 1px solid rgba(46, 125, 138, 0.2);">
                <span style="color: #2E7D8A; font-weight: bold;">OPTIONAL</span> — Push leads to campaigns
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
            <div style="background: rgba(148, 163, 184, 0.1); padding: 16px; border-radius: 12px; margin-bottom: 16px; border: 1px solid rgba(148, 163, 184, 0.2);">
                <span style="color: #94a3b8; font-weight: bold;">RECOMMENDED</span> — For production deployment
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
            st.markdown("#### Connect to Supabase")

            st.markdown("**Step 1:** Create a free Supabase project at [supabase.com](https://supabase.com)")

            st.markdown("**Step 2:** Set up the database tables")

            # Download SQL button instead of showing code
            sql_schema = """-- Bright Automations Database Schema
-- Run this in your Supabase SQL Editor

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
"""
            st.download_button(
                "Download SQL Schema",
                sql_schema,
                file_name="bright_automations_schema.sql",
                mime="text/plain",
                use_container_width=True
            )
            st.caption("Download and run this SQL in your Supabase SQL Editor")

            st.markdown("---")

            st.markdown("**Step 3:** Enter your Supabase credentials")

            # Supabase connection form
            with st.form("supabase_form"):
                supabase_url = st.text_input(
                    "Supabase URL",
                    value=st.session_state.supabase_url,
                    placeholder="https://xxxxx.supabase.co",
                    help="Found in Settings → API → Project URL"
                )
                supabase_key = st.text_input(
                    "Supabase Anon Key",
                    value=st.session_state.supabase_key,
                    type="password",
                    placeholder="eyJhbGciOiJIUzI1NiIs...",
                    help="Found in Settings → API → anon public key"
                )
                submitted = st.form_submit_button("Connect to Supabase", type="primary", use_container_width=True)

                if submitted and supabase_url and supabase_key:
                    with st.spinner("Testing connection..."):
                        try:
                            # Test the connection
                            os.environ["SUPABASE_URL"] = supabase_url
                            os.environ["SUPABASE_KEY"] = supabase_key
                            from supabase_client import SupabaseClient
                            test_client = SupabaseClient(supabase_url, supabase_key)
                            if test_client.test_connection():
                                st.session_state.supabase_url = supabase_url
                                st.session_state.supabase_key = supabase_key
                                st.session_state.supabase_connected = True
                                st.success("Connected to Supabase! Reload the page to use cloud database.")
                                st.info("Add these to Railway environment variables for persistence:\n- SUPABASE_URL\n- SUPABASE_KEY")
                            else:
                                st.error("Connection failed. Check your credentials and make sure tables exist.")
                        except Exception as e:
                            st.error(f"Connection failed: {str(e)[:100]}")

            if st.session_state.supabase_connected:
                st.success("Supabase credentials saved in session")

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

    # Getting Started checklist at the top of ALL pages
    render_getting_started_checklist()

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
