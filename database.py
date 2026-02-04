"""
Unified database module for lead management.

Automatically uses Supabase if configured, falls back to SQLite for local development.
"""
import os
import sqlite3
import logging
from typing import List, Dict, Optional, Any
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# Check for Supabase configuration
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
USE_SUPABASE = bool(SUPABASE_URL and SUPABASE_KEY)

# Import Supabase client if available
_supabase_client = None
if USE_SUPABASE:
    try:
        from supabase_client import SupabaseClient, is_supabase_configured
        if is_supabase_configured():
            _supabase_client = SupabaseClient()
            logger.info("Using Supabase for database")
    except Exception as e:
        logger.warning(f"Supabase init failed, falling back to SQLite: {e}")
        USE_SUPABASE = False

if not USE_SUPABASE:
    logger.info("Using SQLite for database (local mode)")

# SQLite configuration
DB_PATH = Path(__file__).parent / "leads.db"


# ========== SQLite Functions ==========

def _get_sqlite_connection() -> sqlite3.Connection:
    """Get a SQLite connection with row factory."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _init_sqlite():
    """Initialize SQLite database schema."""
    conn = _get_sqlite_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            annual_revenue REAL,
            num_locations INTEGER,
            subsidiary_of TEXT,
            status TEXT DEFAULT 'pending',
            personalization_line TEXT,
            artifact_type TEXT,
            confidence_tier TEXT,
            artifact_used TEXT,
            reasoning TEXT,
            campaign_id TEXT,
            campaign_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            processed_at TIMESTAMP,
            pushed_at TIMESTAMP,
            error_message TEXT,
            retry_count INTEGER DEFAULT 0,
            UNIQUE(email, campaign_id)
        )
    """)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_leads_campaign ON leads(campaign_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_leads_created ON leads(created_at)")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS campaigns (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            total_leads INTEGER DEFAULT 0,
            processed_leads INTEGER DEFAULT 0,
            pushed_leads INTEGER DEFAULT 0
        )
    """)

    conn.commit()
    conn.close()


# Initialize SQLite on import (only if not using Supabase)
if not USE_SUPABASE:
    _init_sqlite()


# ========== Unified API Functions ==========

def get_database_type() -> str:
    """Return the current database type being used."""
    return "supabase" if USE_SUPABASE else "sqlite"


def create_campaign(name: str, description: str = "") -> str:
    """Create a new campaign and return its ID."""
    if USE_SUPABASE and _supabase_client:
        return _supabase_client.create_campaign(name, description)

    # SQLite implementation
    import uuid
    campaign_id = str(uuid.uuid4())[:8]

    conn = _get_sqlite_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO campaigns (id, name, description) VALUES (?, ?, ?)",
        (campaign_id, name, description)
    )
    conn.commit()
    conn.close()

    logger.info(f"Created campaign '{name}' with ID: {campaign_id}")
    return campaign_id


def get_campaigns() -> List[Dict[str, Any]]:
    """Get all campaigns with their stats."""
    if USE_SUPABASE and _supabase_client:
        return _supabase_client.get_campaigns()

    # SQLite implementation
    conn = _get_sqlite_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            c.*,
            COUNT(l.id) as actual_total,
            SUM(CASE WHEN l.status = 'processed' THEN 1 ELSE 0 END) as actual_processed,
            SUM(CASE WHEN l.status = 'pushed' THEN 1 ELSE 0 END) as actual_pushed,
            SUM(CASE WHEN l.status = 'pending' THEN 1 ELSE 0 END) as pending_count,
            SUM(CASE WHEN l.status = 'error' THEN 1 ELSE 0 END) as error_count
        FROM campaigns c
        LEFT JOIN leads l ON c.id = l.campaign_id
        GROUP BY c.id
        ORDER BY c.created_at DESC
    """)

    campaigns = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return campaigns


def get_campaign(campaign_id: str) -> Optional[Dict[str, Any]]:
    """Get a single campaign by ID."""
    if USE_SUPABASE and _supabase_client:
        return _supabase_client.get_campaign(campaign_id)

    conn = _get_sqlite_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM campaigns WHERE id = ?", (campaign_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def delete_campaign(campaign_id: str) -> bool:
    """Delete a campaign and all its leads."""
    if USE_SUPABASE and _supabase_client:
        return _supabase_client.delete_campaign(campaign_id)

    conn = _get_sqlite_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM leads WHERE campaign_id = ?", (campaign_id,))
        cursor.execute("DELETE FROM campaigns WHERE id = ?", (campaign_id,))
        conn.commit()
        logger.info(f"Deleted campaign {campaign_id}")
        return True
    except Exception as e:
        logger.error(f"Error deleting campaign: {e}")
        return False
    finally:
        conn.close()


def import_leads_from_csv(
    leads_data: List[Dict[str, Any]],
    campaign_id: str,
) -> Dict[str, int]:
    """Import leads from CSV data into the database."""
    if USE_SUPABASE and _supabase_client:
        return _supabase_client.import_leads_from_csv(leads_data, campaign_id)

    # SQLite implementation
    conn = _get_sqlite_connection()
    cursor = conn.cursor()
    stats = {"imported": 0, "skipped": 0, "errors": 0}

    for lead in leads_data:
        try:
            email = lead.get("email") or lead.get("Email") or lead.get("EMAIL", "")
            company = lead.get("company_name") or lead.get("Company") or lead.get("company", "")

            if not email or not company:
                stats["skipped"] += 1
                continue

            cursor.execute("""
                INSERT OR IGNORE INTO leads (
                    email, company_name, first_name, last_name, job_title,
                    site_url, linkedin_url, city, state, technologies,
                    keywords, annual_revenue, num_locations, subsidiary_of,
                    campaign_id, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
            """, (
                email,
                company,
                lead.get("first_name") or lead.get("First Name") or lead.get("firstName", ""),
                lead.get("last_name") or lead.get("Last Name") or lead.get("lastName", ""),
                lead.get("job_title") or lead.get("Title") or lead.get("title", ""),
                lead.get("site_url") or lead.get("Website") or lead.get("website", ""),
                lead.get("linkedin_url") or lead.get("LinkedIn") or lead.get("linkedin", ""),
                lead.get("city") or lead.get("City", ""),
                lead.get("state") or lead.get("State", ""),
                lead.get("technologies") or lead.get("Technologies", ""),
                lead.get("keywords") or lead.get("Keywords", ""),
                lead.get("annual_revenue") or lead.get("Annual Revenue"),
                lead.get("num_locations") or lead.get("Locations"),
                lead.get("subsidiary_of") or lead.get("Subsidiary Of", ""),
                campaign_id,
            ))

            if cursor.rowcount > 0:
                stats["imported"] += 1
            else:
                stats["skipped"] += 1

        except Exception as e:
            logger.error(f"Error importing lead {lead.get('email', 'unknown')}: {e}")
            stats["errors"] += 1

    conn.commit()
    conn.close()
    logger.info(f"Import complete: {stats}")
    return stats


def get_leads(
    campaign_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """Get leads with optional filtering."""
    if USE_SUPABASE and _supabase_client:
        return _supabase_client.get_leads(campaign_id, status, limit, offset)

    conn = _get_sqlite_connection()
    cursor = conn.cursor()

    query = "SELECT * FROM leads WHERE 1=1"
    params = []

    if campaign_id:
        query += " AND campaign_id = ?"
        params.append(campaign_id)

    if status:
        query += " AND status = ?"
        params.append(status)

    query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    cursor.execute(query, params)
    leads = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return leads


def get_lead_count(
    campaign_id: Optional[str] = None,
    status: Optional[str] = None,
) -> int:
    """Get count of leads matching criteria."""
    if USE_SUPABASE and _supabase_client:
        return _supabase_client.get_lead_count(campaign_id, status)

    conn = _get_sqlite_connection()
    cursor = conn.cursor()

    query = "SELECT COUNT(*) FROM leads WHERE 1=1"
    params = []

    if campaign_id:
        query += " AND campaign_id = ?"
        params.append(campaign_id)

    if status:
        query += " AND status = ?"
        params.append(status)

    cursor.execute(query, params)
    count = cursor.fetchone()[0]
    conn.close()
    return count


def get_pending_leads(campaign_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    """Get pending leads for processing."""
    return get_leads(campaign_id=campaign_id, status="pending", limit=limit)


def update_lead_status(
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
    if USE_SUPABASE and _supabase_client:
        return _supabase_client.update_lead_status(
            lead_id, status, personalization_line, artifact_type,
            confidence_tier, artifact_used, reasoning, error_message
        )

    conn = _get_sqlite_connection()
    cursor = conn.cursor()

    updates = ["status = ?"]
    params = [status]

    if status == "processed":
        updates.append("processed_at = ?")
        params.append(datetime.now().isoformat())
    elif status == "pushed":
        updates.append("pushed_at = ?")
        params.append(datetime.now().isoformat())

    if personalization_line is not None:
        updates.append("personalization_line = ?")
        params.append(personalization_line)
    if artifact_type is not None:
        updates.append("artifact_type = ?")
        params.append(artifact_type)
    if confidence_tier is not None:
        updates.append("confidence_tier = ?")
        params.append(confidence_tier)
    if artifact_used is not None:
        updates.append("artifact_used = ?")
        params.append(artifact_used)
    if reasoning is not None:
        updates.append("reasoning = ?")
        params.append(reasoning)
    if error_message is not None:
        updates.append("error_message = ?")
        params.append(error_message)
        updates.append("retry_count = retry_count + 1")

    params.append(lead_id)

    cursor.execute(f"UPDATE leads SET {', '.join(updates)} WHERE id = ?", params)
    conn.commit()
    conn.close()


def bulk_update_status(lead_ids: List[int], status: str):
    """Update status for multiple leads."""
    if USE_SUPABASE and _supabase_client:
        return _supabase_client.bulk_update_status(lead_ids, status)

    if not lead_ids:
        return

    conn = _get_sqlite_connection()
    cursor = conn.cursor()
    timestamp = datetime.now().isoformat()

    if status == "processed":
        cursor.execute(f"""
            UPDATE leads SET status = ?, processed_at = ?
            WHERE id IN ({','.join('?' * len(lead_ids))})
        """, [status, timestamp] + lead_ids)
    elif status == "pushed":
        cursor.execute(f"""
            UPDATE leads SET status = ?, pushed_at = ?
            WHERE id IN ({','.join('?' * len(lead_ids))})
        """, [status, timestamp] + lead_ids)
    else:
        cursor.execute(f"""
            UPDATE leads SET status = ?
            WHERE id IN ({','.join('?' * len(lead_ids))})
        """, [status] + lead_ids)

    conn.commit()
    conn.close()


def get_lead_stats(campaign_id: Optional[str] = None) -> Dict[str, Any]:
    """Get statistics about leads."""
    if USE_SUPABASE and _supabase_client:
        return _supabase_client.get_lead_stats(campaign_id)

    conn = _get_sqlite_connection()
    cursor = conn.cursor()

    base_query = "FROM leads"
    params = []

    if campaign_id:
        base_query += " WHERE campaign_id = ?"
        params.append(campaign_id)

    cursor.execute(f"SELECT status, COUNT(*) as count {base_query} GROUP BY status", params)
    status_counts = {row["status"]: row["count"] for row in cursor.fetchall()}

    tier_query = base_query
    tier_params = params.copy()
    if campaign_id:
        tier_query += " AND status IN ('processed', 'pushed')"
    else:
        tier_query += " WHERE status IN ('processed', 'pushed')"

    cursor.execute(f"SELECT confidence_tier, COUNT(*) as count {tier_query} GROUP BY confidence_tier", tier_params)
    tier_counts = {row["confidence_tier"]: row["count"] for row in cursor.fetchall()}

    conn.close()

    return {
        "total": sum(status_counts.values()),
        "pending": status_counts.get("pending", 0),
        "processed": status_counts.get("processed", 0),
        "pushed": status_counts.get("pushed", 0),
        "error": status_counts.get("error", 0),
        "tiers": tier_counts,
    }


def export_leads_to_csv(
    campaign_id: str,
    status: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Export leads for CSV download."""
    if USE_SUPABASE and _supabase_client:
        return _supabase_client.export_leads_to_csv(campaign_id, status)

    leads = get_leads(campaign_id=campaign_id, status=status, limit=10000)

    export_data = []
    for lead in leads:
        export_data.append({
            "email": lead["email"],
            "first_name": lead["first_name"] or "",
            "last_name": lead["last_name"] or "",
            "company_name": lead["company_name"],
            "personalization": lead["personalization_line"] or "",
            "website": lead["site_url"] or "",
            "city": lead["city"] or "",
            "state": lead["state"] or "",
            "confidence_tier": lead["confidence_tier"] or "",
            "artifact_type": lead["artifact_type"] or "",
        })

    return export_data


def reset_error_leads(campaign_id: str) -> int:
    """Reset error leads back to pending."""
    if USE_SUPABASE and _supabase_client:
        return _supabase_client.reset_error_leads(campaign_id)

    conn = _get_sqlite_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE leads SET status = 'pending', error_message = NULL
        WHERE campaign_id = ? AND status = 'error'
    """, (campaign_id,))
    count = cursor.rowcount
    conn.commit()
    conn.close()
    return count
