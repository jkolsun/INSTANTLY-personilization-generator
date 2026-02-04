"""
FastAPI endpoint for automated lead personalization.

This API allows n8n (or any automation tool) to send leads and receive
personalized lines back, enabling daily automated uploads to Instantly.

Run with: uvicorn api:app --host 0.0.0.0 --port 8000
"""
import os
import logging
from typing import List, Optional
from datetime import datetime

from fastapi import FastAPI, HTTPException, Header, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
import pandas as pd

from serper_client import SerperClient, extract_artifacts_from_serper
from ai_line_generator import AILineGenerator
from column_normalizer import normalize_columns

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Lead Personalization API",
    description="API for automated lead personalization using Serper research and Claude AI",
    version="1.0.0",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Environment variables for API keys
SERPER_API_KEY = os.environ.get("SERPER_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
API_SECRET_KEY = os.environ.get("API_SECRET_KEY", "")  # For authenticating requests


# ========== Pydantic Models ==========

class LeadInput(BaseModel):
    """Input model for a single lead."""
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: EmailStr
    company_name: str
    job_title: Optional[str] = None
    site_url: Optional[str] = None
    linkedin_url: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    # Optional additional fields from Apollo
    technologies: Optional[str] = None
    keywords: Optional[str] = None
    annual_revenue: Optional[float] = None
    num_locations: Optional[int] = None
    subsidiary_of: Optional[str] = None


class LeadOutput(BaseModel):
    """Output model for a personalized lead."""
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: str
    company_name: str
    job_title: Optional[str] = None
    site_url: Optional[str] = None
    linkedin_url: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    # Personalization results
    personalization_line: str
    artifact_type: str
    confidence_tier: str
    artifact_used: Optional[str] = None
    reasoning: Optional[str] = None


class PersonalizeRequest(BaseModel):
    """Request body for batch personalization."""
    leads: List[LeadInput]


class PersonalizeResponse(BaseModel):
    """Response body for batch personalization."""
    success: bool
    processed_count: int
    leads: List[LeadOutput]
    stats: dict
    processing_time_seconds: float


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    serper_configured: bool
    anthropic_configured: bool
    timestamp: str


# ========== Helper Functions ==========

def verify_api_key(authorization: str = Header(None)) -> bool:
    """Verify the API key from Authorization header."""
    if not API_SECRET_KEY:
        # No API key configured, allow all requests (dev mode)
        return True

    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    # Expected format: "Bearer YOUR_API_KEY"
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid Authorization format. Use: Bearer YOUR_API_KEY")

    if parts[1] != API_SECRET_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

    return True


def personalize_lead(
    lead: LeadInput,
    serper: SerperClient,
    ai_generator: AILineGenerator,
) -> LeadOutput:
    """Personalize a single lead."""
    company_name = lead.company_name or "Unknown"
    domain = lead.site_url or ""
    location = f"{lead.city}, {lead.state}" if lead.city and lead.state else (lead.city or lead.state or "")

    # Build lead_data dict for AI generator
    lead_data = {
        "location": location,
        "technologies": lead.technologies,
        "keywords": lead.keywords,
        "person_title": lead.job_title,
    }

    if lead.annual_revenue:
        lead_data["annual_revenue"] = lead.annual_revenue
    if lead.num_locations:
        lead_data["num_locations"] = lead.num_locations
    if lead.subsidiary_of:
        lead_data["subsidiary_of"] = lead.subsidiary_of

    # Serper research
    serper_description = ""
    try:
        company_info = serper.get_company_info(company_name, domain, location)
        serper_description = extract_artifacts_from_serper(company_info)
        logger.info(f"Serper data for {company_name}: {serper_description[:200]}...")
    except Exception as e:
        logger.warning(f"Serper lookup failed for {company_name}: {e}")

    # AI line generation
    result = ai_generator.generate_line(
        company_name=company_name,
        serper_data=serper_description,
        lead_data=lead_data,
    )

    logger.info(f"Generated line for {company_name}: {result.line} (Tier: {result.confidence_tier})")

    return LeadOutput(
        first_name=lead.first_name,
        last_name=lead.last_name,
        email=lead.email,
        company_name=lead.company_name,
        job_title=lead.job_title,
        site_url=lead.site_url,
        linkedin_url=lead.linkedin_url,
        city=lead.city,
        state=lead.state,
        personalization_line=result.line,
        artifact_type=result.artifact_type,
        confidence_tier=result.confidence_tier,
        artifact_used=result.artifact_used,
        reasoning=result.reasoning,
    )


# ========== API Endpoints ==========

@app.get("/", response_model=HealthResponse)
async def root():
    """Root endpoint with health check."""
    return HealthResponse(
        status="healthy",
        serper_configured=bool(SERPER_API_KEY),
        anthropic_configured=bool(ANTHROPIC_API_KEY),
        timestamp=datetime.utcnow().isoformat(),
    )


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse(
        status="healthy",
        serper_configured=bool(SERPER_API_KEY),
        anthropic_configured=bool(ANTHROPIC_API_KEY),
        timestamp=datetime.utcnow().isoformat(),
    )


@app.post("/api/personalize", response_model=PersonalizeResponse)
async def personalize_leads(
    request: PersonalizeRequest,
    authorization: str = Header(None),
):
    """
    Personalize a batch of leads.

    Accepts a JSON array of leads, runs them through Serper research and
    Claude AI personalization, and returns the leads with personalization lines.

    **Authorization**: Bearer YOUR_API_KEY (if API_SECRET_KEY is configured)

    **Request Body**:
    ```json
    {
        "leads": [
            {
                "email": "john@example.com",
                "company_name": "Example Corp",
                "first_name": "John",
                "site_url": "https://example.com"
            }
        ]
    }
    ```

    **Response**:
    ```json
    {
        "success": true,
        "processed_count": 1,
        "leads": [...],
        "stats": {"S": 0, "A": 1, "B": 0, "errors": 0},
        "processing_time_seconds": 2.5
    }
    ```
    """
    # Verify API key
    verify_api_key(authorization)

    # Validate API keys are configured
    if not SERPER_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="SERPER_API_KEY not configured. Set it as an environment variable."
        )
    if not ANTHROPIC_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="ANTHROPIC_API_KEY not configured. Set it as an environment variable."
        )

    # Validate request
    if not request.leads:
        raise HTTPException(status_code=400, detail="No leads provided")

    if len(request.leads) > 500:
        raise HTTPException(
            status_code=400,
            detail=f"Too many leads ({len(request.leads)}). Maximum is 500 per request."
        )

    logger.info(f"Processing {len(request.leads)} leads...")
    start_time = datetime.utcnow()

    # Initialize clients
    serper = SerperClient(SERPER_API_KEY)
    ai_generator = AILineGenerator(ANTHROPIC_API_KEY)

    # Process leads
    results: List[LeadOutput] = []
    stats = {"S": 0, "A": 0, "B": 0, "errors": 0}

    for idx, lead in enumerate(request.leads):
        try:
            logger.info(f"Processing lead {idx + 1}/{len(request.leads)}: {lead.company_name}")
            personalized = personalize_lead(lead, serper, ai_generator)
            results.append(personalized)

            # Update stats
            tier = personalized.confidence_tier
            if tier in stats:
                stats[tier] += 1

        except Exception as e:
            logger.error(f"Error processing {lead.company_name}: {e}")
            stats["errors"] += 1

            # Return lead with error fallback
            results.append(LeadOutput(
                first_name=lead.first_name,
                last_name=lead.last_name,
                email=lead.email,
                company_name=lead.company_name,
                job_title=lead.job_title,
                site_url=lead.site_url,
                linkedin_url=lead.linkedin_url,
                city=lead.city,
                state=lead.state,
                personalization_line="Came across your company online.",
                artifact_type="ERROR",
                confidence_tier="B",
                artifact_used="",
                reasoning=f"Error: {str(e)[:100]}",
            ))

    end_time = datetime.utcnow()
    processing_time = (end_time - start_time).total_seconds()

    logger.info(f"Completed processing {len(results)} leads in {processing_time:.2f}s")
    logger.info(f"Stats: {stats}")

    return PersonalizeResponse(
        success=True,
        processed_count=len(results),
        leads=results,
        stats=stats,
        processing_time_seconds=round(processing_time, 2),
    )


@app.post("/api/personalize/single", response_model=LeadOutput)
async def personalize_single_lead(
    lead: LeadInput,
    authorization: str = Header(None),
):
    """
    Personalize a single lead.

    Useful for testing or real-time personalization.
    """
    verify_api_key(authorization)

    if not SERPER_API_KEY or not ANTHROPIC_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="API keys not configured. Set SERPER_API_KEY and ANTHROPIC_API_KEY."
        )

    serper = SerperClient(SERPER_API_KEY)
    ai_generator = AILineGenerator(ANTHROPIC_API_KEY)

    try:
        return personalize_lead(lead, serper, ai_generator)
    except Exception as e:
        logger.error(f"Error personalizing lead: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========== Entry Point ==========

if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
