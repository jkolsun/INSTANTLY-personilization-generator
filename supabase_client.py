"""
Supabase client for persistent lead management.

Cloud PostgreSQL database with real-time capabilities.
Replaces SQLite for production deployment.
"""
import os
import logging
from typing import List, Dict, Optional, Any
from datetime import datetime
import json

logger = logging.getLogger(__name__)

# Supabase configuration from environment
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")  # Use anon/public key for client

# Try to import supabase
try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    logger.warning("Supabase not installed. Run: pip install supabase")


class SupabaseClient:
    """
    Supabase client for lead and campaign management.

    Provides the same interface as the SQLite database module
    for easy migration.
    """

    def __init__(self, url: str = None, key: str = None):
        """Initialize Supabase client."""
        if not SUPABASE_AVAILABLE:
            raise ImportError("Supabase not installed. Run: pip install supabase")

        self.url = url or SUPABASE_URL
        self.key = key or SUPABASE_KEY

        if not self.url or not self.key:
            raise ValueError(
                "Supabase credentials not configured. "
                "Set SUPABASE_URL and SUPABASE_KEY environment variables."
            )

        self.client: Client = create_client(self.url, self.key)
        logger.info("Supabase client initialized")

    # ========== Campaign Methods ==========

    def create_campaign(self, name: str, description: str = "") -> str:
        """Create a new campaign and return its ID."""
        import uuid
        campaign_id = str(uuid.uuid4())[:8]

        data = {
            "id": campaign_id,
            "name": name,
            "description": description,
            "created_at": datetime.now().isoformat(),
        }

        result = self.client.table("campaigns").insert(data).execute()
        logger.info(f"Created campaign '{name}' with ID: {campaign_id}")
        return campaign_id

    def get_campaigns(self) -> List[Dict[str, Any]]:
        """Get all campaigns with their stats."""
        # Get campaigns
        campaigns_result = self.client.table("campaigns").select("*").order("created_at", desc=True).execute()
        campaigns = campaigns_result.data or []

        # Get stats for each campaign
        for campaign in campaigns:
            stats = self.get_lead_stats(campaign["id"])
            campaign["pending_count"] = stats.get("pending", 0)
            campaign["actual_processed"] = stats.get("processed", 0)
            campaign["actual_pushed"] = stats.get("pushed", 0)
            campaign["error_count"] = stats.get("error", 0)
            campaign["actual_total"] = stats.get("total", 0)

        return campaigns

    def get_campaign(self, campaign_id: str) -> Optional[Dict[str, Any]]:
        """Get a single campaign by ID."""
        result = self.client.table("campaigns").select("*").eq("id", campaign_id).execute()
        return result.data[0] if result.data else None

    def delete_campaign(self, campaign_id: str) -> bool:
        """Delete a campaign and all its leads."""
        try:
            # Delete leads first
            self.client.table("leads").delete().eq("campaign_id", campaign_id).execute()
            # Then delete campaign
            self.client.table("campaigns").delete().eq("id", campaign_id).execute()
            logger.info(f"Deleted campaign {campaign_id}")
            return True
        except Exception as e:
            logger.error(f"Error deleting campaign: {e}")
            return False

    # ========== Lead Methods ==========

    def import_leads_from_csv(
        self,
        leads_data: List[Dict[str, Any]],
        campaign_id: str,
    ) -> Dict[str, int]:
        """Import leads from CSV data into Supabase."""
        stats = {"imported": 0, "skipped": 0, "errors": 0}

        for lead in leads_data:
            try:
                # Normalize field names
                email = lead.get("email") or lead.get("Email") or lead.get("EMAIL", "")
                company = lead.get("company_name") or lead.get("Company") or lead.get("company", "")

                if not email or not company:
                    stats["skipped"] += 1
                    continue

                # Check if lead already exists
                existing = self.client.table("leads").select("id").eq("email", email).eq("campaign_id", campaign_id).execute()

                if existing.data:
                    stats["skipped"] += 1
                    continue

                # Insert new lead
                data = {
                    "email": email,
                    "company_name": company,
                    "first_name": lead.get("first_name") or lead.get("First Name") or lead.get("firstName", ""),
                    "last_name": lead.get("last_name") or lead.get("Last Name") or lead.get("lastName", ""),
                    "job_title": lead.get("job_title") or lead.get("Title") or lead.get("title", ""),
                    "site_url": lead.get("site_url") or lead.get("Website") or lead.get("website", ""),
                    "linkedin_url": lead.get("linkedin_url") or lead.get("LinkedIn") or lead.get("linkedin", ""),
                    "city": lead.get("city") or lead.get("City", ""),
                    "state": lead.get("state") or lead.get("State", ""),
                    "technologies": lead.get("technologies") or lead.get("Technologies", ""),
                    "keywords": lead.get("keywords") or lead.get("Keywords", ""),
                    "annual_revenue": lead.get("annual_revenue") or lead.get("Annual Revenue"),
                    "num_locations": lead.get("num_locations") or lead.get("Locations"),
                    "subsidiary_of": lead.get("subsidiary_of") or lead.get("Subsidiary Of", ""),
                    "campaign_id": campaign_id,
                    "status": "pending",
                    "created_at": datetime.now().isoformat(),
                }

                self.client.table("leads").insert(data).execute()
                stats["imported"] += 1

            except Exception as e:
                logger.error(f"Error importing lead {lead.get('email', 'unknown')}: {e}")
                stats["errors"] += 1

        logger.info(f"Import complete: {stats}")
        return stats

    def get_leads(
        self,
        campaign_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Get leads with optional filtering."""
        query = self.client.table("leads").select("*")

        if campaign_id:
            query = query.eq("campaign_id", campaign_id)

        if status:
            query = query.eq("status", status)

        query = query.order("created_at", desc=True).range(offset, offset + limit - 1)

        result = query.execute()
        return result.data or []

    def get_lead_count(
        self,
        campaign_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> int:
        """Get count of leads matching criteria."""
        query = self.client.table("leads").select("id", count="exact")

        if campaign_id:
            query = query.eq("campaign_id", campaign_id)

        if status:
            query = query.eq("status", status)

        result = query.execute()
        return result.count or 0

    def get_pending_leads(
        self,
        campaign_id: str,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Get pending leads for processing."""
        return self.get_leads(campaign_id=campaign_id, status="pending", limit=limit)

    def update_lead_status(
        self,
        lead_id: int,
        status: str,
        personalization_line: Optional[str] = None,
        artifact_type: Optional[str] = None,
        confidence_tier: Optional[str] = None,
        artifact_used: Optional[str] = None,
        reasoning: Optional[str] = None,
        error_message: Optional[str] = None,
    ):
        """Update a lead's status and personalization data."""
        updates = {"status": status}

        if status == "processed":
            updates["processed_at"] = datetime.now().isoformat()
        elif status == "pushed":
            updates["pushed_at"] = datetime.now().isoformat()

        if personalization_line is not None:
            updates["personalization_line"] = personalization_line
        if artifact_type is not None:
            updates["artifact_type"] = artifact_type
        if confidence_tier is not None:
            updates["confidence_tier"] = confidence_tier
        if artifact_used is not None:
            updates["artifact_used"] = artifact_used
        if reasoning is not None:
            updates["reasoning"] = reasoning
        if error_message is not None:
            updates["error_message"] = error_message

        self.client.table("leads").update(updates).eq("id", lead_id).execute()

    def bulk_update_status(self, lead_ids: List[int], status: str):
        """Update status for multiple leads."""
        if not lead_ids:
            return

        updates = {"status": status}

        if status == "processed":
            updates["processed_at"] = datetime.now().isoformat()
        elif status == "pushed":
            updates["pushed_at"] = datetime.now().isoformat()

        for lead_id in lead_ids:
            self.client.table("leads").update(updates).eq("id", lead_id).execute()

    def get_lead_stats(self, campaign_id: Optional[str] = None) -> Dict[str, Any]:
        """Get statistics about leads."""
        base_query = self.client.table("leads").select("status, confidence_tier", count="exact")

        if campaign_id:
            base_query = base_query.eq("campaign_id", campaign_id)

        # Get all leads to count by status
        all_leads = base_query.execute()

        status_counts = {"pending": 0, "processed": 0, "pushed": 0, "error": 0}
        tier_counts = {}

        for lead in (all_leads.data or []):
            status = lead.get("status", "pending")
            if status in status_counts:
                status_counts[status] += 1

            tier = lead.get("confidence_tier")
            if tier and status in ["processed", "pushed"]:
                tier_counts[tier] = tier_counts.get(tier, 0) + 1

        return {
            "total": sum(status_counts.values()),
            "pending": status_counts["pending"],
            "processed": status_counts["processed"],
            "pushed": status_counts["pushed"],
            "error": status_counts["error"],
            "tiers": tier_counts,
        }

    def export_leads_to_csv(
        self,
        campaign_id: str,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Export leads for CSV download."""
        leads = self.get_leads(campaign_id=campaign_id, status=status, limit=10000)

        export_data = []
        for lead in leads:
            export_data.append({
                "email": lead.get("email", ""),
                "first_name": lead.get("first_name", ""),
                "last_name": lead.get("last_name", ""),
                "company_name": lead.get("company_name", ""),
                "personalization": lead.get("personalization_line", ""),
                "website": lead.get("site_url", ""),
                "city": lead.get("city", ""),
                "state": lead.get("state", ""),
                "confidence_tier": lead.get("confidence_tier", ""),
                "artifact_type": lead.get("artifact_type", ""),
            })

        return export_data

    def reset_error_leads(self, campaign_id: str) -> int:
        """Reset error leads back to pending."""
        result = self.client.table("leads").update({
            "status": "pending",
            "error_message": None
        }).eq("campaign_id", campaign_id).eq("status", "error").execute()

        return len(result.data) if result.data else 0

    def test_connection(self) -> bool:
        """Test if Supabase connection is working."""
        try:
            self.client.table("campaigns").select("id").limit(1).execute()
            return True
        except Exception as e:
            logger.error(f"Supabase connection test failed: {e}")
            return False


# ========== Helper Functions ==========

def get_supabase_client() -> Optional[SupabaseClient]:
    """Get a Supabase client instance if configured."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None

    try:
        return SupabaseClient()
    except Exception as e:
        logger.error(f"Failed to create Supabase client: {e}")
        return None


def is_supabase_configured() -> bool:
    """Check if Supabase is configured."""
    return bool(SUPABASE_URL and SUPABASE_KEY and SUPABASE_AVAILABLE)


# ========== SQL Schema for Supabase Setup ==========

SUPABASE_SCHEMA = """
-- Run this in your Supabase SQL Editor to set up the tables

-- Campaigns table
CREATE TABLE IF NOT EXISTS campaigns (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    total_leads INTEGER DEFAULT 0,
    processed_leads INTEGER DEFAULT 0,
    pushed_leads INTEGER DEFAULT 0
);

-- Leads table
CREATE TABLE IF NOT EXISTS leads (
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

    -- Status tracking
    status TEXT DEFAULT 'pending',

    -- Personalization results
    personalization_line TEXT,
    artifact_type TEXT,
    confidence_tier TEXT,
    artifact_used TEXT,
    reasoning TEXT,

    -- Campaign tracking
    campaign_id TEXT REFERENCES campaigns(id) ON DELETE CASCADE,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    processed_at TIMESTAMPTZ,
    pushed_at TIMESTAMPTZ,

    -- Error tracking
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,

    -- Unique constraint
    UNIQUE(email, campaign_id)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);
CREATE INDEX IF NOT EXISTS idx_leads_campaign ON leads(campaign_id);
CREATE INDEX IF NOT EXISTS idx_leads_created ON leads(created_at);

-- Enable Row Level Security (optional but recommended)
ALTER TABLE campaigns ENABLE ROW LEVEL SECURITY;
ALTER TABLE leads ENABLE ROW LEVEL SECURITY;

-- Create policies for public access (adjust as needed)
CREATE POLICY "Allow all operations on campaigns" ON campaigns FOR ALL USING (true);
CREATE POLICY "Allow all operations on leads" ON leads FOR ALL USING (true);
"""
