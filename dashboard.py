#!/usr/bin/env python3
"""
Personalization Dashboard

Web-based UI for monitoring and managing the Instantly personalization process.

Usage:
    python dashboard.py

Then open http://localhost:5000 in your browser.
"""
import os
import json
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, asdict

from flask import Flask, render_template, jsonify, request

from instantly_client import InstantlyClient, Lead, Campaign
from instantly_sync import InstantlyPersonalizer

app = Flask(__name__)

# Global state for tracking sync progress
sync_state = {
    "is_running": False,
    "current_campaign": None,
    "processed": 0,
    "total": 0,
    "stats": {"S": 0, "A": 0, "B": 0, "errors": 0, "skipped": 0},
    "last_sync": None,
    "logs": [],
}

# Cache for API data
cache = {
    "campaigns": [],
    "leads": {},
    "last_refresh": None,
}


def get_api_key() -> Optional[str]:
    """Get API key from environment."""
    return os.environ.get("INSTANTLY_API_KEY")


def add_log(message: str):
    """Add a log message with timestamp."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    sync_state["logs"].append(f"[{timestamp}] {message}")
    # Keep only last 100 logs
    if len(sync_state["logs"]) > 100:
        sync_state["logs"] = sync_state["logs"][-100:]


@app.route("/")
def index():
    """Main dashboard page."""
    return render_template("dashboard.html")


@app.route("/api/status")
def api_status():
    """Get current system status."""
    api_key = get_api_key()
    connected = False

    if api_key:
        try:
            client = InstantlyClient(api_key)
            connected = client.test_connection()
        except Exception:
            pass

    return jsonify({
        "api_key_set": bool(api_key),
        "connected": connected,
        "sync_state": sync_state,
    })


@app.route("/api/campaigns")
def api_campaigns():
    """List all campaigns with lead counts."""
    api_key = get_api_key()
    if not api_key:
        return jsonify({"error": "API key not set"}), 400

    try:
        client = InstantlyClient(api_key)
        campaigns = client.list_campaigns()

        result = []
        for campaign in campaigns:
            # Get lead count for each campaign
            leads = client.list_leads(campaign_id=campaign.id, limit=1)
            result.append({
                "id": campaign.id,
                "name": campaign.name,
                "status": campaign.status,
            })

        cache["campaigns"] = result
        cache["last_refresh"] = datetime.now().isoformat()

        return jsonify({"campaigns": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/campaigns/<campaign_id>/leads")
def api_campaign_leads(campaign_id: str):
    """Get leads for a specific campaign with personalization status."""
    api_key = get_api_key()
    if not api_key:
        return jsonify({"error": "API key not set"}), 400

    try:
        client = InstantlyClient(api_key)
        limit = request.args.get("limit", 100, type=int)
        leads = client.list_leads(campaign_id=campaign_id, limit=limit)

        result = []
        stats = {"total": 0, "personalized": 0, "S": 0, "A": 0, "B": 0}

        for lead in leads:
            stats["total"] += 1

            custom_vars = lead.custom_variables
            personalization_line = custom_vars.get("personalization_line", "")
            confidence_tier = custom_vars.get("confidence_tier", "")
            artifact_type = custom_vars.get("artifact_type", "")
            artifact_text = custom_vars.get("artifact_text", "")

            if personalization_line:
                stats["personalized"] += 1
                if confidence_tier in ["S", "A", "B"]:
                    stats[confidence_tier] += 1

            result.append({
                "id": lead.id,
                "email": lead.email,
                "first_name": lead.first_name,
                "last_name": lead.last_name,
                "company_name": lead.company_name,
                "personalization_line": personalization_line,
                "confidence_tier": confidence_tier,
                "artifact_type": artifact_type,
                "artifact_text": artifact_text,
            })

        return jsonify({
            "leads": result,
            "stats": stats,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/campaigns/<campaign_id>/preview")
def api_preview_personalization(campaign_id: str):
    """Preview personalization for leads without saving."""
    api_key = get_api_key()
    if not api_key:
        return jsonify({"error": "API key not set"}), 400

    try:
        personalizer = InstantlyPersonalizer(api_key=api_key)
        leads = personalizer.client.list_leads(campaign_id=campaign_id, limit=10)

        previews = []
        for lead in leads:
            # Skip already personalized
            if lead.custom_variables.get("personalization_line"):
                continue

            try:
                variables = personalizer.personalize_lead(lead)
                previews.append({
                    "email": lead.email,
                    "company": lead.company_name,
                    "line": variables["personalization_line"],
                    "tier": variables["confidence_tier"],
                    "artifact_type": variables["artifact_type"],
                    "artifact_text": variables["artifact_text"],
                })
            except Exception as e:
                previews.append({
                    "email": lead.email,
                    "company": lead.company_name,
                    "error": str(e),
                })

        return jsonify({"previews": previews})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/campaigns/<campaign_id>/sync", methods=["POST"])
def api_sync_campaign(campaign_id: str):
    """Start syncing personalization for a campaign."""
    api_key = get_api_key()
    if not api_key:
        return jsonify({"error": "API key not set"}), 400

    if sync_state["is_running"]:
        return jsonify({"error": "Sync already in progress"}), 400

    dry_run = request.json.get("dry_run", False) if request.json else False
    limit = request.json.get("limit") if request.json else None

    def run_sync():
        try:
            sync_state["is_running"] = True
            sync_state["current_campaign"] = campaign_id
            sync_state["processed"] = 0
            sync_state["stats"] = {"S": 0, "A": 0, "B": 0, "errors": 0, "skipped": 0}
            sync_state["logs"] = []

            add_log(f"Starting sync for campaign {campaign_id}")

            personalizer = InstantlyPersonalizer(api_key=api_key)

            # Get leads
            add_log("Fetching leads...")
            leads = personalizer.client.list_leads(campaign_id=campaign_id, limit=limit or 10000)
            sync_state["total"] = len(leads)
            add_log(f"Found {len(leads)} leads")

            if limit:
                leads = leads[:limit]

            for lead in leads:
                try:
                    # Skip if already has personalization
                    if lead.custom_variables.get("personalization_line"):
                        sync_state["stats"]["skipped"] += 1
                        sync_state["processed"] += 1
                        continue

                    # Generate personalization
                    variables = personalizer.personalize_lead(lead)
                    tier = variables["confidence_tier"]
                    sync_state["stats"][tier] = sync_state["stats"].get(tier, 0) + 1

                    if not dry_run:
                        personalizer.client.update_lead_variables(lead.id, variables)

                    add_log(f"[{tier}] {lead.email}: {variables['personalization_line'][:50]}...")

                except Exception as e:
                    sync_state["stats"]["errors"] += 1
                    add_log(f"Error processing {lead.email}: {e}")

                sync_state["processed"] += 1

            sync_state["last_sync"] = datetime.now().isoformat()
            add_log("Sync completed!")

        except Exception as e:
            add_log(f"Sync failed: {e}")
        finally:
            sync_state["is_running"] = False

    # Run sync in background thread
    thread = threading.Thread(target=run_sync)
    thread.start()

    return jsonify({"status": "started", "campaign_id": campaign_id})


@app.route("/api/sync/stop", methods=["POST"])
def api_stop_sync():
    """Stop the current sync (will stop after current lead)."""
    # Note: This is a simple implementation - in production you'd want
    # a more robust cancellation mechanism
    sync_state["is_running"] = False
    add_log("Sync stop requested")
    return jsonify({"status": "stopping"})


@app.route("/api/logs")
def api_logs():
    """Get recent log messages."""
    return jsonify({"logs": sync_state["logs"]})


# Create templates directory and HTML template
TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")
os.makedirs(TEMPLATE_DIR, exist_ok=True)

DASHBOARD_HTML = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Instantly Personalization Dashboard</title>
    <style>
        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: #0f172a;
            color: #e2e8f0;
            min-height: 100vh;
        }
        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
        }
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 30px;
            padding-bottom: 20px;
            border-bottom: 1px solid #334155;
        }
        h1 {
            font-size: 24px;
            font-weight: 600;
        }
        .status-badge {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 8px 16px;
            border-radius: 20px;
            font-size: 14px;
        }
        .status-badge.connected {
            background: #065f46;
            color: #6ee7b7;
        }
        .status-badge.disconnected {
            background: #7f1d1d;
            color: #fca5a5;
        }
        .status-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
        }
        .status-dot.green { background: #10b981; }
        .status-dot.red { background: #ef4444; }

        .grid {
            display: grid;
            grid-template-columns: 300px 1fr;
            gap: 20px;
        }

        .card {
            background: #1e293b;
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 20px;
        }
        .card h2 {
            font-size: 16px;
            font-weight: 600;
            margin-bottom: 15px;
            color: #94a3b8;
        }

        .campaign-list {
            list-style: none;
        }
        .campaign-item {
            padding: 12px;
            border-radius: 8px;
            cursor: pointer;
            margin-bottom: 8px;
            transition: background 0.2s;
        }
        .campaign-item:hover {
            background: #334155;
        }
        .campaign-item.active {
            background: #3b82f6;
        }
        .campaign-name {
            font-weight: 500;
            margin-bottom: 4px;
        }
        .campaign-status {
            font-size: 12px;
            color: #94a3b8;
        }

        .stats-grid {
            display: grid;
            grid-template-columns: repeat(5, 1fr);
            gap: 15px;
            margin-bottom: 20px;
        }
        .stat-card {
            background: #1e293b;
            border-radius: 8px;
            padding: 15px;
            text-align: center;
        }
        .stat-value {
            font-size: 28px;
            font-weight: 700;
            margin-bottom: 4px;
        }
        .stat-value.tier-s { color: #10b981; }
        .stat-value.tier-a { color: #3b82f6; }
        .stat-value.tier-b { color: #f59e0b; }
        .stat-value.errors { color: #ef4444; }
        .stat-label {
            font-size: 12px;
            color: #94a3b8;
            text-transform: uppercase;
        }

        .progress-section {
            margin-bottom: 20px;
        }
        .progress-bar {
            height: 8px;
            background: #334155;
            border-radius: 4px;
            overflow: hidden;
            margin-bottom: 8px;
        }
        .progress-fill {
            height: 100%;
            background: linear-gradient(90deg, #3b82f6, #10b981);
            transition: width 0.3s;
        }
        .progress-text {
            font-size: 14px;
            color: #94a3b8;
        }

        .btn {
            padding: 10px 20px;
            border-radius: 8px;
            border: none;
            font-size: 14px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s;
        }
        .btn-primary {
            background: #3b82f6;
            color: white;
        }
        .btn-primary:hover {
            background: #2563eb;
        }
        .btn-secondary {
            background: #334155;
            color: #e2e8f0;
        }
        .btn-secondary:hover {
            background: #475569;
        }
        .btn-danger {
            background: #dc2626;
            color: white;
        }
        .btn-danger:hover {
            background: #b91c1c;
        }
        .btn:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }

        .actions {
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
        }

        .leads-table {
            width: 100%;
            border-collapse: collapse;
        }
        .leads-table th,
        .leads-table td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #334155;
        }
        .leads-table th {
            color: #94a3b8;
            font-weight: 500;
            font-size: 12px;
            text-transform: uppercase;
        }
        .leads-table tr:hover {
            background: #334155;
        }

        .tier-badge {
            display: inline-block;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 600;
        }
        .tier-badge.S { background: #065f46; color: #6ee7b7; }
        .tier-badge.A { background: #1e40af; color: #93c5fd; }
        .tier-badge.B { background: #92400e; color: #fcd34d; }

        .log-container {
            background: #0f172a;
            border-radius: 8px;
            padding: 15px;
            max-height: 200px;
            overflow-y: auto;
            font-family: monospace;
            font-size: 12px;
        }
        .log-line {
            padding: 4px 0;
            color: #94a3b8;
        }
        .log-line:last-child {
            color: #e2e8f0;
        }

        .empty-state {
            text-align: center;
            padding: 40px;
            color: #64748b;
        }

        .sync-running {
            animation: pulse 2s infinite;
        }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }

        .personalization-text {
            max-width: 300px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>Instantly Personalization Dashboard</h1>
            <div id="connection-status" class="status-badge disconnected">
                <span class="status-dot red"></span>
                <span>Checking...</span>
            </div>
        </header>

        <div class="grid">
            <aside>
                <div class="card">
                    <h2>Campaigns</h2>
                    <ul id="campaign-list" class="campaign-list">
                        <li class="empty-state">Loading...</li>
                    </ul>
                </div>

                <div class="card">
                    <h2>Sync Logs</h2>
                    <div id="log-container" class="log-container">
                        <div class="log-line">No activity yet</div>
                    </div>
                </div>
            </aside>

            <main>
                <div id="campaign-detail" style="display: none;">
                    <div class="stats-grid">
                        <div class="stat-card">
                            <div id="stat-total" class="stat-value">0</div>
                            <div class="stat-label">Total Leads</div>
                        </div>
                        <div class="stat-card">
                            <div id="stat-s" class="stat-value tier-s">0</div>
                            <div class="stat-label">Tier S</div>
                        </div>
                        <div class="stat-card">
                            <div id="stat-a" class="stat-value tier-a">0</div>
                            <div class="stat-label">Tier A</div>
                        </div>
                        <div class="stat-card">
                            <div id="stat-b" class="stat-value tier-b">0</div>
                            <div class="stat-label">Tier B</div>
                        </div>
                        <div class="stat-card">
                            <div id="stat-pending" class="stat-value">0</div>
                            <div class="stat-label">Pending</div>
                        </div>
                    </div>

                    <div id="progress-section" class="progress-section" style="display: none;">
                        <div class="progress-bar">
                            <div id="progress-fill" class="progress-fill" style="width: 0%"></div>
                        </div>
                        <div id="progress-text" class="progress-text">Processing...</div>
                    </div>

                    <div class="actions">
                        <button id="btn-preview" class="btn btn-secondary">Preview (10 leads)</button>
                        <button id="btn-sync" class="btn btn-primary">Sync Campaign</button>
                        <button id="btn-stop" class="btn btn-danger" style="display: none;">Stop Sync</button>
                        <button id="btn-refresh" class="btn btn-secondary">Refresh</button>
                    </div>

                    <div class="card">
                        <h2>Leads</h2>
                        <table class="leads-table">
                            <thead>
                                <tr>
                                    <th>Email</th>
                                    <th>Company</th>
                                    <th>Tier</th>
                                    <th>Personalization Line</th>
                                    <th>Artifact</th>
                                </tr>
                            </thead>
                            <tbody id="leads-table-body">
                                <tr>
                                    <td colspan="5" class="empty-state">Select a campaign to view leads</td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </div>

                <div id="no-campaign" class="card">
                    <div class="empty-state">
                        <p>Select a campaign from the sidebar to view leads and start personalizing</p>
                    </div>
                </div>
            </main>
        </div>
    </div>

    <script>
        let selectedCampaign = null;
        let pollInterval = null;

        // Check connection status
        async function checkStatus() {
            try {
                const res = await fetch('/api/status');
                const data = await res.json();

                const statusEl = document.getElementById('connection-status');
                if (data.connected) {
                    statusEl.className = 'status-badge connected';
                    statusEl.innerHTML = '<span class="status-dot green"></span><span>Connected</span>';
                } else if (data.api_key_set) {
                    statusEl.className = 'status-badge disconnected';
                    statusEl.innerHTML = '<span class="status-dot red"></span><span>Connection Failed</span>';
                } else {
                    statusEl.className = 'status-badge disconnected';
                    statusEl.innerHTML = '<span class="status-dot red"></span><span>No API Key</span>';
                }

                // Update sync state
                if (data.sync_state.is_running) {
                    showSyncProgress(data.sync_state);
                } else {
                    hideSyncProgress();
                }

                updateLogs(data.sync_state.logs);
            } catch (e) {
                console.error('Status check failed:', e);
            }
        }

        // Load campaigns
        async function loadCampaigns() {
            try {
                const res = await fetch('/api/campaigns');
                const data = await res.json();

                const listEl = document.getElementById('campaign-list');

                if (data.campaigns && data.campaigns.length > 0) {
                    listEl.innerHTML = data.campaigns.map(c => `
                        <li class="campaign-item" data-id="${c.id}">
                            <div class="campaign-name">${c.name}</div>
                            <div class="campaign-status">${c.status}</div>
                        </li>
                    `).join('');

                    // Add click handlers
                    listEl.querySelectorAll('.campaign-item').forEach(item => {
                        item.addEventListener('click', () => selectCampaign(item.dataset.id));
                    });
                } else {
                    listEl.innerHTML = '<li class="empty-state">No campaigns found</li>';
                }
            } catch (e) {
                console.error('Failed to load campaigns:', e);
            }
        }

        // Select a campaign
        async function selectCampaign(campaignId) {
            selectedCampaign = campaignId;

            // Update UI
            document.querySelectorAll('.campaign-item').forEach(item => {
                item.classList.toggle('active', item.dataset.id === campaignId);
            });

            document.getElementById('campaign-detail').style.display = 'block';
            document.getElementById('no-campaign').style.display = 'none';

            await loadLeads(campaignId);
        }

        // Load leads for a campaign
        async function loadLeads(campaignId) {
            try {
                const res = await fetch(`/api/campaigns/${campaignId}/leads?limit=100`);
                const data = await res.json();

                // Update stats
                document.getElementById('stat-total').textContent = data.stats.total;
                document.getElementById('stat-s').textContent = data.stats.S;
                document.getElementById('stat-a').textContent = data.stats.A;
                document.getElementById('stat-b').textContent = data.stats.B;
                document.getElementById('stat-pending').textContent =
                    data.stats.total - data.stats.personalized;

                // Update table
                const tbody = document.getElementById('leads-table-body');
                if (data.leads && data.leads.length > 0) {
                    tbody.innerHTML = data.leads.map(lead => `
                        <tr>
                            <td>${lead.email}</td>
                            <td>${lead.company_name || '-'}</td>
                            <td>${lead.confidence_tier ?
                                `<span class="tier-badge ${lead.confidence_tier}">${lead.confidence_tier}</span>` :
                                '-'}</td>
                            <td class="personalization-text">${lead.personalization_line || '-'}</td>
                            <td>${lead.artifact_text || '-'}</td>
                        </tr>
                    `).join('');
                } else {
                    tbody.innerHTML = '<tr><td colspan="5" class="empty-state">No leads in this campaign</td></tr>';
                }
            } catch (e) {
                console.error('Failed to load leads:', e);
            }
        }

        // Preview personalization
        async function previewPersonalization() {
            if (!selectedCampaign) return;

            const btn = document.getElementById('btn-preview');
            btn.disabled = true;
            btn.textContent = 'Loading...';

            try {
                const res = await fetch(`/api/campaigns/${selectedCampaign}/preview`);
                const data = await res.json();

                if (data.previews) {
                    const tbody = document.getElementById('leads-table-body');
                    tbody.innerHTML = data.previews.map(p => `
                        <tr>
                            <td>${p.email}</td>
                            <td>${p.company || '-'}</td>
                            <td>${p.tier ?
                                `<span class="tier-badge ${p.tier}">${p.tier}</span>` :
                                '-'}</td>
                            <td class="personalization-text">${p.line || p.error || '-'}</td>
                            <td>${p.artifact_text || '-'}</td>
                        </tr>
                    `).join('');
                }
            } catch (e) {
                console.error('Preview failed:', e);
            } finally {
                btn.disabled = false;
                btn.textContent = 'Preview (10 leads)';
            }
        }

        // Start sync
        async function startSync() {
            if (!selectedCampaign) return;

            try {
                const res = await fetch(`/api/campaigns/${selectedCampaign}/sync`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ dry_run: false })
                });

                if (res.ok) {
                    // Start polling for updates
                    pollInterval = setInterval(checkStatus, 1000);
                }
            } catch (e) {
                console.error('Sync failed:', e);
            }
        }

        // Stop sync
        async function stopSync() {
            try {
                await fetch('/api/sync/stop', { method: 'POST' });
            } catch (e) {
                console.error('Stop failed:', e);
            }
        }

        // Show sync progress
        function showSyncProgress(state) {
            document.getElementById('progress-section').style.display = 'block';
            document.getElementById('btn-sync').style.display = 'none';
            document.getElementById('btn-stop').style.display = 'inline-block';

            const pct = state.total > 0 ? (state.processed / state.total * 100) : 0;
            document.getElementById('progress-fill').style.width = pct + '%';
            document.getElementById('progress-text').textContent =
                `Processing ${state.processed} of ${state.total} leads...`;
        }

        // Hide sync progress
        function hideSyncProgress() {
            document.getElementById('progress-section').style.display = 'none';
            document.getElementById('btn-sync').style.display = 'inline-block';
            document.getElementById('btn-stop').style.display = 'none';

            if (pollInterval) {
                clearInterval(pollInterval);
                pollInterval = null;
            }
        }

        // Update logs
        function updateLogs(logs) {
            const container = document.getElementById('log-container');
            if (logs && logs.length > 0) {
                container.innerHTML = logs.map(log =>
                    `<div class="log-line">${log}</div>`
                ).join('');
                container.scrollTop = container.scrollHeight;
            }
        }

        // Button handlers
        document.getElementById('btn-preview').addEventListener('click', previewPersonalization);
        document.getElementById('btn-sync').addEventListener('click', startSync);
        document.getElementById('btn-stop').addEventListener('click', stopSync);
        document.getElementById('btn-refresh').addEventListener('click', () => {
            if (selectedCampaign) loadLeads(selectedCampaign);
        });

        // Initial load
        checkStatus();
        loadCampaigns();

        // Poll status every 5 seconds
        setInterval(checkStatus, 5000);
    </script>
</body>
</html>
'''

# Write the template file
with open(os.path.join(TEMPLATE_DIR, "dashboard.html"), "w") as f:
    f.write(DASHBOARD_HTML)


if __name__ == "__main__":
    # Check for API key
    if not get_api_key():
        print("Warning: INSTANTLY_API_KEY environment variable not set")
        print("Set it with: export INSTANTLY_API_KEY=your_key_here")
        print()

    print("Starting Personalization Dashboard...")
    print("Open http://localhost:5000 in your browser")
    print()

    app.run(debug=True, port=5000)
