"""
SQLite database for lead management.

Provides local storage for leads with status tracking, personalization results,
and push history. Designed to be migrated to Supabase later.
"""
import sqlite3
import logging
from typing import List, Dict, Optional, Any
from datetime import datetime
from pathlib import Path
import json

logger = logging.getLogger(__name__)

# Database file location
DB_PATH = Path(__file__).parent / "leads.db"


def get_connection() -> sqlite3.Connection:
    """Get a database connection with row factory."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_database():
    """Initialize the database schema."""
    conn = get_connection()
    cursor = conn.cursor()

    # Create leads table
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

            -- Status tracking
            status TEXT DEFAULT 'pending',

            -- Personalization results
            personalization_line TEXT,
            artifact_type TEXT,
            confidence_tier TEXT,
            artifact_used TEXT,
            reasoning TEXT,

            -- Campaign tracking
            campaign_id TEXT,
            campaign_name TEXT,

            -- Timestamps
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            processed_at TIMESTAMP,
            pushed_at TIMESTAMP,

            -- Error tracking
            error_message TEXT,
            retry_count INTEGER DEFAULT 0,

            -- Unique constraint on email per campaign
            UNIQUE(email, campaign_id)
        )
    """)

    # Create index for faster queries
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_leads_campaign ON leads(campaign_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_leads_created ON leads(created_at)")

    # Create campaigns table for organizing leads
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
    logger.info("Database initialized successfully")


def create_campaign(name: str, description: str = "") -> str:
    """Create a new campaign and return its ID."""
    import uuid
    campaign_id = str(uuid.uuid4())[:8]

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO campaigns (id, name, description)
        VALUES (?, ?, ?)
    """, (campaign_id, name, description))

    conn.commit()
    conn.close()

    logger.info(f"Created campaign '{name}' with ID: {campaign_id}")
    return campaign_id


def get_campaigns() -> List[Dict[str, Any]]:
    """Get all campaigns with their stats."""
    conn = get_connection()
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
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM campaigns WHERE id = ?", (campaign_id,))
    row = cursor.fetchone()
    conn.close()

    return dict(row) if row else None


def delete_campaign(campaign_id: str) -> bool:
    """Delete a campaign and all its leads."""
    conn = get_connection()
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
    """
    Import leads from CSV data into the database.

    Args:
        leads_data: List of lead dictionaries
        campaign_id: Campaign to associate leads with

    Returns:
        Dict with import stats: imported, skipped, errors
    """
    conn = get_connection()
    cursor = conn.cursor()

    stats = {"imported": 0, "skipped": 0, "errors": 0}

    for lead in leads_data:
        try:
            # Normalize field names (handle various CSV formats)
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
                stats["skipped"] += 1  # Duplicate

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
    conn = get_connection()
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
    conn = get_connection()
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


def get_pending_leads(
    campaign_id: str,
    limit: int = 50,
) -> List[Dict[str, Any]]:
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
    """Update a lead's status and optionally its personalization data."""
    conn = get_connection()
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

    cursor.execute(f"""
        UPDATE leads SET {', '.join(updates)} WHERE id = ?
    """, params)

    conn.commit()
    conn.close()


def bulk_update_status(lead_ids: List[int], status: str):
    """Update status for multiple leads at once."""
    if not lead_ids:
        return

    conn = get_connection()
    cursor = conn.cursor()

    timestamp = datetime.now().isoformat()

    if status == "processed":
        cursor.execute(f"""
            UPDATE leads
            SET status = ?, processed_at = ?
            WHERE id IN ({','.join('?' * len(lead_ids))})
        """, [status, timestamp] + lead_ids)
    elif status == "pushed":
        cursor.execute(f"""
            UPDATE leads
            SET status = ?, pushed_at = ?
            WHERE id IN ({','.join('?' * len(lead_ids))})
        """, [status, timestamp] + lead_ids)
    else:
        cursor.execute(f"""
            UPDATE leads
            SET status = ?
            WHERE id IN ({','.join('?' * len(lead_ids))})
        """, [status] + lead_ids)

    conn.commit()
    conn.close()


def get_lead_stats(campaign_id: Optional[str] = None) -> Dict[str, Any]:
    """Get statistics about leads."""
    conn = get_connection()
    cursor = conn.cursor()

    base_query = "FROM leads"
    params = []

    if campaign_id:
        base_query += " WHERE campaign_id = ?"
        params.append(campaign_id)

    # Status counts
    cursor.execute(f"""
        SELECT
            status,
            COUNT(*) as count
        {base_query}
        GROUP BY status
    """, params)

    status_counts = {row["status"]: row["count"] for row in cursor.fetchall()}

    # Tier distribution (for processed leads)
    tier_query = base_query
    tier_params = params.copy()
    if campaign_id:
        tier_query += " AND status IN ('processed', 'pushed')"
    else:
        tier_query += " WHERE status IN ('processed', 'pushed')"

    cursor.execute(f"""
        SELECT
            confidence_tier,
            COUNT(*) as count
        {tier_query}
        GROUP BY confidence_tier
    """, tier_params)

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
    """
    Export leads for CSV download.

    Returns leads formatted for Instantly CSV format.
    """
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
    """Reset error leads back to pending status."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE leads
        SET status = 'pending', error_message = NULL
        WHERE campaign_id = ? AND status = 'error'
    """, (campaign_id,))

    count = cursor.rowcount
    conn.commit()
    conn.close()

    return count


# Initialize database on module import
init_database()
